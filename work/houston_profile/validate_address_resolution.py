"""Integration checks for exact, normalized, duplicate-source, and missing matches."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "work/houston_profile/resolve_houston_address.py"
OUT = ROOT / "outputs/houston_profile/address_validation"
OUT.mkdir(parents=True, exist_ok=True)


def run(address: str, name: str) -> dict:
    path = OUT / f"{name}.json"
    subprocess.run([sys.executable, str(SCRIPT), address, "--output", str(path)], check=True)
    return json.loads(path.read_text())


ordinary = run("1344 Woodcrest Drive, Houston, TX 77018", "ordinary_exact")
assert ordinary["normalized_street_address"] == "1344 WOODCREST DR"
assert ordinary["resolution"] == "safe_single_service_match"
assert ordinary["selected_service"]["addrkey"] == 100001
assert ordinary["generated_profile"]

collapsed = run("1518 Du Barry Lane, Houston TX 77018", "collapsed_duplicate_sources")
assert collapsed["resolution"] == "safe_single_service_match"
assert collapsed["logical_service_candidates"] == 1
assert collapsed["selected_service"]["source_row_count"] == 264

ambiguous = run("7101 Keller Street, Houston TX 77087", "multiple_logical_services")
assert ambiguous["resolution"] == "service_confirmation_required"
assert ambiguous["logical_service_candidates"] == 42
assert ambiguous["generated_profile"] is None

missing = run("999999 Definitely Not A Houston Street, Houston TX 77018", "not_found")
assert missing["resolution"] == "not_found"
assert missing["generated_profile"] is None

summary = {
    "status": "PASS",
    "exact_normalized_address": True,
    "addrkey_join": True,
    "duplicate_source_rows_collapsed": True,
    "multiple_real_services_require_confirmation": True,
    "missing_address_does_not_generate_profile": True,
    "ordinary_test_addrkey": 100001,
    "duplicate_test_source_rows": 264,
    "ambiguous_test_logical_services": 42,
}
(OUT / "validation_summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
