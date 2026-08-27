"""Shared rate limiting and privacy-safe process metrics."""

from __future__ import annotations

import os
import threading
import time
from collections import Counter


class RateLimiter:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.redis_url = os.getenv("TAPTRACE_REDIS_URL")
        self.require_redis = os.getenv("TAPTRACE_REQUIRE_REDIS", "false").lower() == "true"
        self._redis = None
        self._lock = threading.Lock()
        self._local: dict[str, list[float]] = {}
        if self.redis_url:
            try:
                import redis
                self._redis = redis.Redis.from_url(self.redis_url, socket_timeout=2, decode_responses=True)
                self._redis.ping()
            except Exception:
                if self.require_redis:
                    raise RuntimeError("Required shared Redis rate limiter is unavailable")

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "local_process"

    def healthy(self) -> bool:
        if self._redis is None:
            return not self.require_redis
        try:
            return bool(self._redis.ping())
        except Exception:
            return False

    def allow(self, client_key: str) -> tuple[bool, int]:
        now = time.time()
        if self._redis is not None:
            bucket = int(now // 60)
            key = f"taptrace:rate:{bucket}:{client_key}"
            try:
                count = self._redis.incr(key)
                if count == 1:
                    self._redis.expire(key, 120)
                return count <= self.limit, max(1, 60 - int(now % 60))
            except Exception:
                if self.require_redis:
                    return False, 60
        with self._lock:
            recent = [stamp for stamp in self._local.get(client_key, []) if now - stamp < 60]
            if len(recent) >= self.limit:
                return False, max(1, 60 - int(now - recent[0]))
            recent.append(now)
            self._local[client_key] = recent
        return True, 0


class Metrics:
    """No addresses, query strings, API keys, or client IPs are retained."""

    def __init__(self) -> None:
        self.started = time.time()
        self._lock = threading.Lock()
        self.requests = Counter()
        self.latency_sum = Counter()
        self.inflight = 0

    def begin(self) -> None:
        with self._lock:
            self.inflight += 1

    def end(self, route: str, status: int, elapsed: float) -> None:
        status_class = f"{status // 100}xx"
        with self._lock:
            self.inflight = max(0, self.inflight - 1)
            self.requests[(route, status_class)] += 1
            self.latency_sum[route] += elapsed

    def prometheus(self) -> str:
        with self._lock:
            lines = [
                "# HELP taptrace_uptime_seconds Process uptime.",
                "# TYPE taptrace_uptime_seconds gauge",
                f"taptrace_uptime_seconds {time.time() - self.started:.3f}",
                "# HELP taptrace_requests_inflight Current in-flight requests.",
                "# TYPE taptrace_requests_inflight gauge",
                f"taptrace_requests_inflight {self.inflight}",
                "# HELP taptrace_http_requests_total Requests by route and status class.",
                "# TYPE taptrace_http_requests_total counter",
            ]
            for (route, status_class), count in sorted(self.requests.items()):
                lines.append(f'taptrace_http_requests_total{{route="{route}",status_class="{status_class}"}} {count}')
            lines.extend(["# HELP taptrace_request_duration_seconds_sum Total request duration by route.",
                          "# TYPE taptrace_request_duration_seconds_sum counter"])
            for route, value in sorted(self.latency_sum.items()):
                lines.append(f'taptrace_request_duration_seconds_sum{{route="{route}"}} {value:.6f}')
        return "\n".join(lines) + "\n"
