from __future__ import annotations

import hashlib
import json
import socket
import ssl
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from .file_transfer import CHUNK_SIZE, FileEntry, TransferLimits, receive_file, validate_relative_path

MAX_FRAME = 64 * 1024
CONNECT_TIMEOUT = 5.0
TRANSFER_TIMEOUT = 600.0


class PairingRequired(ConnectionError):
    """Raised when a peer's TLS certificate has not been explicitly trusted."""


class TransferRejected(ConnectionError):
    """Raised when a paired peer declines an incoming file."""


class PinnedTlsTransport:
    """TLS 1.2+ transport with explicit SHA-256 certificate pinning.

    Discovery is not authentication: every TLS peer must already have a trusted
    fingerprint. Unknown certificates are rejected rather than silently trusted.
    """

    def __init__(
        self,
        peer_id: str,
        cert_dir: Path,
        trusted_fingerprints: dict[str, str],
        on_message: Callable[[dict], None],
        on_error: Callable[[str], None] | None = None,
        host: str = "0.0.0.0",
        port: int = 47888,
        trusted_certificates: dict[str, str] | None = None,
        on_file_offer: Callable[[dict], Path | None] | None = None,
        on_file_received: Callable[[dict, Path], None] | None = None,
    ):
        self.peer_id = peer_id
        self.cert_dir = Path(cert_dir)
        self.trusted = {k: v.replace(":", "").lower() for k, v in trusted_fingerprints.items()}
        self.trusted_certificates = dict(trusted_certificates or {})
        self.on_message = on_message
        self.on_error = on_error or (lambda _message: None)
        self.on_file_offer = on_file_offer or (lambda _packet: None)
        self.on_file_received = on_file_received or (lambda _packet, _path: None)
        self.host, self.port = host, port
        self._stop = threading.Event()
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._send_lock = threading.Lock()
        self.fingerprint = ""
        self.certificate_pem = ""

    def _identity(self) -> tuple[Path, Path]:
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        key_path, cert_path = self.cert_dir / "identity-key.pem", self.cert_dir / "identity-cert.pem"
        if key_path.exists() and cert_path.exists():
            return cert_path, key_path
        # ECDSA P-256 gives each installation a persistent identity; private-key file ACLs protect it at rest.
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, self.peer_id)])
        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .sign(key, hashes.SHA256())
        )
        key_path.write_bytes(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        try:
            key_path.chmod(0o600)
        except OSError:
            pass
        return cert_path, key_path

    def start(self) -> int:
        if self._thread and self._thread.is_alive():
            return self.port
        cert, key = self._identity()
        der = ssl.PEM_cert_to_DER_cert(cert.read_text(encoding="ascii"))
        self.fingerprint = hashlib.sha256(der).hexdigest()
        self.certificate_pem = cert.read_text(encoding="ascii")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(str(cert), str(key))
        # Only imported peer certificates enter the trust store; CERT_OPTIONAL permits pairing UI to run before any peers are known.
        context.verify_mode = ssl.CERT_OPTIONAL
        if self.trusted_certificates:
            context.load_verify_locations(cadata="\n".join(self.trusted_certificates.values()))
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.host, self.port))
        listener.listen(20)
        listener.settimeout(0.5)
        self.port = listener.getsockname()[1]
        self._listener = listener
        self._server_context = context
        self._thread = threading.Thread(target=self._serve, name="LAN-TLS-server", daemon=True)
        self._thread.start()
        return self.port

    def stop(self) -> None:
        self._stop.set()
        if self._listener:
            try:
                self._listener.close()
            except OSError:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def trust_peer(self, peer_id: str, fingerprint: str, certificate_pem: str) -> None:
        normalized = fingerprint.replace(":", "").lower()
        if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
            raise ValueError("A SHA-256 certificate fingerprint (64 hex characters) is required")
        try:
            der = ssl.PEM_cert_to_DER_cert(certificate_pem)
        except (ValueError, ssl.SSLError) as exc:
            raise ValueError("A valid PEM certificate is required") from exc
        if hashlib.sha256(der).hexdigest() != normalized:
            raise ValueError("Certificate does not match the supplied fingerprint")
        self.trusted[peer_id] = normalized
        self.trusted_certificates[peer_id] = certificate_pem
        if hasattr(self, "_server_context"):
            self._server_context.load_verify_locations(cadata=certificate_pem)

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                raw, address = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(raw, address), daemon=True).start()

    def _handle(self, raw: socket.socket, address) -> None:
        try:
            raw.settimeout(10.0)
            with self._server_context.wrap_socket(raw, server_side=True) as conn:
                cert = conn.getpeercert(binary_form=True)
                if not cert:
                    return
                actual = hashlib.sha256(cert).hexdigest()
                stream = conn.makefile("rwb")
                request = self._read_frame(stream)
                sender = str(request.get("sender_id", ""))
                try:
                    peer_cert = x509.load_der_x509_certificate(cert)
                    certificate_peer_id = peer_cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
                except (ValueError, IndexError):
                    return
                if not sender or certificate_peer_id != sender or self.trusted.get(sender) != actual:
                    self._write_frame(stream, {"type": "error", "error": "pairing_required"})
                    return

                request_type = request.get("type")
                if request_type == "message":
                    body = request.get("body")
                    message_id = request.get("message_id")
                    if not isinstance(body, str) or not body or len(body.encode("utf-8")) > 48 * 1024:
                        return
                    self.on_message({
                        "message_id": str(message_id or uuid.uuid4()),
                        "sender_id": sender,
                        "body": body,
                    })
                    self._write_frame(stream, {"type": "ack", "message_id": message_id})
                    return

                if request_type == "file":
                    conn.settimeout(TRANSFER_TIMEOUT)
                    self._receive_file(stream, request, sender)
                    return
                self._write_frame(stream, {"type": "error", "error": "unsupported_type"})
        except (OSError, ssl.SSLError, ValueError, json.JSONDecodeError, EOFError) as exc:
            self.on_error(str(exc))
        finally:
            try:
                raw.close()
            except OSError:
                pass

    def _receive_file(self, stream, request: dict, sender: str) -> None:
        transfer_id = str(request.get("transfer_id", ""))
        filename = request.get("filename")
        size = request.get("size")
        digest = request.get("sha256")
        if not transfer_id or not isinstance(filename, str) or not isinstance(size, int) or isinstance(size, bool):
            self._write_frame(stream, {"type": "error", "error": "invalid_manifest"})
            return
        try:
            safe_name = validate_relative_path(filename, max_path_chars=240)
            if len(safe_name.parts) != 1:
                raise ValueError("only a file name is accepted in a single-file offer")
            limits = TransferLimits()
            if not 0 <= size <= limits.max_file_bytes or not isinstance(digest, str) or len(digest) != 64:
                raise ValueError("file manifest exceeds limits or has an invalid digest")
            packet = {"transfer_id": transfer_id, "sender_id": sender, "filename": safe_name.name, "size": size, "sha256": digest}
            destination_root = self.on_file_offer(packet)
            if destination_root is None:
                self._write_frame(stream, {"type": "rejected", "transfer_id": transfer_id})
                return
            self._write_frame(stream, {"type": "ready", "transfer_id": transfer_id})
            entry = FileEntry(safe_name.name, size, digest)
            saved_path = receive_file(stream, Path(destination_root), entry, limits=limits)
            self._write_frame(stream, {"type": "file_ack", "transfer_id": transfer_id})
            self.on_file_received(packet, saved_path)
        except (ValueError, OSError, EOFError) as exc:
            self._write_frame(stream, {"type": "error", "error": str(exc)[:300], "transfer_id": transfer_id})

    @staticmethod
    def _read_frame(stream) -> dict:
        line = stream.readline(MAX_FRAME + 1)
        if not line or len(line) > MAX_FRAME or not line.endswith(b"\n"):
            raise ValueError("Invalid or oversized protocol frame")
        value = json.loads(line.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Protocol frame must be a JSON object")
        return value

    @staticmethod
    def _write_frame(stream, value: dict) -> None:
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(raw) > MAX_FRAME:
            raise ValueError("Protocol frame is too large")
        stream.write(raw)
        stream.flush()

    def _client_context(self) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        cert_path, key_path = self._identity()
        context.load_cert_chain(str(cert_path), str(key_path))
        return context

    def _open_peer(self, host: str, port: int, peer_id: str):
        expected = self.trusted.get(peer_id)
        if not expected:
            raise PairingRequired(f"Peer {peer_id} has not been paired")
        raw = socket.create_connection((host, port), timeout=CONNECT_TIMEOUT)
        try:
            conn = self._client_context().wrap_socket(raw, server_hostname=peer_id)
            actual = hashlib.sha256(conn.getpeercert(binary_form=True)).hexdigest()
            if actual != expected:
                conn.close()
                raise ssl.SSLError("Peer certificate fingerprint mismatch")
            conn.settimeout(TRANSFER_TIMEOUT)
            return conn
        except Exception:
            raw.close()
            raise

    def send_message(self, host: str, port: int, peer_id: str, body: str, message_id: str | None = None) -> str:
        message_id = message_id or str(uuid.uuid4())
        with self._send_lock:
            with self._open_peer(host, port, peer_id) as conn:
                stream = conn.makefile("rwb")
                self._write_frame(stream, {
                    "type": "message", "sender_id": self.peer_id,
                    "message_id": message_id, "body": body,
                })
                response = self._read_frame(stream)
                if response.get("type") != "ack" or response.get("message_id") != message_id:
                    if response.get("error") == "pairing_required":
                        raise PairingRequired("The receiving device has not trusted this device")
                    raise ConnectionError("Message was not acknowledged")
        return message_id

    def send_file(self, host: str, port: int, peer_id: str, path: Path, transfer_id: str | None = None) -> str:
        """Send one file over the already-paired TLS channel; receiver verifies size and SHA-256 before publishing."""
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            raise ValueError("source must be a regular, non-symlink file")
        size = path.stat().st_size
        limits = TransferLimits()
        if size > limits.max_file_bytes:
            raise ValueError("file exceeds per-file transfer limit")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
                digest.update(chunk)
        if path.stat().st_size != size:
            raise OSError("source file changed while preparing transfer")
        transfer_id = transfer_id or str(uuid.uuid4())
        with self._send_lock:
            with self._open_peer(host, port, peer_id) as conn:
                stream = conn.makefile("rwb")
                self._write_frame(stream, {
                    "type": "file", "sender_id": self.peer_id,
                    "transfer_id": transfer_id, "filename": path.name,
                    "size": size, "sha256": digest.hexdigest(),
                })
                response = self._read_frame(stream)
                if response.get("type") == "rejected":
                    raise TransferRejected("The receiving user declined the file")
                if response.get("type") != "ready" or response.get("transfer_id") != transfer_id:
                    raise ConnectionError(response.get("error", "Receiver did not accept the file offer"))
                # The file body follows the bounded JSON manifest on the same authenticated TLS stream.
                with path.open("rb") as source:
                    sent = 0
                    while True:
                        chunk = source.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        stream.write(chunk)
                        sent += len(chunk)
                    stream.flush()
                if sent != size:
                    raise OSError("source file changed while being transferred")
                response = self._read_frame(stream)
                if response.get("type") != "file_ack" or response.get("transfer_id") != transfer_id:
                    raise ConnectionError(response.get("error", "File transfer was not acknowledged"))
        return transfer_id
