"""Publish benchmark evidence without publishing residential addresses."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("private_jsonl", type=Path)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--salt", required=True)
    args = parser.parse_args()
    latest = {}
    for line in args.private_jsonl.read_text(encoding="utf-8").splitlines():
        row = json.loads(line); latest[row["case_id"]] = row
    rows = []
    for row in latest.values():
        address = row.pop("address", "")
        row.pop("matched_address", None)
        row.pop("longitude", None); row.pop("latitude", None)
        row["address_hash"] = hashlib.sha256(f"{args.salt}|{address.upper()}".encode()).hexdigest()
        rows.append(row)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with (args.output_dir / "redacted_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    summary["privacy"] = "Raw addresses and coordinates excluded; salted hashes only."
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print({"status": "PASS", "redacted_rows": len(rows)})


if __name__ == "__main__":
    main()
