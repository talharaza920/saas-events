"""The text-model port (AI_WIZARD_PLAN "Provider abstraction").

One method wide, on purpose: every media input is normalised to text BEFORE
this seam (Gemini transcribe step), and venue resolution happens in plain code
AFTER it (Google Places), so the text model only ever does text in → JSON out.
No streaming, no vision, no tool-calling, no multi-turn — those are where
cross-provider abstractions rot, and the pipeline needs none of them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel

# Normalised reasoning depth. Each adapter maps these to its provider's knob
# (Anthropic: output_config.effort — the API also has xhigh/max, deliberately
# not exposed here; a pipeline step that needs them is a design smell).
Effort = Literal["low", "medium", "high"]

EFFORT_VALUES: tuple[str, ...] = ("low", "medium", "high")


@dataclass(frozen=True)
class RenderedPrompt:
    """A fully-rendered prompt ready for one provider call.

    `system` is registry-controlled (platform admins only — see prompts.py);
    `user` is the pipeline-assembled data turn (submissions, facts, steer
    notes — everything untrusted lives here, never in `system`).

    `cache_prefix` is a HINT: the Anthropic adapter sets a cache breakpoint on
    the system block; other adapters may ignore it. `key`/`version`/`provider`
    identify the registry row that produced the template, so ai_variants can
    record exactly what generated an artifact.
    """

    key: str
    system: str
    user: str
    cache_prefix: bool = True
    version: int = 0  # 0 = code default
    provider: str = ""  # registry row provider ('' = shared/code)
    model: str | None = None  # per-prompt model override (None = configured)
    effort: Effort | None = None  # per-prompt effort override
    max_tokens: int = 2048


@dataclass(frozen=True)
class Usage:
    """Normalised per-call usage. Token counts are NOT comparable across
    providers (different tokenizers) — price them into money at write time
    (pricing.py) and never recompute later."""

    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    request_id: str | None = None


@dataclass(frozen=True)
class Completion:
    """The validated object plus what it cost to make."""

    output: BaseModel
    usage: Usage


class ProviderError(RuntimeError):
    """Any provider failure the pipeline should treat as 'this step failed'
    (job → failed, hold refunded). Never leaks provider SDK exception types."""


class ProviderRefusal(ProviderError):
    """The provider declined the request (Anthropic stop_reason == "refusal",
    OpenAI content filter). The pipeline catches it once, marks the job
    failed, and refunds the hold — a refusal never charges the couple."""


class TextModel(Protocol):
    """The port. Adapters: providers/anthropic.py (reference), providers/
    fake.py (offline). Selection is config (`ai_text_provider`), not code."""

    def generate_structured(
        self, prompt: RenderedPrompt, schema: type[BaseModel], *, effort: Effort
    ) -> Completion: ...
