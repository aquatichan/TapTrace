# TapTrace data setup

The source repository excludes downloaded and generated datasets. Build them from
official sources before running the complete backend.

## Required production assets

| Local asset | Purpose | Builder / source |
|---|---|---|
| `outputs/backend/sdwis_system_registry.sqlite` | National systems and compliance | `work/backend/build_sdwis_registry.py` |
| `outputs/national_contaminants/taptrace_ucmr5.sqlite` | EPA UCMR 5 summaries | `work/national_contaminants/build_ucmr5_registry.py` |
| `outputs/national_ccr/taptrace_ccr.sqlite` | Validated CCR measurements | `work/national_ccr/build_ccr_registry.py` |
| `work/data/raw/national_city_audit/SDWIS_service_line_inventory_USA_2026Q1.csv` | System service-line totals | EPA SDWIS service-line inventory download |
| `work/data/raw/houston_lcrr_inventory/houston_lcrr_inventory_raw.csv` | Houston property records | `work/day1/download_houston_inventory.py` |
| `work/data/raw/dc_water_inventory/dc_water_inventory_raw.csv` | DC Water property records | `work/day1/download_dc_verified_labels.py` |

The builders and downloaders record source metadata and validation results under
`outputs/`. Use a current quarterly source and update filenames/constants together;
do not silently relabel an older snapshot as current.

## Typical rebuild order

```bash
pip install -r work/backend/requirements.txt
python work/backend/build_sdwis_registry.py --help
python work/national_contaminants/build_ucmr5_registry.py
python work/national_ccr/build_ccr_registry.py
python work/national_contaminants/validate_ucmr5_registry.py
python work/national_ccr/validate_ccr_registry.py
```

Some builders require the official bulk archives to be downloaded first. Run each
command with `--help`, inspect its declared input paths, and retain the official URL,
retrieval date, checksum, reporting period, and validation output with every release.

Do not commit full addresses, benchmark samples, API caches, user submissions, or
secrets. Generated registries should be distributed as versioned release artifacts
or rebuilt during a controlled data-release process.

