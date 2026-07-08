"""Owner (admin) authentication — the only auth surface in the app.

Two paths, chosen by what's configured:

  • Production — **token introspection**. The frontend sends the Supabase session
    access token as a bearer; we hand it to Supabase's `/auth/v1/user` endpoint
    and trust Supabase to validate it (no JWT secret, works with symmetric OR the
    newer asymmetric signing keys), then require the returned `email` to be in the
    admin allowlist (`settings.admin_emails`).
  • Local dev — accept a static **dev bearer token** (`settings.dev_admin_token`,
    set in `.env.local`) so the dashboard works on SQLite without Supabase Auth.
    The dev path is OFF unless that token is set, and is ignored in production.

Guests never authenticate (they use signed links); this module is admin-only.
"""
from __future__ import annotations

import os
import secrets

import httpx
from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel

from app.config import Settings, get_settings


class Owner(BaseModel):
    """The authenticated admin principal handed to admin endpoints."""

    sub: str  # stable id — Supabase user id, or "dev" for the local token
    email: str
    via: str  # "supabase" | "dev"


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized("Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise _unauthorized("Missing bearer token")
    return token


def verify_supabase_token(settings: Settings, token: str) -> dict:
    """Ask Supabase to validate the access token; return its user object.

    Isolated so tests can monkeypatch it (no live Supabase needed offline).
    """
    url = settings.supabase_url.rstrip("/") + "/auth/v1/user"
    try:
        resp = httpx.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": settings.supabase_publishable_key,
            },
            timeout=5.0,
        )
    except httpx.HTTPError:
        raise _unauthorized("Could not reach the auth service")
    if resp.status_code != 200:
        raise _unauthorized("Invalid or expired session")
    return resp.json()


def get_current_owner(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Owner:
    """FastAPI dependency: resolve the bearer token to an authorized Owner."""
    token = _bearer_token(authorization)

    # --- Local-dev token (never honoured in production) -------------------
    # Belt-and-braces: besides ENVIRONMENT, refuse the dev path whenever we're
    # running on Vercel at all (guards against an ENVIRONMENT misconfig), and
    # compare in constant time.
    if (
        not settings.is_production
        and not os.environ.get("VERCEL")
        and settings.dev_admin_token
    ):
        if secrets.compare_digest(token, settings.dev_admin_token):
            email = settings.admin_email_list[0] if settings.admin_email_list else "dev@local"
            return Owner(sub="dev", email=email, via="dev")
        # Fall through: a non-matching token may still be a real Supabase session.

    # --- Supabase token introspection -------------------------------------
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise _unauthorized("Admin auth is not configured")
    user = verify_supabase_token(settings, token)

    email = (user.get("email") or "").strip().lower()
    if not email or email not in settings.admin_email_list:
        # Authenticated but not allowlisted → 403 (distinct from 401).
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is not an authorized admin",
        )
    return Owner(sub=str(user.get("id") or ""), email=email, via="supabase")
