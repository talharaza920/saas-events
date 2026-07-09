"""Observability (REVIEW_BACKLOG P1-10): logging setup, structured-event helper,
optional Sentry.

Everything degrades to nothing: no SENTRY_DSN → no Sentry (the SDK isn't even
imported); logging falls back to stdlib defaults if configuration fails. Nothing
here may ever take a request down.

Loggers: modules call `logging.getLogger("app.<area>")`. For events worth
querying later, prefer `log_event(logger, "rsvp.submit", wedding_id=...,
user_sub=...)` — one logfmt line (`event=rsvp.submit wedding_id=… …`) that's
grep-able locally and parseable by any log pipeline.
"""
from __future__ import annotations

import logging

from app.config import Settings

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def setup_logging(settings: Settings) -> None:
    """Configure root logging once at startup. INFO by default (LOG_LEVEL env)."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(level=level, format=_FORMAT)


def _fmt_value(value) -> str:
    text = str(value)
    # ASCII-safe (Windows consoles default to cp1252) and logfmt-friendly.
    text = text.encode("ascii", "replace").decode()
    return f'"{text}"' if " " in text else text


def log_event(logger: logging.Logger, event: str, **fields) -> None:
    """One structured (logfmt) line: `event=<name> key=value …`. None values are
    dropped so callers can pass optional context unconditionally."""
    parts = [f"event={_fmt_value(event)}"]
    parts += [f"{k}={_fmt_value(v)}" for k, v in fields.items() if v is not None]
    logger.info(" ".join(parts))


def init_sentry(settings: Settings) -> None:
    """Start Sentry when a DSN is configured. Import is lazy and failures are
    swallowed — an unprovisioned or broken Sentry must never block boot."""
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            # Error tracking only for now; keep transaction sampling off until
            # there's traffic worth tracing (and a quota to spend).
            traces_sample_rate=0.0,
        )
        logging.getLogger("app.obs").info("Sentry enabled (env=%s)", settings.environment)
    except Exception as exc:  # missing SDK, bad DSN, network — boot anyway
        logging.getLogger("app.obs").warning("Sentry init failed: %s", exc)
