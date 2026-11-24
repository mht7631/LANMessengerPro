from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from .config import DB_PATH


class Store:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

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
                kind TEXT NOT NULL DEFAULT 'text'
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

    def add_message(self, peer_id: str, direction: str, body: str, kind: str = "text"):
        import uuid
        now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        with self.connect() as db:
            db.execute(
                """INSERT INTO messages(message_id,conversation_id,peer_id,direction,body,created_at,kind)
                   VALUES(?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), peer_id, peer_id, direction, body, now, kind),
            )
