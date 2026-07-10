"""Deterministic offline adapter — the test/dev stand-in for a real provider.

Configured with canned payloads per prompt key (or a callable for dynamic
behaviour); records every call so tests can assert exactly what the pipeline
sent through the port. Also the golden-set eval harness's replay seam: fixture
payloads go in, deterministic outputs come out, zero dollars spent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from pydantic import BaseModel

from app.ai.types import Completion, Effort, ProviderError, RenderedPrompt, Usage

# A canned entry: a payload dict validated against the step's schema, an
# exception instance to raise (e.g. ProviderRefusal("...")), or a callable
# (prompt, schema) -> payload dict.
CannedResponse = dict | Exception | Callable[[RenderedPrompt, type[BaseModel]], dict]


@dataclass
class RecordedCall:
    prompt: RenderedPrompt
    schema: type[BaseModel]
    effort: Effort


@dataclass
class FakeTextModel:
    responses: dict[str, CannedResponse] = field(default_factory=dict)
    calls: list[RecordedCall] = field(default_factory=list)
    input_tokens: int = 100
    output_tokens: int = 50

    def generate_structured(
        self, prompt: RenderedPrompt, schema: type[BaseModel], *, effort: Effort
    ) -> Completion:
        self.calls.append(RecordedCall(prompt=prompt, schema=schema, effort=effort))
        canned = self.responses.get(prompt.key)
        if canned is None:
            raise ProviderError(
                f"FakeTextModel has no canned response for prompt key {prompt.key!r}"
            )
        if isinstance(canned, Exception):
            raise canned
        payload = canned(prompt, schema) if callable(canned) else canned
        return Completion(
            output=schema.model_validate(payload),
            usage=Usage(
                provider="fake",
                model="fake-model",
                input_tokens=self.input_tokens,
                output_tokens=self.output_tokens,
                request_id=f"fake-{len(self.calls)}",
            ),
        )
