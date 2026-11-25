from __future__ import annotations

import hashlib
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Callable

CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True)
class TransferLimits:
    max_file_bytes: int = 512 * 1024 * 1024
    max_files: int = 1024
    max_total_bytes: int = 2 * 1024 * 1024 * 1024
    max_path_chars: int = 240


@dataclass(frozen=True)
class FileEntry:
    relative_path: str
    size: int
    sha256: str


def validate_relative_path(raw: str, *, max_path_chars: int = 240) -> PurePosixPath:
    """Validate an untrusted manifest path before joining it to a receive root."""
    if not isinstance(raw, str) or not raw or len(raw) > max_path_chars:
        raise ValueError("invalid relative path length")
    if "\x00" in raw or "\\" in raw:
        raise ValueError("invalid path separator or NUL")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise ValueError("absolute paths are not allowed")
    parts = raw.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("path traversal or empty path component")
    for part in parts:
        if ":" in part or part.endswith((".", " ")):
            raise ValueError("Windows alternate streams and ambiguous names are not allowed")
        stem = part.split(".", 1)[0].upper()
        reserved = {"CON", "PRN", "AUX", "NUL"}
        reserved.update(f"COM{i}" for i in range(1, 10))
        reserved.update(f"LPT{i}" for i in range(1, 10))
        if stem in reserved:
            raise ValueError("reserved Windows device name")
    return PurePosixPath(*parts)


def build_manifest(root: Path, limits: TransferLimits = TransferLimits()) -> list[FileEntry]:
    """Create a deterministic manifest; symbolic links and special files are rejected."""
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("folder transfer source must be a directory")
    entries: list[FileEntry] = []
    total = 0
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if path.is_symlink():
            raise ValueError(f"symbolic links are not transferable: {path.name}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"unsupported filesystem entry: {path.name}")
        relative = path.relative_to(root).as_posix()
        validate_relative_path(relative, max_path_chars=limits.max_path_chars)
        size = path.stat().st_size
        if size > limits.max_file_bytes:
            raise ValueError(f"file exceeds per-file limit: {relative}")
        total += size
        if len(entries) >= limits.max_files or total > limits.max_total_bytes:
            raise ValueError("folder exceeds transfer limits")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
                digest.update(chunk)
        entries.append(FileEntry(relative, size, digest.hexdigest()))
    return entries


def _ensure_safe_parent(root: Path, relative: PurePosixPath) -> Path:
    """Create parent directories while refusing symlink/reparse-point traversal."""
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve(strict=True)
    current = root
    for component in relative.parts[:-1]:
        current = current / component
        try:
            current.mkdir()
        except FileExistsError:
            pass
        if current.is_symlink() or not current.is_dir():
            raise ValueError("unsafe destination directory")
        resolved = current.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError("destination escapes receive directory")
        current = resolved
    return current


def receive_file(
    source: BinaryIO,
    receive_root: Path,
    entry: FileEntry,
    *,
    limits: TransferLimits = TransferLimits(),
    on_progress: Callable[[int, int], None] | None = None,
) -> Path:
    """Receive exactly one file, verify it, then publish it without overwriting."""
    relative = validate_relative_path(entry.relative_path, max_path_chars=limits.max_path_chars)
    if not 0 <= entry.size <= limits.max_file_bytes:
        raise ValueError("file size is outside allowed limits")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", entry.sha256):
        raise ValueError("invalid SHA-256 digest")
    parent = _ensure_safe_parent(Path(receive_root), relative)
    destination = parent / relative.name
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)

    temporary = parent / ("." + relative.name + "." + secrets.token_hex(8) + ".part")
    digest = hashlib.sha256()
    received = 0
    try:
        with temporary.open("xb") as output:
            while received < entry.size:
                chunk = source.read(min(CHUNK_SIZE, entry.size - received))
                if not chunk:
                    raise EOFError("transfer ended before the declared file size")
                if len(chunk) > entry.size - received:
                    raise ValueError("source returned more bytes than requested")
                output.write(chunk)
                digest.update(chunk)
                received += len(chunk)
                if on_progress:
                    on_progress(received, entry.size)
            output.flush()
            os.fsync(output.fileno())
        if digest.hexdigest().lower() != entry.sha256.lower():
            raise ValueError("file SHA-256 verification failed")
        # Hard-link creation is atomic and fails if another process created the target.
        os.link(temporary, destination)
        temporary.unlink()
        return destination
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def send_file(
    path: Path,
    destination: BinaryIO,
    *,
    limits: TransferLimits = TransferLimits(),
    on_progress: Callable[[int, int], None] | None = None,
) -> FileEntry:
    """Stream a file and return the manifest entry used to verify its receipt."""
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("source must be a regular, non-symlink file")
    size = path.stat().st_size
    if size > limits.max_file_bytes:
        raise ValueError("file exceeds per-file transfer limit")
    digest = hashlib.sha256()
    sent = 0
    with path.open("rb") as source:
        while True:
            chunk = source.read(CHUNK_SIZE)
            if not chunk:
                break
            destination.write(chunk)
            digest.update(chunk)
            sent += len(chunk)
            if on_progress:
                on_progress(sent, size)
    if sent != size:
        raise OSError("source file changed while being transferred")
    return FileEntry(path.name, size, digest.hexdigest())


def peer_folder_name(peer_id: str) -> str:
    """Return a stable filesystem-safe directory name for an untrusted peer identifier."""
    if not isinstance(peer_id, str) or not peer_id:
        raise ValueError("peer identifier must be a non-empty string")
    return hashlib.sha256(peer_id.encode("utf-8")).hexdigest()[:20]
