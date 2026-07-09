"""The email seam (REVIEW_BACKLOG P0-3): Resend is called only when configured,
payload is right, and NO failure mode ever raises (a dead email provider must
not roll back the state change the email announces)."""
from __future__ import annotations

import app.emailer as emailer_module
from app.config import Settings


class _FakeResp:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_unconfigured_send_stays_in_outbox(monkeypatch):
    calls: list = []
    monkeypatch.setattr(
        emailer_module.httpx, "post", lambda *a, **k: calls.append((a, k)) or _FakeResp()
    )
    emailer_module.OUTBOX.clear()
    emailer_module.send_email(_settings(), "to@example.com", "Hello", "Body")
    assert calls == []  # no provider call without RESEND_API_KEY + EMAIL_FROM
    assert emailer_module.OUTBOX[-1].to == "to@example.com"


def test_configured_send_calls_resend(monkeypatch):
    calls: list = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append((url, headers, json))
        return _FakeResp(200)

    monkeypatch.setattr(emailer_module.httpx, "post", fake_post)
    s = _settings(resend_api_key="re_test_key", email_from="Invites <invites@example.com>")
    emailer_module.send_email(s, "to@example.com", "Hello", "Body text")
    url, headers, payload = calls[0]
    assert url == emailer_module._RESEND_URL
    assert headers["Authorization"] == "Bearer re_test_key"
    assert payload == {
        "from": "Invites <invites@example.com>",
        "to": ["to@example.com"],
        "subject": "Hello",
        "text": "Body text",
    }


def test_provider_exception_never_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(emailer_module.httpx, "post", boom)
    s = _settings(resend_api_key="re_test_key", email_from="invites@example.com")
    emailer_module.send_email(s, "to@example.com", "Hello", "Body")  # must not raise
    assert emailer_module.OUTBOX[-1].subject == "Hello"


def test_provider_4xx_never_raises(monkeypatch):
    monkeypatch.setattr(
        emailer_module.httpx, "post", lambda *a, **k: _FakeResp(422, "invalid from")
    )
    s = _settings(resend_api_key="re_test_key", email_from="invites@example.com")
    emailer_module.send_email(s, "to@example.com", "Hello", "Body")  # must not raise
