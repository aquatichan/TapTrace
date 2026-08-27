"""Build a defensible Houston TapTrace water profile from official local data.

The service-line inventory is property/service-connection specific. CCR values are
public-water-system level. This script preserves that distinction in every output.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "work/data/raw/houston_lcrr_inventory/houston_lcrr_inventory_raw.csv"
SYSTEMS = ROOT / "work/houston_profile/houston_systems.csv"
MEASUREMENTS = ROOT / "work/houston_profile/houston_2025_ccr_measurements.csv"
OUT = ROOT / "outputs/houston_profile"

SYSTEM_NAME_TO_PWSID = {
    "CITY OF HOUSTON": "TX1010013",
    "CITY OF HOUSTON UD 5 - KINGWOOD": "TX1010348",
    "CITY OF HOUSTON WILLOW CHASE": "TX1011902",
    "CITY OF HOUSTON DISTRICT 73": "TX1011585",
    "CITY OF HOUSTON DISTRICT 82": "TX1011593",
    "CITY OF HOUSTON BELLEAU WOODS": "TX1011594",
}


def clean_number(value):
    if pd.isna(value) or str(value).strip() == "":
        return None
    return float(value)


def select_record(df: pd.DataFrame, args: argparse.Namespace) -> pd.Series:
    if args.objectid is not None:
        rows = df[df["OBJECTID"] == args.objectid]
    elif args.addrkey is not None:
        rows = df[df["ADDRKEY"] == args.addrkey]
    elif args.latitude is not None and args.longitude is not None:
        valid = df["LATITUDE"].between(28.5, 31.0) & df["LONGITUDE"].between(-96.5, -94.0)
        candidates = df.loc[valid].copy()
        # Equirectangular approximation is sufficient for selecting a nearby record.
        lat_scale = math.cos(math.radians(args.latitude))
        candidates["distance2"] = (
            (candidates["LATITUDE"] - args.latitude) ** 2
            + ((candidates["LONGITUDE"] - args.longitude) * lat_scale) ** 2
        )
        rows = candidates.nsmallest(1, "distance2")
    else:
        raise ValueError("Provide --objectid, --addrkey, or both --latitude and --longitude")
    if rows.empty:
        raise LookupError("No Houston service-line record matched the supplied identifier")
    return rows.iloc[0]


def measurement_status(row: pd.Series) -> str:
    if row["result_kind"] == "not_detected":
        return "not_detected_in_system_samples"
    if row["benchmark_value"] != "" and pd.notna(row["benchmark_value"]):
        result = clean_number(row["comparison_value"])
        benchmark = clean_number(row["benchmark_value"])
        if result is not None and benchmark is not None:
            return "below_regulatory_benchmark" if result <= benchmark else "above_regulatory_benchmark"
    return "reported_without_direct_benchmark_comparison"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--objectid", type=int)
    parser.add_argument("--addrkey", type=int)
    parser.add_argument("--latitude", type=float)
    parser.add_argument("--longitude", type=float)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    inventory = pd.read_csv(
        INVENTORY,
        dtype={"ZipCode": "string", "PWSID": "string"},
    )
    record = select_record(inventory, args)
    system_name = str(record["PWSID"])
    pwsid = SYSTEM_NAME_TO_PWSID.get(system_name)
    if not pwsid:
        raise LookupError(f"No federal PWSID mapping for inventory system {system_name!r}")

    systems = pd.read_csv(SYSTEMS, dtype=str).set_index("pwsid")
    measurements = pd.read_csv(MEASUREMENTS, dtype=str).fillna("")
    system = systems.loc[pwsid]
    system_measurements = measurements[measurements["pwsid"] == pwsid].copy()

    material = str(record["Both_Sides_Category"])
    known = "Unknown" not in material
    infrastructure = {
        "official_status": material,
        "utility_side": str(record["Utility_Side_Category"]),
        "customer_side": str(record["Customer_Side_Category"]),
        "evidence_level": "official_property_record",
        "is_resolved": known,
        "prediction": None,
        "prediction_policy": (
            "No consumer-facing Houston pipe prediction is currently admitted. "
            "The national model failed the held-out-city reliability gate."
        ) if not known else "Prediction is unnecessary because an official category is available.",
    }

    contaminants = []
    for _, row in system_measurements.iterrows():
        contaminants.append({
            "name": row["contaminant"],
            "unit": row["unit"],
            "sample_location": row["sample_location"],
            "sample_period": row["sample_period"],
            "result_kind": row["result_kind"],
            "minimum": clean_number(row["minimum"]),
            "average": clean_number(row["average"]),
            "maximum": clean_number(row["maximum"]),
            "percentile_90": clean_number(row["percentile_90"]),
            "benchmark_type": row["benchmark_type"] or None,
            "benchmark_value": clean_number(row["benchmark_value"]),
            "status": measurement_status(row),
            "evidence_level": "official_system_measurement",
            "home_specific": False,
            "source_page": int(row["source_page"]),
        })

    profile = {
        "schema_version": "1.0.0",
        "profile_scope": "Houston prototype",
        "service_connection": {
            "objectid": int(record["OBJECTID"]),
            "addrkey": None if pd.isna(record["ADDRKEY"]) else int(record["ADDRKEY"]),
            "compkey": None if pd.isna(record["COMPKEY"]) else int(record["COMPKEY"]),
            "latitude": clean_number(record["LATITUDE"]),
            "longitude": clean_number(record["LONGITUDE"]),
            "zip_code": None if pd.isna(record["ZipCode"]) else str(record["ZipCode"]),
        },
        "water_system": {
            "name": system["system_name"],
            "pwsid": pwsid,
            "source_water": system["source_water"],
            "source_detail": system["source_detail"],
            "population_or_customers": system["population_or_customers"],
            "evidence_level": "official_system_record",
        },
        "infrastructure": infrastructure,
        "water_quality": {
            "report_year": 2025,
            "scope_warning": (
                "These results describe samples reported for the public water system. "
                "They do not measure water from this residence and must not be presented as a home test."
            ),
            "measurements": contaminants,
        },
        "actions": [
            {
                "priority": 1,
                "action": "Use the official Houston service-line status as the infrastructure result.",
                "reason": "Property-specific official evidence outranks any model estimate.",
            },
            {
                "priority": 2,
                "action": "Offer residence-level testing when the user wants certainty about tap water.",
                "reason": "System measurements cannot establish the concentration at one faucet.",
            },
            {
                "priority": 3,
                "action": "Offer Houston's optional service-line verification flow when the official material is unknown.",
                "reason": "This can replace uncertainty with property-specific evidence; it is optional, not a prerequisite for viewing the profile.",
            },
        ],
        "provenance": [
            {
                "dataset": "Houston LCRR Inventory Public View",
                "url": "https://services1.arcgis.com/VVapzOPgBae5joyC/arcgis/rest/services/Houston_TX_LCRR_Inventory_Public_View/FeatureServer/0",
                "grain": "service connection",
            },
            {
                "dataset": "Houston Water Quality Report 2025",
                "url": "https://www.houstonpublicworks.org/sites/g/files/nwywnm456/files/doc/003_2025_houston_water_quality_report.pdf",
                "grain": "public water system / monitoring location / contaminant",
            },
        ],
    }

    OUT.mkdir(parents=True, exist_ok=True)
    output = args.output or OUT / f"profile_objectid_{int(record['OBJECTID'])}.json"
    output.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
