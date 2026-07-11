"""Text-model adapter selection — config, not code (`ai_text_provider`)."""
from __future__ import annotations

from app.ai.types import ProviderError, TextModel
from app.config import Settings


def get_text_model(settings: Settings) -> TextModel:
    provider = settings.ai_text_provider.strip().lower()
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
