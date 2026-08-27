"""Download the public Houston LCRR inventory without owner/contact fields.

Source: City of Houston LCRR Inventory Public View (ArcGIS FeatureServer).
The script paginates deterministically by OBJECTID and preserves the raw
attributes exactly as returned by the public service.
"""

from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


BASE = (
    "https://services1.arcgis.com/VVapzOPgBae5joyC/arcgis/rest/services/"
    "Houston_TX_LCRR_Inventory_Public_View/FeatureServer/0"
)
OUT_DIR = Path("work/data/raw/houston_lcrr_inventory")
FIELDS = [
    "OBJECTID",
    "ADDRKEY",
    "COMPKEY",
    "LATITUDE",
    "LONGITUDE",
    "ZipCode",
    "PWSID",
    "Utility_Side_Category",
    "Customer_Side_Category",
    "Both_Sides_Category",
]
PAGE_SIZE = 2000
WORKERS = 4


def get_json(url: str, params: dict[str, str] | None = None) -> dict:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "TapTrace-Day1-Audit/1.0"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.load(response)
        except Exception:
            if attempt == 4:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def post_json(url: str, params: dict[str, str]) -> dict:
    request = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode(), headers={"User-Agent": "TapTrace-Data-Installer/1.0"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.load(response)
        except Exception:
            if attempt == 4:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    metadata = get_json(BASE, {"f": "json"})
    (OUT_DIR / "layer_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    id_payload = get_json(f"{BASE}/query", {"where": "1=1", "returnIdsOnly": "true", "f": "json"})
    object_ids = sorted(int(value) for value in id_payload["objectIds"])
    expected = len(object_ids)
    batches = [object_ids[index:index + PAGE_SIZE] for index in range(0, expected, PAGE_SIZE)]

    def fetch(batch: list[int]) -> list[dict]:
        payload = post_json(f"{BASE}/query", {
            "objectIds": ",".join(map(str, batch)), "outFields": ",".join(FIELDS),
            "returnGeometry": "false", "orderByFields": "OBJECTID ASC", "f": "json",
        })
        if "error" in payload:
            raise RuntimeError(payload["error"])
        return payload.get("features", [])
    output_path = OUT_DIR / "houston_lcrr_inventory_raw.csv"
    rows_written = 0
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for batch_number, features in enumerate(pool.map(fetch, batches), 1):
                for feature in features:
                    writer.writerow({field: feature["attributes"].get(field) for field in FIELDS})
                rows_written += len(features)
                if batch_number == 1 or batch_number % 20 == 0:
                    print(f"downloaded {rows_written:,}/{expected:,}", flush=True)
    manifest = {
        "source_url": BASE,
        "downloaded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "expected_rows": expected,
        "rows_written": rows_written,
        "fields": FIELDS,
        "excluded_personal_fields": True,
    }
    (OUT_DIR / "download_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    if rows_written != expected:
        raise RuntimeError(f"row mismatch: wrote {rows_written}, expected {expected}")
    print(output_path)


if __name__ == "__main__":
    main()
