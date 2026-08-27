"""Add EPA SDWIS ZIP/city/county/tribal service areas to the local registry."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sqlite3
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--registry", type=Path, required=True)
    args = parser.parse_args()
    inserted = 0
    with sqlite3.connect(args.registry) as connection:
        connection.execute("DROP TABLE IF EXISTS geographic_areas")
        connection.execute("""CREATE TABLE geographic_areas (
            pwsid TEXT NOT NULL, area_type TEXT NOT NULL, state TEXT,
            zip_code TEXT, city TEXT, county TEXT, tribal_code TEXT,
            last_reported_date TEXT,
            PRIMARY KEY(pwsid,area_type,state,zip_code,city,county,tribal_code)
        )""")
        with zipfile.ZipFile(args.archive) as bundle, bundle.open("SDWA_GEOGRAPHIC_AREAS.csv") as raw:
            batch = []
            for row in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")):
                if row["PWS_ACTIVITY_CODE"] != "A":
                    continue
                batch.append((row["PWSID"], row["AREA_TYPE_CODE"], row["STATE_SERVED"],
                              row["ZIP_CODE_SERVED"], row["CITY_SERVED"].upper(),
                              row["COUNTY_SERVED"].upper(), row["TRIBAL_CODE"], row["LAST_REPORTED_DATE"]))
                if len(batch) >= 10_000:
                    connection.executemany("INSERT OR IGNORE INTO geographic_areas VALUES (?,?,?,?,?,?,?,?)", batch)
                    inserted += len(batch); batch.clear()
            connection.executemany("INSERT OR IGNORE INTO geographic_areas VALUES (?,?,?,?,?,?,?,?)", batch)
            inserted += len(batch)
        connection.execute("CREATE INDEX geographic_zip_idx ON geographic_areas(state,zip_code)")
        connection.execute("CREATE INDEX geographic_city_idx ON geographic_areas(state,city)")
        connection.execute("CREATE INDEX geographic_tribal_idx ON geographic_areas(tribal_code)")
        connection.commit()
    print(json.dumps({"status": "PASS", "rows_considered": inserted}, indent=2))


if __name__ == "__main__":
    main()
