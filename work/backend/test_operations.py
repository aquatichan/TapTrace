"""Deterministic operations tests without external services."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

os.environ.pop("TAPTRACE_REDIS_URL", None)
os.environ.pop("TAPTRACE_REQUIRE_REDIS", None)

from backup import backup_database  # noqa: E402
from operations import Metrics, RateLimiter  # noqa: E402


def main() -> None:
    limiter = RateLimiter(2)
    assert limiter.backend == "local_process"
    assert limiter.allow("hashed-client")[0]
    assert limiter.allow("hashed-client")[0]
    allowed, retry = limiter.allow("hashed-client")
    assert not allowed and retry > 0

    metrics = Metrics()
    metrics.begin(); metrics.end("/health", 200, 0.01)
    text = metrics.prometheus()
    assert 'route="/health",status_class="2xx"' in text
    assert "address" not in text.lower()

    with tempfile.TemporaryDirectory(prefix="taptrace-backup-test-") as directory:
        source = Path(directory) / "source.sqlite"
        destination = Path(directory) / "backup.sqlite"
        with sqlite3.connect(source) as connection:
            connection.execute("CREATE TABLE sample (value TEXT)")
            connection.execute("INSERT INTO sample VALUES ('ok')")
        record = backup_database(source, destination)
        assert record["integrity_check"] == "ok"
        with sqlite3.connect(destination) as connection:
            assert connection.execute("SELECT value FROM sample").fetchone()[0] == "ok"
    print({"status": "PASS", "rate_limit": True, "privacy_safe_metrics": True, "backup_restore": True})


if __name__ == "__main__":
    main()
