"""Compose the consumer-facing TapTrace water profile from validated layers."""

from __future__ import annotations

import hashlib
import csv
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from recommendations import build_recommendations


ROOT = Path(__file__).resolve().parents[2]
RESOLVER = ROOT / "work/national_profile/resolve_national_address.py"
STATE_DIR = Path(os.getenv("TAPTRACE_STATE_DIR", ROOT / "outputs/backend"))
CACHE_DB = STATE_DIR / "water_profile_cache.sqlite"
COVERAGE_DB = ROOT / "outputs/national_ccr_coverage/ccr_coverage_queue.sqlite"
CACHE_TTL_SECONDS = 24 * 60 * 60
EPA_CCR_SEARCH = "https://ordspub.epa.gov/ords/safewater/f?p=136:102"
SERVICE_LINE_INVENTORY = ROOT / "work/data/raw/national_city_audit/SDWIS_service_line_inventory_USA_2026Q1.csv"
SOURCE_FRESHNESS = ROOT / "outputs/national_ccr/source_freshness.json"
_SERVICE_LINE_INDEX: dict[str, dict] | None = None


def _cache_key(address: str, selected_pwsid: str | None, enhanced: bool) -> str:
    normalized = " ".join(address.upper().split())
    material = json.dumps(
        [normalized, selected_pwsid, enhanced, "profile-v3.1-nearby-infrastructure-context"],
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode()).hexdigest()


def _connect_cache() -> sqlite3.Connection:
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(CACHE_DB)
    connection.execute("""CREATE TABLE IF NOT EXISTS profiles (
        cache_key TEXT PRIMARY KEY,
        created_at INTEGER NOT NULL,
        response_json TEXT NOT NULL
    )""")
    return connection


def initialize_state() -> None:
    """Create writable state before readiness checks and the first backup."""
    connection = _connect_cache()
    connection.close()


def _coverage_record(pwsid: str | None) -> dict | None:
    if not pwsid or not COVERAGE_DB.exists():
        return None
    connection = sqlite3.connect(COVERAGE_DB)
    connection.row_factory = sqlite3.Row
    row = connection.execute("SELECT * FROM coverage_queue WHERE pwsid=?", (pwsid,)).fetchone()
    connection.close()
    return dict(row) if row else None


def _read_cache(key: str) -> dict | None:
    connection = _connect_cache()
    row = connection.execute(
        "SELECT created_at,response_json FROM profiles WHERE cache_key=?", (key,)
    ).fetchone()
    connection.close()
    if not row or int(time.time()) - row[0] > CACHE_TTL_SECONDS:
        return None
    result = json.loads(row[1])
    result["meta"]["cache"] = "hit"
    return result


def _write_cache(key: str, result: dict) -> None:
    stored = json.loads(json.dumps(result))
    stored["meta"]["cache"] = "miss"
    connection = _connect_cache()
    connection.execute(
        "INSERT OR REPLACE INTO profiles VALUES (?,?,?)",
        (key, int(time.time()), json.dumps(stored, separators=(",", ":"))),
    )
    connection.commit()
    connection.close()


def _run_resolver(address: str, selected_pwsid: str | None, enhanced: bool) -> dict:
    with tempfile.TemporaryDirectory(prefix="taptrace-profile-") as directory:
        output = Path(directory) / "resolved.json"
        command = [sys.executable, str(RESOLVER), address, "--output", str(output)]
        if selected_pwsid:
            command.extend(["--select-pwsid", selected_pwsid])
        if not enhanced:
            command.append("--skip-enhanced")
        completed = subprocess.run(command, capture_output=True, text=True, timeout=150)
        if completed.returncode:
            detail = completed.stderr.strip().splitlines()[-1] if completed.stderr.strip() else "resolver failed"
            raise RuntimeError(detail)
        return json.loads(output.read_text(encoding="utf-8"))


