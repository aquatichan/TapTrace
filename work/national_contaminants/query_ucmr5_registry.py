"""Return a consumer-safe UCMR 5 system contaminant profile by PWSID."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "outputs/national_contaminants/taptrace_ucmr5.sqlite"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pwsid")
    parser.add_argument("--include-samples", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    pwsid = args.pwsid.strip().upper()

    connection = sqlite3.connect(DB)
    connection.row_factory = sqlite3.Row
    summaries = [dict(row) for row in connection.execute(
        "SELECT * FROM pws_contaminant_summary WHERE pwsid=? ORDER BY contaminant", (pwsid,)
    )]
    for row in summaries:
        row["detected_in_at_least_one_sample"] = row["detect_count"] > 0
        row["result_scope"] = "public_water_system"
        row["home_specific"] = False

    samples = []
    if args.include_samples:
        samples = [dict(row) for row in connection.execute("""
            SELECT collection_date, facility_id, facility_name, facility_water_type,
                   sample_point_id, sample_point_name, sample_point_type, sample_id,
                   contaminant, mrl, units, method_id, result_sign, result_value,
                   is_detect, sample_event_code, monitoring_requirement,
                   evidence_level, home_specific
            FROM results WHERE pwsid=?
            ORDER BY collection_date DESC, contaminant, sample_id
        """, (pwsid,))]
        for row in samples:
            row["home_specific"] = False
    zips = [row[0] for row in connection.execute(
        "SELECT zip_code FROM pws_zip_codes WHERE pwsid=? ORDER BY zip_code", (pwsid,)
    )]
    connection.close()

    result = {
        "pwsid": pwsid,
        "ucmr_cycle": 5,
        "monitoring_period": "2023-2025",
        "has_ucmr5_results": bool(summaries),
        "system_name": summaries[0]["pws_name"] if summaries else None,
        "zip_codes_reported_by_ucmr": zips,
        "contaminant_summaries": summaries,
        "samples": samples if args.include_samples else None,
        "scope_warning": (
            "These are UCMR samples associated with the public water system. They are not a test of the "
            "selected residence. A non-detect means below the UCMR minimum reporting level for that sample, not zero."
        ),
        "regulatory_warning": (
            "UCMR monitors contaminants that were unregulated under the monitoring cycle. Do not label a "
            "detection as a regulatory violation unless a separate current regulatory source establishes that."
        ),
        "source": "US EPA UCMR 5 occurrence data",
        "source_url": "https://www.epa.gov/dwucmr/occurrence-data-unregulated-contaminant-monitoring-rule",
    }
    output = args.output or ROOT / "outputs/national_contaminants" / f"{pwsid}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
