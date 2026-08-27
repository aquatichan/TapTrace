"""Create integrity-checked SQLite backups and optionally upload them to S3."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASES = [
    ROOT / "outputs/backend/sdwis_system_registry.sqlite",
    ROOT / "outputs/national_ccr/taptrace_ccr.sqlite",
    ROOT / "outputs/national_contaminants/taptrace_ucmr5.sqlite",
]


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def backup_database(source: Path, destination: Path) -> dict:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
    with sqlite3.connect(destination) as check:
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise RuntimeError(f"Integrity check failed for {source.name}: {integrity}")
    return {"source": str(source), "file": destination.name, "bytes": destination.stat().st_size,
            "sha256": digest(destination), "integrity_check": integrity}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path(os.getenv("TAPTRACE_BACKUP_DIR", "/backups")))
    parser.add_argument("--retention-days", type=int, default=int(os.getenv("TAPTRACE_BACKUP_RETENTION_DAYS", "14")))
    args = parser.parse_args()
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    snapshot = args.output_dir / timestamp
    records = []
    state_dir = Path(os.getenv("TAPTRACE_STATE_DIR", ROOT / "outputs/backend"))
    candidates = [state_dir / "water_profile_cache.sqlite", state_dir / "echo_system_cache.sqlite", state_dir / "ccr_submissions.sqlite"]
    if os.getenv("TAPTRACE_BACKUP_INCLUDE_REGISTRIES", "false").lower() == "true":
        candidates = DEFAULT_DATABASES + candidates
    seen = set()
    for source in candidates:
        resolved = source.resolve()
        if resolved in seen or not source.exists():
            continue
        seen.add(resolved)
        records.append(backup_database(source, snapshot / source.name))
    if not records:
        shutil.rmtree(snapshot)
        raise RuntimeError("No TapTrace databases were available to back up")
    manifest = {"created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "databases": records}
    (snapshot / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    archive = Path(shutil.make_archive(str(snapshot), "gztar", snapshot))
    manifest["archive"] = {"file": archive.name, "bytes": archive.stat().st_size, "sha256": digest(archive)}
    (snapshot / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    bucket = os.getenv("TAPTRACE_BACKUP_S3_BUCKET")
    if bucket:
        import boto3
        key = f"{os.getenv('TAPTRACE_BACKUP_S3_PREFIX', 'taptrace')}/{archive.name}"
        boto3.client("s3").upload_file(str(archive), bucket, key)
        manifest["offsite"] = {"bucket": bucket, "key": key}
    (snapshot / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (args.output_dir / "latest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    cutoff = time.time() - args.retention_days * 86400
    for path in args.output_dir.iterdir():
        if path.stat().st_mtime < cutoff:
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
