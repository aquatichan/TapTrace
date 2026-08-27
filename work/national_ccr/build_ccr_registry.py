"""Build the validated Consumer Confidence Report registry."""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "work/national_ccr/ccr_reports.csv"
MEASUREMENTS = ROOT / "work/national_ccr/ccr_measurements.csv"
RAW = ROOT / "work/data/raw/ccr_2025"
OUT = ROOT / "outputs/national_ccr"
DB = OUT / "taptrace_ccr.sqlite"


def nullable_float(value: str):
    return float(value) if value.strip() else None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    connection = sqlite3.connect(DB)
    connection.executescript("""
        CREATE TABLE reports (
            pwsid TEXT NOT NULL,
            system_name TEXT NOT NULL,
            report_year INTEGER NOT NULL,
            data_year INTEGER NOT NULL,
            report_url TEXT NOT NULL,
            landing_page_url TEXT NOT NULL,
            publisher TEXT NOT NULL,
            document_format TEXT NOT NULL,
            extraction_status TEXT NOT NULL,
            validation_status TEXT NOT NULL,
            notes TEXT,
            local_file TEXT,
            local_sha256 TEXT,
            PRIMARY KEY (pwsid, report_year)
        );
        CREATE TABLE measurements (
            measurement_id INTEGER PRIMARY KEY,
            pwsid TEXT NOT NULL,
            report_year INTEGER NOT NULL,
            data_year INTEGER NOT NULL,
            contaminant TEXT NOT NULL,
            unit TEXT NOT NULL,
            sample_scope TEXT NOT NULL,
            statistic_type TEXT NOT NULL,
            result_text TEXT NOT NULL,
            minimum REAL,
            average REAL,
            maximum REAL,
            percentile_90 REAL,
            comparison_value REAL,
            benchmark_type TEXT,
            benchmark_value REAL,
            violation TEXT NOT NULL,
            source_page INTEGER NOT NULL,
            notes TEXT,
            evidence_level TEXT NOT NULL DEFAULT 'official_ccr_system_measurement',
            home_specific INTEGER NOT NULL DEFAULT 0 CHECK(home_specific=0),
            FOREIGN KEY (pwsid, report_year) REFERENCES reports(pwsid, report_year)
        );
    """)

    with REPORTS.open(newline="", encoding="utf-8") as handle:
        report_rows = list(csv.DictReader(handle))
    for row in report_rows:
        extension = ".html" if row["document_format"] == "html" else ".pdf"
        local = RAW / f"{row['pwsid']}_{row['report_year']}{extension}"
        if not local.exists():
            raise FileNotFoundError(local)
        digest = hashlib.sha256(local.read_bytes()).hexdigest()
        connection.execute(
            "INSERT INTO reports VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                row["pwsid"], row["system_name"], int(row["report_year"]), int(row["data_year"]),
                row["report_url"], row["landing_page_url"], row["publisher"], row["document_format"],
                row["extraction_status"], row["validation_status"], row["notes"],
                str(local.relative_to(ROOT)), digest,
            ),
        )

    with MEASUREMENTS.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        connection.execute("""INSERT INTO measurements (
            pwsid,report_year,data_year,contaminant,unit,sample_scope,statistic_type,
            result_text,minimum,average,maximum,percentile_90,comparison_value,
            benchmark_type,benchmark_value,violation,source_page,notes
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            row["pwsid"], int(row["report_year"]), int(row["data_year"]), row["contaminant"],
            row["unit"], row["sample_scope"], row["statistic_type"], row["result_text"],
            nullable_float(row["minimum"]), nullable_float(row["average"]), nullable_float(row["maximum"]),
            nullable_float(row["percentile_90"]), nullable_float(row["comparison_value"]),
            row["benchmark_type"] or None, nullable_float(row["benchmark_value"]),
            row["violation"], int(row["source_page"]), row["notes"],
        ))

    connection.executescript("""
        CREATE UNIQUE INDEX idx_ccr_measurement_key ON measurements(
            pwsid,report_year,data_year,contaminant,sample_scope,statistic_type
        );
        CREATE INDEX idx_ccr_pwsid ON measurements(pwsid, report_year);
    """)
    metadata = {
        "build_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "validated_reports": len(report_rows),
        "normalized_measurements": len(rows),
        "systems": sorted({row["pwsid"] for row in report_rows}),
        "coverage_policy": "Only source-page-validated report measurements are admitted.",
    }
    connection.commit()
    connection.close()
    (OUT / "build_metadata.json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
