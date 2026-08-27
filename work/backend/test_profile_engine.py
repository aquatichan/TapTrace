"""Deterministic backend contract tests plus optional live resolution."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work/backend"))
from profile_engine import _category, compose_profile  # noqa: E402


FIXTURE = json.loads((ROOT / "outputs/national_profile/validation/houston.json").read_text())


def main() -> None:
    assert _category("Lead") == "lead_and_plumbing_metals"
    assert _category("PFOA") == "pfas"
    assert _category("Total Trihalomethanes") == "disinfection_and_byproducts"

    with patch("profile_engine._run_resolver", return_value=FIXTURE):
        profile = compose_profile("1344 Woodcrest Dr, Houston, TX 77018", use_cache=False)
    assert profile["water_system"]["pwsid"] == "TX1010013"
    assert profile["water_quality"]["home_specific"] is False
    assert profile["infrastructure"]["evidence_level"] == "official_property_record"
    assert "prediction" not in profile["infrastructure"]
    assert "model_support" not in profile["infrastructure"]
    assert "ml_decision_support" not in profile
    assert profile["schema_version"] == "3.0.0"
    assert profile["infrastructure"]["display_status"] == "Infrastructure assessment available"
    assert profile["infrastructure"]["classification_status"] == "assessment_only"
    assert profile["infrastructure"]["assessment"]["concern_level"] in {"Lower", "Moderate", "Elevated"}
    assert "household_probability" not in profile["infrastructure"]["assessment"]
    assert profile["infrastructure"]["confidence"]["score"] == 55
    assert "not the chance" in profile["infrastructure"]["confidence"]["meaning"]
    assert profile["profile_confidence"]["score"] >= 0
    assert "not a water-safety percentage" in profile["profile_confidence"]["meaning"]
    assert profile["water_quality"]["sections"]
    for section in profile["water_quality"]["sections"]:
        assert section["evidence_scope"] == "public_water_system"
        assert all(item["home_specific"] is False for item in section["measurements"])
    assert "Missing or unextracted" in profile["safety"]["missing_data_rule"]
    assert profile["data_quality"]["not_established"]
    assert profile["data_freshness"]["provider_report"]["status"] in {"current_or_recent", "older_report"}
    assert all(action.get("reason") for action in profile["recommended_actions"])
    assert "unverified" not in json.dumps(profile).lower()
    print(json.dumps({"status": "PASS", "contract": "water-profile-v3"}, indent=2))


if __name__ == "__main__":
    main()