def _category(name: str) -> str:
    value = name.lower()
    if "lead" in value or "copper" in value:
        return "lead_and_plumbing_metals"
    if any(token in value for token in ("pfo", "pfa", "genx", "hfpo", "fts", "adona")):
        return "pfas"
    if any(token in value for token in ("trihalomethane", "haloacetic", "chlorine", "chlorite", "bromate")):
        return "disinfection_and_byproducts"
    if any(token in value for token in ("coliform", "e. coli", "microbial")):
        return "microbial"
    if "nitrate" in value or "nitrite" in value:
        return "nitrates"
    if any(token in value for token in ("hardness", "dissolved solids", "alkalinity", "sodium", "ph")):
        return "aesthetic_and_mineral"
    return "other_detected_or_monitored"


def _quality_sections(resolved: dict) -> list[dict]:
    grouped: dict[str, dict] = {}
    ccr = (resolved.get("consumer_confidence_report_profile") or {}).get("measurements") or []
    for measurement in ccr:
        category = _category(measurement["contaminant"])
        section = grouped.setdefault(category, {
            "category": category,
            "status": "reported",
            "evidence_scope": "public_water_system",
            "measurements": [],
        })
        item = {
            "name": measurement["contaminant"],
            "result": measurement["result_text"],
            "unit": measurement["unit"],
            "statistic": measurement["statistic_type"],
            "benchmark_type": measurement["benchmark_type"],
            "benchmark_value": measurement["benchmark_value"],
            "benchmark_comparison": measurement["benchmark_comparison"],
            "reported_violation": measurement["violation"],
            "data_year": measurement["data_year"],
            "source_page": measurement["source_page"],
            "notes": measurement["notes"],
            "home_specific": False,
        }
        section["measurements"].append(item)
        if measurement["violation"] == "yes" or measurement["benchmark_comparison"] == "above_reported_benchmark":
            section["status"] = "attention"

    ucmr = (resolved.get("national_contaminant_profile") or {}).get("contaminant_summaries") or []
    detected = [row for row in ucmr if row.get("detected_in_at_least_one_sample")]
    if detected:
        section = grouped.setdefault("unregulated_monitoring", {
            "category": "unregulated_monitoring",
            "status": "detections_reported",
            "evidence_scope": "public_water_system",
            "measurements": [],
        })
        section["measurements"].extend({
            "name": row["contaminant"],
            "result": f"{row['detect_count']} detections among {row['sample_result_count']} results",
            "unit": row["units"],
            "maximum_detect": row["maximum_detect"],
            "latest_sample_date": row["latest_sample_date"],
            "regulatory_interpretation": "A UCMR detection is not automatically a violation.",
            "home_specific": False,
        } for row in detected)

    federal = resolved.get("federal_water_system_profile") or {}
    if federal:
        current = bool(federal.get("current_violation_flag"))
        grouped["federal_compliance"] = {
            "category": "federal_compliance",
            "status": "attention" if current else "no_current_violation_flag_reported",
            "evidence_scope": "public_water_system",
            "measurements": [{
                "name": "Federal drinking-water compliance record",
                "result": "Current violation flag reported" if current else "No current violation flag reported",
                "current_violation_flag": current,
                "serious_violator": federal.get("serious_violator"),
                "quarters_with_violation_last_3_years": federal.get("quarters_with_violation_last_3_years"),
                "rules_violated_last_3_years": federal.get("rules_violated_last_3_years"),
                "violation_categories": federal.get("violation_categories"),
                "record_freshness": federal.get("freshness_note"),
                "home_specific": False,
            }],
        }
    return sorted(grouped.values(), key=lambda row: row["category"])


