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
        from app.ai.providers.fake import FakeTextModel

        return FakeTextModel()
    if provider == "openai":
        # Deliberate: ship one adapter, keep the seam (AI_WIZARD_PLAN "do not
        # gate the launch on having both"). The port is one method wide, so
        # adding openai.py later touches nothing outside providers/.
        raise ProviderError(
            "The openai text adapter isn't implemented yet — set "
            "AI_TEXT_PROVIDER=anthropic (or 'fake' for offline runs)."
        )
    raise ProviderError(f"Unknown ai_text_provider {settings.ai_text_provider!r}")
