"""Anthropic adapter — the reference implementation of the TextModel port.

Request-shape notes that are easy to get wrong (verified against the Claude
API docs at build time; the golden-set eval is the gate for changes):

- `thinking: {"type": "adaptive"}` must be set EXPLICITLY — omitting the field
  on Opus 4.8 runs without thinking.
- Reasoning depth is `output_config.effort`. The API also has xhigh/max; the
  port's Effort is low|medium|high by design (see types.py).
- `temperature`/`top_p`/`top_k` all 400 on Opus 4.8 — the port exposes no
  sampling knobs, which is the right call regardless of provider.
- Structured output goes through `client.messages.parse(output_format=…)`:
  the SDK strips schema constraints the API doesn't support (string lengths,
  numeric bounds) and validates them client-side after parsing — exactly the
  split the plan calls for ("enforce bounds in Pydantic after parsing").
- A refusal is a SUCCESSFUL response with `stop_reason == "refusal"` — check
  it before reading content, raise ProviderRefusal (the pipeline refunds).
- `cache_prefix` sets a cache breakpoint on the system block. Verify caching
  with `usage.cache_read_input_tokens`; a persistent zero across identical
  runs means something in the prefix is varying (a timestamp, an unsorted
  dict, a per-request id), not that caching is broken. Opus 4.8's minimum
  cacheable prefix is 4096 tokens — below that the marker is a silent no-op.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from app.ai.types import (
    Completion,
    Effort,
    ProviderError,
    ProviderRefusal,
    RenderedPrompt,
    Usage,
)
from app.config import Settings
from app.obs import log_event

logger = logging.getLogger("app.ai")


class AnthropicTextModel:
    """`client` is injectable for tests; the real SDK import is lazy so the
    whole app (and the offline test suite) never needs the `anthropic`
    package unless this adapter is actually selected."""

    def __init__(self, settings: Settings, client: Any | None = None):
        self._settings = settings
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - environment issue
                raise ProviderError(
                    "ai_text_provider=anthropic but the 'anthropic' package is "
                    "not installed (pip install anthropic)"
                ) from exc
            if not self._settings.anthropic_api_key:
                raise ProviderError("ANTHROPIC_API_KEY is not configured")
            # SDK default retries (2, with backoff honouring retry-after)
            # cover the low rate-limit tiers a new org starts on.
            self._client = anthropic.Anthropic(api_key=self._settings.anthropic_api_key)
        return self._client

    def generate_structured(
        self, prompt: RenderedPrompt, schema: type[BaseModel], *, effort: Effort
    ) -> Completion:
        model = prompt.model or self._settings.ai_text_model
        system_block: dict = {"type": "text", "text": prompt.system}
        if prompt.cache_prefix:
            system_block["cache_control"] = {"type": "ephemeral"}
        try:
            response = self._get_client().messages.parse(
                model=model,
                max_tokens=prompt.max_tokens,
                system=[system_block],
                thinking={"type": "adaptive"},
                output_config={"effort": effort},
                messages=[{"role": "user", "content": prompt.user}],
                output_format=schema,
            )
        except ProviderError:
            raise
        except Exception as exc:
            # Never leak SDK exception types past the port — the pipeline has
            # exactly one failure path (job failed, hold refunded).
            raise ProviderError(f"anthropic call failed: {exc}") from exc

        if response.stop_reason == "refusal":
            detail = getattr(response, "stop_details", None)
            category = getattr(detail, "category", None) if detail else None
            log_event(logger, "ai.provider.refusal", model=model, category=category)
            raise ProviderRefusal(f"model declined the request (category={category})")
        if response.stop_reason == "max_tokens":
            raise ProviderError(
                f"output truncated at {prompt.max_tokens} tokens for {prompt.key}"
            )
        parsed = response.parsed_output
        if parsed is None:
            raise ProviderError(f"provider returned unparseable output for {prompt.key}")

        return Completion(
            output=parsed,
            usage=Usage(
                provider="anthropic",
                model=response.model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                request_id=getattr(response, "_request_id", None),
            ),
        )
