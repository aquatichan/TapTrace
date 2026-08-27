"""Record completed human review after normalized rows pass registry validation."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "outputs/national_ccr_pipeline/national_ccr_pipeline.sqlite"
REGISTRY = ROOT / "outputs/national_ccr/taptrace_ccr.sqlite"
ADMITTED = {"CA0110005": 10, "OH1801212": 8, "VA6059501": 11}


def main() -> None:
    registry = sqlite3.connect(REGISTRY)
    pipeline = sqlite3.connect(PIPELINE)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    results = []
    for pwsid, expected in ADMITTED.items():
        report = registry.execute("SELECT validation_status FROM reports WHERE pwsid=? AND report_year=2025", (pwsid,)).fetchone()
        count = registry.execute("SELECT COUNT(*) FROM measurements WHERE pwsid=? AND report_year=2025", (pwsid,)).fetchone()[0]
        if not report or report[0] != "validated" or count != expected:
            raise RuntimeError(f"registry admission mismatch for {pwsid}: {count} rows")
        detail = json.dumps({
            "review_completed": True, "normalized_measurements_admitted": count,
            "candidate_lines_were_evidence_not_direct_imports": True,
        }, separators=(",", ":"))
        pipeline.execute("UPDATE jobs SET status='admitted_to_validated_registry',status_detail=?,checked_at_utc=? WHERE pwsid=?", (detail, now, pwsid))
        pipeline.execute("UPDATE staged_candidates SET admission_status='review_complete_normalized_separately' WHERE pwsid=?", (pwsid,))
        results.append({"pwsid": pwsid, "normalized_measurements_admitted": count})
    pipeline.commit(); pipeline.close(); registry.close()
    print(json.dumps({"status": "PASS", "reports_admitted": len(results), "results": results}, indent=2))


if __name__ == "__main__":
    main()