def _provider_resources(selected: dict | None, federal: dict | None, report: dict | None) -> dict:
    selected = selected or {}
    federal = federal or {}
    pwsid = selected.get("pwsid") or federal.get("pwsid")
    return {
        "pwsid": pwsid,
        "provider_name": federal.get("name") or selected.get("name"),
        "validated_report_url": (report or {}).get("report_url"),
        "validated_report_landing_page": (report or {}).get("landing_page_url"),
        "official_facility_record": federal.get("detailed_facility_report") or selected.get("detailed_facility_report"),
        "epa_ccr_search": EPA_CCR_SEARCH,
        "contact_instruction": (
            f"Ask the provider for the latest Consumer Confidence Report and service-line inventory for PWSID {pwsid}."
            if pwsid else "Use a recent bill to identify the provider, then request its latest Consumer Confidence Report."
        ),
    }


def _integer(value) -> int:
    try:
        return int(str(value or "0").replace(",", ""))
    except ValueError:
        return 0


def _service_line_record(pwsid: str | None) -> dict | None:
    """Return current system totals; these are never treated as household labels."""
    global _SERVICE_LINE_INDEX
    if not pwsid or not SERVICE_LINE_INVENTORY.exists():
        return None
    if _SERVICE_LINE_INDEX is None:
        _SERVICE_LINE_INDEX = {}
        with SERVICE_LINE_INVENTORY.open(newline="", encoding="cp1252") as handle:
            for row in csv.DictReader(handle):
                _SERVICE_LINE_INDEX[row["PWS ID"].strip()] = row
    row = _SERVICE_LINE_INDEX.get(pwsid)
    if not row:
        return None
    lead = _integer(row["# Lead Service Lines"])
    grr = _integer(row["# Galvanized Requiring Replacement Service Lines"])
    unchecked = _integer(row["# Lead Status Unknown Service Lines"])
    nonlead = _integer(row["# Non-lead Service Lines"])
    known = lead + grr + nonlead
    return {
        "reporting_period": row["Submission Year Quarter"],
        "lead": lead,
        "galvanized_requiring_replacement": grr,
        "not_yet_classified": unchecked,
        "nonlead": nonlead,
        "total_reported": _integer(row["Total # Service Lines Reported"]),
        "known_concern_share": round((lead + grr) / known, 4) if known else None,
        "scope": "water_system",
    }


def _concern_level(record: dict | None) -> str:
    share = (record or {}).get("known_concern_share")
    if share is None:
        return "Assessment unavailable"
    if share >= 0.35:
        return "Elevated"
    if share >= 0.10:
        return "Moderate"
    return "Lower"


