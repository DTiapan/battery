from typer.testing import CliRunner

from battery.checkpoint import handle_hook_event, ingest_checkpoint
from battery.cli import app
from battery.db import get_connection, init_db, list_memories
from battery.handoff import (
    export_handoff,
    format_handoff_markdown,
    get_handoff_dir,
    get_latest_handoff_context,
    load_handoff,
    read_handoff_artifact,
    verify_changed_files,
)

runner = CliRunner()


def test_verify_changed_files(tmp_path):
    existing = tmp_path / "src" / "main.py"
    existing.parent.mkdir(parents=True)
    existing.write_text("print('ok')", encoding="utf-8")

    result = verify_changed_files(
        [str(existing), str(tmp_path / "missing.py")],
        tmp_path,
    )
    assert result["status"] == "partial"
    assert result["valid_count"] == 1
    assert result["missing_count"] == 1


def test_export_and_load_handoff_roundtrip(tmp_path):
    db_path = tmp_path / "handoff.db"
    md_path = tmp_path / "BATTERY.md"
    conn = get_connection(db_path)
    init_db(conn)

    payload = {
        "session_id": "sess-handoff",
        "event_type": "session_end",
        "project_root": str(tmp_path),
        "task_summary": "Implement cross-tool handoff",
        "next_step": "Switch to Claude Code",
        "decisions": ["Store artifacts under .battery/handoff"],
        "rejected_approaches": ["Cloud sync"],
        "changed_files": [],
        "blockers": [],
    }
    ingest_checkpoint(conn, payload, md_path)
    conn.commit()

    export_result = export_handoff(
        conn,
        project_root=tmp_path,
        profile="default",
        from_client="cursor",
        to_client="claude-code",
    )
    conn.commit()

    handoff_dir = get_handoff_dir(tmp_path)
    assert (handoff_dir / "HANDOFF.json").exists()
    assert (handoff_dir / "HANDOFF.md").exists()
    assert export_result["artifact"]["from_client"] == "cursor"
    assert "cross-tool handoff" in export_result["markdown"]

    artifact = read_handoff_artifact(project_root=tmp_path)
    assert artifact["handoff_id"] == export_result["handoff_id"]
    assert artifact["decisions"] == payload["decisions"]

    load_result = load_handoff(
        conn,
        md_path,
        project_root=tmp_path,
        ingest=True,
        to_client="claude-code",
    )
    conn.commit()

    assert "Implement cross-tool handoff" in load_result["markdown"]
    assert load_result["memory_id"] is not None
    episodic = list_memories(conn, category="episodic")
    assert any("Handoff loaded from cursor" in row["content"] for row in episodic)


def test_handoff_lineage_on_second_export(tmp_path):
    db_path = tmp_path / "lineage.db"
    md_path = tmp_path / "BATTERY.md"
    conn = get_connection(db_path)
    init_db(conn)

    payload = {
        "session_id": "sess-1",
        "event_type": "session_end",
        "project_root": str(tmp_path),
        "task_summary": "First session",
        "next_step": "Continue",
        "decisions": [],
        "rejected_approaches": [],
        "changed_files": [],
        "blockers": [],
    }
    ingest_checkpoint(conn, payload, md_path)
    conn.commit()

    first = export_handoff(
        conn,
        project_root=tmp_path,
        profile="default",
        from_client="cursor",
        to_client="claude-code",
    )
    conn.commit()

    payload["task_summary"] = "Second session"
    ingest_checkpoint(conn, payload, md_path)
    conn.commit()

    second = export_handoff(
        conn,
        project_root=tmp_path,
        profile="default",
        from_client="claude-code",
        to_client="cursor",
    )
    conn.commit()

    lineage = second["artifact"]["lineage"]
    assert len(lineage) == 1
    assert lineage[0]["handoff_id"] == first["handoff_id"]


