"""Structured utility CCR source submissions with a review-only workflow."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]
DB = Path(os.getenv("TAPTRACE_STATE_DIR", ROOT / "outputs/backend")) / "ccr_submissions.sqlite"
PWSID = re.compile(r"^(?:[A-Z]{2}\d{7}|UTAH\d{5})$")


def submit(payload: dict) -> dict:
    pwsid = str(payload.get("pwsid", "")).strip().upper()
    source_url = str(payload.get("source_url", "")).strip()
    system_name = str(payload.get("system_name", "")).strip()
    try:
        report_year = int(payload.get("report_year"))
    except (TypeError, ValueError):
        raise ValueError("report_year must be a four-digit year")
    parsed = urlparse(source_url)
    if not PWSID.fullmatch(pwsid):
        raise ValueError("invalid PWSID")
    if not system_name or len(system_name) > 200:
        raise ValueError("system_name is required and must be at most 200 characters")
    if report_year < 2000 or report_year > 2100:
        raise ValueError("report_year is outside the accepted range")
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("source_url must be HTTPS")
    submission_id = uuid.uuid4().hex
    DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB)
    connection.execute("""CREATE TABLE IF NOT EXISTS submissions (
        submission_id TEXT PRIMARY KEY,pwsid TEXT,system_name TEXT,report_year INTEGER,
        source_url TEXT,status TEXT,submitted_at_utc TEXT,review_notes TEXT
    )""")
    connection.execute("INSERT INTO submissions VALUES (?,?,?,?,?,?,?,?)", (
        submission_id, pwsid, system_name, report_year, source_url,
        "source_review_pending", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), None,
    ))
    connection.commit(); connection.close()
    return {
        "submission_id": submission_id, "pwsid": pwsid,
        "status": "source_review_pending",
        "message": "Source received. It will not affect consumer profiles until provenance and measurements pass validation.",
    }
