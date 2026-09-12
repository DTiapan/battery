from battery.db import get_connection, hash_file_snippet, init_db, insert_memory, list_memories
from battery.prune import prune_stale_memories


def test_prune_dry_run_finds_stale(tmp_path):
    db_path = tmp_path / "prune.db"
    conn = get_connection(db_path)
    init_db(conn)

    file_path = tmp_path / "legacy.py"
    file_path.write_text("legacy = True\n", encoding="utf-8")
    insert_memory(
        conn,
        "Legacy module still active",
        [0.2] * 384,
        category="general",
        citations=[{"file_path": str(file_path), "snippet_hash": hash_file_snippet(file_path)}],
    )
    conn.commit()

    file_path.unlink()
    result = prune_stale_memories(conn, project_root=tmp_path, dry_run=True)
    assert result["candidates"] >= 1
    assert len(list_memories(conn)) == 1

    result_apply = prune_stale_memories(conn, project_root=tmp_path, dry_run=False)
    assert len(result_apply["pruned_ids"]) >= 1
    assert len(list_memories(conn)) == 0
