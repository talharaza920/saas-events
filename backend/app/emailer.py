"""Transactional email — invites, approval notices, membership changes.

No provider is wired yet (SAAS_PLAN 1.1 earmarks Resend / Supabase SMTP once
real infrastructure exists). Until then every send lands in `OUTBOX` (visible
to tests) and the server log, so flows are fully exercisable offline. The
signature is the seam: swapping in a provider later touches only this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.config import Settings


@dataclass
class OutboundEmail:
    to: str
    subject: str
    body: str
    sent_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# Dev/test outbox — inspect (and clear) in tests; bounded so a long-running dev
# server doesn't grow it forever.
OUTBOX: list[OutboundEmail] = []
_OUTBOX_CAP = 200


def send_email(settings: Settings, to: str, subject: str, body: str) -> None:
    """Queue/send one email. Never raises — a failed notification must not roll
    back the state change it announces."""
    email = OutboundEmail(to=to, subject=subject, body=body)
    OUTBOX.append(email)
    del OUTBOX[:-_OUTBOX_CAP]
    print(f"[email → {to}] {subject}")
