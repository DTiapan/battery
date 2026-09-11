from battery.db import get_connection, init_db, insert_memory
from battery.migrate import SCHEMA_VERSION, get_schema_version, log_memory_event


def test_schema_migration_to_v2(tmp_path):
    db_path = tmp_path / "migrate.db"
    conn = get_connection(db_path)
    init_db(conn)

    version = get_schema_version(conn)
    assert version == SCHEMA_VERSION

    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "memory_events" in tables
    assert "memory_citations" in tables
    assert "session_checkpoints" in tables

    cols = {row[1] for row in conn.execute("PRAGMA table_info(memories)").fetchall()}
    assert "staleness" in cols
    assert "source" in cols


def test_memory_event_log(tmp_path):
    db_path = tmp_path / "events.db"
    conn = get_connection(db_path)
    init_db(conn)

    fake_vec = [0.1] * 384
    result = insert_memory(conn, "Test event logging", fake_vec, category="general")
    event_id = log_memory_event(conn, "ASSERT", result["id"], {"test": True})
    conn.commit()

    row = conn.execute(
        "SELECT event_type, memory_id FROM memory_events WHERE event_id = ?",
        (event_id,),
    ).fetchone()
    assert row["event_type"] == "ASSERT"
    assert row["memory_id"] == result["id"]
