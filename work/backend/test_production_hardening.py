"""Security, provenance, freshness, local-inventory, and throughput checks."""

from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work/backend"))
sys.path.insert(0, str(ROOT / "work/national_profile"))
from profile_engine import compose_profile  # noqa: E402
from resolve_national_address import dc_property_record  # noqa: E402


FIXTURE = json.loads((ROOT / "outputs/national_profile/validation/houston.json").read_text())


def main() -> None:
    dc = dc_property_record("420 W ST NW, Washington, DC 20001")
    assert dc and dc["record_id"] == "1"
    assert dc["evidence_scope"] == "official_property_inventory_record"

    with patch("profile_engine._run_resolver", return_value=FIXTURE):
        profile = compose_profile("100 Valid Test Street, Houston, TX 77002", use_cache=False)
        assert profile["data_freshness"]["provider_report"]["source_integrity_status"] in {
            "unchanged", "changed_review_required", "not_checked"
        }
        assert "ml_decision_support" not in profile
        serialized = json.dumps(profile).lower()
        assert "household_probability" not in serialized
        assert "consumer_pipe_probability" not in serialized

        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(
                lambda n: compose_profile(f"{100 + n} Valid Test Street, Houston, TX 77002", use_cache=False),
                range(500),
            ))
        elapsed = time.perf_counter() - started
    assert len(results) == 500
    assert all(row["schema_version"] == "3.0.0" for row in results)
    print(json.dumps({
        "status": "PASS", "profiles": len(results), "workers": 16,
        "elapsed_seconds": round(elapsed, 3),
        "profiles_per_second": round(len(results) / elapsed, 1),
        "scope": "profile composition with resolver mocked; not live upstream capacity",
    }, indent=2))


if __name__ == "__main__":
    main()
