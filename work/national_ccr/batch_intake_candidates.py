"""Run PDF intake for reviewed official source candidates; never auto-admit."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = ROOT / "work/national_ccr/ccr_source_candidates.csv"
INTAKE = ROOT / "work/national_ccr/intake_report.py"
RUNTIME_PYTHON = Path("/Users/miheerparasnis/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    with CANDIDATES.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row["status"] == "ready_for_intake" and row["format"] == "pdf"]
    results = []
    for row in rows[:args.limit]:
        completed = subprocess.run(
            [str(RUNTIME_PYTHON if RUNTIME_PYTHON.exists() else Path(sys.executable)),
             str(INTAKE), row["pwsid"], row["report_year"], row["official_url"]],
            capture_output=True, text=True,
        )
        results.append({
            "pwsid": row["pwsid"], "status": "review_created" if completed.returncode == 0 else "intake_failed",
            "detail": (completed.stdout or completed.stderr).strip().splitlines()[-1],
        })
    print(json.dumps({"automatic_admission": False, "results": results}, indent=2))


if __name__ == "__main__":
    main()
