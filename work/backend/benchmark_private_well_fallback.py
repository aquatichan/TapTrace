"""Measure EPA private-well context coverage on locked no-provider cases."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work/national_profile"))
from resolve_national_address import private_well_context  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("private_results_jsonl", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    latest = {}
    for line in args.private_results_jsonl.read_text(encoding="utf-8").splitlines():
        row = json.loads(line); latest[row["case_id"]] = row
    cases = [row for row in latest.values() if row["resolution_status"] == "no_mapped_public_water_system"]
    with ThreadPoolExecutor(max_workers=8) as pool:
        contexts = list(pool.map(lambda row: private_well_context(float(row["longitude"]), float(row["latitude"])), cases))
    rows = []
    for case, context in zip(cases, contexts):
        rows.append({"case_id": case["case_id"], "state": case["state"], "context_available": bool(context),
                     "likelihood_band": (context or {}).get("likelihood_band"),
                     "estimated_well_use_percent_2010": (context or {}).get("estimated_well_use_percent_2010")})
    available = sum(row["context_available"] for row in rows)
    summary = {
        "case_count": len(rows), "private_well_context_available": available,
        "coverage_rate": round(available / len(rows), 4) if rows else None,
        "likelihood_bands": dict(Counter(row["likelihood_band"] for row in rows if row["likelihood_band"])),
        "interpretation": "Area-level 2010 EPA estimates; never property-level well confirmation.",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "redacted_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
