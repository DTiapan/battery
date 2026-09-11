import pytest
from battery.db import get_connection, init_db, insert_memory, list_memories
from battery.embeddings import embed_text
from battery.sync import export_battery_md, import_battery_md

def test_export_and_import_cycle(tmp_path):
    db_path = tmp_path / "test_sync.db"
    md_path = tmp_path / "BATTERY.md"
    
    conn = get_connection(db_path)
    init_db(conn)
    
    # Insert initial memory
    vec = embed_text("Initial rule: all APIs must require authentication")
    insert_memory(conn, "Initial rule: all APIs must require authentication", vec, category="rule")
    
    # 1. Export to Markdown
    exported_file = export_battery_md(conn, md_path)
    assert exported_file.exists()
    content = exported_file.read_text(encoding="utf-8")
    assert "Active Rules & Constraints" in content
    assert "Initial rule: all APIs must require authentication" in content
    
    # 2. Simulate human manual edit in BATTERY.md
    additional_markdown = (
        content + "\n## Architectural Decisions\n\n- New decision: Use Redis for pubsub event bus\n"
    )
    md_path.write_text(additional_markdown, encoding="utf-8")
    
    # 3. Import back into database
    imported_count = import_battery_md(conn, md_path)
    assert imported_count == 1
    
    # Verify new memory is in SQLite
    all_memories = list_memories(conn)
    contents = [m["content"] for m in all_memories]
    assert "New decision: Use Redis for pubsub event bus" in contents
    
    conn.close()
