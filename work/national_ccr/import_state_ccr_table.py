"""Stage a state/primacy tabular CCR export using an explicit column map."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import time
from pathlib import Path


PWSID = re.compile(r"^(?:[A-Z]{2}\d{7}|UTAH\d{5})$")
REQUIRED = ("pwsid", "report_year", "contaminant", "unit", "result", "source_url")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("column_map_json", type=Path, help="JSON mapping canonical names to source column names")
    parser.add_argument("--output-db", type=Path, required=True)
    args = parser.parse_args()
    mapping = json.loads(args.column_map_json.read_text(encoding="utf-8"))
    missing = [key for key in REQUIRED if key not in mapping]
    if missing:
        raise ValueError(f"column map missing: {', '.join(missing)}")
    connection = sqlite3.connect(args.output_db)
    connection.execute("""CREATE TABLE IF NOT EXISTS staged_state_rows (
        pwsid TEXT, report_year INTEGER, contaminant TEXT, unit TEXT, result_text TEXT,
        statistic_type TEXT, benchmark_type TEXT, benchmark_value TEXT, violation TEXT,
        source_url TEXT, source_row INTEGER, adapter_status TEXT, imported_at_utc TEXT,
        UNIQUE(pwsid,report_year,contaminant,statistic_type,source_row)
    )""")
    accepted = rejected = 0
    with args.input_csv.open(newline="", encoding="utf-8-sig") as handle:
        for source_row, row in enumerate(csv.DictReader(handle), 2):
            value = lambda key: (row.get(mapping.get(key, "")) or "").strip()
            pwsid = value("pwsid").upper()
            url = value("source_url")
            try:
                year = int(value("report_year"))
            except ValueError:
                year = 0
            if not PWSID.fullmatch(pwsid) or not (2000 <= year <= 2100) or not url.startswith("https://") or not value("contaminant"):
                rejected += 1; continue
            connection.execute("INSERT OR IGNORE INTO staged_state_rows VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                pwsid, year, value("contaminant"), value("unit"), value("result"),
                value("statistic_type") or None, value("benchmark_type") or None,
                value("benchmark_value") or None, value("violation") or None, url,
                source_row, "review_required", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            ))
            accepted += 1
    connection.commit(); connection.close()
    print(json.dumps({"status": "PASS", "staged": accepted, "rejected": rejected, "automatic_admission": False}, indent=2))


if __name__ == "__main__":
    main()
