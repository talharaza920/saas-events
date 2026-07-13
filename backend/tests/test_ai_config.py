"""AI live-call switches + per-provider model selection (config.py).

Two footguns are pinned here, both of which have already cost us something:

  1. "Go offline" used to mean setting THREE unrelated things (fake provider,
     blank Gemini key, blank Places key). Miss one and an "offline" browser
     smoke quietly spent real money on images. Now it is one switch, and a
     `true` on a per-capability flag can never re-open what the master shut.

  2. The text model used to be configured independently of the provider, so
     `AI_TEXT_PROVIDER=openai` with the default model was a writable config
     that pointed a Claude id at OpenAI. The model now follows the provider.
"""
from __future__ import annotations

import pytest

from app.ai.media import GeminiMedia
from app.ai.providers import get_text_model
from app.ai.providers.anthropic import AnthropicTextModel
from app.ai.providers.fake import FakeTextModel
from app.ai.providers.openai import OpenAITextModel
from app.ai.types import ProviderError
from app.config import Settings

LIVE = dict(
    gemini_api_key="gem-key",
    google_places_api_key="places-key",
    anthropic_api_key="ant-key",
)


def _settings(**kw) -> Settings:
    # _env_file=None (the suite's convention): these assert DEFAULTS, so they
    # must not read whatever the developer happens to have in .env / .env.local.
    return Settings(_env_file=None, **{**LIVE, **kw})


# --- the master switch --------------------------------------------------------


def test_live_calls_off_serves_the_fake_model_even_with_a_real_provider():
    settings = _settings(ai_text_provider="anthropic", ai_live_calls=False)
    assert isinstance(get_text_model(settings), FakeTextModel)


def test_live_calls_off_disables_every_capability_despite_real_keys():
    """The exact configuration that made the 'offline' smoke spend money: keys
    present in .env, one switch expected to hold them all back."""
    settings = _settings(ai_live_calls=False)
    assert settings.ai_text_live is False
    assert settings.ai_transcribe_enabled is False
    assert settings.ai_images_enabled is False
    assert settings.ai_places_enabled is False


def test_a_per_capability_true_cannot_resurrect_what_the_master_switched_off():
    settings = _settings(
        ai_live_calls=False,
        ai_live_text=True,
        ai_live_images=True,
        ai_live_transcribe=True,
        ai_live_places=True,
    )
    assert settings.ai_text_live is False
    assert settings.ai_images_enabled is False
    assert settings.ai_transcribe_enabled is False
    assert settings.ai_places_enabled is False
    assert isinstance(get_text_model(settings), FakeTextModel)


# --- per-capability overrides -------------------------------------------------


def test_live_by_default_when_the_keys_are_there():
    settings = _settings()
    assert settings.ai_text_live is True
    assert settings.ai_transcribe_enabled is True
    assert settings.ai_images_enabled is True
    assert settings.ai_places_enabled is True


def test_images_can_be_switched_off_alone():
    """Draft real text, stop paying per image — the capability the flags exist
    for; nothing else moves."""
    settings = _settings(ai_live_images=False)
    assert settings.ai_images_enabled is False
    assert settings.ai_text_live is True
    assert settings.ai_transcribe_enabled is True
    assert settings.ai_places_enabled is True
    assert isinstance(get_text_model(settings), AnthropicTextModel)


def test_a_missing_key_disables_its_capability_even_when_live():
    settings = Settings(_env_file=None, ai_live_calls=True)  # no keys at all
    assert settings.ai_transcribe_enabled is False
    assert settings.ai_images_enabled is False
    assert settings.ai_places_enabled is False


def test_the_media_seam_refuses_to_build_a_client_when_calls_are_off():
    """Backstop for a call site that forgets to check the capability: the seam
    itself will not reach the network."""
    media = GeminiMedia(_settings(ai_live_calls=False))
    with pytest.raises(ProviderError, match="switched off"):
        media.transcribe(b"\x00", "audio/mpeg")


# --- the model follows the provider -------------------------------------------


def test_selecting_a_provider_selects_its_model():
    assert _settings(ai_text_provider="anthropic").text_model == "claude-opus-4-8"
    assert _settings(ai_text_provider="openai").text_model == "gpt-5.1"


def test_switching_provider_alone_is_a_complete_config():
    """The old footgun: AI_TEXT_PROVIDER=openai + the default model = a Claude
    id sent to OpenAI. The adapter's guard must now have nothing to catch."""
    settings = _settings(ai_text_provider="openai", openai_api_key="oai-key")
    assert isinstance(get_text_model(settings), OpenAITextModel)
    assert not settings.text_model.startswith("claude")


def test_an_explicit_model_pins_a_snapshot_over_the_provider_default():
    settings = _settings(ai_text_provider="openai", ai_text_model="gpt-5.1-2026-04-01")
    assert settings.text_model == "gpt-5.1-2026-04-01"


def test_ai_mode_says_out_loud_when_the_model_is_faked():
    assert "OFFLINE" in _settings(ai_live_calls=False).ai_mode
    live = _settings(ai_text_provider="anthropic", ai_live_images=False).ai_mode
    assert "claude-opus-4-8" in live and "images" not in live
