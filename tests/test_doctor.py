from pathlib import Path

from typer.testing import CliRunner

from battery.cli import app
from battery.db import get_connection, init_db, insert_memory
from battery.doctor import ONBOARD_SEED_MEMORIES, run_doctor
from battery.embeddings import embed_text
from battery.sync import export_battery_md

runner = CliRunner()


def test_run_doctor_healthy(tmp_path):
    db_file = tmp_path / "doctor.db"
    md_file = tmp_path / "BATTERY.md"
    conn = get_connection(db_file)
    init_db(conn)
    export_battery_md(conn, md_file)

    report = run_doctor(conn, md_file, adoption=False)
    assert report["healthy"] is True
    assert report["passed"] == report["total"]
    assert any(c["name"] == "schema_version" and c["ok"] for c in report["checks"])


def test_run_doctor_adoption_with_seeded_memories(tmp_path):
    db_file = tmp_path / "doctor.db"
    md_file = tmp_path / "BATTERY.md"
    conn = get_connection(db_file)
    init_db(conn)
    for content, category in ONBOARD_SEED_MEMORIES:
        insert_memory(conn, content, embed_text(content), category=category)
    export_battery_md(conn, md_file)

    report = run_doctor(conn, md_file, adoption=True, project_dir=tmp_path)
    names = {c["name"] for c in report["checks"]}
    assert "mcp_context" in names
    assert "mcp_rules" in names
    assert "recall_smoke" in names

    by_name = {c["name"]: c for c in report["checks"]}
    assert by_name["mcp_context"]["ok"] is True
    assert by_name["mcp_rules"]["ok"] is True
    assert by_name["recall_smoke"]["ok"] is True


def test_cli_onboard_seeds_and_runs_doctor(tmp_path, monkeypatch):
    db_file = tmp_path / "onboard.db"
    md_file = tmp_path / "BATTERY.md"
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "onboard",
            "--skip-setup",
            "--db",
            str(db_file),
            "--md",
            str(md_file),
        ],
    )

    assert db_file.exists()
    assert md_file.exists()
    assert "Seeded:" in result.output
    assert "mcp_context" in result.output
    assert "recall_smoke" in result.output
    # MCP/hook checks may fail in CI without client configs; core resource checks should pass.
    assert result.exit_code in (0, 1)
