# TapTrace

TapTrace is an address-based U.S. drinking-water information backend. It resolves
an address to a public water system, combines official federal compliance data,
EPA UCMR monitoring, source-validated Consumer Confidence Report measurements,
service-line inventory context, and supported property-level infrastructure
records, then returns evidence-scoped actions.

TapTrace does **not** claim that utility monitoring describes water from one
faucet, and it does not generate household pipe-material predictions. A household
pipe classification appears only when a safe, unique official property record is
available.

## Current capabilities

- National address geocoding and EPA service-area matching
- SDWIS public-water-system and compliance records
- EPA UCMR 5 contaminant monitoring summaries
- Source-page-validated CCR normalization
- National service-line inventory context
- Property-level inventory connectors for Houston and DC Water
- Private-well area context without claiming property well ownership
- Evidence quality, source freshness, limitations, and actionable guidance
- Production HTTPS, Redis rate limiting, protected Prometheus metrics, backups,
  restore tooling, and health checks

## Repository layout

- `work/backend/` — API, profile composition, recommendations, operations, tests
- `work/national_profile/` — national address and water-system resolver
- `work/national_ccr/` — CCR discovery, staging, validation, and registry tools
- `work/national_contaminants/` — EPA UCMR registry tools
- `work/houston_profile/` — Houston property-inventory connector
- `docker-compose.production.yml` — production deployment stack

## Data assets

Downloaded government datasets and generated SQLite registries are intentionally
not stored in Git. The working research directory is several gigabytes and includes
files above GitHub's 100 MB limit. See [DATA_SETUP.md](DATA_SETUP.md) for authoritative
sources, expected local paths, and rebuild commands.

This separation keeps the public repository reviewable and prevents stale generated
data from being mistaken for source code. Production releases should version the
resulting registries separately and record their checksums.

## Local API

After preparing the data assets and installing dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r work/backend/requirements.txt
python work/backend/api.py --port 8080
```

Then request:

```text
GET http://127.0.0.1:8080/water-profile?address=1344%20Woodcrest%20Dr%2C%20Houston%2C%20TX%2077018
```

## Tests

Core tests are executable after the data setup:

```bash
python work/backend/test_profile_engine.py
python work/backend/test_backend_branches.py
python work/backend/test_national_profile_v2.py
python work/backend/test_operations.py
```

## Production

Copy `work/backend/.env.example` to `work/backend/.env`, replace every placeholder,
and follow [the deployment guide](docs/PRODUCTION_DEPLOYMENT.md).

```bash
docker compose -f docker-compose.production.yml up -d --build
```

Never embed `TAPTRACE_API_KEY` in a public browser or mobile client. Use a trusted
server-side proxy for authenticated production requests, or deliberately run the
public API without that shared secret and rely on strict rate limiting and CORS.

## Data and health disclaimer

TapTrace summarizes public records and system-level monitoring. It is not a medical
diagnosis, a real-time emergency notification service, or a laboratory test of a
specific faucet. Missing data never means a contaminant is absent. Follow current
instructions from the water provider and public-health authorities.

## License

MIT. Government and utility source data retain their original terms and attribution.

