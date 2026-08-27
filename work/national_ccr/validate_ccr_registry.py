"""Validate report files, normalized schema, comparisons, and national integration."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "outputs/national_ccr/taptrace_ccr.sqlite"
OUT = ROOT / "outputs/national_ccr"
connection = sqlite3.connect(DB)
connection.row_factory = sqlite3.Row

reports = [dict(row) for row in connection.execute("SELECT * FROM reports ORDER BY pwsid")]
measurements = [dict(row) for row in connection.execute("SELECT * FROM measurements ORDER BY measurement_id")]
duplicate_keys = connection.execute("""SELECT COUNT(*) FROM (
    SELECT pwsid,report_year,data_year,contaminant,sample_scope,statistic_type,COUNT(*) n
    FROM measurements GROUP BY 1,2,3,4,5,6 HAVING n>1
)""").fetchone()[0]
orphans = connection.execute("""SELECT COUNT(*) FROM measurements m LEFT JOIN reports r
    ON m.pwsid=r.pwsid AND m.report_year=r.report_year WHERE r.pwsid IS NULL""").fetchone()[0]
connection.close()

assert len(reports) >= 15
assert len(measurements) >= 149
assert duplicate_keys == 0 and orphans == 0
assert all(row["home_specific"] == 0 for row in measurements)
assert all(row["source_page"] > 0 for row in measurements)
assert all(row["validation_status"] == "validated" for row in reports)

page_counts = {}
for report in reports:
    path = ROOT / report["local_file"]
    if report["document_format"] == "html":
        pages = 1
    else:
        info = subprocess.run(["pdfinfo", str(path)], check=True, capture_output=True, text=True).stdout
        pages = int(next(line.split(":", 1)[1] for line in info.splitlines() if line.startswith("Pages:")))
    page_counts[report["pwsid"]] = pages
    used = [row["source_page"] for row in measurements if row["pwsid"] == report["pwsid"]]
    assert used and max(used) <= pages

above = [row for row in measurements if row["comparison_value"] is not None and
         row["benchmark_value"] is not None and row["comparison_value"] > row["benchmark_value"]]
assert not above

summary = {
    "status": "PASS",
    "validated_reports": len(reports),
    "normalized_measurements": len(measurements),
    "duplicate_measurement_keys": duplicate_keys,
    "orphan_measurements": orphans,
    "all_measurements_non_home_specific": True,
    "source_pages_within_documents": True,
    "page_counts": page_counts,
    "systems": {pwsid: sum(row["pwsid"] == pwsid for row in measurements) for pwsid in page_counts},
    "comparison_values_above_reported_benchmarks": len(above),
    "coverage_statement": "Validated starter cohort, not national CCR completeness.",
}
(OUT / "validation_results.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
