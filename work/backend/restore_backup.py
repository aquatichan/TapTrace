"""Validate and atomically restore one writable TapTrace state database."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path


ALLOWED = {"water_profile_cache.sqlite", "echo_system_cache.sqlite", "ccr_submissions.sqlite"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("database", choices=sorted(ALLOWED))
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if not args.confirm:
        raise SystemExit("Refusing to restore without --confirm")
    manifest = json.loads((args.snapshot / "manifest.json").read_text(encoding="utf-8"))
    record = next((row for row in manifest["databases"] if row["file"] == args.database), None)
    if not record:
        raise SystemExit("Database is not present in the snapshot manifest")
    source = args.snapshot / args.database
    if sha256(source) != record["sha256"]:
        raise SystemExit("Backup checksum mismatch")
    with sqlite3.connect(source) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise SystemExit("Backup integrity check failed")
    state_dir = Path(os.getenv("TAPTRACE_STATE_DIR", "/data"))
    state_dir.mkdir(parents=True, exist_ok=True)
    destination = state_dir / args.database
    with tempfile.NamedTemporaryFile(dir=state_dir, prefix=f".{args.database}.", delete=False) as handle:
        temporary = Path(handle.name)
    shutil.copy2(source, temporary)
    temporary.replace(destination)
    print(json.dumps({"status": "restored", "database": args.database, "destination": str(destination)}))


if __name__ == "__main__":
    main()
