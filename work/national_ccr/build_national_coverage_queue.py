"""Build the national PWSID inventory and auditable CCR acquisition queue."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/national_ccr_coverage"
DB = OUT / "ccr_coverage_queue.sqlite"
CSV_OUT = OUT / "ccr_coverage_queue.csv.gz"
REPORTS = ROOT / "work/national_ccr/ccr_reports.csv"
SERVICE = (
    "https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/"
    "Water_System_Boundaries/FeatureServer/0/query"
)
FIELDS = "PWSID,PWS_Name,Primacy_Agency,Population_Served_Count,Service_Connections_Count"


def tls_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def get_json(params: dict) -> dict:
    url = SERVICE + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "TapTrace-CCR-Coverage/1.0"})
    with urllib.request.urlopen(request, timeout=90, context=tls_context()) as response:
        return json.load(response)


def fetch_systems() -> list[dict]:
    systems: dict[str, dict] = {}
    offset = 0
    while True:
        payload = get_json({
            "where": "PWSID IS NOT NULL",
            "outFields": FIELDS,
            "returnGeometry": "false",
            "orderByFields": "PWSID ASC",
            "resultOffset": offset,
            "resultRecordCount": 2000,
            "f": "json",
        })
        features = payload.get("features", [])
        if not features:
            break
        for feature in features:
            row = feature["attributes"]
            pwsid = (row.get("PWSID") or "").strip().upper()
            if not pwsid:
                continue
            current = systems.setdefault(pwsid, {
                "pwsid": pwsid,
                "pws_name": row.get("PWS_Name"),
                "primacy_agency": row.get("Primacy_Agency"),
                "population_served": row.get("Population_Served_Count"),
                "service_connections": row.get("Service_Connections_Count"),
                "boundary_feature_count": 0,
            })
            current["boundary_feature_count"] += 1
            for key in ("population_served", "service_connections"):
                value = row.get({"population_served": "Population_Served_Count", "service_connections": "Service_Connections_Count"}[key])
                if value is not None and (current[key] is None or value > current[key]):
                    current[key] = value
        offset += len(features)
        if not payload.get("exceededTransferLimit"):
            break
    return sorted(systems.values(), key=lambda row: row["pwsid"])


def validated_reports() -> dict[str, dict]:
    with REPORTS.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {row["pwsid"]: row for row in rows if row["validation_status"] == "validated"}


def existing_systems() -> list[dict]:
    if not DB.exists():
        raise FileNotFoundError("coverage database does not exist; run a live build first")
    connection = sqlite3.connect(DB)
    connection.row_factory = sqlite3.Row
    rows = [dict(row) for row in connection.execute(
        "SELECT pwsid,pws_name,primacy_agency,population_served,service_connections,boundary_feature_count FROM coverage_queue"
    )]
    connection.close()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reuse-existing-boundary-inventory", action="store_true",
                        help="Refresh CCR joins without re-downloading the EPA boundary inventory")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    systems = existing_systems() if args.reuse_existing_boundary_inventory else fetch_systems()
    reports = validated_reports()
    connection = sqlite3.connect(DB)
    connection.executescript("""
        DROP TABLE IF EXISTS coverage_queue;
        CREATE TABLE coverage_queue (
            pwsid TEXT PRIMARY KEY,
            pws_name TEXT,
            primacy_agency TEXT,
            population_served INTEGER,
            service_connections INTEGER,
            boundary_feature_count INTEGER NOT NULL,
            report_status TEXT NOT NULL,
            report_year INTEGER,
            report_url TEXT,
            validation_status TEXT NOT NULL,
            next_action TEXT NOT NULL,
            last_checked_utc TEXT
        );
    """)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    rows = []
    for system in systems:
        report = reports.get(system["pwsid"])
        rows.append((
            system["pwsid"], system["pws_name"], system["primacy_agency"],
            system["population_served"], system["service_connections"], system["boundary_feature_count"],
            "validated" if report else "not_discovered_or_not_validated",
            int(report["report_year"]) if report else None,
            report["report_url"] if report else None,
            "validated" if report else "pending",
            "serve_validated_profile" if report else "discover_official_ccr_url",
            now if report else None,
        ))
    connection.executemany("INSERT INTO coverage_queue VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    connection.execute("CREATE INDEX idx_coverage_priority ON coverage_queue(validation_status,population_served DESC)")
    connection.commit()
    counts = dict(connection.execute(
        "SELECT validation_status,COUNT(*) FROM coverage_queue GROUP BY validation_status"
    ).fetchall())
    population = connection.execute(
        "SELECT SUM(COALESCE(population_served,0)), SUM(CASE WHEN validation_status='validated' THEN COALESCE(population_served,0) ELSE 0 END) FROM coverage_queue"
    ).fetchone()
    connection.close()

    import gzip
    with gzip.open(CSV_OUT, "wt", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["pwsid", "pws_name", "primacy_agency", "population_served", "service_connections", "boundary_feature_count", "report_status", "report_year", "report_url", "validation_status", "next_action", "last_checked_utc"])
        writer.writerows(rows)
    summary = {
        "build_utc": now,
        "mapped_unique_pwsids": len(systems),
        "validated_ccr_pwsids": counts.get("validated", 0),
        "pending_ccr_pwsids": counts.get("pending", 0),
        "pwsid_coverage_rate": counts.get("validated", 0) / len(systems) if systems else 0,
        "mapped_population_sum_non_deduplicated": population[0],
        "population_with_validated_ccr_non_deduplicated": population[1],
        "population_coverage_rate_non_deduplicated": population[1] / population[0] if population[0] else 0,
        "important_limit": "The boundary inventory is not every US water system and population values can overlap; private wells are outside CCR coverage.",
    }
    (OUT / "coverage_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
