"""Build the local federal-system registry from EPA's quarterly SDWIS archive."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sqlite3
import time
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


SOURCE_NAMES = {"GW": "Ground water", "SW": "Surface water", "GU": "Ground water under influence"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    systems = {}
    with zipfile.ZipFile(args.archive) as bundle:
        with bundle.open("SDWA_PUB_WATER_SYSTEMS.csv") as raw:
            for row in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")):
                pwsid = row["PWSID"]
                systems[pwsid] = {
                    "pwsid": pwsid, "name": row["PWS_NAME"], "state": row["STATE_CODE"],
                    "type": row["PWS_TYPE_CODE"], "activity": row["PWS_ACTIVITY_CODE"],
                    "primary_source": SOURCE_NAMES.get(row["PRIMARY_SOURCE_CODE"], row["PRIMARY_SOURCE_CODE"]),
                    "population_served": int(row["POPULATION_SERVED_COUNT"] or 0),
                    "owner": row["OWNER_TYPE_CODE"], "serious_violator": None,
                    "current_violation_flag": False, "quarters_with_violation_last_3_years": 0,
                    "rules_violated_last_3_years": 0, "violation_categories": None,
                    "contaminants_or_rules_in_violation_last_3_years": None,
                    "contaminants_or_rules_in_current_violation": None,
                    "last_site_visit": None, "detailed_facility_report": None,
                    "evidence_level": "official_federal_quarterly_registry",
                    "freshness_note": f"EPA SDWIS quarterly snapshot {row['SUBMISSIONYEARQUARTER']}.",
                    "submission_year_quarter": row["SUBMISSIONYEARQUARTER"], "cache_status": "local_registry",
                }
        categories, rules, quarters, current_contaminants = defaultdict(set), defaultdict(set), defaultdict(set), defaultdict(set)
        cutoff = datetime.utcnow() - timedelta(days=3 * 365 + 90)
        with bundle.open("SDWA_VIOLATIONS_ENFORCEMENT.csv") as raw:
            for index, row in enumerate(csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")), 1):
                pwsid = row["PWSID"]
                if pwsid not in systems:
                    continue
                end = row["NON_COMPL_PER_END_DATE"] or row["COMPL_PER_END_DATE"]
                try:
                    recent = datetime.strptime(end, "%m/%d/%Y") >= cutoff
                except ValueError:
                    recent = False
                if recent:
                    if row["RULE_CODE"]: rules[pwsid].add(row["RULE_CODE"])
                    if row["VIOLATION_CATEGORY_CODE"]: categories[pwsid].add(row["VIOLATION_CATEGORY_CODE"])
                    quarters[pwsid].add(row["SUBMISSIONYEARQUARTER"])
                if row["VIOLATION_STATUS"].lower() not in {"resolved", "archived"}:
                    systems[pwsid]["current_violation_flag"] = True
                    if row["CONTAMINANT_CODE"]: current_contaminants[pwsid].add(row["CONTAMINANT_CODE"])
                if index % 1_000_000 == 0:
                    print(f"processed {index:,} violation/enforcement rows", flush=True)
    fetched = int(time.time())
    with sqlite3.connect(args.output) as connection:
        connection.execute("DROP TABLE IF EXISTS systems")
        connection.execute("CREATE TABLE systems (pwsid TEXT PRIMARY KEY,fetched_at INTEGER NOT NULL,payload TEXT NOT NULL)")
        payloads = []
        for pwsid, system in systems.items():
            system["quarters_with_violation_last_3_years"] = len(quarters[pwsid])
            system["rules_violated_last_3_years"] = len(rules[pwsid])
            system["violation_categories"] = ", ".join(sorted(categories[pwsid])) or None
            system["contaminants_or_rules_in_current_violation"] = ", ".join(sorted(current_contaminants[pwsid])) or None
            payloads.append((pwsid, fetched, json.dumps(system, separators=(",", ":"))))
        connection.executemany("INSERT INTO systems VALUES (?,?,?)", payloads)
        connection.commit()
    print(json.dumps({"status": "PASS", "systems": len(systems), "source": str(args.archive)}, indent=2))


if __name__ == "__main__":
    main()
