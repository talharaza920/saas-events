"""Deterministic offline adapter — the test/dev stand-in for a real provider.

Configured with canned payloads per prompt key (or a callable for dynamic
behaviour); records every call so tests can assert exactly what the pipeline
sent through the port. Also the golden-set eval harness's replay seam: fixture
payloads go in, deterministic outputs come out, zero dollars spent.
"""
from __future__ import annotations

import copy
import itertools
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


# --- Local-dev demo canned set -------------------------------------------------
# What `ai_text_provider=fake` serves OUTSIDE tests (tests script their own
# FakeTextModel): a full wizard run works offline against the seeded template
# wedding, the grounding pass flags one claim (so the amber-flag review path is
# visible), and draft/glyph regenerations cycle alternates so variants differ.
# The steer note is deliberately not interpreted — this is canned data, not a
# model.

_DEMO_EXTRACT = {
    "couple_names": {"value": "Alex & Sam", "supported_by": "we're Alex and Sam"},
    "venue_name": {"value": "Fern Hall", "supported_by": "at Fern Hall"},
    "city": {"value": "Riverton", "supported_by": "here in Riverton"},
    "event_date": {"value": "2027-05-01", "supported_by": "on May 1st, 2027"},
}

_DEMO_ARCS = [
    {
        "kicker": "Our story",
        "heading": "Alex & Sam",
        "intro": "Six years, two cities, one very patient cat.",
        "beats": [
            {"text": "They met at a bus stop, sharing one umbrella.",
             "image_prompt": "a rainy bus stop at dusk, one umbrella, warm light"},
            {"text": "Sam moved cities; Alex followed a season later.",
             "image_prompt": "two suitcases by an open door, morning light"},
            {"text": "The question was asked over burnt pancakes.",
             "image_prompt": "a small kitchen table, pancakes, a ring box"},
        ],
        "climax": "And now — come celebrate with them.",
    },
    {
        "kicker": "How it began",
        "heading": "Alex & Sam",
        "intro": "A missed bus, a shared umbrella, and everything after.",
        "beats": [
            {"text": "One late bus threw two strangers under the same awning.",
             "image_prompt": "a bus-stop awning in the rain, city lights"},
            {"text": "Letters became visits; visits became a shared address.",
             "image_prompt": "a stack of letters tied with string"},
            {"text": "The yes was instant. The pancakes were not saved.",
             "image_prompt": "smoke over a pan, two people laughing"},
        ],
        "climax": "Join them for the next chapter.",
    },
]

# Legibility doesn't matter — these exist so regenerated glyph variants differ.
_DEMO_GLYPHS = [
    {"svg_children":
        '<circle cx="38" cy="50" r="22" fill="currentColor"/>'
        '<circle cx="62" cy="50" r="22" fill="currentColor"/>',
     "concept": "two overlapping rings"},
    {"svg_children":
        '<polygon points="50,18 61,40 85,44 67,61 72,85 50,73 28,85 33,61 15,44 39,40" '
        'fill="currentColor"/>',
     "concept": "a single star"},
    {"svg_children":
        '<rect x="35" y="35" width="30" height="30" transform="rotate(45 50 50)" '
        'fill="currentColor"/><circle cx="50" cy="14" r="6" fill="currentColor"/>',
     "concept": "a diamond and a rising sun"},
]

# Raw lines exactly as "the couple wrote them" — the deterministic
# guest_import parser (not the model, not this fake) turns the markers into
# tiers, so the demo exercises the real tier path offline.
_DEMO_GUEST_LINES = {
    "lines": [
        "Jordan Lee",
        "Riley Park",
        "Riley Park +1",
        "Casey Nguyen",
        "Casey Nguyen +1",
        "Kid (Casey Nguyen)",
        "Sasha Chen",
    ]
}

_DEMO_GROUND = {
    "unsupported": [
        {
            "draft_text": "Six years, two cities, one very patient cat.",
            "reason": "The submissions don't say how long they've been together.",
        }
    ],
    "all_supported": False,
}


# Module-level on purpose: the provider factory builds a fresh FakeTextModel
# per request (it's a FastAPI dependency), so per-instance cycles would reset
# every call and a "regenerated" variant would be identical to the original.
_ARC_CYCLE = itertools.cycle(_DEMO_ARCS)
_GLYPH_CYCLE = itertools.cycle(_DEMO_GLYPHS)


def demo_responses() -> dict[str, CannedResponse]:
    return {
        "extract.system": _DEMO_EXTRACT,
        "extract_guests.system": _DEMO_GUEST_LINES,
        "draft_arc.system": lambda _p, _s: copy.deepcopy(next(_ARC_CYCLE)),
        "ground.system": _DEMO_GROUND,
        "glyph.system": lambda _p, _s: copy.deepcopy(next(_GLYPH_CYCLE)),
    }
