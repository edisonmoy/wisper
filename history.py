import sqlite3
from pathlib import Path


class HistoryDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(exist_ok=True)
        with self._conn() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    audio_ms INTEGER DEFAULT 0,
                    model TEXT DEFAULT '',
                    latency_ms INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                )
            ''')
            # Migrate existing DBs that predate model/latency columns.
            existing = {row[1] for row in conn.execute('PRAGMA table_info(history)')}
            if 'model' not in existing:
                conn.execute("ALTER TABLE history ADD COLUMN model TEXT DEFAULT ''")
            if 'latency_ms' not in existing:
                conn.execute('ALTER TABLE history ADD COLUMN latency_ms INTEGER DEFAULT 0')

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def add(self, text: str, audio_ms: int = 0, model: str = '', latency_ms: int = 0):
        with self._conn() as conn:
            conn.execute(
                'INSERT INTO history (text, audio_ms, model, latency_ms) VALUES (?, ?, ?, ?)',
                (text.strip(), audio_ms, model, latency_ms),
            )

    def get_recent(self, n: int = 20) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                'SELECT id, text, model, latency_ms, created_at'
                ' FROM history ORDER BY id DESC LIMIT ?',
                (n,),
            ).fetchall()
        return [
            {'id': r[0], 'text': r[1], 'model': r[2], 'latency_ms': r[3], 'created_at': r[4]}
            for r in rows
        ]

    def clear(self):
        with self._conn() as conn:
            conn.execute('DELETE FROM history')
