from __future__ import annotations

import json
import socket
import threading
import time
from dataclasses import dataclass
from typing import Callable

DISCOVERY_GROUP = "239.255.77.77"
DISCOVERY_PORT = 47777
PROTOCOL_VERSION = 1
ANNOUNCE_INTERVAL = 3.0
PEER_TIMEOUT = 12.0
MAX_PACKET = 4096


@dataclass(frozen=True)
class Peer:
    peer_id: str
    display_name: str
    host: str
    port: int
    last_seen: float


class LanDiscovery:
    """LAN presence discovery. This phase deliberately does not transmit chat data."""

    def __init__(
        self,
        peer_id: str,
        display_name: str,
        on_peers: Callable[[list[Peer]], None],
        tcp_port: int = 0,
    ):
        self.peer_id = peer_id
        self.display_name = display_name
        self.tcp_port = tcp_port
        self.on_peers = on_peers
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._peers: dict[str, Peer] = {}
        self._lock = threading.Lock()
        self._socket: socket.socket | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="LAN-discovery", daemon=True)
        self._thread.start()

    def update_profile(self, display_name: str) -> None:
        self.display_name = display_name
        self._announce()

    def stop(self) -> None:
        self._stop.set()
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def peers(self) -> list[Peer]:
        with self._lock:
            return list(self._peers.values())

    def _new_socket(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass
        sock.bind(("", DISCOVERY_PORT))
        membership = socket.inet_aton(DISCOVERY_GROUP) + socket.inet_aton("0.0.0.0")
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
        sock.settimeout(0.5)
        return sock

    def _packet(self) -> bytes:
        payload = {
            "app": "LANMessengerPro",
            "version": PROTOCOL_VERSION,
            "type": "presence",
            "peer_id": self.peer_id,
            "display_name": self.display_name[:64],
            "tcp_port": self.tcp_port,
            "sent_at": int(time.time()),
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def _announce(self) -> None:
        packet = self._packet()
        for address in (DISCOVERY_GROUP, "255.255.255.255"):
            try:
                if self._socket is not None:
                    self._socket.sendto(packet, (address, DISCOVERY_PORT))
                else:
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                        sender.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                        sender.sendto(packet, (address, DISCOVERY_PORT))
            except OSError:
                continue

    def _run(self) -> None:
        try:
            self._socket = self._new_socket()
        except OSError:
            self._socket = None
        last_announce = 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            if now - last_announce >= ANNOUNCE_INTERVAL:
                self._announce()
                last_announce = now
            if self._socket is not None:
                try:
                    raw, address = self._socket.recvfrom(MAX_PACKET)
                    self._consume(raw, address[0])
                except socket.timeout:
                    pass
                except OSError:
                    if not self._stop.is_set():
                        time.sleep(0.2)
            self._expire()
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def _consume(self, raw: bytes, host: str) -> None:
        try:
            data = json.loads(raw.decode("utf-8"))
            if data.get("app") != "LANMessengerPro" or data.get("type") != "presence":
                return
            if data.get("version") != PROTOCOL_VERSION:
                return
            peer_id = str(data["peer_id"])
            name = str(data["display_name"]).strip()[:64]
            port = int(data["tcp_port"])
            if not peer_id or peer_id == self.peer_id or not name or not 0 <= port <= 65535:
                return
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return
        with self._lock:
            self._peers[peer_id] = Peer(peer_id, name, host, port, time.time())
            snapshot = list(self._peers.values())
        self.on_peers(snapshot)

    def _expire(self) -> None:
        cutoff = time.time() - PEER_TIMEOUT
        changed = False
        with self._lock:
            expired = [key for key, peer in self._peers.items() if peer.last_seen < cutoff]
            for key in expired:
                del self._peers[key]
                changed = True
            snapshot = list(self._peers.values())
        if changed:
            self.on_peers(snapshot)
