"""Scalable, fail-closed CCR acquisition and normalization pipeline.

This pipeline automates prioritization, source intake, text extraction, and
candidate-row staging. It deliberately does not auto-admit heterogeneous CCR
tables into the consumer registry without deterministic validation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
QUEUE_DB = ROOT / "outputs/national_ccr_coverage/ccr_coverage_queue.sqlite"
SOURCES = ROOT / "work/national_ccr/ccr_source_candidates.csv"
RAW = ROOT / "work/data/raw/ccr_2025"
OUT = ROOT / "outputs/national_ccr_pipeline"
DB = OUT / "national_ccr_pipeline.sqlite"
STAGED = OUT / "staged_measurement_candidates.csv"

CONTAMINANTS = {
    "lead": re.compile(r"\blead\b", re.I),
    "copper": re.compile(r"\bcopper\b", re.I),
    "arsenic": re.compile(r"\barsenic\b", re.I),
    "nitrate": re.compile(r"\bnitrate(?:s)?\b", re.I),
    "total trihalomethanes": re.compile(r"(?:total\s+)?trihalomethanes|\bTTHM\b", re.I),
    "haloacetic acids": re.compile(r"haloacetic\s+acids?|\bHAA5\b", re.I),
    "total coliform": re.compile(r"total\s+coliform", re.I),
    "radium": re.compile(r"combined\s+radium|radium[-\s]226|radium[-\s]228", re.I),
    "PFOA": re.compile(r"\bPFOA\b", re.I),
    "PFOS": re.compile(r"\bPFOS\b", re.I),
    "lithium": re.compile(r"\blithium\b", re.I),
}
UNIT = re.compile(r"\b(ppb|ppm|ppt|mg/L|ug/L|µg/L|ng/L|pCi/L|NTU|CFU|%)\b", re.I)
NUMBER = re.compile(r"(?<![A-Za-z])(?:<\s*)?-?\d+(?:\.\d+)?")
STATISTIC = re.compile(r"90th\s*percentile|highest\s+LRAA|LRAA|running\s+annual\s+average|range|average", re.I)
BENCHMARK = re.compile(r"\b(MCLG|MCL|MRDLG|MRDL|Action\s+Level|AL)\b", re.I)


def tls_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def connect() -> sqlite3.Connection:
    OUT.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB)
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            pwsid TEXT NOT NULL, report_year INTEGER NOT NULL, system_name TEXT,
            population_served INTEGER, source_url TEXT, source_format TEXT,
            status TEXT NOT NULL, status_detail TEXT, checked_at_utc TEXT NOT NULL,
            PRIMARY KEY (pwsid, report_year)
        );
        CREATE TABLE IF NOT EXISTS artifacts (
            pwsid TEXT NOT NULL, report_year INTEGER NOT NULL, local_file TEXT,
            sha256 TEXT, page_count INTEGER, identity_signal INTEGER,
            year_signal INTEGER, PRIMARY KEY (pwsid, report_year)
        );
        CREATE TABLE IF NOT EXISTS staged_candidates (
            pwsid TEXT NOT NULL, report_year INTEGER NOT NULL, source_page INTEGER NOT NULL,
            contaminant TEXT NOT NULL, source_line TEXT NOT NULL, unit_hint TEXT,
            number_hints TEXT, statistic_hint TEXT, benchmark_hint TEXT,
            extraction_confidence REAL NOT NULL, admission_status TEXT NOT NULL,
            UNIQUE (pwsid, report_year, source_page, contaminant, source_line)
        );
    """)
    return connection


def source_candidates() -> dict[str, dict]:
    with SOURCES.open(newline="", encoding="utf-8") as handle:
        return {row["pwsid"]: row for row in csv.DictReader(handle)}


def prioritized_jobs(limit: int) -> list[dict]:
    candidates = source_candidates()
    queue = sqlite3.connect(QUEUE_DB)
    queue.row_factory = sqlite3.Row
    rows = [dict(row) for row in queue.execute("""
        SELECT pwsid,pws_name,population_served FROM coverage_queue
        WHERE validation_status='pending' ORDER BY COALESCE(population_served,0) DESC
    """)]
    queue.close()
    jobs = []
    # Downloadable reviewed sources run first; the remaining national queue is
    # retained as discovery work rather than guessed URLs.
    rows.sort(key=lambda row: (row["pwsid"] not in candidates, -(row["population_served"] or 0)))
    for row in rows[:limit]:
        source = candidates.get(row["pwsid"])
        jobs.append({**row, "source": source})
    return jobs


