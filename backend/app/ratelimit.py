"""Per-instance rate limiting for the UNAUTHENTICATED guest API (P0-4 in
docs/REVIEW_BACKLOG.md).

Guests never log in, so `/api/i/*` and the public landing endpoints are open to
anyone holding (or hammering for) a URL — this bounds wish spam, RSVP
flip-flood and read hammering per client IP with a fixed one-minute window.

Deliberately simple and IN-PROCESS: on serverless each instance counts its own
window, so the effective ceiling is `limit × concurrent instances` —
approximate abuse protection, not a hard quota. The durable outer layer is the
platform WAF (Vercel, Phase 0 backlog P1-2); revisit a shared store
(Upstash/Redis) only if real abuse shows up.

Enabled by default only in production (`settings.rate_limit_enabled is None`);
tests and local dev opt in explicitly via RATE_LIMIT_ENABLED.
"""
from __future__ import annotations

import threading
import time

from fastapi import Depends, HTTPException, Request

from app.config import Settings, get_settings

WINDOW_SECONDS = 60.0
_MAX_BUCKETS = 10_000  # safety valve against key-cardinality abuse

# (scope, ip) → (window_start, count)
_buckets: dict[tuple[str, str], tuple[float, int]] = {}
_lock = threading.Lock()


def reset() -> None:
    """Testing seam — the buckets are module-level state."""
    with _lock:
        _buckets.clear()


def _client_ip(request: Request) -> str:
    # Vercel/most proxies put the real client first in X-Forwarded-For. Spoofable
    # when NOT behind a proxy, but a spoofed header only ever splits the limiter's
    # buckets for that caller — it can't widen anyone else's budget.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _enabled(settings: Settings) -> bool:
    if settings.rate_limit_enabled is not None:
        return settings.rate_limit_enabled
    return settings.is_production


def check(request: Request, settings: Settings, scope: str, limit: int) -> None:
    """Count this request against (scope, client-ip); 429 when over `limit`/min."""
    if not _enabled(settings) or limit <= 0:
        return
    key = (scope, _client_ip(request))
    now = time.monotonic()
    with _lock:
        if len(_buckets) > _MAX_BUCKETS:
            cutoff = now - WINDOW_SECONDS
            for stale in [k for k, (start, _) in _buckets.items() if start < cutoff]:
                _buckets.pop(stale, None)
        start, count = _buckets.get(key, (now, 0))
        if now - start >= WINDOW_SECONDS:
            start, count = now, 0
        count += 1
        _buckets[key] = (start, count)
    if count > limit:
        raise HTTPException(
            status_code=429,
            detail="Too many requests — please try again in a minute",
            headers={"Retry-After": str(int(WINDOW_SECONDS))},
        )


def guest_read_limit(request: Request, settings: Settings = Depends(get_settings)) -> None:
    """Dependency for guest-facing GETs (invite payload, wishes wall, landings)."""
    check(request, settings, "guest-read", settings.rate_limit_guest_reads_per_minute)


def guest_write_limit(request: Request, settings: Settings = Depends(get_settings)) -> None:
    """Dependency for guest-facing writes (RSVP submit, wish create)."""
    check(request, settings, "guest-write", settings.rate_limit_guest_writes_per_minute)
