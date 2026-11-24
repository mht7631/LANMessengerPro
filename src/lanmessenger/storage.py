from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
from typing import Iterator
from .config import DB_PATH


class Store:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Open a short-lived connection and always release its file handle.

        sqlite3.Connection's context manager commits/rolls back but does not
        close the connection; explicit close is required on Windows so temp
        databases can be removed and application files can be replaced.
        """
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _init(self):
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS contacts (
                peer_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'offline',
                last_seen TEXT,
                address TEXT,
                tcp_port INTEGER
            );
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                peer_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'text',
                delivery_status TEXT NOT NULL DEFAULT 'delivered'
            );
            CREATE INDEX IF NOT EXISTS ix_messages_conversation
                ON messages(conversation_id, created_at);
            CREATE TABLE IF NOT EXISTS transfers (
                transfer_id TEXT PRIMARY KEY,
                peer_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                direction TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(contacts)")}
            if "address" not in columns:
                db.execute("ALTER TABLE contacts ADD COLUMN address TEXT")
            if "tcp_port" not in columns:
                db.execute("ALTER TABLE contacts ADD COLUMN tcp_port INTEGER")
            message_columns = {row["name"] for row in db.execute("PRAGMA table_info(messages)")}
            if "delivery_status" not in message_columns:
                db.execute("ALTER TABLE messages ADD COLUMN delivery_status TEXT NOT NULL DEFAULT 'delivered'")
            db.execute("UPDATE messages SET delivery_status='queued' WHERE direction='outgoing' AND delivery_status='sending'")

    def sync_discovered_peers(self, peers):
        now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        with self.connect() as db:
            db.execute("UPDATE contacts SET status='offline'")
            for peer in peers:
                db.execute(
                    """INSERT INTO contacts(peer_id,display_name,status,last_seen,address,tcp_port)
                       VALUES(?,?, 'online', ?, ?, ?)
                       ON CONFLICT(peer_id) DO UPDATE SET
                         display_name=excluded.display_name,
                         status='online',
                         last_seen=excluded.last_seen,
                         address=excluded.address,
                         tcp_port=excluded.tcp_port""",
                    (peer.peer_id, peer.display_name, now, peer.host, peer.port),
                )

    def contacts(self):
        with self.connect() as db:
            return db.execute(
                "SELECT * FROM contacts ORDER BY CASE status WHEN 'online' THEN 0 ELSE 1 END, display_name COLLATE NOCASE"
            ).fetchall()

    def messages(self, peer_id: str):
        with self.connect() as db:
            return db.execute(
                "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at",
                (peer_id,),
            ).fetchall()

    def add_message(self, peer_id: str, direction: str, body: str, kind: str = "text", message_id: str | None = None, delivery_status: str | None = None):
        import uuid
        message_id = message_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        with self.connect() as db:
            db.execute(
                """INSERT INTO messages(message_id,conversation_id,peer_id,direction,body,created_at,kind,delivery_status)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (message_id, peer_id, peer_id, direction, body, now, kind,
                 delivery_status or ("queued" if direction == "outgoing" else "delivered")),
            )

    def has_message(self, message_id: str) -> bool:
        with self.connect() as db:
            return db.execute("SELECT 1 FROM messages WHERE message_id=?", (message_id,)).fetchone() is not None

    def set_delivery_status(self, message_id: str, status: str):
        if status not in {"queued", "sending", "delivered", "failed"}:
            raise ValueError("Invalid delivery status")
        with self.connect() as db:
            db.execute("UPDATE messages SET delivery_status=? WHERE message_id=?", (status, message_id))

    def pending_messages(self, peer_id: str | None = None):
        query = "SELECT * FROM messages WHERE direction='outgoing' AND delivery_status IN ('queued','failed')"
        args = ()
        if peer_id:
            query += " AND peer_id=?"
            args = (peer_id,)
        query += " ORDER BY created_at"
        with self.connect() as db:
            return db.execute(query, args).fetchall()
