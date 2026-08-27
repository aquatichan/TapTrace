"""Run a transparent, restartable live benchmark of the national resolver."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work/national_profile"))
from resolve_national_address import geocode, water_system_boundaries, geographic_system_candidates, echo_system  # noqa: E402


DEFAULT_CASES = ROOT / "work/backend/nationwide_benchmark_addresses.csv"
DEFAULT_OUT = ROOT / "outputs/backend/nationwide_benchmark"


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))], 3)


def run_case(case: dict) -> dict:
    started = time.monotonic()
    result = {**case, "geocode_status": None, "resolution_status": None, "pwsid": None,
              "provider_name": None, "boundary_confidence": None, "federal_record": False,
              "complete_core_profile": False, "error_class": None, "error_detail": None}
    try:
        geo = geocode(case["address"])
        result["geocode_status"] = geo["status"]
        if geo["status"] != "matched":
            result["resolution_status"] = "address_not_geocoded" if geo["status"] == "not_found" else "address_confirmation_required"
            return result
        match = geo["matches"][0]
        result["matched_address"] = match["matched_address"]
        boundaries = water_system_boundaries(match["longitude"], match["latitude"])
        result["boundary_count"] = len(boundaries)
        if not boundaries:
            candidates = geographic_system_candidates(match)
            if candidates:
                result["resolution_status"] = "water_system_confirmation_required"
                result["candidate_pwsids"] = ";".join(row["pwsid"] for row in candidates)
                result["fallback_method"] = "sdwis_geographic_fallback"
                result["candidate_count"] = len(candidates)
            else:
                result["resolution_status"] = "no_mapped_public_water_system"
            return result
        if len(boundaries) > 1:
            result["resolution_status"] = "water_system_confirmation_required"
            result["candidate_pwsids"] = ";".join(row["pwsid"] or "" for row in boundaries)
            return result
        boundary = boundaries[0]
        result.update({"resolution_status": "single_water_system_candidate", "pwsid": boundary["pwsid"],
                       "provider_name": boundary["name"], "boundary_confidence": boundary["boundary_confidence"]})
        federal = echo_system(boundary["pwsid"])
        result["federal_record"] = bool(federal)
        result["complete_core_profile"] = bool(federal)
        if not federal:
            result["error_class"] = "federal_record_not_returned"
    except Exception as exc:
        result["resolution_status"] = "upstream_error"
        result["error_class"] = type(exc).__name__
        result["error_detail"] = str(exc)[:300]
    finally:
        result["latency_seconds"] = round(time.monotonic() - started, 3)
    return result


def summarize(rows: list[dict]) -> dict:
    total = len(rows)
    count = lambda predicate: sum(1 for row in rows if predicate(row))
    latencies = [float(row["latency_seconds"]) for row in rows]
    return {
        "benchmark_version": "1.0.0",
        "case_count": total,
        "geographies": sorted({row["state"] for row in rows}),
        "sampling_warning": (
            "Equal-per-state OpenAddresses sample; nationally broad but not population-weighted or a complete hard-cohort benchmark."
            if any(str(row.get("source", "")).startswith("OpenAddresses") for row in rows)
            else "One civic address per state/DC tests geographic reach, not 99% household coverage."
        ),
        "rates": {
            "address_geocoded": round(count(lambda r: r["geocode_status"] == "matched") / total, 4),
            "single_provider_resolved": round(count(lambda r: r["resolution_status"] == "single_water_system_candidate") / total, 4),
            "user_confirmation_required": round(count(lambda r: r["resolution_status"] in {"address_confirmation_required", "water_system_confirmation_required"}) / total, 4),
            "no_mapped_system": round(count(lambda r: r["resolution_status"] == "no_mapped_public_water_system") / total, 4),
            "upstream_error": round(count(lambda r: r["resolution_status"] == "upstream_error") / total, 4),
            "complete_core_profile": round(count(lambda r: r["complete_core_profile"]) / total, 4),
        },
        "resolution_counts": dict(Counter(row["resolution_status"] for row in rows)),
        "error_counts": dict(Counter(row["error_class"] for row in rows if row["error_class"])),
        "latency_seconds": {"median": round(statistics.median(latencies), 3), "p95": percentile(latencies, .95), "maximum": max(latencies)},
        "claim_gate": {
            "can_claim_99_percent": False,
            "reason": "The claim requires a population-representative sample plus minimum quotas for every hard cohort; this dataset does not satisfy both conditions."
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    with args.cases.open(newline="", encoding="utf-8") as handle:
        cases = list(csv.DictReader(handle))
    if args.limit:
        cases = cases[:args.limit]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = args.output_dir / "results.jsonl"
    completed = {}
    if checkpoint.exists():
        for line in checkpoint.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            # Upstream failures are retryable execution outcomes, not address
            # outcomes, and must never become permanent benchmark results.
            if row.get("resolution_status") != "upstream_error":
                completed[row["case_id"]] = row
    pending = [case for case in cases if case["case_id"] not in completed]
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {executor.submit(run_case, case): case for case in pending}
        for future in as_completed(futures):
            case = futures[future]
            row = future.result()
            with checkpoint.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, separators=(",", ":")) + "\n")
            completed[case["case_id"]] = row
            print(f"{case['case_id']}: {row['resolution_status']}", flush=True)
    rows = [completed[case["case_id"]] for case in cases]
    fields = sorted({key for row in rows for key in row})
    with (args.output_dir / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    summary = summarize(rows)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
