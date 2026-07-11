"""OpenAI adapter — the second implementation of the TextModel port.

Same one-method contract as providers/anthropic.py; the differences the plan's
leak table predicted, and how they land here:

- Structured output goes through `client.responses.parse(text_format=…)` (the
  Responses API): the SDK converts the Pydantic model to OpenAI's strict-JSON
  subset and validates client-side after parsing — bounds live in Pydantic,
  same split as the Anthropic adapter.
- Reasoning depth maps to `reasoning: {"effort": low|medium|high}`. That
  parameter only exists on reasoning models (the gpt-5 family) — if the
  configured model rejects it, the adapter retries ONCE without it and logs
  `ai.openai.reasoning_unsupported`, so a platform admin pinning a
  non-reasoning model in a prompt row degrades a knob instead of failing jobs.
- `cache_prefix` is ignored: OpenAI prefix-caches automatically; the hint is
  Anthropic-shaped by design.
- A refusal is a `refusal` content part (or an `incomplete` response with
  reason `content_filter`) — both raise ProviderRefusal, so the pipeline's
  single refund path holds across providers.
- No sampling knobs, deliberately (the port exposes none).
- `ai_text_model` must actually be an OpenAI id (e.g. `gpt-5.1`) when this
  adapter is selected — the configured default is a Claude id, and sending it
  here would only fail slower, so the adapter refuses it with the fix named.

Per the plan: a provider change that hasn't passed the golden-set eval (8.1c)
doesn't reach production, however tempting the price per token looks.
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


class OpenAITextModel:
    """`client` is injectable for tests; the real SDK import is lazy so the
    app (and the offline suite) never needs the `openai` package unless this
    adapter is actually selected."""

    def __init__(self, settings: Settings, client: Any | None = None):
        self._settings = settings
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import openai
            except ImportError as exc:  # pragma: no cover - environment issue
                raise ProviderError(
                    "ai_text_provider=openai but the 'openai' package is not "
                    "installed (pip install openai)"
                ) from exc
            if not self._settings.openai_api_key:
                raise ProviderError("OPENAI_API_KEY is not configured")
            # SDK default retries (2, honouring retry-after) cover rate limits.
            self._client = openai.OpenAI(api_key=self._settings.openai_api_key)
        return self._client

    def generate_structured(
        self, prompt: RenderedPrompt, schema: type[BaseModel], *, effort: Effort
    ) -> Completion:
        model = prompt.model or self._settings.ai_text_model
        if model.startswith("claude"):
            raise ProviderError(
                f"ai_text_provider=openai but the model is {model!r} — set "
                "AI_TEXT_MODEL to an OpenAI model (e.g. gpt-5.1) or override "
                "the model per prompt key"
            )
        kwargs: dict = {
            "model": model,
            "max_output_tokens": prompt.max_tokens,
            "reasoning": {"effort": effort},
            "input": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
            "text_format": schema,
        }
        try:
            response = self._parse(kwargs)
        except ProviderError:
            raise
        except Exception as exc:
            # Never leak SDK exception types past the port — the pipeline has
            # exactly one failure path (job failed, hold refunded).
            raise ProviderError(f"openai call failed: {exc}") from exc

        refusal = self._refusal_text(response)
        if refusal is not None:
            log_event(logger, "ai.provider.refusal", model=model, provider="openai")
            raise ProviderRefusal(f"model declined the request ({refusal[:200]})")
        if getattr(response, "status", None) == "incomplete":
            reason = getattr(getattr(response, "incomplete_details", None), "reason", None)
            if reason == "content_filter":
                log_event(logger, "ai.provider.refusal", model=model, provider="openai")
                raise ProviderRefusal("model declined the request (content filter)")
            raise ProviderError(
                f"output truncated at {prompt.max_tokens} tokens for {prompt.key}"
                if reason == "max_output_tokens"
                else f"provider returned an incomplete response ({reason}) for {prompt.key}"
            )
        parsed = response.output_parsed
        if parsed is None:
            raise ProviderError(f"provider returned unparseable output for {prompt.key}")

        return Completion(
            output=parsed,
            usage=Usage(
                provider="openai",
                model=response.model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                request_id=getattr(response, "_request_id", None),
            ),
        )

    def _parse(self, kwargs: dict) -> Any:
        client = self._get_client()
        try:
            return client.responses.parse(**kwargs)
        except Exception as exc:
            # Non-reasoning models 400 on the `reasoning` parameter; degrade
            # the knob rather than the job, once, loudly.
            if "reasoning" in kwargs and "reasoning" in str(exc).lower():
                log_event(
                    logger, "ai.openai.reasoning_unsupported", model=kwargs.get("model")
                )
                retry = {k: v for k, v in kwargs.items() if k != "reasoning"}
                return client.responses.parse(**retry)
            raise

    @staticmethod
    def _refusal_text(response: Any) -> str | None:
        for item in getattr(response, "output", None) or []:
            if getattr(item, "type", None) != "message":
                continue
            for part in getattr(item, "content", None) or []:
                if getattr(part, "type", None) == "refusal":
                    return getattr(part, "refusal", "") or "no reason given"
        return None
