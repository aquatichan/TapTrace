"""Integration checks for TapTrace's layered national CCR coverage system."""

from __future__ import annotations

import csv
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_coverage_plan() -> None:
    plan = json.loads((ROOT / "outputs/national_ccr_coverage/population_coverage_plan.json").read_text())
    assert 0 < plan["current_coverage"] < 1
    ranks = [plan["milestones"][f"{target}_percent"]["additional_utilities_needed"] for target in (50, 75, 90, 95)]
    assert all(isinstance(rank, int) and rank > 0 for rank in ranks)
    assert ranks == sorted(ranks)


def test_adapter_registry() -> None:
    registry = json.loads((ROOT / "work/national_ccr/source_adapter_registry.json").read_text())
    kinds = {adapter["id"] for adapter in registry["adapters"] if adapter["status"] == "active"}
    assert {"official_pdf", "official_html", "state_tabular_bulk", "utility_structured_submission"} <= kinds


def test_state_bulk_staging() -> None:
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        source = temp / "state.csv"
        mapping = temp / "map.json"
        database = temp / "staged.sqlite"
        columns = ["id", "year", "name", "units", "value", "url"]
        with source.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerow({"id": "TX1234567", "year": "2025", "name": "Arsenic", "units": "ppb", "value": "1.2", "url": "https://example.gov/ccr.pdf"})
            writer.writerow({"id": "invalid", "year": "2025", "name": "Lead", "units": "ppb", "value": "2", "url": "http://example.com"})
        mapping.write_text(json.dumps({
            "pwsid": "id", "report_year": "year", "contaminant": "name",
            "unit": "units", "result": "value", "source_url": "url",
        }), encoding="utf-8")
        process = subprocess.run([
            sys.executable, str(ROOT / "work/national_ccr/import_state_ccr_table.py"),
            str(source), str(mapping), "--output-db", str(database),
        ], check=True, capture_output=True, text=True)
        result = json.loads(process.stdout)
        assert result == {"status": "PASS", "staged": 1, "rejected": 1, "automatic_admission": False}
        with sqlite3.connect(database) as connection:
            row = connection.execute("SELECT pwsid,adapter_status FROM staged_state_rows").fetchone()
        assert row == ("TX1234567", "review_required")


if __name__ == "__main__":
    test_coverage_plan()
    test_adapter_registry()
    test_state_bulk_staging()
    print("PASS: layered coverage planner, adapters, and guarded state staging")
