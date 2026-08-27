"""Validate fail-closed invariants for the automated national CCR pipeline."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "outputs/national_ccr_pipeline/national_ccr_pipeline.sqlite"


def main() -> None:
    connection = sqlite3.connect(DB)
    jobs = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    staged = connection.execute("SELECT COUNT(*) FROM staged_candidates").fetchone()[0]
    bad_pages = connection.execute("SELECT COUNT(*) FROM staged_candidates WHERE source_page < 1").fetchone()[0]
    automatic = connection.execute("SELECT COUNT(*) FROM staged_candidates WHERE admission_status='admitted_automatically'").fetchone()[0]
    reviewed = connection.execute("SELECT COUNT(*) FROM staged_candidates WHERE admission_status='review_complete_normalized_separately'").fetchone()[0]
    missing_evidence = connection.execute("SELECT COUNT(*) FROM staged_candidates WHERE source_line='' OR contaminant='' OR extraction_confidence<0 OR extraction_confidence>1").fetchone()[0]
    connection.close()
    assert jobs > 0 and staged > 0
    assert bad_pages == automatic == missing_evidence == 0
    print(json.dumps({
        "status": "PASS", "jobs": jobs, "staged_candidates": staged,
        "automatic_admissions": automatic, "reviewed_evidence_rows": reviewed, "invalid_source_pages": bad_pages,
        "invalid_evidence_rows": missing_evidence,
    }, indent=2))


if __name__ == "__main__":
    main()
