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
                last_seen TEXT
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

    def seed_demo(self):
        samples = [
            ("peer-kari", "KariouSL", "online"),
            ("peer-ten", "Ten.04", "away"),
            ("peer-hitman", "hitman", "offline"),
            ("peer-ram", "Ram", "offline"),
        ]
        with self.connect() as db:
            for row in samples:
                db.execute("INSERT OR IGNORE INTO contacts(peer_id,display_name,status) VALUES(?,?,?)", row)

    def contacts(self):
        with self.connect() as db:
            return db.execute("SELECT * FROM contacts ORDER BY display_name COLLATE NOCASE").fetchall()

    def messages(self, peer_id: str):
        with self.connect() as db:
            return db.execute(
                "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at",
                (peer_id,)
            ).fetchall()

    def add_message(self, peer_id: str, direction: str, body: str, kind: str = "text"):
        import uuid
        now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        with self.connect() as db:
            db.execute(
                """INSERT INTO messages(message_id,conversation_id,peer_id,direction,body,created_at,kind)
                   VALUES(?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), peer_id, peer_id, direction, body, now, kind)
            )
