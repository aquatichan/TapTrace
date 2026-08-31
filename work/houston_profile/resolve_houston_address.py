"""Resolve a typed Houston address to logical service connections and a profile.

Address points are queried from the City of Houston's public authoritative layer.
The local LCRR inventory is then joined by ADDRKEY. Repeated source rows with the
same logical connection and classifications are collapsed without deleting source
provenance.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import ssl
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd


def tls_context() -> ssl.SSLContext:
    """Use certifi's maintained CA bundle when the host Python lacks system roots."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "work/data/raw/houston_lcrr_inventory/houston_lcrr_inventory_raw.csv"
ADDRESS_QUERY = (
    "https://houstonwatergis.org/arcgis/rest/services/INFORHW/"
    "AddressPtsAndParcelsIPS/FeatureServer/0/query"
)
OUT_FIELDS = (
    "OBJECTID,ADDRKEY,FULLADDRESS,STREET_NUM,FRACTION,PREFIX,STREET_NAME,"
    "SUFFIX,STREET_TYPE,UNITTYPE,UNITID,CITY,STATE,ZIPCODE,Latitude,Longitude,STATUS"
)
SUFFIXES = {
    "STREET": "ST", "ST": "ST", "ROAD": "RD", "RD": "RD",
    "DRIVE": "DR", "DR": "DR", "LANE": "LN", "LN": "LN",
    "COURT": "CT", "CT": "CT", "AVENUE": "AVE", "AVE": "AVE",
    "BOULEVARD": "BLVD", "BLVD": "BLVD", "PLACE": "PL", "PL": "PL",
    "PARKWAY": "PKWY", "PKWY": "PKWY", "CIRCLE": "CIR", "CIR": "CIR",
    "TRAIL": "TRL", "TRL": "TRL", "WAY": "WAY", "HIGHWAY": "HWY",
    "TERRACE": "TER", "TER": "TER", "LOOP": "LOOP",
}


def normalize_address(raw: str) -> tuple[str, str | None]:
    text = raw.upper().replace("#", " UNIT ")
    text = re.sub(r"[,.]", " ", text)
    # Keep only characters that can occur in the controlled address comparison.
    # This also prevents user input from becoming SQL wildcard/control syntax.
    text = re.sub(r"[^A-Z0-9'\- ]", " ", text)
    text = re.sub(r"\bHOUSTON\b", " ", text)
    text = re.sub(r"\bTEXAS\b|\bTX\b", " ", text)
    zip_match = re.search(r"\b(7\d{4})(?:-\d{4})?\b", text)
    zipcode = zip_match.group(1) if zip_match else None
    text = re.sub(r"\b7\d{4}(?:-\d{4})?\b", " ", text)
    tokens = [SUFFIXES.get(token, token) for token in text.split()]
    normalized = " ".join(tokens)
    if not normalized or not re.match(r"^\d", normalized):
        raise ValueError("Enter a Houston street address beginning with a house number")
    return normalized, zipcode


def arcgis_query(where: str) -> list[dict]:
    params = {
        "where": where,
        "outFields": OUT_FIELDS,
        "returnGeometry": "false",
        "orderByFields": "OBJECTID ASC",
        "resultRecordCount": "100",
        "f": "json",
    }
    request = urllib.request.Request(
        ADDRESS_QUERY + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": "TapTrace-Houston-Address-Resolver/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60, context=tls_context()) as response:
        payload = json.load(response)
    if "error" in payload:
        raise RuntimeError(payload["error"])
    return [feature["attributes"] for feature in payload.get("features", [])]


def find_address_points(raw: str) -> tuple[str, str | None, list[dict], str]:
    normalized, zipcode = normalize_address(raw)
    safe = normalized.replace("'", "''")
    zip_clause = f" AND ZIPCODE = '{zipcode}'" if zipcode else ""
    exact = arcgis_query(f"FULLADDRESS = '{safe}'{zip_clause}")
    if exact:
        return normalized, zipcode, exact, "exact_official_address"

    # A controlled fallback supports records where unit text or suffix rendering
    # differs. It never auto-selects a result unless only one official address is returned.
    fallback = arcgis_query(f"FULLADDRESS LIKE '{safe}%'{zip_clause}")
    return normalized, zipcode, fallback, "prefix_candidate_search"


def logical_services(inventory: pd.DataFrame, addrkey: int) -> list[dict]:
    rows = inventory[inventory["ADDRKEY"] == addrkey].copy()
    if rows.empty:
        return []
    identity = [
        "ADDRKEY", "COMPKEY", "PWSID", "LATITUDE", "LONGITUDE",
        "Utility_Side_Category", "Customer_Side_Category", "Both_Sides_Category",
    ]
    services = []
    for _, group in rows.groupby(identity, dropna=False, sort=True):
        representative = group.sort_values("OBJECTID").iloc[0]
        services.append({
            "representative_objectid": int(representative["OBJECTID"]),
            "source_objectids": [int(x) for x in group["OBJECTID"].sort_values()],
            "source_row_count": len(group),
            "addrkey": int(representative["ADDRKEY"]),
            "compkey": None if pd.isna(representative["COMPKEY"]) else int(representative["COMPKEY"]),
            "water_system_name": str(representative["PWSID"]),
            "utility_side": str(representative["Utility_Side_Category"]),
            "customer_side": str(representative["Customer_Side_Category"]),
            "both_sides": str(representative["Both_Sides_Category"]),
        })
    return services


