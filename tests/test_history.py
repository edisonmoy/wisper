import pytest

from history import HistoryDB


@pytest.fixture
def db(tmp_path):
    return HistoryDB(tmp_path / "test.db")


def test_empty(db):
    assert db.get_recent() == []


def test_add_and_retrieve(db):
    db.add("hello world", audio_ms=1000, model="base.en", latency_ms=200)
    items = db.get_recent()
    assert len(items) == 1
    assert items[0]["text"] == "hello world"
    assert items[0]["model"] == "base.en"
    assert items[0]["latency_ms"] == 200


def test_add_strips_whitespace(db):
    db.add("  hello  ")
    assert db.get_recent()[0]["text"] == "hello"


def test_most_recent_first(db):
    db.add("first")
    db.add("second")
    items = db.get_recent()
    assert items[0]["text"] == "second"
    assert items[1]["text"] == "first"


def test_limit(db):
    for i in range(5):
        db.add(f"item {i}")
    assert len(db.get_recent(3)) == 3


def test_limit_does_not_exceed_total(db):
    db.add("only one")
    assert len(db.get_recent(20)) == 1


def test_clear(db):
    db.add("hello")
    db.clear()
    assert db.get_recent() == []


def test_clear_then_add(db):
    db.add("before")
    db.clear()
    db.add("after")
    items = db.get_recent()
    assert len(items) == 1
    assert items[0]["text"] == "after"


def test_migration_idempotent(tmp_path):
    """Opening the same DB twice should not error or duplicate data."""
    path = tmp_path / "test.db"
    db1 = HistoryDB(path)
    db1.add("hello")
    db2 = HistoryDB(path)
    assert len(db2.get_recent()) == 1


def test_result_has_all_fields(db):
    db.add("test", audio_ms=500, model="tiny.en", latency_ms=100)
    item = db.get_recent()[0]
    assert {"id", "text", "model", "latency_ms", "created_at"} <= item.keys()


def test_migration_adds_missing_columns(tmp_path):
    """Opening an old-schema DB (no model/latency_ms columns) triggers ALTER TABLE."""
    import sqlite3

    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            audio_ms INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.execute("INSERT INTO history (text, audio_ms) VALUES ('hello', 500)")
    conn.commit()
    conn.close()

    db = HistoryDB(db_path)
    items = db.get_recent()
    assert len(items) == 1
    assert items[0]["text"] == "hello"
    assert items[0]["model"] == ""
    assert items[0]["latency_ms"] == 0
