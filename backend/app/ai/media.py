"""Media understanding seam (AI_WIZARD_PLAN: "audio/pdf/image → Gemini").

A seam in the FILE-LAYOUT sense only — it makes no promise of
substitutability (the plan explicitly rejects abstracting media providers:
all leak, no port). Everything media-shaped becomes TEXT here, before the
text-LLM port ever sees it; that normalisation is what keeps the text port
one method wide.

The Gemini call itself is NOT implemented yet — it needs a billing-enabled
Google AI Studio project (free-tier input may be used for product
improvement, which is unacceptable for guest PII) and the current model id
confirmed against Google's docs (the id churns; never trust a written-down
one). Until RT provisions that key, media inputs fail with a clear
ProviderError and TEXT inputs pass through untouched — the whole pipeline
works offline on pasted text.
"""
from __future__ import annotations

from app.ai.types import ProviderError
from app.config import Settings
from app.models import AiInput

# Pasted text can be long (a WhatsApp history) but the working set must stay
# bounded — this caps what one input contributes to the job state.
MAX_TRANSCRIPT_CHARS = 20_000


def transcribe_input(settings: Settings, ai_input: AiInput) -> str:
    """One submission → text. `text` inputs pass through; media kinds need
    the Gemini seam implemented + GEMINI_API_KEY configured."""
    if ai_input.kind == "text":
        return (ai_input.text_content or "")[:MAX_TRANSCRIPT_CHARS]
    if not settings.gemini_api_key:
        raise ProviderError(
            f"Cannot transcribe a {ai_input.kind!r} input: media understanding "
            "(Gemini) isn't configured — set GEMINI_API_KEY (billing-enabled "
            "project only; see AI_WIZARD_PLAN's key table)."
        )
    # TODO(Phase 8.1b-infra): implement the Gemini transcribe call when the
    # key exists — confirm the current model id against Google's docs at that
    # moment (google-genai SDK; audio/PDF/image → text).
    raise ProviderError(
        "Gemini transcription is not implemented yet (blocked on provisioning; "
        "AI_WIZARD_PLAN Phase 8.1b-infra)."
    )
