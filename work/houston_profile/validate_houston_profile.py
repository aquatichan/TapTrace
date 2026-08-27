"""Fail-fast quality checks for Houston profile source tables and generated output."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
PYTHON = Path(__import__("sys").executable)
systems = pd.read_csv(ROOT / "work/houston_profile/houston_systems.csv", dtype=str)
measurements = pd.read_csv(ROOT / "work/houston_profile/houston_2025_ccr_measurements.csv", dtype=str)

assert len(systems) == 6
assert systems["pwsid"].is_unique
assert systems["pwsid"].str.fullmatch(r"TX\d{7}").all()
assert set(measurements["pwsid"]) == set(systems["pwsid"])
assert measurements[["pwsid", "contaminant", "sample_location", "sample_period"]].duplicated().sum() == 0
assert measurements["source_page"].astype(int).between(7, 19).all()
assert measurements["evidence_level"].isna().all() if "evidence_level" in measurements else True

out = ROOT / "outputs/houston_profile/validation_sample.json"
subprocess.run(
    [str(PYTHON), str(ROOT / "work/houston_profile/build_houston_profile.py"),
     "--objectid", "1", "--output", str(out)], check=True
)
profile = json.loads(out.read_text())
assert profile["water_system"]["pwsid"] == "TX1010013"
assert profile["infrastructure"]["evidence_level"] == "official_property_record"
assert profile["water_quality"]["measurements"]
assert all(x["home_specific"] is False for x in profile["water_quality"]["measurements"])
assert all(x["evidence_level"] == "official_system_measurement" for x in profile["water_quality"]["measurements"])

result = {
    "status": "PASS",
    "systems": len(systems),
    "curated_measurements": len(measurements),
    "unique_measurement_keys": True,
    "all_six_inventory_systems_mapped": True,
    "system_results_blocked_from_home_specific_claims": True,
    "sample_profile": str(out.relative_to(ROOT)),
}
(ROOT / "outputs/houston_profile/validation_results.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