def nearby_inventory_context(inventory: pd.DataFrame, latitude: float, longitude: float,
                             radius_feet: float = 250.0) -> dict | None:
    """Summarize nearby official records without relabeling them as this property."""
    if pd.isna(latitude) or pd.isna(longitude):
        return None
    lat_scale = 69.0
    lon_scale = 69.0 * math.cos(math.radians(float(latitude)))
    distances_miles = (
        ((inventory["LATITUDE"] - float(latitude)) * lat_scale) ** 2
        + ((inventory["LONGITUDE"] - float(longitude)) * lon_scale) ** 2
    ) ** 0.5
    nearby = inventory.loc[distances_miles * 5280 <= radius_feet].copy()
    if nearby.empty:
        return None
    nearby["distance_feet"] = (distances_miles.loc[nearby.index] * 5280).round(1)
    nearest = nearby.sort_values(["distance_feet", "OBJECTID"]).head(25)

    def counts(column: str) -> dict[str, int]:
        values = nearest[column].fillna("Not reported").astype(str)
        return {str(key): int(value) for key, value in values.value_counts().sort_index().items()}

    return {
        "status": "nearby_official_records_available",
        "evidence_scope": "nearby_service_connections_not_property_match",
        "radius_feet": radius_feet,
        "records_in_radius": int(len(nearby)),
        "records_summarized": int(len(nearest)),
        "nearest_record_distance_feet": float(nearest.iloc[0]["distance_feet"]),
        "utility_side_material_counts": counts("Utility_Side_Category"),
        "customer_side_material_counts": counts("Customer_Side_Category"),
        "both_sides_material_counts": counts("Both_Sides_Category"),
        "pwsids": sorted(nearest["PWSID"].dropna().astype(str).unique().tolist()),
        "explanation": (
            "These are official inventory records near the address. They describe the surrounding "
            "service connections and must not be presented as this property's pipe material."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("address")
    parser.add_argument("--select-objectid", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    normalized, zipcode, points, strategy = find_address_points(args.address)
    inventory = pd.read_csv(
        INVENTORY,
        dtype={"ADDRKEY": "Int64", "COMPKEY": "Int64", "PWSID": "string", "ZipCode": "string"},
    )
    candidates = []
    for point in points:
        addrkey = point.get("ADDRKEY")
        services = logical_services(inventory, int(addrkey)) if addrkey is not None else []
        candidates.append({
            "official_address": point.get("FULLADDRESS"),
            "city": point.get("CITY"),
            "state": point.get("STATE"),
            "zip_code": point.get("ZIPCODE"),
            "addrkey": addrkey,
            "latitude": point.get("Latitude"),
            "longitude": point.get("Longitude"),
            "address_status": point.get("STATUS"),
            "logical_services": services,
        })

    service_count = sum(len(x["logical_services"]) for x in candidates)
    if not candidates:
        resolution = "not_found"
    elif strategy != "exact_official_address" or len(candidates) > 1:
        resolution = "address_confirmation_required"
    elif service_count == 0:
        resolution = "official_address_found_no_inventory_connection"
    elif service_count == 1:
        resolution = "safe_single_service_match"
    else:
        resolution = "service_confirmation_required"

    selected = None
    all_services = [s for c in candidates for s in c["logical_services"]]
    if args.select_objectid is not None:
        matches = [s for s in all_services if args.select_objectid in s["source_objectids"]]
        if len(matches) != 1:
            raise ValueError("--select-objectid did not uniquely identify a returned logical service")
        selected = matches[0]
    elif resolution == "safe_single_service_match":
        selected = all_services[0]

    profile_path = None
    if selected:
        out_dir = ROOT / "outputs/houston_profile/address_profiles"
        out_dir.mkdir(parents=True, exist_ok=True)
        profile_path = out_dir / f"profile_objectid_{selected['representative_objectid']}.json"
        subprocess.run(
            [sys.executable, str(ROOT / "work/houston_profile/build_houston_profile.py"),
             "--objectid", str(selected["representative_objectid"]), "--output", str(profile_path)],
            check=True,
            stdout=subprocess.DEVNULL,
        )

    area_context = None
    if resolution == "official_address_found_no_inventory_connection" and len(candidates) == 1:
        point = candidates[0]
        area_context = nearby_inventory_context(inventory, point["latitude"], point["longitude"])

    result = {
        "input_address": args.address,
        "normalized_street_address": normalized,
        "input_zip_code": zipcode,
        "match_strategy": strategy,
        "resolution": resolution,
        "official_address_candidates": len(candidates),
        "logical_service_candidates": service_count,
        "candidates": candidates,
        "selected_service": selected,
        "generated_profile": None if profile_path is None else str(profile_path.relative_to(ROOT)),
        "area_context": area_context,
        "safety_policy": (
            "A profile is generated automatically only for one exact official address with one logical "
            "service. Multiple addresses or genuinely different services require user confirmation."
        ),
        "provenance": {
            "address_layer": "City of Houston Address Points",
            "address_layer_url": ADDRESS_QUERY.rsplit("/query", 1)[0],
            "inventory": "Houston LCRR Inventory Public View",
        },
    }
    output = args.output or ROOT / "outputs/houston_profile/address_resolution.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
