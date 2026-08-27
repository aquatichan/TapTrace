"""Exercise every resolution and evidence branch without relying on live services."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work/backend"))
from profile_engine import compose_profile  # noqa: E402


BASE = json.loads((ROOT / "outputs/national_profile/validation/houston.json").read_text())


def profile(fixture: dict) -> dict:
    with patch("profile_engine._run_resolver", return_value=fixture):
        return compose_profile("100 Valid Test Street, Austin, TX 78701", use_cache=False)


def main() -> None:
    passed = []

    result = profile(BASE)
    assert result["resolution"]["status"] == "single_water_system_candidate"
    assert result["water_quality"]["sections"]
    assert "ml_decision_support" not in result
    assert result["infrastructure"]["display_status"] == "Infrastructure assessment available"
    assert "household_probability" not in result["infrastructure"]["assessment"]
    passed.append("single_system_enhanced_unknown_pipe")

    no_ccr = copy.deepcopy(BASE)
    no_ccr["consumer_confidence_report_profile"] = {
        "registry_available": True, "has_validated_ccr": False, "measurements": [],
        "reason": "No source-page-validated CCR has been admitted for this PWSID."
    }
    no_ccr["enhanced_connector"] = None
    result = profile(no_ccr)
    assert result["water_quality"]["availability"] == "provider_report_not_yet_checked"
    assert "prediction" not in result["infrastructure"]
    assert result["infrastructure"]["classification_status"] == "assessment_only"
    assert result["coverage"]["national_core_status"] == "complete"
    assert result["coverage"]["profile_is_valid_without_local_enhancement"] is True
    assert any(section["category"] == "federal_compliance" for section in result["water_quality"]["sections"])
    assert result["provider_resources"]["pwsid"] == "TX1010013"
    passed.append("national_system_without_validated_ccr")

    ambiguous = copy.deepcopy(no_ccr)
    ambiguous["resolution"] = "water_system_confirmation_required"
    ambiguous["selected_water_system_boundary"] = None
    ambiguous["federal_water_system_profile"] = None
    ambiguous["water_system_candidates"] = [BASE["water_system_candidates"][0], {**BASE["water_system_candidates"][0], "pwsid": "TX0000001"}]
    result = profile(ambiguous)
    assert result["resolution"]["requires_user_confirmation"] is True
    assert result["water_system"] is None
    passed.append("overlapping_systems")

    missing = copy.deepcopy(no_ccr)
    missing.update({
        "resolution": "address_not_geocoded", "geocoding": {"status": "not_found", "matches": []},
        "water_system_candidates": [], "selected_water_system_boundary": None,
        "federal_water_system_profile": None, "national_contaminant_profile": None,
        "consumer_confidence_report_profile": None,
    })
    result = profile(missing)
    assert result["resolution"]["status"] == "address_not_geocoded"
    assert result["water_system"] is None and result["water_quality"]["sections"] == []
    passed.append("address_not_geocoded")

    unmapped = copy.deepcopy(missing)
    unmapped["resolution"] = "no_mapped_public_water_system"
    unmapped["geocoding"] = BASE["geocoding"]
    result = profile(unmapped)
    assert result["resolution"]["status"] == "no_mapped_public_water_system"
    assert "Missing or unextracted" in result["safety"]["missing_data_rule"]
    passed.append("private_well_or_unmapped_system")

    well = copy.deepcopy(unmapped)
    well["private_well_context"] = {
        "status": "area_estimate_available", "estimated_well_use_percent_2010": 92,
        "likelihood_band": "high", "evidence_scope": "census_block_area_estimate_not_property_confirmation",
    }
    result = profile(well)
    assert result["water_source_assessment"]["private_well_context"]["likelihood_band"] == "high"
    assert result["water_source_assessment"]["property_well_status"] == "not_confirmed"
    assert any(action["type"] == "confirm_private_well" for action in result["recommended_actions"])
    passed.append("private_well_area_context_never_becomes_property_claim")

    violation = copy.deepcopy(BASE)
    violation["enhanced_connector"] = None
    violation["consumer_confidence_report_profile"]["measurements"][0]["violation"] = "yes"
    result = profile(violation)
    assert any(section["status"] == "attention" for section in result["water_quality"]["sections"])
    assert any(action["type"] == "review_utility_notice" for action in result["recommended_actions"])
    passed.append("reported_violation")

    assert all(
        item.get("home_specific") is False
        for section in result["water_quality"]["sections"]
        for item in section["measurements"]
    )
    passed.append("system_measurements_never_home_specific")

    assert "unknown" not in result["infrastructure"]["display_status"].lower()
    assert all(action.get("reason") and action.get("title") for action in result["recommended_actions"])
    assert "unverified" not in json.dumps(result).lower()
    passed.append("consumer_status_and_actions_are_explainable")
    print(json.dumps({"status": "PASS", "branches": passed, "branch_count": len(passed)}, indent=2))


if __name__ == "__main__":
    main()
