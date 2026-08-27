"""Privacy-safe, quota-gated benchmark for difficult US address cohorts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

from nationwide_address_benchmark import run_case


REQUIRED_STRATA = {
    "urban_residential", "rural_residential", "private_well_likely",
    "multifamily_apartment", "tribal_area", "territory",
    "recent_construction", "utility_boundary_edge",
}


def wilson(successes: int, total: int, z: float = 1.96) -> dict:
    if not total:
        return {"estimate": None, "lower_95": None, "upper_95": None}
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return {"estimate": round(p, 4), "lower_95": round(center - margin, 4), "upper_95": round(center + margin, 4)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cases", type=Path, help="Private CSV; never copied to output")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--minimum-per-stratum", type=int, default=100)
    args = parser.parse_args()
    salt = os.environ.get("TAPTRACE_BENCHMARK_SALT")
    if not salt or len(salt) < 16:
        raise ValueError("Set TAPTRACE_BENCHMARK_SALT to at least 16 characters")
    with args.cases.open(newline="", encoding="utf-8") as handle:
        cases = list(csv.DictReader(handle))
    required = {"case_id", "state", "address", "stratum", "source", "sampling_weight"}
    if not cases or required - set(cases[0]):
        raise ValueError(f"Input must contain: {', '.join(sorted(required))}")
    counts = Counter(row["stratum"] for row in cases)
    missing = REQUIRED_STRATA - set(counts)
    under = {key: counts[key] for key in REQUIRED_STRATA if counts[key] < args.minimum_per_stratum}
    if missing or under:
        raise ValueError(f"Quota gate failed; missing={sorted(missing)}, under_quota={under}")
    results = []
    for case in cases:
        live = run_case(case)
        address_hash = hashlib.sha256(f"{salt}|{case['address'].upper()}".encode()).hexdigest()
        results.append({key: value for key, value in live.items() if key not in {"address", "matched_address"}} | {
            "address_hash": address_hash,
        })
        print(f"{case['case_id']}: {live['resolution_status']}", flush=True)
    by_stratum = defaultdict(list)
    for row in results:
        by_stratum[row["stratum"]].append(row)
    strata = {}
    for name, rows in sorted(by_stratum.items()):
        complete = sum(bool(row["complete_core_profile"]) for row in rows)
        safe = sum(row["resolution_status"] != "upstream_error" for row in rows)
        strata[name] = {
            "cases": len(rows), "complete_core_profile": wilson(complete, len(rows)),
            "safe_response": wilson(safe, len(rows)),
            "resolution_counts": dict(Counter(row["resolution_status"] for row in rows)),
        }
    total_complete = sum(bool(row["complete_core_profile"]) for row in results)
    overall = wilson(total_complete, len(results))
    summary = {
        "schema_version": "1.0.0", "privacy": "Raw and matched addresses excluded; salted hashes only.",
        "case_count": len(results), "strata": strata, "unweighted_complete_core_profile": overall,
        "release_gate": {
            "passed": bool(overall["lower_95"] is not None and overall["lower_95"] >= .99
                           and all(value["complete_core_profile"]["lower_95"] >= .95 for value in strata.values())),
            "rule": "Overall 95% lower confidence bound >=99% and every stratum lower bound >=95%.",
        },
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in results for key in row})
    with (args.output_dir / "redacted_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(results)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