def _infrastructure(resolved: dict) -> dict:
    selected = resolved.get("selected_water_system_boundary") or {}
    system_record = _service_line_record(selected.get("pwsid"))
    enhanced = resolved.get("enhanced_connector") or {}
    path = enhanced.get("generated_property_profile")
    embedded = enhanced.get("property_record")
    if path or embedded:
        if embedded:
            infrastructure = embedded
        else:
            property_profile = json.loads((ROOT / path).read_text(encoding="utf-8"))
            infrastructure = property_profile.get("infrastructure", {})
        raw_official_status = infrastructure.get("official_status")
        status_is_unclassified = bool(raw_official_status and any(
            token in raw_official_status.lower() for token in ("unknown", "no information")
        ))
        official_status = "Not yet classified" if status_is_unclassified else raw_official_status
        contextual_property_status = None if status_is_unclassified else official_status
        checked = bool(infrastructure.get("is_resolved"))
        if checked:
            assessment = {
                "concern_level": "Known property classification",
                "basis": "official_property_record",
                "system_context": system_record,
            }
        else:
            assessment = {
                "concern_level": contextual_property_status or _concern_level(system_record),
                "basis": "official_property_inventory_context" if contextual_property_status else "water_system_inventory_context",
                "system_context": system_record,
                "explanation": (
                    "The utility's property record is not marked verified, so it is context rather than a confirmed material."
                    if contextual_property_status else
                    "This level describes infrastructure concern in the water system; it is not a claim about this home's pipe material."
                ),
            }
        return {
            "availability": "property_record_available",
            "official_status": official_status,
            "source_status": raw_official_status,
            "display_status": official_status if checked else "Infrastructure assessment available",
            "classification_status": "officially_classified" if checked else "assessment_only",
            "utility_side": infrastructure.get("utility_side"),
            "customer_side": infrastructure.get("customer_side"),
            "point_of_entry": infrastructure.get("point_of_entry"),
            "is_resolved": infrastructure.get("is_resolved"),
            "evidence_level": "official_property_record",
            "source": infrastructure.get("source"),
            "source_url": infrastructure.get("source_url"),
            "assessment": assessment,
            "confidence": {
                "score": 95 if checked else 55,
                "label": "High" if checked else "Limited",
                "meaning": "Strength of evidence supporting the infrastructure assessment—not the chance that this home has a particular pipe material.",
            },
        }
    area_context = enhanced.get("area_context")
    if area_context:
        return {
            "availability": "nearby_official_records_available",
            "official_status": None,
            "display_status": "Nearby infrastructure context available",
            "classification_status": "area_context_only",
            "evidence_level": "nearby_official_inventory_records",
            "assessment": {
                "concern_level": _concern_level(system_record),
                "basis": "nearby_official_service_connections_plus_water_system_inventory",
                "system_context": system_record,
                "nearby_records": area_context,
                "explanation": area_context.get("explanation"),
            },
            "confidence": {
                "score": 45,
                "label": "Area context",
                "meaning": (
                    "Confidence that the nearby records describe surrounding infrastructure; "
                    "they do not identify the service line connected to this property."
                ),
            },
        }
    return {
        "availability": "system_assessment_available" if system_record else "property_details_not_available",
        "official_status": None,
        "display_status": "Infrastructure assessment available" if system_record else "Limited infrastructure data",
        "classification_status": "assessment_only" if system_record else "limited_data",
        "evidence_level": "system_information_only",
        "assessment": {
            "concern_level": _concern_level(system_record),
            "basis": "water_system_inventory_context" if system_record else "insufficient_system_inventory",
            "system_context": system_record,
            "explanation": "This level describes infrastructure concern in the water system; it is not a claim about this home's pipe material.",
        },
        "confidence": {
            "score": 40 if system_record else 10,
            "label": "Limited",
            "meaning": "Strength of evidence supporting the infrastructure assessment—not the chance that this home has a particular pipe material.",
        },
    }


def _freshness(report: dict | None, resolved: dict) -> dict:
    """Expose age without converting missing dates into false precision."""
    current_year = int(time.strftime("%Y", time.gmtime()))
    report_year = _integer((report or {}).get("report_year")) or None
    report_age = current_year - report_year if report_year else None
    ucmr_rows = (resolved.get("national_contaminant_profile") or {}).get("contaminant_summaries") or []
    latest_ucmr = max((str(row.get("latest_sample_date")) for row in ucmr_rows if row.get("latest_sample_date")), default=None)
    source_check = None
    if report and SOURCE_FRESHNESS.exists():
        checks = json.loads(SOURCE_FRESHNESS.read_text(encoding="utf-8")).get("checks", [])
        source_check = next((row for row in checks if row.get("pwsid") == report.get("pwsid") and row.get("report_year") == report.get("report_year")), None)
    return {
        "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provider_report": {
            "report_year": report_year,
            "age_years": report_age,
            "status": "current_or_recent" if report_age is not None and report_age <= 1 else "older_report" if report_age is not None else "not_available",
            "source_integrity_status": (source_check or {}).get("status") or "not_checked",
            "source_checked_at": json.loads(SOURCE_FRESHNESS.read_text(encoding="utf-8")).get("checked_at_utc") if source_check else None,
        },
        "ucmr_latest_sample_date": latest_ucmr,
        "federal_record": {
            "status": "periodically_reported_not_realtime" if resolved.get("federal_water_system_profile") else "not_available",
            "note": (resolved.get("federal_water_system_profile") or {}).get("freshness_note"),
        },
        "service_line_inventory_period": ((resolved.get("selected_water_system_boundary") or {}) and (_service_line_record((resolved.get("selected_water_system_boundary") or {}).get("pwsid")) or {}).get("reporting_period")),
    }


