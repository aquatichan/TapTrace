"""Profile source grain, completeness, mapping coverage, and output risks."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
inventory = pd.read_csv(
    ROOT / "work/data/raw/houston_lcrr_inventory/houston_lcrr_inventory_raw.csv",
    dtype={"PWSID": "string", "ZipCode": "string"},
)
systems = pd.read_csv(ROOT / "work/houston_profile/houston_systems.csv", dtype=str)
measurements = pd.read_csv(ROOT / "work/houston_profile/houston_2025_ccr_measurements.csv", dtype=str)

mapping = dict(zip(systems["inventory_system_name"], systems["pwsid"]))
mapped = inventory["PWSID"].map(mapping)
valid_coords = (
    inventory["LATITUDE"].between(28.5, 31.0)
    & inventory["LONGITUDE"].between(-96.5, -94.0)
)
unknown = inventory["Both_Sides_Category"].fillna("").str.contains("Unknown")

by_system = (
    inventory.assign(federal_pwsid=mapped, unresolved=unknown, valid_coordinates=valid_coords)
    .groupby(["PWSID", "federal_pwsid"], dropna=False)
    .agg(
        service_records=("OBJECTID", "size"),
        unresolved_records=("unresolved", "sum"),
        valid_coordinate_records=("valid_coordinates", "sum"),
    )
    .reset_index()
)
by_system["unresolved_rate"] = by_system["unresolved_records"] / by_system["service_records"]
by_system["coordinate_valid_rate"] = by_system["valid_coordinate_records"] / by_system["service_records"]
by_system.to_csv(ROOT / "outputs/houston_profile/inventory_profile_by_system.csv", index=False)

summary = {
    "inventory_grain": "service connection record",
    "water_quality_grain": "PWSID + contaminant + sample location + sample period",
    "inventory_rows": len(inventory),
    "inventory_unique_objectids": int(inventory["OBJECTID"].nunique()),
    "inventory_duplicate_objectids": int(inventory["OBJECTID"].duplicated().sum()),
    "inventory_systems": int(inventory["PWSID"].nunique(dropna=True)),
    "mapped_system_records": int(mapped.notna().sum()),
    "unmapped_system_records": int(mapped.isna().sum()),
    "mapped_system_record_rate": round(float(mapped.notna().mean()), 6),
    "valid_coordinate_records": int(valid_coords.sum()),
    "valid_coordinate_rate": round(float(valid_coords.mean()), 6),
    "unresolved_both_sides_records": int(unknown.sum()),
    "unresolved_both_sides_rate": round(float(unknown.mean()), 6),
    "curated_ccr_measurements": len(measurements),
    "ccr_systems": int(measurements["pwsid"].nunique()),
    "duplicate_measurement_keys": int(
        measurements[["pwsid", "contaminant", "sample_location", "sample_period"]]
        .duplicated().sum()
    ),
    "critical_policy_checks": {
        "system_measurements_are_not_home_measurements": True,
        "unknown_pipe_material_is_not_a_negative_label": True,
        "national_prediction_is_not_admitted_for_houston_household_identification": True,
    },
}
(ROOT / "outputs/houston_profile/source_audit.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
