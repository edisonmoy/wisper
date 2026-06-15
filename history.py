import sqlite3
from pathlib import Path
from typing import TypedDict


class HistoryEntry(TypedDict):
    id: int
    text: str
    model: str
    latency_ms: int
    created_at: str


class HistoryDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(exist_ok=True)
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    audio_ms INTEGER DEFAULT 0,
                    model TEXT DEFAULT '',
                    latency_ms INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                )
            """)
            # Migrate existing DBs that predate model/latency columns.
            existing = {row[1] for row in conn.execute("PRAGMA table_info(history)")}
            if "model" not in existing:
                conn.execute("ALTER TABLE history ADD COLUMN model TEXT DEFAULT ''")
            if "latency_ms" not in existing:
                conn.execute("ALTER TABLE history ADD COLUMN latency_ms INTEGER DEFAULT 0")

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def add(self, text: str, audio_ms: int = 0, model: str = "", latency_ms: int = 0):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO history (text, audio_ms, model, latency_ms) VALUES (?, ?, ?, ?)",
                (text.strip(), audio_ms, model, latency_ms),
            )

    def get_recent(self, n: int = 20) -> list[HistoryEntry]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, text, model, latency_ms, created_at"
                " FROM history ORDER BY id DESC LIMIT ?",
                (n,),
            ).fetchall()
        return [
            HistoryEntry(
                id=row["id"],
                text=row["text"],
                model=row["model"],
                latency_ms=row["latency_ms"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def clear(self):
        with self._conn() as conn:
            conn.execute("DELETE FROM history")
