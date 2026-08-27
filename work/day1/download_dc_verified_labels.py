"""Download DC Water's public premise material inventory for model-label fallback."""

from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path


BASE = "https://geo.dcwater.com/arcgis/rest/services/Public/WaterServiceInfo_LPRAP/MapServer/1"
OUT_DIR = Path("work/data/raw/dc_water_inventory")
FIELDS = [
    "OBJECTID",
    "PremiseAddress",
    "Pub_Display_Category",
    "PublicServiceMaterialType",
    "Priv_Display_Category",
    "PrivateServiceMaterialType",
    "POE_Description",
    "POEServiceMaterialType",
    "POEServiceMaterialOrigin",
    "Display_Category",
    "PublicServiceReplacementDate",
    "PublicServiceInspectionDate",
    "PrivateServiceReplacementDate",
    "PrivateServiceInspectionDate",
    "POEServiceInspectionDate",
    "Latitude",
    "Longitude",
]
PAGE_SIZE = 2000


def get_json(url: str, params: dict[str, str] | None = None) -> dict:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "TapTrace-Day1-Audit/1.0"})
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.load(response)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    metadata = get_json(BASE, {"f": "json"})
    (OUT_DIR / "layer_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    count = int(get_json(f"{BASE}/query", {"where": "1=1", "returnCountOnly": "true", "f": "json"})["count"])
    output = OUT_DIR / "dc_water_inventory_raw.csv"
    written = 0
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for offset in range(0, count, PAGE_SIZE):
            payload = get_json(
                f"{BASE}/query",
                {
                    "where": "1=1",
                    "outFields": ",".join(FIELDS),
                    "returnGeometry": "false",
                    "orderByFields": "OBJECTID ASC",
                    "resultOffset": str(offset),
                    "resultRecordCount": str(PAGE_SIZE),
                    "f": "json",
                },
            )
            if "error" in payload:
                raise RuntimeError(payload["error"])
            features = payload.get("features", [])
            for feature in features:
                writer.writerow({field: feature["attributes"].get(field) for field in FIELDS})
            written += len(features)
            if not features:
                break
            if offset % 20000 == 0:
                print(f"downloaded {written:,}/{count:,}", flush=True)
    manifest = {
        "source_url": BASE,
        "downloaded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "expected_rows": count,
        "rows_written": written,
        "fields": FIELDS,
    }
    (OUT_DIR / "download_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if written != count:
        raise RuntimeError(f"row mismatch: wrote {written}, expected {count}")
    print(output)


if __name__ == "__main__":
    main()
