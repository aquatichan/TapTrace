"""Build an indexed national UCMR 5 contaminant registry from EPA text files.

The ZIP is read as a stream; raw qualifiers and sample context are preserved.
No non-detect is converted to zero, and no result is treated as home-specific.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "work/data/raw/ucmr5/ucmr5-occurrence-data-by-state.zip"
OUT = ROOT / "outputs/national_contaminants"
DB = OUT / "taptrace_ucmr5.sqlite"
RESULT_FILES = ["UCMR5_All_Tribes_AK_LA.txt", "UCMR5_All_MA_WY.txt"]


def nullable_float(value: str):
    value = value.strip()
    return float(value) if value else None


def iso_date(value: str):
    value = value.strip()
    return datetime.strptime(value, "%m/%d/%Y").date().isoformat() if value else None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    connection = sqlite3.connect(DB)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.executescript("""
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE results (
            result_id INTEGER PRIMARY KEY,
            pwsid TEXT NOT NULL,
            pws_name TEXT NOT NULL,
            size_category TEXT,
            facility_id TEXT,
            facility_name TEXT,
            facility_water_type TEXT,
            sample_point_id TEXT,
            sample_point_name TEXT,
            sample_point_type TEXT,
            associated_facility_id TEXT,
            associated_sample_point_id TEXT,
            collection_date TEXT,
            sample_id TEXT,
            contaminant TEXT NOT NULL,
            mrl REAL,
            units TEXT,
            method_id TEXT,
            result_sign TEXT NOT NULL,
            result_value REAL,
            is_detect INTEGER NOT NULL CHECK (is_detect IN (0,1)),
            sample_event_code TEXT,
            monitoring_requirement TEXT,
            region TEXT,
            state TEXT,
            ucmr1_sample_type TEXT,
            evidence_level TEXT NOT NULL DEFAULT 'official_system_analytical_result',
            home_specific INTEGER NOT NULL DEFAULT 0 CHECK (home_specific = 0)
        );
        CREATE TABLE pws_zip_codes (
            pwsid TEXT NOT NULL,
            zip_code TEXT NOT NULL,
            PRIMARY KEY (pwsid, zip_code)
        );
    """)

    insert = """INSERT INTO results (
        pwsid,pws_name,size_category,facility_id,facility_name,facility_water_type,
        sample_point_id,sample_point_name,sample_point_type,associated_facility_id,
        associated_sample_point_id,collection_date,sample_id,contaminant,mrl,units,
        method_id,result_sign,result_value,is_detect,sample_event_code,
        monitoring_requirement,region,state,ucmr1_sample_type
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""

    total = detects = non_detects = 0
    started = time.time()
    with ZipFile(SOURCE) as archive:
        for filename in RESULT_FILES:
            with archive.open(filename) as raw:
                reader = csv.DictReader(io.TextIOWrapper(raw, encoding="cp1252", newline=""), delimiter="\t")
                batch = []
                for row in reader:
                    sign = row["AnalyticalResultsSign"].strip()
                    value = nullable_float(row["AnalyticalResultValue"])
                    is_detect = int(sign == "=" and value is not None)
                    batch.append((
                        row["PWSID"].strip(), row["PWSName"].strip(), row["Size"].strip(),
                        row["FacilityID"].strip(), row["FacilityName"].strip(), row["FacilityWaterType"].strip(),
                        row["SamplePointID"].strip(), row["SamplePointName"].strip(), row["SamplePointType"].strip(),
                        row["AssociatedFacilityID"].strip(), row["AssociatedSamplePointID"].strip(),
                        iso_date(row["CollectionDate"]), row["SampleID"].strip(), row["Contaminant"].strip(),
                        nullable_float(row["MRL"]), row["Units"].strip(), row["MethodID"].strip(),
                        sign, value, is_detect, row["SampleEventCode"].strip(),
                        row["MonitoringRequirement"].strip(), row["Region"].strip(),
                        row["State"].strip(), row["UCMR1SampleType"].strip(),
                    ))
                    total += 1
                    detects += is_detect
                    non_detects += 1 - is_detect
                    if len(batch) == 20_000:
                        connection.executemany(insert, batch)
                        connection.commit()
                        batch.clear()
                        if total % 200_000 == 0:
                            print(f"loaded {total:,} results", flush=True)
                if batch:
                    connection.executemany(insert, batch)
                    connection.commit()

        with archive.open("UCMR5_ZIPCodes.txt") as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="cp1252", newline=""), delimiter="\t")
            connection.executemany(
                "INSERT OR IGNORE INTO pws_zip_codes (pwsid, zip_code) VALUES (?, ?)",
                ((row["PWSID"].strip(), row["ZIPCODE"].strip()) for row in reader),
            )

    connection.executescript("""
        CREATE INDEX idx_results_pwsid ON results(pwsid);
        CREATE INDEX idx_results_pws_contaminant ON results(pwsid, contaminant);
        CREATE INDEX idx_results_detects ON results(pwsid, is_detect, contaminant);
        CREATE INDEX idx_results_date ON results(collection_date);
        CREATE VIEW pws_contaminant_summary AS
        SELECT
            pwsid,
            MAX(pws_name) AS pws_name,
            contaminant,
            MAX(units) AS units,
            COUNT(*) AS sample_result_count,
            SUM(is_detect) AS detect_count,
            COUNT(*) - SUM(is_detect) AS below_mrl_count,
            MIN(CASE WHEN is_detect = 1 THEN result_value END) AS minimum_detect,
            AVG(CASE WHEN is_detect = 1 THEN result_value END) AS average_detect,
            MAX(CASE WHEN is_detect = 1 THEN result_value END) AS maximum_detect,
            MIN(collection_date) AS first_sample_date,
            MAX(collection_date) AS latest_sample_date,
            COUNT(DISTINCT facility_id || '|' || sample_point_id) AS sample_points
        FROM results
        GROUP BY pwsid, contaminant;
    """)

    sha256 = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    metadata = {
        "dataset": "EPA UCMR 5 occurrence data by state",
        "source_url": "https://www.epa.gov/system/files/other-files/2023-08/ucmr5-occurrence-data-by-state.zip",
        "source_sha256": sha256,
        "build_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "result_rows": total,
        "detect_rows": detects,
        "below_mrl_rows": non_detects,
        "elapsed_seconds": round(time.time() - started, 2),
        "interpretation": "UCMR results are public-water-system samples, not measurements from a selected residence.",
    }
    connection.executemany("INSERT INTO metadata(key,value) VALUES (?,?)", ((k, json.dumps(v)) for k, v in metadata.items()))
    connection.commit()
    connection.close()
    (OUT / "build_metadata.json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
