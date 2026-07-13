"""Effective AI text config: env is the bootstrap, the platform console overrides.

Model ids churn faster than deploys, so which provider/model the pipeline uses
is a platform-admin decision, not a redeploy — the same argument that already
put the prompt registry in the DB. `.env` keeps the BOOTSTRAP default (and the
API keys, which never leave it); a `platform_settings['ai']` row overrides it
platform-wide.

Two rules carried over from `prompts.py`, for the same reason — never let bad
config brick every tenant's AI:

  * A malformed override is IGNORED (logged), falling back to the env value.
    A typo'd model id in one field must not take the pipeline down.
  * The override can only pick a provider/model/effort. It cannot switch AI
    *on*: `AI_LIVE_CALLS` stays env-only, deliberately. A kill switch that
    needs the database to be reachable is a kill switch that fails exactly
    when you need it.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.config import Settings
from app.obs import log_event

logger = logging.getLogger("app.ai")

# What a platform admin may select. `fake` is deliberately NOT here: serving
# couples canned demo stories is not an ops action, and the thing an admin
# actually wants in an incident — stop calling the provider — is the kill
# switch, which fails closed rather than silently lying to users.
CONSOLE_PROVIDERS = ("anthropic", "openai")
EFFORTS = ("low", "medium", "high")
MAX_MODEL_LEN = 100


def effective_settings(db: Session, settings: Settings) -> Settings:
    """`settings` with the console's text-model overrides applied.

    Returns the SAME object when nothing is overridden, so the common path
    allocates nothing and behaviour is identical to pre-console.
    """
    from app.ai.jobs import get_ai_settings  # local: jobs imports config

    row = get_ai_settings(db)
    updates: dict[str, str] = {}

    provider = _clean(row.get("text_provider"))
    if provider:
        if provider in CONSOLE_PROVIDERS:
            updates["ai_text_provider"] = provider
        else:
            _ignored("text_provider", provider)

    model = _clean(row.get("text_model"))
    if model:
        if len(model) <= MAX_MODEL_LEN:
            updates["ai_text_model"] = model
        else:
            _ignored("text_model", model[:40] + "...")
    elif "ai_text_provider" in updates:
        # Switching provider from the console with no model of its own: DROP any
        # AI_TEXT_MODEL pin from .env, so `text_model` falls through to the new
        # provider's own default (AI_MODEL_ANTHROPIC / AI_MODEL_OPENAI).
        # Otherwise an env pin left over from the previous provider would ride
        # along and send, say, a gpt id to Anthropic.
        updates["ai_text_model"] = ""

    effort = _clean(row.get("text_effort"))
    if effort:
        if effort in EFFORTS:
            updates["ai_text_effort"] = effort
        else:
            _ignored("text_effort", effort)

    if not updates:
        return settings
    return settings.model_copy(update=updates)


def _clean(value: object) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _ignored(field: str, value: str) -> None:
    log_event(logger, "ai.console_override.ignored", field=field, value=value)
