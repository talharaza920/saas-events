"""Platform-console control of the text model (env = bootstrap, DB = override).

Model ids churn faster than deploys, so which provider/model the pipeline uses
is a platform-admin decision made in the console — the same argument that put
the prompt registry in the DB. The three things worth pinning:

  * the override REACHES the pipeline (not just the settings table),
  * bad config degrades to the env default instead of bricking every tenant,
  * the console cannot re-enable AI that `AI_LIVE_CALLS` switched off.
"""
from __future__ import annotations

import pytest

from app.ai.jobs import set_ai_settings
from app.ai.prompts import resolve_spec
from app.ai.providers import get_text_model
from app.ai.providers.fake import FakeTextModel
from app.ai.runtime import effective_settings
from app.config import Settings
from app.models import AiPrompt
from tests.helpers import platform_auth

ENV = dict(
    ai_text_provider="anthropic",
    anthropic_api_key="ant-key",
    openai_api_key="oai-key",
)


def _env(**kw) -> Settings:
    return Settings(_env_file=None, **{**ENV, **kw})


def _store(db, **values) -> None:
    set_ai_settings(db, {"kill_switch": False, "daily_cost_ceiling_usd": 25.0, **values})
    db.commit()


# --- resolution ---------------------------------------------------------------


def test_no_override_returns_the_env_settings_untouched(db_session):
    settings = _env()
    assert effective_settings(db_session, settings) is settings


def test_console_provider_and_model_override_env(db_session):
    _store(db_session, text_provider="openai", text_model="gpt-5.1", text_effort="low")
    live = effective_settings(db_session, _env())
    assert live.ai_text_provider == "openai"
    assert live.text_model == "gpt-5.1"
    assert live.ai_text_effort == "low"


def test_switching_provider_drops_a_stale_env_model_pin(db_session):
    """.env pins AI_TEXT_MODEL for the OLD provider; the console switches
    provider without naming a model. The pin must not ride along — that would
    send a gpt id to Anthropic, the very pairing we removed from env."""
    _store(db_session, text_provider="anthropic")
    live = effective_settings(db_session, _env(ai_text_provider="openai", ai_text_model="gpt-5.1"))
    assert live.ai_text_provider == "anthropic"
    assert live.text_model == "claude-opus-4-8"  # the anthropic default, not the pin


def test_a_malformed_override_falls_back_to_env_instead_of_bricking(db_session):
    """A typo in the console must not take every tenant's AI down — same rule as
    a malformed prompt row."""
    _store(db_session, text_provider="grok", text_effort="maximum", text_model="x" * 300)
    live = effective_settings(db_session, _env())
    assert live.ai_text_provider == "anthropic"
    assert live.ai_text_effort == "high"
    assert live.text_model == "claude-opus-4-8"


def test_the_console_cannot_re_enable_ai_that_the_env_switched_off(db_session):
    """AI_LIVE_CALLS is env-only on purpose: a kill switch that needs the DB to
    be reachable fails exactly when it is needed."""
    _store(db_session, text_provider="openai", text_model="gpt-5.1")
    live = effective_settings(db_session, _env(ai_live_calls=False))
    assert live.ai_text_live is False
    assert isinstance(get_text_model(live), FakeTextModel)


# --- the override reaches the pipeline ----------------------------------------


def test_the_console_provider_selects_the_provider_specific_prompt(db_session):
    """The end-to-end claim: an admin switching provider in the console changes
    which prompt row the NEXT run resolves. Env says anthropic; the console says
    openai; the openai-tuned row must win."""
    db_session.add(
        AiPrompt(
            key="extract.system", provider="openai", version=3,
            template="OPENAI-TUNED", active=True, max_tokens=2048,
        )
    )
    db_session.commit()

    env_only = resolve_spec(db_session, "extract.system", provider=_env().ai_text_provider)
    assert env_only.version == 0  # the code default — no anthropic row exists

    _store(db_session, text_provider="openai")
    live = effective_settings(db_session, _env())
    chosen = resolve_spec(db_session, "extract.system", provider=live.ai_text_provider)
    assert chosen.version == 3 and chosen.template == "OPENAI-TUNED"


# --- the HTTP surface ---------------------------------------------------------


def test_console_reads_back_what_is_actually_in_force(make_client):
    client = make_client(**ENV)
    before = client.get("/api/platform/settings/ai", headers=platform_auth()).json()
    assert before["from_env"] is True
    assert before["effective_provider"] == "anthropic"
    assert before["effective_model"] == "claude-opus-4-8"
    # Booleans only: an API key must never cross this wire.
    assert before["keys_configured"] == {"anthropic": True, "openai": True}
    assert "ant-key" not in str(before)

    saved = client.put(
        "/api/platform/settings/ai",
        json={
            "kill_switch": False, "daily_cost_ceiling_usd": 25.0,
            "text_provider": "openai", "text_model": "gpt-5.1", "text_effort": "medium",
        },
        headers=platform_auth(),
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["from_env"] is False
    assert (body["effective_provider"], body["effective_model"]) == ("openai", "gpt-5.1")


def test_clearing_a_field_restores_the_deployed_default(make_client):
    client = make_client(**ENV)
    base = {"kill_switch": False, "daily_cost_ceiling_usd": 25.0}
    client.put(
        "/api/platform/settings/ai",
        json={**base, "text_provider": "openai", "text_model": "gpt-5.1"},
        headers=platform_auth(),
    )
    body = client.put(
        "/api/platform/settings/ai", json=base, headers=platform_auth()
    ).json()
    assert body["from_env"] is True
    assert body["effective_provider"] == "anthropic"


@pytest.mark.parametrize(
    "provider,model",
    [("openai", "claude-opus-4-8"), ("anthropic", "gpt-5.1")],
)
def test_a_model_from_the_wrong_family_is_refused(make_client, provider, model):
    """Rejected at the console, where an admin can read the reason — not at the
    provider, on some couple's next run."""
    client = make_client(**ENV)
    r = client.put(
        "/api/platform/settings/ai",
        json={
            "kill_switch": False, "daily_cost_ceiling_usd": 25.0,
            "text_provider": provider, "text_model": model,
        },
        headers=platform_auth(),
    )
    assert r.status_code == 422


def test_the_fake_provider_is_not_selectable_from_the_console(make_client):
    """Stopping AI is the kill switch's job (fails closed). Quietly serving
    couples canned demo prose would fail OPEN."""
    client = make_client(**ENV)
    r = client.put(
        "/api/platform/settings/ai",
        json={
            "kill_switch": False, "daily_cost_ceiling_usd": 25.0, "text_provider": "fake",
        },
        headers=platform_auth(),
    )
    assert r.status_code == 422


def test_only_platform_admins_may_change_the_model(make_client):
    from tests.helpers import user_auth

    client = make_client(**ENV)
    r = client.put(
        "/api/platform/settings/ai",
        json={"kill_switch": False, "daily_cost_ceiling_usd": 25.0, "text_provider": "openai"},
        headers=user_auth("nobody@example.com"),
    )
    assert r.status_code in (401, 403, 404)
