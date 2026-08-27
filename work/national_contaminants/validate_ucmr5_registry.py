"""Data-quality and integration checks for the UCMR 5 registry."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "outputs/national_contaminants/taptrace_ucmr5.sqlite"
OUT = ROOT / "outputs/national_contaminants"
connection = sqlite3.connect(DB)


def scalar(query: str):
    return connection.execute(query).fetchone()[0]


rows = scalar("SELECT COUNT(*) FROM results")
detects = scalar("SELECT SUM(is_detect) FROM results")
below_mrl = rows - detects
pwsids = scalar("SELECT COUNT(DISTINCT pwsid) FROM results")
contaminants = scalar("SELECT COUNT(DISTINCT contaminant) FROM results")
first_date, last_date = connection.execute("SELECT MIN(collection_date), MAX(collection_date) FROM results").fetchone()
duplicate_keys = scalar("""SELECT COUNT(*) FROM (
    SELECT pwsid,facility_id,sample_point_id,collection_date,sample_id,contaminant,
           method_id,result_sign,result_value,COUNT(*) AS n
    FROM results GROUP BY 1,2,3,4,5,6,7,8,9 HAVING n>1
)""")
invalid_detects = scalar("SELECT COUNT(*) FROM results WHERE is_detect=1 AND (result_sign!='=' OR result_value IS NULL)")
invalid_nondetects = scalar("SELECT COUNT(*) FROM results WHERE is_detect=0 AND result_sign!='<' ")
units = [row[0] for row in connection.execute("SELECT DISTINCT units FROM results")]
connection.close()

assert rows == 1_928_117
assert detects == 55_890
assert below_mrl == 1_872_227
assert contaminants == 30
assert duplicate_keys == 0
assert invalid_detects == 0 and invalid_nondetects == 0
assert units == ["µg/L"]

profiles = {}
for pwsid in ["TX1010013", "DC0000002", "NY7003493", "CA3810011"]:
    path = OUT / f"{pwsid}.json"
    subprocess.run([
        sys.executable, str(ROOT / "work/national_contaminants/query_ucmr5_registry.py"),
        pwsid, "--output", str(path),
    ], check=True, stdout=subprocess.DEVNULL)
    profile = json.loads(path.read_text())
    assert profile["has_ucmr5_results"]
    assert len(profile["contaminant_summaries"]) == 30
    assert all(x["home_specific"] is False for x in profile["contaminant_summaries"])
    profiles[pwsid] = {
        "system_name": profile["system_name"],
        "analytes": len(profile["contaminant_summaries"]),
        "analytes_with_detections": sum(x["detected_in_at_least_one_sample"] for x in profile["contaminant_summaries"]),
    }

summary = {
    "status": "PASS",
    "result_rows": rows,
    "public_water_systems": pwsids,
    "contaminants": contaminants,
    "detect_rows": detects,
    "below_mrl_rows": below_mrl,
    "first_collection_date": first_date,
    "last_collection_date": last_date,
    "duplicate_analytical_keys": duplicate_keys,
    "invalid_result_qualifiers": invalid_detects + invalid_nondetects,
    "units": units,
    "multistate_profiles": profiles,
}
(OUT / "validation_results.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
