"""The Supabase-introspection cache (REVIEW_BACKLOG P0-2): a valid token is
introspected once per TTL, failures are never cached, and expiry re-verifies.
The conftest autouse fixture clears the cache between tests."""
from __future__ import annotations

import app.auth as auth_module


def _fake_introspection(calls):
    def fake(settings, token):
        calls.append(token)
        return {
            "id": f"user-{token}",
            "email": f"{token}@example.com",
            "email_confirmed_at": "2026-01-01T00:00:00Z",
        }

    return fake


def test_valid_token_introspected_once(client, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(auth_module, "verify_supabase_token", _fake_introspection(calls))
    headers = {"Authorization": "Bearer cache-tok-1"}
    assert client.get("/api/me", headers=headers).status_code == 200
    assert client.get("/api/me", headers=headers).status_code == 200
    assert client.get("/api/me", headers=headers).status_code == 200
    assert len(calls) == 1


def test_distinct_tokens_cached_separately(client, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(auth_module, "verify_supabase_token", _fake_introspection(calls))
    r1 = client.get("/api/me", headers={"Authorization": "Bearer cache-tok-a"})
    r2 = client.get("/api/me", headers={"Authorization": "Bearer cache-tok-b"})
    assert (r1.status_code, r2.status_code) == (200, 200)
    assert r1.json()["email"] != r2.json()["email"]
    assert len(calls) == 2


def test_failures_are_not_cached(client, monkeypatch):
    calls: list[str] = []

    def fake(settings, token):
        calls.append(token)
        raise auth_module._unauthorized("Invalid or expired session")

    monkeypatch.setattr(auth_module, "verify_supabase_token", fake)
    headers = {"Authorization": "Bearer bad-tok"}
    assert client.get("/api/me", headers=headers).status_code == 401
    assert client.get("/api/me", headers=headers).status_code == 401
    assert len(calls) == 2  # every failed attempt re-verifies


def test_unverified_email_is_not_cached(client, monkeypatch):
    calls: list[str] = []

    def fake(settings, token):
        calls.append(token)
        return {"id": "user-9", "email": "new@example.com"}  # no email_confirmed_at

    monkeypatch.setattr(auth_module, "verify_supabase_token", fake)
    headers = {"Authorization": "Bearer unverified-tok"}
    assert client.get("/api/me", headers=headers).status_code == 403
    assert client.get("/api/me", headers=headers).status_code == 403
    assert len(calls) == 2


def test_cache_expires_after_ttl(client, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(auth_module, "verify_supabase_token", _fake_introspection(calls))
    monkeypatch.setattr(auth_module, "INTROSPECTION_TTL_SECONDS", 0.0)
    headers = {"Authorization": "Bearer expiring-tok"}
    assert client.get("/api/me", headers=headers).status_code == 200
    assert client.get("/api/me", headers=headers).status_code == 200
    assert len(calls) == 2