def _data_quality(resolved: dict, infrastructure: dict, report: dict | None) -> dict:
    selected = resolved.get("selected_water_system_boundary") or {}
    checks = {
        "address_geocoded": bool((resolved.get("geocoding") or {}).get("matches")),
        "provider_confirmed_by_boundary": bool(selected),
        "official_federal_system_record": bool(resolved.get("federal_water_system_profile")),
        "source_validated_provider_report": bool(report),
        "official_property_pipe_record": infrastructure.get("classification_status") == "officially_classified",
    }
    return {
        "checks": checks,
        "property_specific_fields": ["official service-line material"] if checks["official_property_pipe_record"] else [],
        "system_level_fields": ["utility monitoring", "federal compliance", "UCMR monitoring", "service-line totals"],
        "not_established": ["water quality at this faucet"] + ([] if checks["official_property_pipe_record"] else ["this property's service-line material"]),
        "missing_data_interpretation": "A missing measurement means unavailable or not normalized; it does not mean the contaminant was absent.",
    }


def _profile_confidence(resolved: dict, infrastructure: dict, report: dict | None) -> dict:
    """Score source coverage, not safety or model certainty."""
    selected = resolved.get("selected_water_system_boundary") or {}
    federal = resolved.get("federal_water_system_profile") or {}
    score = 0
    factors = []
    if selected:
        points = 20 if selected.get("boundary_confidence") == "high" else 10
        score += points; factors.append({"source": "address_to_provider", "points": points})
    if federal:
        score += 20; factors.append({"source": "federal_system_record", "points": 20})
    if report:
        score += 25; factors.append({"source": "normalized_provider_report", "points": 25})
    if (resolved.get("national_contaminant_profile") or {}).get("contaminant_summaries") is not None:
        score += 15; factors.append({"source": "national_contaminant_monitoring", "points": 15})
    if infrastructure.get("classification_status") == "officially_classified":
        score += 20; factors.append({"source": "official_property_pipe_classification", "points": 20})
    elif (infrastructure.get("assessment") or {}).get("system_context"):
        score += 10; factors.append({"source": "system_service_line_inventory", "points": 10})
    return {
        "score": min(score, 100),
        "label": "High" if score >= 85 else "Moderate" if score >= 65 else "Limited",
        "meaning": "Completeness and strength of the data used for this profile—not a water-safety percentage or pipe-material probability.",
        "factors": factors,
    }


