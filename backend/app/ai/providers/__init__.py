"""Text-model adapter selection — config, not code (`ai_text_provider`)."""
from __future__ import annotations

import logging

from app.ai.types import ProviderError, TextModel
from app.config import Settings
from app.obs import log_event

logger = logging.getLogger("app.ai")


def get_text_model(settings: Settings) -> TextModel:
    provider = settings.ai_text_provider.strip().lower()
    if not settings.ai_text_live and provider != "fake":
        # Live calls are switched off for this process (AI_LIVE_CALLS /
        # AI_LIVE_TEXT). Serve the offline demo set instead of the configured
        # provider: the whole pipeline still runs end to end — which is what
        # makes the browser smokes safe to run on a box whose .env holds real
        # keys — and not one token is billed. Logged, because a silently faked
        # model is a debugging nightmare.
        from app.ai.providers.fake import FakeTextModel, demo_responses

        log_event(logger, "ai.provider.offline", configured=provider)
        return FakeTextModel(responses=demo_responses())
    if provider == "anthropic":
        from app.ai.providers.anthropic import AnthropicTextModel

        return AnthropicTextModel(settings)
    if provider == "fake":
        # The demo canned set: a full offline wizard run for local dev / the
        # smoke E2E. Tests bypass this factory and script their own instances.
        from app.ai.providers.fake import FakeTextModel, demo_responses

        return FakeTextModel(responses=demo_responses())
    if provider == "openai":
        from app.ai.providers.openai import OpenAITextModel

        return OpenAITextModel(settings)
    raise ProviderError(f"Unknown ai_text_provider {settings.ai_text_provider!r}")
