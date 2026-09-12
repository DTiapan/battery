"""Tests for profile export/import portability bundles."""

import json
import zipfile

import pytest
from typer.testing import CliRunner

from battery.cli import app
from battery.db import get_connection, init_db, insert_memory, list_memories
from battery.embeddings import embed_text
from battery.portability import export_profile_bundle, import_profile_bundle, inspect_bundle

runner = CliRunner()


def test_export_import_roundtrip(tmp_path, monkeypatch):
    db_path = tmp_path / "profiles" / "default" / "battery.db"
    db_path.parent.mkdir(parents=True)
    md_path = tmp_path / "BATTERY.md"
    bundle_path = tmp_path / "backup.battery-bundle"
    restore_home = tmp_path / "restored" / "home"
    restore_db = restore_home / "profiles" / "work" / "battery.db"
    restore_md = tmp_path / "restored" / "BATTERY_work.md"

    monkeypatch.setenv("BATTERY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("BATTERY_DB_PATH", str(db_path))
    monkeypatch.setenv("BATTERY_MD_PATH", str(md_path))

    conn = get_connection(db_path)
    init_db(conn)
    insert_memory(
        conn,
        "Use SQLite WAL mode for hybrid storage",
        embed_text("Use SQLite WAL mode for hybrid storage"),
        category="decision",
    )
    conn.commit()
    conn.close()
    md_path.write_text("# Battery\n\n- decision\n", encoding="utf-8")

    export_result = export_profile_bundle(
        profile="default",
        out_path=bundle_path,
        md_path=md_path,
        include_md=True,
        battery_version="0.4.0",
    )
    assert bundle_path.exists()
    assert "battery.db" in export_result["files"]
    assert "BATTERY.md" in export_result["files"]

    manifest = inspect_bundle(bundle_path)
    assert manifest["profile"] == "default"
    assert manifest["checksums"]["battery.db"]

    monkeypatch.setenv("BATTERY_HOME", str(restore_home))
    monkeypatch.delenv("BATTERY_DB_PATH", raising=False)
    monkeypatch.setenv("BATTERY_MD_PATH", str(restore_md))

    import_result = import_profile_bundle(
        bundle_path,
        profile="work",
        md_path=restore_md,
        force=True,
    )
    assert import_result["profile"] == "work"
    assert restore_db.exists()

    conn2 = get_connection(restore_db)
    rows = list_memories(conn2)
    conn2.close()
    assert len(rows) == 1
    assert "SQLite WAL" in rows[0]["content"]


def test_import_rejects_checksum_tamper(tmp_path):
    bundle_path = tmp_path / "bad.battery-bundle"
    with zipfile.ZipFile(bundle_path, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "bundle_format": "battery-bundle",
                    "bundle_version": 1,
                    "profile": "default",
                    "checksums": {"battery.db": "deadbeef"},
                }
            ),
        )
        archive.writestr("battery.db", b"not-a-database")

    with pytest.raises(ValueError, match="Checksum mismatch"):
        import_profile_bundle(bundle_path, profile="default", force=True)


def test_cli_profile_export_import(tmp_path, monkeypatch):
    home = tmp_path / "home"
    db_path = home / "battery.db"
    md_path = tmp_path / "BATTERY.md"
    bundle_path = tmp_path / "cli.battery-bundle"

    monkeypatch.setenv("BATTERY_HOME", str(home))
    monkeypatch.setenv("BATTERY_DB_PATH", str(db_path))
    monkeypatch.setenv("BATTERY_MD_PATH", str(md_path))
    monkeypatch.chdir(tmp_path)

    init_res = runner.invoke(app, ["init"])
    assert init_res.exit_code == 0

    export_res = runner.invoke(
        app,
        ["profile", "export", "--out", str(bundle_path), "--include-md"],
    )
    assert export_res.exit_code == 0
    assert "Exported profile" in export_res.output

    inspect_res = runner.invoke(app, ["profile", "inspect", str(bundle_path)])
    assert inspect_res.exit_code == 0
    assert "battery-bundle" in inspect_res.output

    import_res = runner.invoke(
        app,
        ["profile", "import", str(bundle_path), "--profile", "imported", "--force"],
    )
    assert import_res.exit_code == 0
    assert "Imported profile" in import_res.output
