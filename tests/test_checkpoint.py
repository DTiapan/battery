from battery.checkpoint import build_checkpoint_payload, handle_hook_event, ingest_checkpoint
from battery.db import get_connection, init_db, list_memories, list_session_checkpoints


def test_checkpoint_ingest(tmp_path):
    db_path = tmp_path / "checkpoint.db"
    md_path = tmp_path / "BATTERY.md"
    conn = get_connection(db_path)
    init_db(conn)

    payload = {
        "session_id": "sess-123",
        "event_type": "session_end",
        "project_root": str(tmp_path),
        "task_summary": "Implement memory hooks",
        "next_step": "Run tests",
        "decisions": ["Use SQLite event log"],
        "rejected_approaches": [],
        "changed_files": [],
        "blockers": [],
    }
    result = ingest_checkpoint(conn, payload, md_path)
    conn.commit()

    assert result["checkpoint_id"] > 0
    assert result["memory_id"] > 0
    memories = list_memories(conn, category="episodic")
    assert len(memories) == 1
    checkpoints = list_session_checkpoints(conn, project_root=str(tmp_path))
    assert len(checkpoints) == 1


def test_handle_session_end_hook(tmp_path):
    db_path = tmp_path / "hook.db"
    md_path = tmp_path / "BATTERY.md"
    conn = get_connection(db_path)
    init_db(conn)

    hook_input = {
        "hook_event_name": "SessionEnd",
        "session_id": "abc",
        "cwd": str(tmp_path),
    }
    payload = build_checkpoint_payload(hook_input, event_type="session_end")
    assert payload["session_id"] == "abc"

    result = handle_hook_event(conn, hook_input, md_path)
    conn.commit()
    assert result["status"] == "ok"
    assert result["event"] == "SessionEnd"
