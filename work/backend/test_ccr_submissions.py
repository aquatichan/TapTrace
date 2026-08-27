"""Contract tests for structured review-only CCR submissions."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work/backend"))
import ccr_submissions  # noqa: E402


def main() -> None:
    test_db = ROOT / "outputs/backend/test_ccr_submissions.sqlite"
    if test_db.exists():
        test_db.unlink()
    with patch.object(ccr_submissions, "DB", test_db):
        result = ccr_submissions.submit({
            "pwsid": "TX1010013", "system_name": "City of Houston Main System",
            "report_year": 2026, "source_url": "https://example.gov/official-ccr.pdf",
        })
        assert result["status"] == "source_review_pending"
        connection = sqlite3.connect(test_db)
        row = connection.execute("SELECT pwsid,status FROM submissions").fetchone()
        connection.close()
        assert row == ("TX1010013", "source_review_pending")
        for bad in (
            {"pwsid": "bad", "system_name": "x", "report_year": 2026, "source_url": "https://example.gov/a.pdf"},
            {"pwsid": "TX1010013", "system_name": "x", "report_year": 2026, "source_url": "http://example.gov/a.pdf"},
        ):
            try:
                ccr_submissions.submit(bad)
                raise AssertionError("invalid submission accepted")
            except ValueError:
                pass
    test_db.unlink()
    print({"status": "PASS", "workflow": "review_only"})


if __name__ == "__main__":
    main()
