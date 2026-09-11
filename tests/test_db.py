try:
    import pysqlite3 as sqlite3
except ImportError:
    import sqlite3
import pytest
from battery.db import (
    get_connection,
    init_db,
    insert_memory,
    list_memories,
    tombstone_memory,
    hash_content,
)

@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / "test_battery.db"
    conn = get_connection(db_path)
    init_db(conn)
    yield conn
    conn.close()

def test_wal_mode_and_pragmas(test_db):
    journal_mode = test_db.execute("PRAGMA journal_mode;").fetchone()[0]
    assert journal_mode.lower() == "wal"

def test_insert_and_deduplication(test_db):
    fake_vec = [0.1] * 384
    
    # 1. First insert
    res1 = insert_memory(test_db, "Always use snake_case in Python", fake_vec, category="rule")
    assert res1["status"] == "created"
    assert res1["id"] == 1
    
    # 2. Duplicate insert with exact same content
    res2 = insert_memory(test_db, "  Always use snake_case in Python  ", fake_vec, category="rule")
    assert res2["status"] == "existing"
    assert res2["id"] == 1
    
    # Ensure only 1 record exists in table
    records = list_memories(test_db)
    assert len(records) == 1

def test_tombstone_memory(test_db):
    fake_vec = [0.2] * 384
    res = insert_memory(test_db, "Deprecated API endpoint v1", fake_vec, category="general")
    mem_id = res["id"]
    
    # Delete
    assert tombstone_memory(test_db, mem_id) is True
    
    # Verify omitted by default in list
    active = list_memories(test_db, include_deleted=False)
    assert len(active) == 0
    
    # Verify present when include_deleted=True
    all_records = list_memories(test_db, include_deleted=True)
    assert len(all_records) == 1
    assert all_records[0]["is_deleted"] == 1

def test_fts5_trigger_synchronization(test_db):
    fake_vec = [0.0] * 384
    insert_memory(test_db, "PostgreSQL uses port 5432 by default", fake_vec, category="rule")
    
    # Query FTS5 table directly
    match = test_db.execute(
        "SELECT rowid FROM memories_fts WHERE memories_fts MATCH '\"5432\"'"
    ).fetchone()
    assert match is not None
    assert match[0] == 1
