"""Build a population-first CCR acquisition plan and target milestones."""

from __future__ import annotations

import csv
import gzip
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "outputs/national_ccr_coverage/ccr_coverage_queue.sqlite"
OUT = ROOT / "outputs/national_ccr_coverage/population_coverage_plan.csv.gz"
SUMMARY = ROOT / "outputs/national_ccr_coverage/population_coverage_plan.json"
TARGETS = (0.50, 0.75, 0.90, 0.95)


def main() -> None:
    connection = sqlite3.connect(DB)
    connection.row_factory = sqlite3.Row
    rows = [dict(row) for row in connection.execute("""
        SELECT pwsid,pws_name,primacy_agency,COALESCE(population_served,0) population_served,
               validation_status,report_status,next_action
        FROM coverage_queue ORDER BY population_served DESC,pwsid
    """)]
    connection.close()
    total = sum(row["population_served"] for row in rows)
    validated_population = sum(row["population_served"] for row in rows if row["validation_status"] == "validated")
    pending = [row for row in rows if row["validation_status"] != "validated"]
    cumulative = validated_population
    plan = []
    for rank, row in enumerate(pending, 1):
        cumulative += row["population_served"]
        plan.append({
            "priority_rank": rank, **row,
            "projected_population_covered": cumulative,
            "projected_population_coverage": cumulative / total if total else 0,
        })
    milestones = {}
    for target in TARGETS:
        reached = next((row for row in plan if row["projected_population_coverage"] >= target), None)
        milestones[f"{int(target*100)}_percent"] = {
            "additional_utilities_needed": reached["priority_rank"] if reached else None,
            "last_pwsid": reached["pwsid"] if reached else None,
            "projected_coverage": reached["projected_population_coverage"] if reached else validated_population / total,
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=plan[0].keys())
        writer.writeheader(); writer.writerows(plan)
    result = {
        "population_basis": "non-deduplicated mapped population; service areas can overlap",
        "mapped_population": total,
        "currently_validated_population": validated_population,
        "current_coverage": validated_population / total if total else 0,
        "pending_systems": len(pending),
        "milestones": milestones,
        "strategy": "Acquire in descending population order; state bulk imports and reusable utility parsers can move multiple ranks at once.",
    }
    SUMMARY.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
