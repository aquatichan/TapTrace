"""Live integration tests across multiple US states and a missing address."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "work/national_profile/resolve_national_address.py"
OUT = ROOT / "outputs/national_profile/validation"
OUT.mkdir(parents=True, exist_ok=True)

CASES = {
    "houston": ("1344 Woodcrest Dr, Houston, TX 77018", "TX1010013"),
    "washington_dc": ("1600 Pennsylvania Ave NW, Washington, DC 20500", "DC0000002"),
    "new_york": ("350 5th Ave, New York, NY 10118", "NY7003493"),
    "san_francisco": ("1 Dr Carlton B Goodlett Pl, San Francisco, CA 94102", "CA3810011"),
    "los_angeles": ("200 N Spring St, Los Angeles, CA 90012", "CA1910067"),
    "phoenix": ("200 W Washington St, Phoenix, AZ 85003", "AZ0407025"),
    "philadelphia": ("1400 John F Kennedy Blvd, Philadelphia, PA 19107", "PA1510001"),
    "miami_dade": ("111 NW 1st St, Miami, FL 33128", "FL4130871"),
    "san_antonio": ("100 Military Plaza, San Antonio, TX 78205", "TX0150018"),
    "baltimore": ("100 Holliday St, Baltimore, MD 21202", "MD0300002"),
    "las_vegas": ("495 S Main St, Las Vegas, NV 89101", "NV0000090"),
    "san_diego": ("202 C St, San Diego, CA 92101", "CA3710020"),
    "denver": ("1437 Bannock St, Denver, CO 80202", "CO0116001"),
}

results = {}
for name, (address, expected_pwsid) in CASES.items():
    path = OUT / f"{name}.json"
    command = [sys.executable, str(SCRIPT), address, "--output", str(path)]
    if name != "houston":
        command.append("--skip-enhanced")
    subprocess.run(command, check=True)
    data = json.loads(path.read_text())
    assert data["geocoding"]["status"] == "matched"
    assert data["selected_water_system_boundary"]["pwsid"] == expected_pwsid
    assert data["federal_water_system_profile"]["pwsid"] == expected_pwsid
    assert data["federal_water_system_profile"]["evidence_level"] in {
        "official_federal_system_record", "official_federal_quarterly_registry"
    }
    assert data["national_contaminant_profile"]["has_ucmr5_results"]
    assert data["consumer_confidence_report_profile"]["has_validated_ccr"]
    assert data["consumer_confidence_report_profile"]["measurements"]
    assert all(x["home_specific"] is False for x in data["consumer_confidence_report_profile"]["measurements"])
    results[name] = {
        "pwsid": expected_pwsid,
        "resolution": data["resolution"],
        "profile_tier": data["profile_tier"],
        "boundary_confidence": data["selected_water_system_boundary"]["boundary_confidence"],
    }

missing_path = OUT / "missing.json"
subprocess.run([
    sys.executable, str(SCRIPT),
    "999999 Definitely Not A Real Street, Nowhere, TX 00000",
    "--skip-enhanced", "--output", str(missing_path),
], check=True)
missing = json.loads(missing_path.read_text())
assert missing["resolution"] == "address_not_geocoded"
assert missing["federal_water_system_profile"] is None

summary = {
    "status": "PASS",
    "states_or_districts_tested": ["TX", "DC", "NY", "CA", "AZ", "PA", "FL", "MD", "NV", "CO"],
    "successful_multistate_cases": len(results),
    "invalid_address_safe_failure": True,
    "houston_enhanced_connector_exercised": True,
    "cases": results,
}
(OUT / "validation_summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