def test_session_start_prefers_handoff(tmp_path, monkeypatch):
    db_path = tmp_path / "hook.db"
    md_path = tmp_path / "BATTERY.md"
    conn = get_connection(db_path)
    init_db(conn)

    payload = {
        "session_id": "sess-hook",
        "event_type": "session_end",
        "project_root": str(tmp_path),
        "task_summary": "Older checkpoint task",
        "next_step": "Old next step",
        "decisions": [],
        "rejected_approaches": [],
        "changed_files": [],
        "blockers": [],
    }
    ingest_checkpoint(conn, payload, md_path)
    conn.commit()

    export_handoff(
        conn,
        project_root=tmp_path,
        profile="default",
        from_client="cursor",
        to_client="claude-code",
    )
    conn.commit()

    monkeypatch.chdir(tmp_path)
    result = handle_hook_event(
        conn,
        {"hook_event_name": "SessionStart", "cwd": str(tmp_path)},
        md_path,
    )
    assert result["status"] == "ok"
    assert "Battery handoff (switch tools)" in result["additionalContext"]
    assert "# Battery Handoff" in result["additionalContext"]


def test_get_latest_handoff_context(tmp_path):
    db_path = tmp_path / "ctx.db"
    md_path = tmp_path / "BATTERY.md"
    conn = get_connection(db_path)
    init_db(conn)

    payload = {
        "session_id": "sess-ctx",
        "event_type": "session_end",
        "project_root": str(tmp_path),
        "task_summary": "Context export test",
        "next_step": "Verify",
        "decisions": [],
        "rejected_approaches": [],
        "changed_files": [],
        "blockers": [],
    }
    ingest_checkpoint(conn, payload, md_path)
    conn.commit()
    export_handoff(conn, project_root=tmp_path, from_client="cursor")
    conn.commit()

    context = get_latest_handoff_context(tmp_path)
    assert context is not None
    assert "Context export test" in context


def test_cli_handoff_export_and_load(tmp_path, monkeypatch):
    db_path = tmp_path / "cli.db"
    md_path = tmp_path / "BATTERY.md"
    monkeypatch.chdir(tmp_path)

    init_res = runner.invoke(app, ["init", "--db", str(db_path), "--md", str(md_path)])
    assert init_res.exit_code == 0

    add_res = runner.invoke(
        app,
        [
            "add",
            "Decision: use local SQLite for memory",
            "-c",
            "decision",
            "--db",
            str(db_path),
            "--md",
            str(md_path),
        ],
    )
    assert add_res.exit_code == 0

    conn = get_connection(db_path)
    init_db(conn)
    ingest_checkpoint(
        conn,
        {
            "session_id": "cli-sess",
            "event_type": "session_end",
            "project_root": str(tmp_path),
            "task_summary": "CLI handoff test",
            "next_step": "Load in Claude",
            "decisions": ["Use MCP handoff"],
            "rejected_approaches": [],
            "changed_files": [],
            "blockers": [],
        },
        md_path,
    )
    conn.commit()

    export_res = runner.invoke(
        app,
        [
            "handoff",
            "export",
            "--from-client",
            "cursor",
            "--to-client",
            "claude-code",
            "--db",
            str(db_path),
        ],
    )
    assert export_res.exit_code == 0
    assert "Exported handoff" in export_res.output

    load_res = runner.invoke(
        app,
        ["handoff", "load", "--latest", "--db", str(db_path), "--md", str(md_path)],
    )
    assert load_res.exit_code == 0
    assert "CLI handoff test" in load_res.output

    show_res = runner.invoke(app, ["handoff", "show"])
    assert show_res.exit_code == 0
    assert "cursor" in show_res.output


def test_format_handoff_markdown_includes_sections():
    artifact = {
        "from_client": "cursor",
        "to_client": "claude-code",
        "project_root": "/tmp/project",
        "profile": "default",
        "created_at": "2026-09-12T00:00:00+00:00",
        "verification_status": "valid",
        "task_summary": "Ship handoff",
        "next_action": "Run tests",
        "decisions": ["Keep artifacts local"],
        "rejected_approaches": ["Cloud export"],
        "blockers": ["None"],
        "changed_files": ["src/handoff.py"],
        "active_context": [{"id": 1, "category": "rule", "content": "Use type hints"}],
        "lineage": [],
    }
    markdown = format_handoff_markdown(artifact)
    assert "# Battery Handoff" in markdown
    assert "Ship handoff" in markdown
    assert "Use type hints" in markdown
