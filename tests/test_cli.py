import json
from pathlib import Path
from typer.testing import CliRunner
from battery.cli import app

runner = CliRunner()

def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Battery Context Engine" in result.output

def test_cli_init_and_add_and_list(tmp_path):
    db_file = tmp_path / "test_cli.db"
    md_file = tmp_path / "TEST_BATTERY.md"

    # Init
    init_res = runner.invoke(app, ["init", "--db", str(db_file), "--md", str(md_file)])
    assert init_res.exit_code == 0
    assert db_file.exists()
    assert md_file.exists()

    # Add
    add_res = runner.invoke(app, [
        "add", "Rule: Never commit secrets to git",
        "-c", "rule",
        "--db", str(db_file),
        "--md", str(md_file)
    ])
    assert add_res.exit_code == 0
    assert "Saved memory" in add_res.output

    # List
    list_res = runner.invoke(app, ["list", "--db", str(db_file)])
    assert list_res.exit_code == 0
    assert "Never commit secrets to git" in list_res.output

    # Query
    query_res = runner.invoke(app, ["query", "secrets git", "--db", str(db_file)])
    assert query_res.exit_code == 0
    assert "Never commit secrets" in query_res.output
