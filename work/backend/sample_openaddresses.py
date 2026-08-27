"""Deterministically sample address rows from regional OpenAddresses archives."""

from __future__ import annotations

import argparse
import csv
import io
import random
import zipfile
from collections import defaultdict
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--per-state", type=int, default=24)
    parser.add_argument("--seed", type=int, default=20260826)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    samples: dict[str, list[dict]] = defaultdict(list)
    seen = defaultdict(int)
    for archive in args.archives:
        with zipfile.ZipFile(archive) as bundle:
            members = [name for name in bundle.namelist() if name.startswith("us/") and name.endswith(".csv")]
            for member in members:
                parts = member.split("/")
                if len(parts) < 3:
                    continue
                state = parts[1].upper()
                with bundle.open(member) as raw:
                    rows = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline=""))
                    for row in rows:
                        number, street = (row.get("NUMBER") or "").strip(), (row.get("STREET") or "").strip()
                        city, postcode = (row.get("CITY") or "").strip(), (row.get("POSTCODE") or "").strip()
                        if not number or not street or (not city and not postcode):
                            continue
                        try:
                            lon, lat = float(row["LON"]), float(row["LAT"])
                        except (TypeError, ValueError):
                            continue
                        candidate = {
                            "state": state, "address": f"{number} {street}, {city}, {state} {postcode}".replace(", ,", ","),
                            "longitude": lon, "latitude": lat, "unit": (row.get("UNIT") or "").strip(),
                            "source": f"OpenAddresses 2021:{member}",
                        }
                        seen[state] += 1
                        bucket = samples[state]
                        if len(bucket) < args.per_state:
                            bucket.append(candidate)
                        else:
                            index = rng.randrange(seen[state])
                            if index < args.per_state:
                                bucket[index] = candidate
    output = []
    for state in sorted(samples):
        for index, row in enumerate(samples[state], 1):
            output.append({"case_id": f"OA_{state}_{index:03d}", **row})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=output[0].keys()); writer.writeheader(); writer.writerows(output)
    print({"rows": len(output), "states": len(samples), "per_state_target": args.per_state})


if __name__ == "__main__":
    main()
