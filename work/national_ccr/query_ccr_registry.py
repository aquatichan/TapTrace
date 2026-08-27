"""Return the latest validated CCR profile for a PWSID."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "outputs/national_ccr/taptrace_ccr.sqlite"


def query(pwsid: str) -> dict:
    connection = sqlite3.connect(DB)
    connection.row_factory = sqlite3.Row
    report_row = connection.execute(
        "SELECT * FROM reports WHERE pwsid=? AND validation_status='validated' ORDER BY report_year DESC LIMIT 1",
        (pwsid,),
    ).fetchone()
    if not report_row:
        connection.close()
        return {
            "pwsid": pwsid,
            "has_validated_ccr": False,
            "measurements": [],
            "reason": "No source-page-validated CCR has been admitted for this PWSID.",
        }
    report = dict(report_row)
    rows = [dict(row) for row in connection.execute(
        "SELECT * FROM measurements WHERE pwsid=? AND report_year=? ORDER BY contaminant,sample_scope",
        (pwsid, report["report_year"]),
    )]
    connection.close()
    for row in rows:
        row["home_specific"] = False
        if row["benchmark_value"] is not None and row["comparison_value"] is not None:
            row["benchmark_comparison"] = (
                "at_or_below_reported_benchmark"
                if row["comparison_value"] <= row["benchmark_value"]
                else "above_reported_benchmark"
            )
        else:
            row["benchmark_comparison"] = "not_applicable"
    return {
        "pwsid": pwsid,
        "has_validated_ccr": True,
        "report": report,
        "measurements": rows,
        "scope_warning": (
            "CCR measurements summarize public-water-system monitoring and do not represent a test at this residence. "
            "Range maxima and individual samples can exceed a benchmark without constituting a system violation when "
            "the applicable compliance statistic is a running average or percentile."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pwsid")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = query(args.pwsid.strip().upper())
    output = args.output or ROOT / "outputs/national_ccr" / f"{result['pwsid']}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
