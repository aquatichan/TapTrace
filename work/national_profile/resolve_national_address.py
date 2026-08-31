"""Resolve a US address to EPA water systems and build a national base profile.

Official services:
- US Census Geocoder for address coordinates.
- EPA Water System Service Area Boundaries v3 for point-in-polygon resolution.
- EPA ECHO/SDWIS web services for system and compliance attributes.

The resolver never silently chooses among overlapping service areas.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/national_profile"
CENSUS = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
ARCGIS_GEOCODER = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
EPA_PRIVATE_WELLS = "https://geodata.epa.gov/arcgis/rest/services/ORD/PrivateDomesticWells2010/MapServer/1/query"
EPA_BOUNDARIES = (
    "https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/"
    "Water_System_Boundaries/FeatureServer/0/query"
)
ECHO_SEARCH = "https://echodata.epa.gov/echo/sdw_rest_services.get_systems"
ECHO_RESULTS = "https://echodata.epa.gov/echo/sdw_rest_services.get_qid"
HOUSTON_PWSIDS = {
    "TX1010013", "TX1010348", "TX1011902", "TX1011585", "TX1011593", "TX1011594"
}
DC_PWSID = "DC0000002"
DC_INVENTORY = ROOT / "work/data/raw/dc_water_inventory/dc_water_inventory_raw.csv"
DC_INVENTORY_SOURCE = "https://geo.dcwater.com/arcgis/rest/services/Public/WaterServiceInfo_LPRAP/MapServer/1"
UCMR5_DB = ROOT / "outputs/national_contaminants/taptrace_ucmr5.sqlite"
CCR_DB = ROOT / "outputs/national_ccr/taptrace_ccr.sqlite"
ECHO_CACHE_DB = Path(os.getenv("TAPTRACE_STATE_DIR", ROOT / "outputs/backend")) / "echo_system_cache.sqlite"
SDWIS_REGISTRY_DB = ROOT / "outputs/backend/sdwis_system_registry.sqlite"
ECHO_CACHE_TTL = 7 * 24 * 60 * 60
BOUNDARY_FIELDS = (
    "OBJECTID,PWSID,PWS_Name,Primacy_Agency,Original_Data_Provider,Data_Provider_Type,"
    "Data_Source,Model_Method,Service_Area_Type,Feature_Type,Method_Details,"
    "Verification_Status,Population_Served_Count,Service_Connections_Count,"
    "Detailed_Facility_Report,Confirmed,Area_SqKM"
)


def connect_registry(path: Path) -> sqlite3.Connection:
    """Open packaged reference data without journal or recovery writes."""
    return sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)


def tls_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def get_json(base: str, params: dict, retries: int = 6) -> dict:
    url = base + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "TapTrace-National-Resolver/1.0"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=60, context=tls_context()) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if attempt + 1 == retries:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            time.sleep(float(retry_after) if retry_after and retry_after.isdigit() else min(30, 2 ** attempt))
        except Exception:
            if attempt + 1 == retries:
                raise
            time.sleep(min(30, 2 ** attempt))
    raise RuntimeError("unreachable")


def geocode(address: str) -> dict:
    payload = get_json(CENSUS, {
        "address": address,
        "benchmark": "Public_AR_Current",
        "format": "json",
    })
    matches = payload.get("result", {}).get("addressMatches", [])
    if not matches:
        # Census omits some valid civic and non-residential addresses. Use a
        # second geocoder, but admit only high-scoring US rooftop/street matches.
        fallback = get_json(ARCGIS_GEOCODER, {
            "SingleLine": address,
            "f": "json",
            "countryCode": "USA",
            "maxLocations": 3,
            "outFields": "Match_addr,Addr_type,Country,City,Region,Postal",
        })
        candidates = [row for row in fallback.get("candidates", [])
                      if float(row.get("score") or 0) >= 90
                      and (row.get("attributes", {}).get("Country") or "USA") == "USA"]
        if not candidates:
            return {"status": "not_found", "matches": [], "providers_attempted": ["US Census", "ArcGIS World Geocoder"]}
        top_score = float(candidates[0]["score"])
        top = [row for row in candidates if float(row["score"]) == top_score]
        cleaned = [{
            "matched_address": row["address"],
            "longitude": row["location"]["x"],
            "latitude": row["location"]["y"],
            "match_score": row["score"],
            "address_type": row.get("attributes", {}).get("Addr_type"),
            "geocoder": "ArcGIS World Geocoder",
            "city": row.get("attributes", {}).get("City"),
            "state": row.get("attributes", {}).get("Region"),
            "zip_code": row.get("attributes", {}).get("Postal"),
        } for row in top]
        return {"status": "matched" if len(cleaned) == 1 else "ambiguous", "matches": cleaned,
                "providers_attempted": ["US Census", "ArcGIS World Geocoder"]}
    cleaned = [{
        "matched_address": match["matchedAddress"],
        "longitude": match["coordinates"]["x"],
        "latitude": match["coordinates"]["y"],
        "tiger_line_id": match.get("tigerLine", {}).get("tigerLineId"),
        "side": match.get("tigerLine", {}).get("side"),
        "geocoder": "US Census",
        "city": match.get("addressComponents", {}).get("city"),
        "state": match.get("addressComponents", {}).get("state"),
        "zip_code": match.get("addressComponents", {}).get("zip"),
    } for match in matches]
    return {"status": "matched" if len(cleaned) == 1 else "ambiguous", "matches": cleaned,
            "providers_attempted": ["US Census"]}


def boundary_confidence(feature: dict) -> tuple[str, str]:
    provider_type = (feature.get("Data_Provider_Type") or "").lower()
    model_method = (feature.get("Model_Method") or "").lower()
    original = feature.get("Original_Data_Provider") or ""
    if "model" in provider_type or model_method:
        return "moderate", "EPA-modeled service area; confirm with a water bill or utility when possible."
    if original or provider_type:
        return "high", "Boundary is attributed to a state, utility, or other original data provider."
    return "moderate", "EPA boundary has limited source-provenance fields; utility confirmation is advisable."


def water_system_boundaries(longitude: float, latitude: float) -> list[dict]:
    payload = get_json(EPA_BOUNDARIES, {
        "where": "1=1",
        "geometry": f"{longitude},{latitude}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": BOUNDARY_FIELDS,
        "returnGeometry": "false",
        "orderByFields": "PWSID ASC",
        "f": "json",
    })
    if "error" in payload:
        raise RuntimeError(payload["error"])
    results = []
    for item in payload.get("features", []):
        feature = item["attributes"]
        confidence, note = boundary_confidence(feature)
        raw_ids = str(feature.get("PWSID") or "")
        pwsids = [value.strip() for value in raw_ids.split(";") if value.strip()]
        raw_names = str(feature.get("PWS_Name") or "")
        names = [value.strip() for value in raw_names.split(";")]
        for index, pwsid in enumerate(pwsids or [None]):
            results.append({
            "pwsid": pwsid,
            "name": names[index] if index < len(names) else raw_names,
            "population_served": feature.get("Population_Served_Count"),
            "service_connections": feature.get("Service_Connections_Count"),
            "service_area_type": feature.get("Service_Area_Type"),
            "data_provider_type": feature.get("Data_Provider_Type"),
            "original_data_provider": feature.get("Original_Data_Provider"),
            "data_source": feature.get("Data_Source"),
            "model_method": feature.get("Model_Method"),
            "verification_status": feature.get("Verification_Status"),
            "boundary_confidence": confidence,
            "boundary_confidence_note": note,
            "detailed_facility_report": feature.get("Detailed_Facility_Report"),
            "composite_boundary_record": len(pwsids) > 1,
        })
    return results


def geographic_system_candidates(match: dict, limit: int = 8) -> list[dict]:
    """Rank SDWIS service-area candidates when no polygon covers the point."""
    if not SDWIS_REGISTRY_DB.exists():
        return []
    state = (match.get("state") or "").upper()
    city = (match.get("city") or "").upper()
    zip_code = (match.get("zip_code") or "").split("-", 1)[0]
    if not state or (not city and not zip_code):
        return []
    with connect_registry(SDWIS_REGISTRY_DB) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("""
            SELECT g.pwsid,g.area_type,g.zip_code,g.city,s.payload
            FROM geographic_areas g JOIN systems s ON s.pwsid=g.pwsid
            WHERE g.state=? AND ((?<>'' AND g.zip_code=?) OR (?<>'' AND g.city=?))
        """, (state, zip_code, zip_code, city, city)).fetchall()
    ranked: dict[str, dict] = {}
    for row in rows:
        system = json.loads(row["payload"])
        if system.get("activity") != "A" or system.get("type") != "CWS":
            continue
        candidate = ranked.setdefault(row["pwsid"], {
            "pwsid": row["pwsid"], "name": system.get("name"),
            "population_served": system.get("population_served"), "service_connections": None,
            "service_area_type": "SDWIS reported geography", "data_provider_type": "EPA SDWIS",
            "original_data_provider": system.get("state"), "data_source": "SDWIS geographic areas",
            "model_method": None, "verification_status": "candidate_requires_confirmation",
            "boundary_confidence": "candidate", "boundary_confidence_note":
                "Candidate shares the address ZIP/city; confirm using a water bill or utility.",
            "detailed_facility_report": None, "resolution_method": "sdwis_geographic_fallback",
            "candidate_score": 0, "matched_geographies": [],
        })
        if zip_code and row["zip_code"] == zip_code:
            candidate["candidate_score"] += 3; candidate["matched_geographies"].append("zip")
        if city and row["city"] == city:
            candidate["candidate_score"] += 2; candidate["matched_geographies"].append("city")
    return sorted(ranked.values(), key=lambda row: (-row["candidate_score"], -(row["population_served"] or 0), row["pwsid"]))[:limit]


def private_well_context(longitude: float, latitude: float) -> dict | None:
    payload = get_json(EPA_PRIVATE_WELLS, {
        "f": "json", "where": "1=1", "geometry": f"{longitude},{latitude}",
        "geometryType": "esriGeometryPoint", "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "GEOID,State,County,Units_10,Hybrid_Wells_10,Hybrid_ROU_10",
        "returnGeometry": "false",
    })
    features = payload.get("features") or []
    if not features:
        return None
    row = features[0]["attributes"]
    share = row.get("Hybrid_ROU_10")
    return {
        "status": "area_estimate_available", "census_block_geoid": row.get("GEOID"),
        "state": row.get("State"), "county": row.get("County"),
        "housing_units_2010": row.get("Units_10"), "estimated_well_housing_units_2010": row.get("Hybrid_Wells_10"),
        "estimated_well_use_percent_2010": share,
        "likelihood_band": "high" if share is not None and share >= 80 else "moderate" if share is not None and share >= 30 else "low",
        "evidence_scope": "census_block_area_estimate_not_property_confirmation",
        "source": "EPA 2010 US Estimated Private Domestic Wells",
        "source_url": EPA_PRIVATE_WELLS.rsplit("/1/query", 1)[0],
        "warning": "This area estimate does not prove that this property uses a private well. Confirm with the owner, a water bill, or a well record.",
    }


def _echo_cache_get(pwsid: str, allow_stale: bool = False) -> dict | None:
    if SDWIS_REGISTRY_DB.exists():
        with connect_registry(SDWIS_REGISTRY_DB) as registry:
            row = registry.execute("SELECT fetched_at,payload FROM systems WHERE pwsid=?", (pwsid,)).fetchone()
        if row:
            result = json.loads(row[1]); result["cache_status"] = "local_registry"
            return result
    try:
        ECHO_CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(ECHO_CACHE_DB, timeout=30) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS systems (pwsid TEXT PRIMARY KEY,fetched_at INTEGER NOT NULL,payload TEXT NOT NULL)")
            row = connection.execute("SELECT fetched_at,payload FROM systems WHERE pwsid=?", (pwsid,)).fetchone()
    except sqlite3.OperationalError:
        # The cache is an optimization. Read-only/ephemeral cloud filesystems
        # must never prevent an otherwise valid public-water profile.
        return None
    if not row:
        return None
    result = json.loads(row[1])
    is_registry = result.get("cache_status") == "local_registry"
    if not is_registry and not allow_stale and int(time.time()) - row[0] > ECHO_CACHE_TTL:
        return None
    result["cache_status"] = "local_registry" if is_registry else ("stale_fallback" if allow_stale else "hit")
    return result


def _echo_cache_put(pwsid: str, result: dict) -> None:
    stored = dict(result); stored["cache_status"] = "stored"
    try:
        ECHO_CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(ECHO_CACHE_DB, timeout=30) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS systems (pwsid TEXT PRIMARY KEY,fetched_at INTEGER NOT NULL,payload TEXT NOT NULL)")
            connection.execute("INSERT OR REPLACE INTO systems VALUES (?,?,?)", (pwsid, int(time.time()), json.dumps(stored)))
            connection.commit()
    except sqlite3.OperationalError:
        return


def echo_system(pwsid: str) -> dict | None:
    if cached := _echo_cache_get(pwsid):
        return cached
    try:
        result = _echo_system_live(pwsid)
        if result:
            _echo_cache_put(pwsid, result)
        return result
    except Exception:
        stale = _echo_cache_get(pwsid, allow_stale=True)
        if stale:
            return stale
        raise


def _echo_system_live(pwsid: str) -> dict | None:
    search = get_json(ECHO_SEARCH, {"output": "JSON", "p_pid": pwsid})
    result = search.get("Results", {})
    if result.get("Message") != "Success" or result.get("QueryRows") == "0":
        return None
    qid = result.get("QueryID")
    for _ in range(8):
        page = get_json(ECHO_RESULTS, {"output": "JSON", "qid": qid, "pageno": 1})
        systems = page.get("Results", {}).get("WaterSystems") or []
        if systems:
            row = next((x for x in systems if x.get("PWSId") == pwsid), systems[0])
            return {
                "pwsid": row.get("PWSId"),
                "name": row.get("PWSName"),
                "state": row.get("StateCode"),
                "type": row.get("PWSTypeDesc"),
                "activity": row.get("PWSActivityDesc"),
                "primary_source": row.get("PrimarySourceDesc"),
                "population_served": int(row["PopulationServedCount"]) if row.get("PopulationServedCount") else None,
                "owner": row.get("OwnerDesc"),
                "serious_violator": row.get("SeriousViolator"),
                "current_violation_flag": row.get("CurrVioFlag") == "1",
                "quarters_with_violation_last_3_years": int(row["QtrsWithVio"]) if row.get("QtrsWithVio") else 0,
                "rules_violated_last_3_years": int(row["RulesVio3yr"]) if row.get("RulesVio3yr") else 0,
                "violation_categories": row.get("ViolationCategories"),
                "contaminants_or_rules_in_violation_last_3_years": row.get("SDWAContaminantsInViol3yr"),
                "contaminants_or_rules_in_current_violation": row.get("SDWAContaminantsInCurViol"),
                "last_site_visit": row.get("SDWDateLastVisit"),
                "detailed_facility_report": row.get("DfrUrl"),
                "evidence_level": "official_federal_system_record",
                "freshness_note": "SDWIS/ECHO data are reported periodically and are not real-time.",
            }
        time.sleep(0.4)
    return None


def ucmr5_system(pwsid: str) -> dict:
    if not UCMR5_DB.exists():
        return {
            "registry_available": False,
            "has_ucmr5_results": None,
            "reason": "The local EPA UCMR 5 registry has not been built.",
        }
    connection = connect_registry(UCMR5_DB)
    connection.row_factory = sqlite3.Row
    rows = [dict(row) for row in connection.execute(
        "SELECT * FROM pws_contaminant_summary WHERE pwsid=? ORDER BY contaminant", (pwsid,)
    )]
    connection.close()
    for row in rows:
        row["detected_in_at_least_one_sample"] = row["detect_count"] > 0
        row["result_scope"] = "public_water_system"
        row["home_specific"] = False
    return {
        "registry_available": True,
        "ucmr_cycle": 5,
        "monitoring_period": "2023-2025",
        "has_ucmr5_results": bool(rows),
        "contaminant_summaries": rows,
        "scope_warning": (
            "UCMR results are associated with the public water system, not this residence. "
            "Below-MRL results are not zero, and detections are not automatically violations."
        ),
        "source": "US EPA UCMR 5 occurrence data",
    }


def ccr_system(pwsid: str) -> dict:
    if not CCR_DB.exists():
        return {"registry_available": False, "has_validated_ccr": None, "measurements": []}
    connection = connect_registry(CCR_DB)
    connection.row_factory = sqlite3.Row
    report_row = connection.execute(
        "SELECT * FROM reports WHERE pwsid=? AND validation_status='validated' ORDER BY report_year DESC LIMIT 1",
        (pwsid,),
    ).fetchone()
    if not report_row:
        connection.close()
        return {
            "registry_available": True,
            "has_validated_ccr": False,
            "measurements": [],
            "reason": "No source-page-validated CCR has been admitted for this PWSID.",
        }
    report = dict(report_row)
    rows = [dict(row) for row in connection.execute(
        "SELECT * FROM measurements WHERE pwsid=? AND report_year=? ORDER BY contaminant,sample_scope",
        (pwsid, report["report_year"]),
    )]
    connection.close()
    for row in rows:
        row["home_specific"] = False
        if row["benchmark_value"] is not None and row["comparison_value"] is not None:
            row["benchmark_comparison"] = (
                "at_or_below_reported_benchmark"
                if row["comparison_value"] <= row["benchmark_value"]
                else "above_reported_benchmark"
            )
        else:
            row["benchmark_comparison"] = "not_applicable"
    return {
        "registry_available": True,
        "has_validated_ccr": True,
        "report": report,
        "measurements": rows,
        "scope_warning": (
            "CCR data summarize system monitoring. Compliance comparisons use the report's applicable "
            "statistic, not necessarily the maximum individual sample, and are not home-specific."
        ),
    }


def dc_property_record(address: str) -> dict | None:
    """Exact-address lookup in DC Water's official public premise inventory."""
    if not DC_INVENTORY.exists():
        return None
    street = address.split(",", 1)[0].upper()
    street = re.sub(r"\s+(?:APT|UNIT|#)\s*[A-Z0-9-]+$", "", street).strip()
    street = " ".join(street.split())
    matches = []
    with DC_INVENTORY.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if " ".join(row["PremiseAddress"].upper().split()) == street:
                matches.append(row)
    if len(matches) != 1:
        return None
    row = matches[0]
    verified = row["Display_Category"].startswith("Verified ")
    return {
        "source": "DC Water Premise Material Status",
        "source_url": DC_INVENTORY_SOURCE,
        "record_id": row["OBJECTID"],
        "matched_premise_address": row["PremiseAddress"],
        "official_status": row["Display_Category"] or "No Information",
        "utility_side": {"status": row["Pub_Display_Category"], "material": row["PublicServiceMaterialType"], "inspection_date": row["PublicServiceInspectionDate"], "replacement_date": row["PublicServiceReplacementDate"]},
        "customer_side": {"status": row["Priv_Display_Category"], "material": row["PrivateServiceMaterialType"], "inspection_date": row["PrivateServiceInspectionDate"], "replacement_date": row["PrivateServiceReplacementDate"]},
        "point_of_entry": {"description": row["POE_Description"], "material": row["POEServiceMaterialType"], "evidence_origin": row["POEServiceMaterialOrigin"], "inspection_date": row["POEServiceInspectionDate"]},
        "is_resolved": verified,
        "evidence_scope": "official_property_inventory_record",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("address")
    parser.add_argument("--select-pwsid")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-enhanced", action="store_true")
    args = parser.parse_args()

    geo = geocode(args.address)
    boundaries = []
    used_geographic_fallback = False
    well_context = None
    if geo["status"] == "matched":
        point = geo["matches"][0]
        boundaries = water_system_boundaries(point["longitude"], point["latitude"])
        if not boundaries:
            boundaries = geographic_system_candidates(point)
            used_geographic_fallback = bool(boundaries)
        if not boundaries:
            well_context = private_well_context(point["longitude"], point["latitude"])

    selected = None
    if args.select_pwsid:
        matches = [x for x in boundaries if x["pwsid"] == args.select_pwsid]
        if len(matches) != 1:
            raise ValueError("--select-pwsid did not uniquely identify a returned service area")
        selected = matches[0]
    elif geo["status"] == "matched" and len(boundaries) == 1 and not used_geographic_fallback:
        selected = boundaries[0]

    if geo["status"] == "not_found":
        resolution = "address_not_geocoded"
    elif geo["status"] == "ambiguous":
        resolution = "address_confirmation_required"
    elif not boundaries:
        resolution = "no_mapped_public_water_system"
    elif selected is not None:
        resolution = "single_water_system_candidate"
    elif used_geographic_fallback or (len(boundaries) > 1 and selected is None):
        resolution = "water_system_confirmation_required"
    else:
        resolution = "single_water_system_candidate"

    federal = echo_system(selected["pwsid"]) if selected else None
    ucmr5 = ucmr5_system(selected["pwsid"]) if selected else None
    ccr = ccr_system(selected["pwsid"]) if selected else None
    enhanced = None
    if selected and selected["pwsid"] in HOUSTON_PWSIDS and not args.skip_enhanced:
        enhanced_out = OUT / "enhanced" / "houston_address_resolution.json"
        enhanced_out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [sys.executable, str(ROOT / "work/houston_profile/resolve_houston_address.py"),
             args.address, "--output", str(enhanced_out)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        enhanced_result = json.loads(enhanced_out.read_text())
        enhanced = {
            "connector": "houston",
            "resolution": enhanced_result["resolution"],
            "result_path": str(enhanced_out.relative_to(ROOT)),
            "generated_property_profile": enhanced_result.get("generated_profile"),
            "area_context": enhanced_result.get("area_context"),
        }
    elif selected and selected["pwsid"] == DC_PWSID and not args.skip_enhanced:
        property_record = dc_property_record(args.address)
        enhanced = {
            "connector": "dc_water",
            "resolution": "safe_single_service_match" if property_record else "no_safe_single_service_match",
            "property_record": property_record,
        }

    result = {
        "schema_version": "1.0.0",
        "input_address": args.address,
        "resolution": resolution,
        "geocoding": geo,
        "water_system_candidates": boundaries,
        "provider_resolution_method": "sdwis_geographic_fallback" if used_geographic_fallback else "epa_service_area_polygon",
        "private_well_context": well_context,
        "selected_water_system_boundary": selected,
        "federal_water_system_profile": federal,
        "national_contaminant_profile": ucmr5,
        "consumer_confidence_report_profile": ccr,
        "profile_tier": "enhanced_property" if enhanced and enhanced.get("generated_property_profile") else ("national_system" if federal else "location_only"),
        "enhanced_connector": enhanced,
        "scope_warning": (
            "The national profile describes a public water system, not a sample from this residence. "
            "EPA-modeled boundaries can differ from actual utility boundaries. A missing boundary may "
            "also indicate a private well or an unmapped public system."
        ),
        "next_actions": [
            "Confirm the provider using a water bill when the boundary is modeled or multiple systems overlap.",
            "Use the utility Consumer Confidence Report for detected system-level contaminants.",
            "Use residence-level testing for claims about water at the selected faucet.",
        ],
        "provenance": [
            {"source": "US Census Geocoder", "url": CENSUS, "grain": "address match"},
            {"source": "ArcGIS World Geocoder", "url": ARCGIS_GEOCODER, "grain": "fallback address match"},
            {"source": "EPA Water System Service Area Boundaries v3", "url": EPA_BOUNDARIES.rsplit("/query", 1)[0], "grain": "PWSID service area"},
            {"source": "EPA ECHO / SDWIS", "url": ECHO_SEARCH, "grain": "public water system"},
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    output = args.output or OUT / "national_address_profile.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
