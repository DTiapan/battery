import json
from pathlib import Path

from battery.hooks import hooks_installed, install_hooks, uninstall_hooks


def test_hook_install_and_uninstall(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"

    result = install_hooks(scope="project", project_dir=tmp_path)
    assert settings_path.exists()
    assert Path(result["hook_script"]).exists()

    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "SessionEnd" in data.get("hooks", {})
    assert hooks_installed("project", tmp_path)

    uninstall_hooks(scope="project", project_dir=tmp_path)
    data_after = json.loads(settings_path.read_text(encoding="utf-8"))
    assert not hooks_installed("project", tmp_path)
    assert "SessionEnd" not in data_after.get("hooks", {})