def compose_profile(address: str, selected_pwsid: str | None = None, enhanced: bool = True,
                    use_cache: bool = True) -> dict:
    address = " ".join(address.split())
    if len(address) < 8 or len(address) > 300:
        raise ValueError("address must be between 8 and 300 characters")
    complete_address = (
        re.search(r",\s*[^,]+,\s*[A-Z]{2}(?:\s+\d{5}(?:-\d{4})?)?$", address, re.IGNORECASE)
        or re.search(r"\b[A-Z]{2}\s+\d{5}(?:-\d{4})?$", address, re.IGNORECASE)
    )
    if not complete_address:
        raise ValueError("enter a complete U.S. address including city, state, and ZIP code")
    if selected_pwsid is not None and not isinstance(selected_pwsid, str):
        raise ValueError("selected_pwsid must be a string")
    selected_pwsid = selected_pwsid.strip().upper() if selected_pwsid else None
    if selected_pwsid and (len(selected_pwsid) > 12 or not selected_pwsid.isalnum()):
        raise ValueError("selected_pwsid must be an alphanumeric public-water-system ID")
    key = _cache_key(address, selected_pwsid, enhanced)
    if use_cache and (cached := _read_cache(key)):
        return cached

    resolved = _run_resolver(address, selected_pwsid, enhanced)
    infrastructure = _infrastructure(resolved)
    sections = _quality_sections(resolved)
    selected = resolved.get("selected_water_system_boundary")
    federal = resolved.get("federal_water_system_profile")
    report = (resolved.get("consumer_confidence_report_profile") or {}).get("report")
    provider_resources = _provider_resources(selected, federal, report)
    national_core_complete = bool(selected and federal)
    result = {
        "schema_version": "3.0.0",
        "meta": {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "cache": "miss"},
        "request": {"address": address, "selected_pwsid": selected_pwsid},
        "resolution": {
            "status": resolved["resolution"],
            "matched_address": ((resolved.get("geocoding") or {}).get("matches") or [{}])[0].get("matched_address"),
            "requires_user_confirmation": resolved["resolution"] in {"address_confirmation_required", "water_system_confirmation_required"},
            "water_system_candidates": resolved.get("water_system_candidates", []),
        },
        "water_system": ({
            "pwsid": selected.get("pwsid"),
            "name": (federal or {}).get("name") or selected.get("name"),
            "primary_source": (federal or {}).get("primary_source"),
            "population_served": (federal or {}).get("population_served") or selected.get("population_served"),
            "boundary_confidence": selected.get("boundary_confidence"),
            "current_violation_flag": (federal or {}).get("current_violation_flag"),
            "serious_violator": (federal or {}).get("serious_violator"),
            "federal_record_freshness": (federal or {}).get("freshness_note"),
        } if selected else None),
        "water_source_assessment": {
            "public_water_provider_status": "resolved" if selected else "confirmation_required" if resolved.get("water_system_candidates") else "no_provider_candidate",
            "private_well_context": resolved.get("private_well_context"),
            "property_well_status": "not_confirmed",
        },
        "infrastructure": infrastructure,
        "profile_confidence": _profile_confidence(resolved, infrastructure, report),
        "data_quality": _data_quality(resolved, infrastructure, report),
        "data_freshness": _freshness(report, resolved),
        "water_quality": {
            "availability": "validated_ccr_available" if report else "provider_report_not_yet_checked",
            "display_status": "Provider report checked" if report else "Provider report not yet checked",
            "report": ({key: report.get(key) for key in ("report_year", "data_year", "report_url", "publisher")} if report else None),
            "sections": sections,
            "scope": "public_water_system",
            "home_specific": False,
            "national_coverage_record": _coverage_record(selected.get("pwsid") if selected else None),
        },
        "coverage": {
            "national_core_status": "complete" if national_core_complete else "needs_provider_confirmation",
            "national_core_includes": [
                "address-to-provider resolution", "federal system and compliance record",
                "EPA UCMR monitoring when the system participated", "official provenance and next steps",
            ],
            "local_enhancement_status": "complete" if report else "not_yet_checked",
            "local_enhancement_includes": ["normalized provider report", "property-level pipe record where available"],
            "profile_is_valid_without_local_enhancement": national_core_complete,
        },
        "provider_resources": provider_resources,
        "recommended_actions": build_recommendations(resolved, infrastructure, sections),
        "safety": {
            "summary": "This profile combines official property records where available with public-water-system monitoring. It is not a test of this home's tap water.",
            "missing_data_rule": "Missing or unextracted data never means that a contaminant is absent.",
            "infrastructure_rule": "TapTrace reports household pipe material only from an official property record. System totals are context and never become a household estimate.",
        },
        "source_layers": {
            "federal_system_record": federal,
            "consumer_confidence_report": resolved.get("consumer_confidence_report_profile"),
            "ucmr5": resolved.get("national_contaminant_profile"),
            "enhanced_connector": resolved.get("enhanced_connector"),
        },
    }
    if use_cache:
        _write_cache(key, result)
    return result
