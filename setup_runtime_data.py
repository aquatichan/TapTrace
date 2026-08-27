"""Install TapTrace runtime data from a verified release and official utilities."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ASSET_URL = "https://github.com/aquatichan/TapTrace/releases/download/v0.1.0-data/taptrace-national-runtime-data-v1.tar.gz"
ASSET_SHA256 = "c8e81eadf556e6b01026e79b6cd70c81aa197502fa9ed8b1dbe8239ba454ce8e"
CORE = [
    ROOT / "outputs/backend/sdwis_system_registry.sqlite",
    ROOT / "outputs/national_contaminants/taptrace_ucmr5.sqlite",
    ROOT / "outputs/national_ccr/taptrace_ccr.sqlite",
    ROOT / "outputs/national_ccr_coverage/ccr_coverage_queue.sqlite",
    ROOT / "work/data/raw/national_city_audit/SDWIS_service_line_inventory_USA_2026Q1.csv",
]
PROPERTY = [
    ROOT / "work/data/raw/houston_lcrr_inventory/houston_lcrr_inventory_raw.csv",
    ROOT / "work/data/raw/dc_water_inventory/dc_water_inventory_raw.csv",
]


def download(url: str, destination: Path) -> str:
    digest = hashlib.sha256()
    request = urllib.request.Request(url, headers={"User-Agent": "TapTrace-Data-Installer/1.0"})
    with urllib.request.urlopen(request, timeout=180) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
            digest.update(chunk)
    return digest.hexdigest()


def safe_extract(archive: Path) -> None:
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            target = (ROOT / member.name).resolve()
            if ROOT.resolve() not in target.parents and target != ROOT.resolve():
                raise RuntimeError(f"Unsafe archive member: {member.name}")
        bundle.extractall(ROOT, filter="data")


def validate() -> dict:
    missing = [str(path.relative_to(ROOT)) for path in CORE + PROPERTY if not path.exists()]
    if missing:
        raise RuntimeError("Missing runtime assets: " + ", ".join(missing))
    integrity = {}
    for path in [item for item in CORE if item.suffix == ".sqlite"]:
        with sqlite3.connect(path) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {path}")
        integrity[str(path.relative_to(ROOT))] = result
    return {
        "status": "ready",
        "core_assets": len(CORE),
        "property_inventories": len(PROPERTY),
        "sqlite_integrity": integrity,
        "property_data_policy": "Fetched directly from official Houston and DC Water public endpoints; not republished by TapTrace.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Replace existing downloaded assets")
    args = parser.parse_args()
    if args.force or not all(path.exists() for path in CORE):
        with tempfile.TemporaryDirectory(prefix="taptrace-data-") as directory:
            archive = Path(directory) / "runtime-data.tar.gz"
            actual = download(ASSET_URL, archive)
            if actual != ASSET_SHA256:
                raise RuntimeError(f"Runtime archive checksum mismatch: {actual}")
            safe_extract(archive)
    downloads = [
        (PROPERTY[0], ROOT / "work/day1/download_houston_inventory.py"),
        (PROPERTY[1], ROOT / "work/day1/download_dc_verified_labels.py"),
    ]
    for destination, script in downloads:
        if args.force or not destination.exists():
            subprocess.run([sys.executable, str(script)], cwd=ROOT, check=True)
    print(json.dumps(validate(), indent=2))


if __name__ == "__main__":
    main()
