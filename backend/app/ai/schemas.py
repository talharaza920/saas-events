"""Step-output schemas for the AI pipeline (AI_WIZARD_PLAN Phase 8.1).

These are the ONLY shapes the text model can return — structured output is
the strongest anti-injection primitive available here, so there is no
free-text channel out of any step. Bounds (string lengths, list sizes) are
enforced HERE in Pydantic, not in the JSON schema sent to the provider: the
providers' strict-schema subsets don't support length constraints, and the
SDK strips-and-validates client-side, which is exactly the split we want.

`extra="forbid"` everywhere: a model that invents fields fails the parse and
the step fails cleanly, rather than smuggling content into the proposal.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SupportedFact(_Strict):
    """A fact plus the exact submission phrase that supports it — the
    extraction prompt demands the receipt, and the grounding pass and the
    review UI both use it."""

    value: str = Field(max_length=200)
    supported_by: str = Field(max_length=500)


class ExtractedFacts(_Strict):
    """What the couple actually told us. Every field is nullable — a null is
    a correct answer (the couple fills it in themselves); a guess is the
    worst outcome available. Venue is a NAME only: the address comes from
    Places resolution in code, never from the model."""

    couple_names: SupportedFact | None = None
    venue_name: SupportedFact | None = None
    city: SupportedFact | None = None
    event_date: SupportedFact | None = None
    event_time: SupportedFact | None = None
    tone: SupportedFact | None = None


class ArcBeat(_Strict):
    text: str = Field(max_length=400)
    image_prompt: str = Field(max_length=600)


class DraftArc(_Strict):
    kicker: str | None = Field(default=None, max_length=80)
    heading: str = Field(max_length=120)
    intro: str | None = Field(default=None, max_length=400)
    beats: list[ArcBeat] = Field(min_length=1, max_length=8)
    climax: str | None = Field(default=None, max_length=400)
    # The unnumbered "you're invited" panel closes the story section, so it is
    # illustrated like any beat (Phase 8.5b) — the model writes its scene here.
    climax_image_prompt: str | None = Field(default=None, max_length=600)


class UnsupportedClaim(_Strict):
    draft_text: str = Field(max_length=400)
    reason: str = Field(max_length=400)


class GroundingReport(_Strict):
    """The grounding pass: every DRAFT claim checked against SOURCE. The
    review UI renders each unsupported claim as an amber flag; an empty list
    with all_supported=True is the clean bill."""

    unsupported: list[UnsupportedClaim] = Field(default_factory=list, max_length=20)
    all_supported: bool


class GuestLines(_Strict):
    """The guest-extraction output: each invited party EXACTLY as the couple
    wrote it ("Riley Park +1", "Kid (Riley Park)") — names only, markers
    preserved. The model never sees, names, or suggests a tier: the
    deterministic guest_import parser assigns tiers from these raw markers in
    code (the invite-tier secret, guardrail 1)."""

    lines: list[Annotated[str, Field(max_length=200)]] = Field(
        default_factory=list, max_length=300
    )


class GlyphOutput(_Strict):
    """LLM-authored SVG children for a 100x100 viewBox. UNTRUSTED until the
    allowlist-rebuild sanitiser (Phase 8.3) has re-serialised it — nothing
    renders or applies this raw."""

    svg_children: str = Field(max_length=4000)
    concept: str = Field(max_length=200)  # owner-facing one-liner ("two cranes")
