"""Transactional email — invites, approval notices, membership changes.

Provider: **Resend** (HTTP API), active when `RESEND_API_KEY` + `EMAIL_FROM`
are configured; otherwise (local dev, tests, unprovisioned prod) every send
lands only in `OUTBOX` (visible to tests) and the server log, so flows are
fully exercisable offline. Either way `send_email` NEVER raises — a failed
notification must not roll back the state change it announces.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from app.config import Settings

_RESEND_URL = "https://api.resend.com/emails"
logger = logging.getLogger("app.email")


@dataclass
class OutboundEmail:
    to: str
    subject: str
    body: str
    sent_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# Dev/test outbox — inspect (and clear) in tests; bounded so a long-running dev
# server doesn't grow it forever. Appended to even when a provider is active
# (harmless, and keeps tests observable regardless of config).
OUTBOX: list[OutboundEmail] = []
_OUTBOX_CAP = 200


def _log(line: str) -> None:
    try:
        # ASCII-only log line: a Windows console defaults to cp1252, where a
        # non-ASCII char in the log stream raises and would 500 the request.
        logger.info(line.encode("ascii", "replace").decode())
    except Exception:
        pass


def _send_resend(settings: Settings, to: str, subject: str, body: str) -> None:
    resp = httpx.post(
        _RESEND_URL,
        headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        json={"from": settings.email_from, "to": [to], "subject": subject, "text": body},
        timeout=10.0,
    )
    if resp.status_code >= 400:
        _log(f"[email FAILED to {to}] Resend {resp.status_code}: {resp.text[:200]}")
    else:
        _log(f"[email sent to {to}] {subject}")


def send_email(settings: Settings, to: str, subject: str, body: str) -> None:
    """Queue/send one email. Never raises."""
    email = OutboundEmail(to=to, subject=subject, body=body)
    OUTBOX.append(email)
    del OUTBOX[:-_OUTBOX_CAP]
    if settings.resend_api_key and settings.email_from:
        try:
            _send_resend(settings, to, subject, body)
        except Exception as exc:  # network/provider outage — log, never propagate
            _log(f"[email FAILED to {to}] {type(exc).__name__}")
    else:
        _log(f"[email outbox to {to}] {subject}")
