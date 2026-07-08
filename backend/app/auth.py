"""Authentication — resolving a bearer token to a platform user.

Since Phase 1 (identity & tenancy) ANY authenticated user is a valid principal;
what they may touch is decided by memberships (app/authz.py), not by an email
allowlist. Two token paths, chosen by what's configured:

  • Production — **token introspection**. The frontend sends the Supabase session
    access token as a bearer; we hand it to Supabase's `/auth/v1/user` endpoint
    and trust Supabase to validate it (no JWT secret, works with symmetric OR the
    newer asymmetric signing keys). Unverified emails are refused (signup flow
    requires verification).
  • Local dev — a static **dev bearer token** (`settings.dev_admin_token`, set in
    `.env.local`) so everything works on SQLite without Supabase Auth:
      - the bare token       → the bootstrap dev principal (sub "dev", platform admin)
      - "<token>:<email>"    → a simulated user with that email (sub "dev:<email>")
        so multi-account flows (memberships, invites, cross-tenant tests) can be
        exercised locally.
    The dev path is OFF unless the token is set, and is refused in production or
    whenever `VERCEL` is set (belt-and-braces against an ENVIRONMENT misconfig).

Guests never authenticate (they use signed links).
"""
from __future__ import annotations

import os
import secrets

import httpx
from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel

from app.config import Settings, get_settings


class AuthedUser(BaseModel):
    """The authenticated principal handed to admin/platform endpoints."""

    sub: str  # stable id — Supabase user id, or "dev"/"dev:<email>" locally
    email: str
    via: str  # "supabase" | "dev"


# Back-compat alias (pre-Phase-1 code called the principal "Owner").
Owner = AuthedUser


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


def _dev_user(settings: Settings, token: str) -> AuthedUser | None:
    """Resolve the local dev token (bare or '<token>:<email>'), or None if this
    isn't a dev credential. Both compares are constant-time."""
    dev = settings.dev_admin_token
    if secrets.compare_digest(token, dev):
        email = settings.admin_email_list[0] if settings.admin_email_list else "dev@local"
        return AuthedUser(sub="dev", email=email, via="dev")
    prefix, sep, email = token.partition(":")
    email = email.strip().lower()
    if sep and email and "@" in email and secrets.compare_digest(prefix, dev):
        return AuthedUser(sub=f"dev:{email}", email=email, via="dev")
    return None


def get_current_user(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> AuthedUser:
    """FastAPI dependency: resolve the bearer token to an authenticated user.

    Authorization (membership / platform-admin checks) happens in app/authz.py —
    this only establishes WHO is calling.
    """
    token = _bearer_token(authorization)

    # --- Local-dev token (never honoured in production / on Vercel) --------
    if (
        not settings.is_production
        and not os.environ.get("VERCEL")
        and settings.dev_admin_token
    ):
        user = _dev_user(settings, token)
        if user is not None:
            return user
        # Fall through: a non-matching token may still be a real Supabase session.

    # --- Supabase token introspection -------------------------------------
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise _unauthorized("Auth is not configured")
    user = verify_supabase_token(settings, token)

    email = (user.get("email") or "").strip().lower()
    if not user.get("id") or not email:
        raise _unauthorized("Invalid session")
    # Mandatory email verification (SAAS_PLAN 1.1). OAuth (Google) accounts come
    # back confirmed; an email/password signup must verify before the API works.
    if not (user.get("email_confirmed_at") or user.get("confirmed_at")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address first",
        )
    return AuthedUser(sub=str(user["id"]), email=email, via="supabase")


# Back-compat alias for pre-Phase-1 call sites.
get_current_owner = get_current_user
