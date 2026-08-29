"""Dependency-free HTTP API for the TapTrace unified water profile."""

from __future__ import annotations

import json
import hashlib
import calendar
import os
import secrets
import time
import uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from profile_engine import compose_profile, initialize_state
from ccr_submissions import submit as submit_ccr_source
from operations import Metrics, RateLimiter


ROOT = Path(__file__).resolve().parents[2]
COVERAGE_SUMMARY = ROOT / "outputs/national_ccr_coverage/coverage_summary.json"
COVERAGE_PLAN = ROOT / "outputs/national_ccr_coverage/population_coverage_plan.json"
MAX_BODY_BYTES = int(os.getenv("TAPTRACE_MAX_BODY_BYTES", "10000"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("TAPTRACE_RATE_LIMIT_PER_MINUTE", "60"))
API_KEY = os.getenv("TAPTRACE_API_KEY")
ALLOWED_ORIGINS = {item.strip() for item in os.getenv("TAPTRACE_ALLOWED_ORIGINS", "").split(",") if item.strip()}
METRICS_TOKEN = os.getenv("TAPTRACE_METRICS_TOKEN")
RATE_KEY_SALT = os.getenv("TAPTRACE_RATE_KEY_SALT", "development-only")
TRUST_PROXY = os.getenv("TAPTRACE_TRUST_PROXY", "false").lower() == "true"
BACKUP_STATUS = Path(os.getenv("TAPTRACE_BACKUP_DIR", "/backups")) / "latest.json"
REQUIRE_RECENT_BACKUP = os.getenv("TAPTRACE_REQUIRE_RECENT_BACKUP", "false").lower() == "true"
RATE_LIMITER = RateLimiter(RATE_LIMIT_PER_MINUTE)
METRICS = Metrics()


def _route(path: str) -> str:
    return path if path in {"/health", "/metrics", "/coverage", "/coverage-plan", "/water-profile", "/ccr-submissions"} else "/other"


def _backup_healthy() -> bool:
    if not BACKUP_STATUS.exists():
        return not REQUIRE_RECENT_BACKUP
    try:
        payload = json.loads(BACKUP_STATUS.read_text(encoding="utf-8"))
        created = time.strptime(payload["created_at_utc"], "%Y-%m-%dT%H:%M:%SZ")
        age = time.time() - calendar.timegm(created)
        return age <= 48 * 60 * 60 and bool(payload.get("databases"))
    except Exception:
        return False


class Handler(BaseHTTPRequestHandler):
    server_version = "TapTrace/1.0"

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        self.send_header("X-Request-ID", getattr(self, "request_id", "unassigned"))
        origin = self.headers.get("Origin")
        if origin and origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)
        self._finish_metrics(status)

    def _send_text(self, status: int, body: str, content_type: str) -> None:
        encoded = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(encoded)
        self._finish_metrics(status)

    def _finish_metrics(self, status: int) -> None:
        if getattr(self, "_metrics_finished", False):
            return
        self._metrics_finished = True
        METRICS.end(_route(urlparse(self.path).path), status, time.monotonic() - self.started_at)

    def _authorize(self) -> bool:
        path = urlparse(self.path).path
        if path == "/metrics":
            supplied = self.headers.get("X-Metrics-Token", "")
            authorization = self.headers.get("Authorization", "")
            if authorization.startswith("Bearer "):
                supplied = authorization[7:]
            if not METRICS_TOKEN or not secrets.compare_digest(supplied, METRICS_TOKEN):
                self._send(401, {"error": "unauthorized"})
                return False
            return True
        if API_KEY and path != "/health" and not secrets.compare_digest(self.headers.get("X-API-Key", ""), API_KEY):
            self._send(401, {"error": "unauthorized"})
            return False
        if path == "/health":
            return True
        client = self.client_address[0]
        if TRUST_PROXY and self.headers.get("X-Forwarded-For"):
            client = self.headers["X-Forwarded-For"].split(",", 1)[0].strip()
        client_key = hashlib.sha256(f"{RATE_KEY_SALT}:{client}".encode()).hexdigest()
        allowed, retry_after = RATE_LIMITER.allow(client_key)
        if not allowed:
            self._send(429, {"error": "rate_limit_exceeded", "retry_after_seconds": retry_after})
            return False
        return True

    def _begin(self) -> bool:
        self.started_at = time.monotonic()
        self._metrics_finished = False
        METRICS.begin()
        self.request_id = uuid.uuid4().hex
        return self._authorize()

    def do_OPTIONS(self) -> None:
        self.started_at = time.monotonic()
        self._metrics_finished = False
        METRICS.begin()
        self.request_id = uuid.uuid4().hex
        origin = self.headers.get("Origin")
        if not origin or origin not in ALLOWED_ORIGINS:
            self._send(403, {"error": "origin_not_allowed"})
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()
        self._finish_metrics(204)

    def do_GET(self) -> None:
        if not self._begin():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/metrics":
            self._send_text(200, METRICS.prometheus(), "text/plain; version=0.0.4; charset=utf-8")
            return
        if parsed.path == "/health":
            dependencies = {
                "sdwis_registry": (ROOT / "outputs/backend/sdwis_system_registry.sqlite").exists(),
                "ccr_registry": (ROOT / "outputs/national_ccr/taptrace_ccr.sqlite").exists(),
                "ucmr_registry": (ROOT / "outputs/national_contaminants/taptrace_ucmr5.sqlite").exists(),
                "rate_limiter": RATE_LIMITER.healthy(),
                "recent_backup": _backup_healthy(),
            }
            status = "ok" if all(dependencies.values()) else "degraded"
            self._send(200 if status == "ok" else 503, {"status": status, "service": "taptrace-water-profile", "schema_version": "3.0.0", "dependencies": dependencies, "rate_limiter_backend": RATE_LIMITER.backend})
            return
        if parsed.path == "/coverage":
            if not COVERAGE_SUMMARY.exists():
                self._send(503, {"error": "coverage_inventory_not_built"})
            else:
                self._send(200, json.loads(COVERAGE_SUMMARY.read_text(encoding="utf-8")))
            return
        if parsed.path == "/coverage-plan":
            if not COVERAGE_PLAN.exists():
                self._send(503, {"error": "coverage_plan_not_built"})
            else:
                self._send(200, json.loads(COVERAGE_PLAN.read_text(encoding="utf-8")))
            return
        if parsed.path == "/water-profile":
            query = parse_qs(parsed.query)
            self._handle_profile({key: values[0] for key, values in query.items()})
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if not self._begin():
            return
        path = urlparse(self.path).path
        if path not in {"/water-profile", "/ccr-submissions"}:
            self._send(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > MAX_BODY_BYTES:
                self._send(413, {"error": "request_too_large"})
                return
            payload = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("JSON body must be an object")
            if path == "/ccr-submissions":
                self._send(202, submit_ccr_source(payload))
            else:
                self._handle_profile(payload)
        except (json.JSONDecodeError, ValueError) as exc:
            self._send(400, {"error": "invalid_request", "detail": str(exc)})

    def _handle_profile(self, payload: dict) -> None:
        try:
            address = payload.get("address", "")
            if not isinstance(address, str):
                raise ValueError("address must be a string")
            profile = compose_profile(
                address,
                selected_pwsid=payload.get("selected_pwsid"),
                enhanced=str(payload.get("enhanced", "true")).lower() not in {"0", "false", "no"},
            )
            self._send(200, profile)
        except ValueError as exc:
            self._send(400, {"error": "invalid_request", "detail": str(exc)})
        except TimeoutError:
            self._send(504, {"error": "upstream_timeout", "request_id": self.request_id})
        except Exception:
            self._send(502, {"error": "upstream_resolution_failed", "request_id": self.request_id})

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=int(os.getenv("PORT", "8080")), type=int)
    args = parser.parse_args()
    initialize_state()
    print(f"TapTrace API listening on http://{args.host}:{args.port}", flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
