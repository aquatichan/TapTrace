# Production deployment

The production stack includes Caddy automatic HTTPS, the TapTrace API, Redis shared
rate limiting, private Prometheus monitoring, persistent state, and automated backups.

1. Provision a Linux host with Docker Compose and persistent storage.
2. Point the API domain to the host and open ports 80 and 443.
3. Copy `work/backend/.env.example` to `work/backend/.env` and replace all placeholders.
4. Start the stack from the repository root:

   `docker compose -f docker-compose.production.yml up -d --build`

5. Confirm `https://YOUR_DOMAIN/health` reports `status: ok`.
6. Configure an alert-delivery integration and an optional private S3 backup bucket.
7. Perform and document a restore drill before public launch.

The API metrics endpoint is blocked at the public proxy and available only to the
private Prometheus service. Metrics never retain addresses, query strings, API keys,
or raw client IPs.

Daily writable-state backups use SQLite's online backup API, integrity checks, and
SHA-256 manifests. Restore tooling is in `work/backend/restore_backup.py`.

