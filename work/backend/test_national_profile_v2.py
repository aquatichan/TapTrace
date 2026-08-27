"""Validate the v3 consumer contract across stored national address fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work/backend"))
from profile_engine import compose_profile  # noqa: E402


def main() -> None:
    fixture_dir = ROOT / "outputs/national_profile/validation"
    results = []
    for path in sorted(fixture_dir.glob("*.json")):
        if path.name == "validation_summary.json":
            continue
        fixture = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(fixture, dict) or "resolution" not in fixture:
            continue
        with patch("profile_engine._run_resolver", return_value=fixture):
            profile = compose_profile("100 National Contract Test Street, Austin, TX 78701", use_cache=False)
        encoded = json.dumps(profile).lower()
        assert profile["schema_version"] == "3.0.0"
        assert "ml_decision_support" not in profile
        assert "prediction" not in profile["infrastructure"]
        assert "profile_confidence" in profile
        assert 0 <= profile["profile_confidence"]["score"] <= 100
        assert "unverified" not in encoded
        assert all(action.get("reason") for action in profile["recommended_actions"])
        if profile["water_system"]:
            assert profile["infrastructure"]["display_status"]
            assessment = profile["infrastructure"]["assessment"]
            assert "household_probability" not in assessment
            assert 0 <= profile["infrastructure"]["confidence"]["score"] <= 100
        results.append({
            "fixture": path.stem,
            "resolution": profile["resolution"]["status"],
            "pwsid": (profile["water_system"] or {}).get("pwsid"),
            "confidence": profile["profile_confidence"]["score"],
            "infrastructure": profile["infrastructure"]["display_status"],
            "actions": len(profile["recommended_actions"]),
        })
    assert len(results) >= 10
    print(json.dumps({"status": "PASS", "fixture_count": len(results), "results": results}, indent=2))


if __name__ == "__main__":
    main()
