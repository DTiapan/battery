import subprocess

from typer.testing import CliRunner

from battery.cli import app
from battery.db import get_connection, init_db, list_memories
from battery.git_capture import capture_commit, format_commit_memory, get_commit_info
from battery.git_hooks import git_hook_installed, install_git_hook, uninstall_git_hook

runner = CliRunner()


def _init_git_repo(path, monkeypatch):
    monkeypatch.chdir(path)
    for cmd in (
        ["git", "init"],
        ["git", "config", "user.email", "battery@test.local"],
        ["git", "config", "user.name", "Battery Test"],
    ):
        subprocess.run(cmd, cwd=path, check=True, capture_output=True)


def _commit_file(path, filename: str, message: str):
    file_path = path / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("content\n", encoding="utf-8")
    subprocess.run(["git", "add", filename], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=path, check=True, capture_output=True)


def test_git_hook_install_and_uninstall(tmp_path, monkeypatch):
    _init_git_repo(tmp_path, monkeypatch)
    _commit_file(tmp_path, "README.md", "init")

    install_git_hook(tmp_path)
    hook_path = tmp_path / ".git" / "hooks" / "post-commit"
    assert hook_path.exists()
    assert git_hook_installed(tmp_path)
    assert "battery git capture" in hook_path.read_text(encoding="utf-8")

    uninstall_git_hook(tmp_path)
    assert not git_hook_installed(tmp_path)


def test_capture_commit_creates_episodic_memory(tmp_path, monkeypatch):
    db_path = tmp_path / "git.db"
    _init_git_repo(tmp_path, monkeypatch)
    _commit_file(tmp_path, "src/main.py", "feat: add retrieval fallback")

    conn = get_connection(db_path)
    init_db(conn)
    result = capture_commit(conn, tmp_path)
    conn.commit()

    assert result["status"] == "created"
    assert result["memory_id"] > 0
    rows = list_memories(conn, category="episodic")
    assert len(rows) == 1
    assert "feat: add retrieval fallback" in rows[0]["content"]
    assert rows[0]["source"] == "git"

    second = capture_commit(conn, tmp_path)
    assert second["status"] == "existing"


def test_get_commit_info(tmp_path, monkeypatch):
    _init_git_repo(tmp_path, monkeypatch)
    _commit_file(tmp_path, "docs/adr.md", "docs: add adr")

    info = get_commit_info(tmp_path)
    assert info["subject"] == "docs: add adr"
    assert "docs/adr.md" in info["files"]

    rendered = format_commit_memory(info)
    assert "docs: add adr" in rendered
    assert "docs/adr.md" in rendered


def test_cli_git_capture(tmp_path, monkeypatch):
    db_path = tmp_path / "cli-git.db"
    monkeypatch.setenv("BATTERY_DB_PATH", str(db_path))
    _init_git_repo(tmp_path, monkeypatch)
    _commit_file(tmp_path, "app.py", "feat: cli git capture")

    capture_res = runner.invoke(app, ["git", "capture"])
    assert capture_res.exit_code == 0
    assert "Captured commit" in capture_res.output

    install_res = runner.invoke(app, ["git", "install"])
    assert install_res.exit_code == 0
    assert git_hook_installed(tmp_path)
