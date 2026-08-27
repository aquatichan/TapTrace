"""Check validated CCR source freshness without silently changing admitted data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import ssl
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "work/national_ccr/ccr_reports.csv"
OUT = ROOT / "outputs/national_ccr/source_freshness.json"


def tls_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pwsid", action="append", help="Limit checks to one or more PWSIDs")
    args = parser.parse_args()
    selected = {item.upper() for item in (args.pwsid or [])}
    with REPORTS.open(newline="", encoding="utf-8") as handle:
        reports = [row for row in csv.DictReader(handle) if not selected or row["pwsid"] in selected]
    checks = []
    for report in reports:
        extension = ".html" if report["document_format"] == "html" else ".pdf"
        local = ROOT / "work/data/raw/ccr_2025" / f"{report['pwsid']}_{report['report_year']}{extension}"
        local_hash = hashlib.sha256(local.read_bytes()).hexdigest()
        request = urllib.request.Request(report["report_url"], headers={
            "User-Agent": "TapTrace-CCR-Freshness/1.0", "Accept": "text/html,application/pdf"
        })
        try:
            with urllib.request.urlopen(request, timeout=90, context=tls_context()) as response:
                body = response.read(30_000_000)
            remote_hash = hashlib.sha256(body).hexdigest()
            status = "unchanged" if remote_hash == local_hash else "changed_review_required"
            error = None
        except Exception as exc:
            remote_hash, status, error = None, "check_failed", type(exc).__name__
        checks.append({
            "pwsid": report["pwsid"], "report_year": int(report["report_year"]),
            "url": report["report_url"], "local_sha256": local_hash,
            "remote_sha256": remote_hash, "status": status, "error_type": error,
            "automatic_admission": False,
        })
    result = {
        "checked_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checks": checks,
        "changed_review_required": sum(row["status"] == "changed_review_required" for row in checks),
        "policy": "Changed reports require source-table review; remote content never overwrites validated data automatically.",
    }
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
