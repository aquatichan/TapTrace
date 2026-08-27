"""Download and inspect an official CCR before human validation/admission."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "work/data/raw/ccr_2025"
REVIEW = ROOT / "outputs/national_ccr_review"
PWSID_PATTERN = re.compile(r"^(?:[A-Z]{2}\d{7}|UTAH\d{5})$")
SIGNALS = {
    "lead": re.compile(r"\blead\b", re.I),
    "copper": re.compile(r"\bcopper\b", re.I),
    "pfas": re.compile(r"\b(?:PFAS|PFOA|PFOS|HFPO.DA|GenX)\b", re.I),
    "nitrate": re.compile(r"\bnitrat(?:e|es)\b", re.I),
    "disinfection_byproducts": re.compile(r"trihalomethane|haloacetic", re.I),
    "violation": re.compile(r"\bviolation\b", re.I),
}


def tls_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pwsid")
    parser.add_argument("report_year", type=int)
    parser.add_argument("official_url")
    args = parser.parse_args()
    pwsid = args.pwsid.strip().upper()
    if not PWSID_PATTERN.fullmatch(pwsid):
        raise ValueError("invalid PWSID")
    parsed = urllib.parse.urlparse(args.official_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("official_url must be HTTPS")

    request = urllib.request.Request(args.official_url, headers={"User-Agent": "TapTrace-CCR-Intake/1.0"})
    with urllib.request.urlopen(request, timeout=120, context=tls_context()) as response:
        content_type = response.headers.get_content_type()
        body = response.read(30_000_000)
    if not body.startswith(b"%PDF"):
        raise ValueError(f"expected PDF, received {content_type}")
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / f"{pwsid}_{args.report_year}.pdf"
    path.write_bytes(body)
    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    page_count = len(pages)
    full_text = "\n".join(pages)
    pwsid_present = pwsid in re.sub(r"[^A-Z0-9]", "", full_text.upper())
    report_year_present = str(args.report_year) in full_text
    candidates = {}
    for name, pattern in SIGNALS.items():
        hits = [index for index, text in enumerate(pages, 1) if pattern.search(text)]
        candidates[name] = hits
    review = {
        "admission_status": "review_required",
        "pwsid": pwsid,
        "report_year": args.report_year,
        "official_url": args.official_url,
        "source_hostname": parsed.hostname,
        "local_file": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(body).hexdigest(),
        "pdf_pages": page_count,
        "pwsid_text_match": pwsid_present,
        "report_year_text_match": report_year_present,
        "candidate_pages": candidates,
        "automatic_validation": False,
        "review_requirements": [
            "Confirm document-to-PWSID identity even if the ID is omitted from the PDF.",
            "Confirm report year separately from measurement/data year.",
            "Normalize units, sample scope, statistic type, benchmark, and violation status.",
            "Retain exact source page and footnote meaning.",
            "Do not admit OCR-only or ambiguous values without review.",
        ],
    }
    REVIEW.mkdir(parents=True, exist_ok=True)
    output = REVIEW / f"{pwsid}_{args.report_year}.json"
    output.write_text(json.dumps(review, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
