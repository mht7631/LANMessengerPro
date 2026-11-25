import hashlib
import io
import tempfile
import unittest
from pathlib import Path

from lanmessenger.file_transfer import (
    FileEntry, TransferLimits, build_manifest, receive_file, send_file,
    validate_relative_path,
)


class FileTransferSafetyTests(unittest.TestCase):
    def test_rejects_unsafe_paths(self):
        unsafe = (
            "../escape.txt", "/root.txt", "C:/root.txt", "folder\\file.txt",
            "a//b", "NUL.txt", "file.txt:stream",
        )
        for value in unsafe:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_relative_path(value)

    def test_round_trip_and_digest(self):
        payload = b"LANMessengerPro secure file transfer" * 1000
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "source.bin"
            src.write_bytes(payload)
            wire = io.BytesIO()
            entry = send_file(src, wire)
            self.assertEqual(entry.sha256, hashlib.sha256(payload).hexdigest())
            wire.seek(0)
            output = receive_file(
                wire, Path(directory) / "received",
                FileEntry("sender/source.bin", entry.size, entry.sha256),
            )
            self.assertEqual(output.read_bytes(), payload)
            self.assertEqual(
                output.relative_to(Path(directory) / "received").resolve().as_posix(),
                "sender/source.bin",
            )

    def test_rejects_corrupt_or_truncated_data_without_publishing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "received"
            bad_digest = FileEntry("bad.bin", 4, "0" * 64)
            with self.assertRaises(ValueError):
                receive_file(io.BytesIO(b"data"), root, bad_digest)
            self.assertFalse((root / "bad.bin").exists())
            truncated = FileEntry(
                "short.bin", 8, hashlib.sha256(b"12345678").hexdigest()
            )
            with self.assertRaises(EOFError):
                receive_file(io.BytesIO(b"short"), root, truncated)
            self.assertFalse((root / "short.bin").exists())

    def test_does_not_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "received"
            (root / "sender").mkdir(parents=True)
            target = root / "sender" / "a.txt"
            target.write_text("original")
            payload = b"new"
            entry = FileEntry(
                "sender/a.txt", len(payload), hashlib.sha256(payload).hexdigest()
            )
            with self.assertRaises(FileExistsError):
                receive_file(io.BytesIO(payload), root, entry)
            self.assertEqual(target.read_text(), "original")

    def test_folder_manifest_and_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "folder"
            root.mkdir()
            (root / "one.txt").write_text("one")
            entries = build_manifest(root)
            self.assertEqual([entry.relative_path for entry in entries], ["one.txt"])
            with self.assertRaises(ValueError):
                build_manifest(root, TransferLimits(max_file_bytes=1))


if __name__ == "__main__":
    unittest.main()
