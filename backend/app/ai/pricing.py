"""Per-(provider, model) price table → money at write time.

Tokenizers differ across providers, so token counts are never comparable —
the ledger stores DOLLARS (micros), priced here the moment the call returns,
and never recomputed later from a stored token count. When a model id is
missing from the table the cost records as 0 with the model string kept on
the row, so the gap is auditable rather than silently mispriced — add the
price and it applies to future rows only (the ledger is append-only).

Prices are USD per million tokens (input, output). Keep in sync with
https://platform.claude.com/docs/en/pricing when models change; model ids are
config, not code (`ai_text_model`), so a new model is a table entry + env
change, no deploy logic.
"""
from __future__ import annotations

import logging

from app.ai.types import Usage
from app.obs import log_event

logger = logging.getLogger("app.ai")

# (provider, model) -> (usd_per_mtok_input, usd_per_mtok_output)
PRICES: dict[tuple[str, str], tuple[float, float]] = {
    ("anthropic", "claude-opus-4-8"): (5.00, 25.00),
    ("anthropic", "claude-opus-4-7"): (5.00, 25.00),
    ("anthropic", "claude-sonnet-4-6"): (3.00, 15.00),
    ("anthropic", "claude-haiku-4-5"): (1.00, 5.00),
    # OpenAI (verify against platform.openai.com/pricing when switching — an
    # id missing here records $0 and logs ai.pricing.unknown_model).
    ("openai", "gpt-5.1"): (1.25, 10.00),
    ("openai", "gpt-5"): (1.25, 10.00),
    ("openai", "gpt-5-mini"): (0.25, 2.00),
    ("openai", "gpt-5-nano"): (0.05, 0.40),
    # Gemini media seam (ai.google.dev/gemini-api/docs/pricing, 2026-07-12).
    # Note flash-lite audio INPUT is $0.50/Mtok (vs $0.25 text) — if the
    # transcribe model ever moves there, split the rate.
    ("google", "gemini-3.5-flash"): (1.50, 9.00),
    ("google", "gemini-3.1-flash-lite"): (0.25, 1.50),
    # The fake adapter is free — keeps offline runs honest in the ledger.
    ("fake", "fake-model"): (0.0, 0.0),
}

# Image generation is priced PER IMAGE, not per token (USD each, at the 1K
# resolution we request). Same unknown-model stance as PRICES: record 0,
# log, fix the table.
IMAGE_PRICES: dict[tuple[str, str], float] = {
    ("google", "gemini-3.1-flash-image"): 0.067,  # "Nano Banana 2"
    ("google", "gemini-3.1-flash-lite-image"): 0.0336,
    ("google", "gemini-3-pro-image"): 0.134,
    ("fake", "fake-image-model"): 0.0,
}


def cost_usd_micros(usage: Usage, *, images: int | None = None) -> int:
    """Dollar cost of one call, in millionths of a USD.

    $X per Mtok is exactly X micros per token, so this is just
    tokens × price with no unit gymnastics. Image calls add a flat
    per-image price on top of any token cost.
    """
    prices = PRICES.get((usage.provider, usage.model))
    image_price = IMAGE_PRICES.get((usage.provider, usage.model)) if images else None
    if prices is None and image_price is None:
        log_event(
            logger, "ai.pricing.unknown_model",
            provider=usage.provider, model=usage.model,
        )
        return 0
    in_price, out_price = prices or (0.0, 0.0)
    total = usage.input_tokens * in_price + usage.output_tokens * out_price
    if images and image_price is not None:
        total += images * image_price * 1_000_000
    return round(total)
