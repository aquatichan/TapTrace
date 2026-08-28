"""Download DC Water's public premise material inventory for the runtime connector."""

from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
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
WORKERS = 4


def get_json(url: str, params: dict[str, str] | None = None) -> dict:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "TapTrace-Day1-Audit/1.0"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
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
    (OUT_DIR / "layer_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    id_payload = get_json(f"{BASE}/query", {"where": "1=1", "returnIdsOnly": "true", "f": "json"})
    object_ids = sorted(int(value) for value in id_payload["objectIds"])
    count = len(object_ids)
    batches = [object_ids[index:index + PAGE_SIZE] for index in range(0, count, PAGE_SIZE)]

    def fetch(batch: list[int]) -> list[dict]:
        payload = post_json(f"{BASE}/query", {
            "objectIds": ",".join(map(str, batch)), "outFields": ",".join(FIELDS),
            "returnGeometry": "false", "orderByFields": "OBJECTID ASC", "f": "json",
        })
        if "error" in payload:
            raise RuntimeError(payload["error"])
        return payload.get("features", [])
    output = OUT_DIR / "dc_water_inventory_raw.csv"
    partial = output.with_suffix(output.suffix + ".part")
    written = 0
    with partial.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for batch_number, features in enumerate(pool.map(fetch, batches), 1):
                for feature in features:
                    writer.writerow({field: feature["attributes"].get(field) for field in FIELDS})
                written += len(features)
                if batch_number == 1 or batch_number % 10 == 0:
                    print(f"downloaded {written:,}/{count:,}", flush=True)
    manifest = {
        "source_url": BASE,
        "downloaded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "expected_rows": count,
        "rows_written": written,
        "fields": FIELDS,
    }
    if written != count:
        raise RuntimeError(f"row mismatch: wrote {written}, expected {count}")
    partial.replace(output)
    manifest_partial = OUT_DIR / "download_manifest.json.part"
    manifest_partial.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    manifest_partial.replace(OUT_DIR / "download_manifest.json")
    print(output)


if __name__ == "__main__":
    main()