def download(job: dict, offline: bool) -> tuple[Path | None, str]:
    source = job["source"]
    if not source:
        return None, "source_discovery_needed"
    extension = ".pdf" if source["format"] == "pdf" else ".html"
    path = RAW / f"{job['pwsid']}_{source['report_year']}{extension}"
    if path.exists():
        return path, "downloaded_or_cached"
    if offline:
        return None, "download_pending"
    url = source["official_url"]
    request = urllib.request.Request(url, headers={"User-Agent": "TapTrace-National-CCR/2.0"})
    with urllib.request.urlopen(request, timeout=120, context=tls_context()) as response:
        body = response.read(30_000_000)
    if source["format"] == "pdf" and not body.startswith(b"%PDF"):
        raise ValueError("official source did not return a PDF")
    RAW.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path, "downloaded_or_cached"


def pages(path: Path) -> list[str]:
    if path.suffix == ".pdf":
        return [(page.extract_text() or "") for page in PdfReader(path).pages]
    return [path.read_text(encoding="utf-8", errors="replace")]


def stage(connection: sqlite3.Connection, pwsid: str, year: int, path: Path) -> tuple[int, dict]:
    body = path.read_bytes()
    page_text = pages(path)
    full = "\n".join(page_text)
    identity = pwsid in re.sub(r"[^A-Z0-9]", "", full.upper())
    year_signal = str(year) in full
    connection.execute("INSERT OR REPLACE INTO artifacts VALUES (?,?,?,?,?,?,?)", (
        pwsid, year, str(path.relative_to(ROOT)), hashlib.sha256(body).hexdigest(),
        len(page_text), int(identity), int(year_signal),
    ))
    count = 0
    for page_number, text in enumerate(page_text, 1):
        for raw_line in text.splitlines():
            line = " ".join(raw_line.split())
            if len(line) < 6 or len(line) > 600:
                continue
            for contaminant, pattern in CONTAMINANTS.items():
                if not pattern.search(line):
                    continue
                unit = UNIT.search(line)
                numbers = NUMBER.findall(line)
                statistic = STATISTIC.search(line)
                benchmark = BENCHMARK.search(line)
                confidence = 0.25
                confidence += 0.2 if unit else 0
                confidence += 0.2 if numbers else 0
                confidence += 0.15 if statistic else 0
                confidence += 0.1 if benchmark else 0
                confidence += 0.05 if year_signal else 0
                # Even high extraction confidence does not establish column
                # semantics, report identity, or legal comparison validity.
                connection.execute("""INSERT OR IGNORE INTO staged_candidates
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (
                    pwsid, year, page_number, contaminant, line,
                    unit.group(0) if unit else None, json.dumps(numbers),
                    statistic.group(0) if statistic else None,
                    benchmark.group(0) if benchmark else None,
                    min(confidence, 0.95), "review_required",
                ))
                count += 1
                break
    return count, {"identity_signal": identity, "year_signal": year_signal, "pages": len(page_text)}


def export(connection: sqlite3.Connection) -> dict:
    columns = [row[1] for row in connection.execute("PRAGMA table_info(staged_candidates)")]
    rows = connection.execute("SELECT * FROM staged_candidates ORDER BY pwsid,report_year,source_page,contaminant").fetchall()
    with STAGED.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle); writer.writerow(columns); writer.writerows(rows)
    statuses = dict(connection.execute("SELECT status,COUNT(*) FROM jobs GROUP BY status").fetchall())
    return {
        "built_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "jobs": sum(statuses.values()), "job_statuses": statuses,
        "staged_candidate_rows": len(rows), "automatically_admitted_rows": 0,
        "policy": "Automation may discover, download, and stage evidence. Consumer admission requires deterministic identity, column, unit, statistic, benchmark, and source-page validation.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    connection = connect()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for job in prioritized_jobs(args.limit):
        source = job["source"]
        year = int(source["report_year"]) if source else 2025
        try:
            path, status = download(job, args.offline)
            detail = None
            if path:
                candidate_count, signals = stage(connection, job["pwsid"], year, path)
                status = "normalization_review_ready"
                detail = json.dumps({"candidate_rows": candidate_count, **signals}, separators=(",", ":"))
        except Exception as exc:
            path, status, detail = None, "intake_failed", type(exc).__name__
        connection.execute("INSERT OR REPLACE INTO jobs VALUES (?,?,?,?,?,?,?,?,?)", (
            job["pwsid"], year, job["pws_name"], job["population_served"],
            source["official_url"] if source else None, source["format"] if source else None,
            status, detail, now,
        ))
        connection.commit()
    summary = export(connection)
    connection.close()
    (OUT / "pipeline_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
