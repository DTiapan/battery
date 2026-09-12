"""Profile export/import bundles for cross-machine portability."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from battery.config import EMBEDDING_MODEL, get_profile_db_path, get_profile_md_path
from battery.db import get_connection
from battery.migrate import get_schema_version, migrate_db

BUNDLE_FORMAT = "battery-bundle"
BUNDLE_VERSION = 1
MANIFEST_NAME = "manifest.json"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checkpoint_db(db_path: Path) -> None:
    """Flushes WAL and creates a consistent SQLite snapshot path."""
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    src_conn = get_connection(db_path)
    try:
        src_conn.execute("PRAGMA wal_checkpoint(FULL)")
        src_conn.commit()
    finally:
        src_conn.close()


def export_profile_bundle(
    *,
    profile: str,
    out_path: Path,
    md_path: Optional[Path] = None,
    include_md: bool = False,
    battery_version: str = "0.0.0",
) -> Dict[str, Any]:
    """Exports a profile database (and optional BATTERY.md) to a .battery-bundle zip."""
    db_path = get_profile_db_path(profile)
    if not db_path.exists():
        raise FileNotFoundError(
            f"Profile '{profile}' has no database at {db_path}. Run 'battery init' or "
            "'battery profile create' first."
        )

    _checkpoint_db(db_path)
    resolved_md = md_path or get_profile_md_path(profile)
    out_path = out_path if out_path.suffix else Path(str(out_path) + ".battery-bundle")
    if out_path.suffix != ".battery-bundle":
        out_path = out_path.with_suffix(".battery-bundle")

    with tempfile.TemporaryDirectory(prefix="battery-export-") as tmp_dir:
        tmp_root = Path(tmp_dir)
        bundle_db = tmp_root / "battery.db"
        shutil.copy2(db_path, bundle_db)

        files: Dict[str, str] = {"battery.db": _sha256_file(bundle_db)}
        bundle_files: List[str] = ["battery.db"]

        if include_md and resolved_md.is_file():
            bundle_md = tmp_root / "BATTERY.md"
            shutil.copy2(resolved_md, bundle_md)
            files["BATTERY.md"] = _sha256_file(bundle_md)
            bundle_files.append("BATTERY.md")

        conn = get_connection(db_path)
        try:
            schema_version = get_schema_version(conn)
        finally:
            conn.close()

        manifest = {
            "bundle_format": BUNDLE_FORMAT,
            "bundle_version": BUNDLE_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "battery_version": battery_version,
            "profile": profile,
            "schema_version": schema_version,
            "embedding_model": EMBEDDING_MODEL,
            "includes_mirror": "BATTERY.md" in files,
            "checksums": files,
            "notes": (
                "Portable SQLite memory store. ONNX embedding weights are not bundled; "
                "they re-download on first embed (~90MB)."
            ),
        }
        manifest_path = tmp_root / MANIFEST_NAME
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(manifest_path, MANIFEST_NAME)
            for name in bundle_files:
                archive.write(tmp_root / name, name)

    return {
        "path": str(out_path),
        "profile": profile,
        "manifest": manifest,
        "files": bundle_files,
    }


def _read_manifest_from_zip(archive: zipfile.ZipFile) -> Dict[str, Any]:
    if MANIFEST_NAME not in archive.namelist():
        raise ValueError(f"Invalid bundle: missing {MANIFEST_NAME}")
    manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
    if manifest.get("bundle_format") != BUNDLE_FORMAT:
        raise ValueError(
            f"Unsupported bundle format: {manifest.get('bundle_format')!r} "
            f"(expected {BUNDLE_FORMAT})"
        )
    if int(manifest.get("bundle_version", 0)) > BUNDLE_VERSION:
        raise ValueError(
            f"Bundle version {manifest.get('bundle_version')} is newer than "
            f"supported importer ({BUNDLE_VERSION}). Upgrade Battery first."
        )
    return manifest


def _verify_bundle_contents(tmp_root: Path, manifest: Dict[str, Any]) -> None:
    checksums = manifest.get("checksums") or {}
    for name, expected in checksums.items():
        path = tmp_root / name
        if not path.is_file():
            raise ValueError(f"Bundle missing expected file: {name}")
        actual = _sha256_file(path)
        if actual != expected:
            raise ValueError(f"Checksum mismatch for {name}")


def import_profile_bundle(
    bundle_path: Path,
    *,
    profile: Optional[str] = None,
    md_path: Optional[Path] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Imports a .battery-bundle zip into a local profile directory."""
    bundle_path = Path(bundle_path)
    if not bundle_path.is_file():
        raise FileNotFoundError(f"Bundle not found: {bundle_path}")

    with tempfile.TemporaryDirectory(prefix="battery-import-") as tmp_dir:
        tmp_root = Path(tmp_dir)
        with zipfile.ZipFile(bundle_path, "r") as archive:
            manifest = _read_manifest_from_zip(archive)
            archive.extractall(tmp_root)

        _verify_bundle_contents(tmp_root, manifest)

        target_profile = profile or str(manifest.get("profile") or "default")
        db_dest = get_profile_db_path(target_profile)
        md_dest = md_path or get_profile_md_path(target_profile)

        if db_dest.exists() and not force:
            raise FileExistsError(
                f"Profile '{target_profile}' already exists at {db_dest}. Use --force to overwrite."
            )

        db_dest.parent.mkdir(parents=True, exist_ok=True)
        if db_dest.exists():
            backup_path = db_dest.with_suffix(db_dest.suffix + ".bak")
            shutil.copy2(db_dest, backup_path)

        shutil.copy2(tmp_root / "battery.db", db_dest)

        imported_md: Optional[str] = None
        bundle_md = tmp_root / "BATTERY.md"
        if bundle_md.is_file():
            md_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bundle_md, md_dest)
            imported_md = str(md_dest)

        conn = get_connection(db_dest)
        try:
            migrate_db(conn)
            conn.commit()
            schema_version = get_schema_version(conn)
        finally:
            conn.close()

    return {
        "profile": target_profile,
        "db_path": str(db_dest),
        "md_path": imported_md,
        "schema_version": schema_version,
        "source_profile": manifest.get("profile"),
        "exported_at": manifest.get("exported_at"),
    }


def inspect_bundle(bundle_path: Path) -> Dict[str, Any]:
    """Returns manifest metadata without importing."""
    with zipfile.ZipFile(bundle_path, "r") as archive:
        return _read_manifest_from_zip(archive)
