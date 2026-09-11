from typer.testing import CliRunner

from battery.cli import app
from battery.config import (
    delete_profile,
    get_active_profile,
    get_profile_db_path,
    list_profiles,
    set_active_profile,
)

runner = CliRunner()


def test_profile_lifecycle(tmp_path, monkeypatch):
    test_battery_home = tmp_path / ".battery"
    monkeypatch.setenv("BATTERY_HOME", str(test_battery_home))
    monkeypatch.delenv("BATTERY_PROFILE", raising=False)
    monkeypatch.delenv("BATTERY_DB_PATH", raising=False)

    # 1. Default profile initially active
    assert get_active_profile() == "default"
    assert get_profile_db_path("default") == test_battery_home / "battery.db"

    # 2. Switch active profile
    set_active_profile("analytics-core")
    assert get_active_profile() == "analytics-core"
    assert get_profile_db_path() == test_battery_home / "profiles" / "analytics-core" / "battery.db"

    # 3. List profiles
    profiles = list_profiles()
    prof_names = [p["name"] for p in profiles]
    assert "default" in prof_names
    assert "analytics-core" in prof_names

    # 4. Delete profile
    deleted = delete_profile("analytics-core")
    assert deleted is True
    assert get_active_profile() == "default"


def test_cli_profile_commands_and_isolation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    test_battery_home = tmp_path / ".battery"
    monkeypatch.setenv("BATTERY_HOME", str(test_battery_home))
    monkeypatch.delenv("BATTERY_PROFILE", raising=False)
    monkeypatch.delenv("BATTERY_DB_PATH", raising=False)

    # 1. Create two isolated profiles via CLI
    res_a = runner.invoke(app, ["profile", "create", "service-a"])
    assert res_a.exit_code == 0
    assert "Created and initialized profile 'service-a'" in res_a.output

    res_b = runner.invoke(app, ["profile", "create", "service-b"])
    assert res_b.exit_code == 0
    assert "Created and initialized profile 'service-b'" in res_b.output

    # 2. Add memory specifically to service-a
    add_a = runner.invoke(
        app, ["add", "Rule: Service A must listen on port 8080", "--profile", "service-a"]
    )
    assert add_a.exit_code == 0

    # 3. Add memory specifically to service-b
    add_b = runner.invoke(
        app, ["add", "Rule: Service B communicates via gRPC on port 9090", "--profile", "service-b"]
    )
    assert add_b.exit_code == 0

    # 4. Validate isolation: Query service-a
    query_a = runner.invoke(app, ["query", "port", "--profile", "service-a"])
    assert query_a.exit_code == 0
    assert "8080" in query_a.output
    assert "9090" not in query_a.output

    # 5. Validate isolation: Query service-b
    query_b = runner.invoke(app, ["query", "port", "--profile", "service-b"])
    assert query_b.exit_code == 0
    assert "9090" in query_b.output
    assert "8080" not in query_b.output

    # 6. Test 'battery use' alias command
    use_res = runner.invoke(app, ["use", "service-a"])
    assert use_res.exit_code == 0
    assert "Switched active profile to 'service-a'" in use_res.output
    assert get_active_profile() == "service-a"

    # 7. List profiles via CLI
    list_prof_res = runner.invoke(app, ["profile", "list"])
    assert list_prof_res.exit_code == 0
    assert "service-a" in list_prof_res.output
    assert "service-b" in list_prof_res.output
