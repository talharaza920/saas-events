"""Illustration styles for story-beat art (AI_WIZARD_PLAN Phase 8.5b).

Two knobs, deliberately unequal in trust:

* `style_preset` — an ALLOWLISTED key. The couple picks a chip; the platform
  owns the sentence that reaches the image model. A key that isn't in the table
  falls back to the default rather than passing anything through.
* `style_note` — the couple's own words, bounded and untrusted. It rides the
  image prompt as data, in the same position and under the same rules as the
  `steer` note on regeneration: it may only nudge the LOOK, and the guardrail
  sentences (no text, no recognisable people) are appended AFTER it so a note
  cannot talk its way past them.

The style lives in `job.state["options"]` rather than in the draft: it is a
rendering choice, iterated on one image after the text is settled (that is the
whole point of the staged wizard), and re-picking it must never touch a word of
the story the couple just approved.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.ai.likeness import LIKENESS_DIRECTION, safe_style_key


@dataclass(frozen=True)
class IllustrationStyle:
    key: str
    label: str  # what the chip says
    description: str  # what the image model is told


STYLE_PRESETS: dict[str, IllustrationStyle] = {
    s.key: s
    for s in (
        IllustrationStyle(
            key="storybook",
            label="Storybook",
            description=(
                "a stylised flat storybook illustration: soft warm palette, gentle "
                "paper texture, simple shapes"
            ),
        ),
        IllustrationStyle(
            key="watercolor",
            label="Watercolour",
            description=(
                "a loose watercolour painting: wet edges, blooming washes, visible "
                "paper grain, muted natural pigments"
            ),
        ),
        IllustrationStyle(
            key="hyper_realistic",
            label="Photographic",
            description=(
                "a photographic image: natural light, shallow depth of field, "
                "realistic materials and textures"
            ),
        ),
        IllustrationStyle(
            key="anime",
            label="Anime",
            description=(
                "an anime/manga illustration: clean linework, cel shading, "
                "expressive light, saturated accents"
            ),
        ),
        IllustrationStyle(
            key="line_art",
            label="Line art",
            description=(
                "a single-weight ink line drawing: no shading, generous white space, "
                "one restrained accent colour"
            ),
        ),
        IllustrationStyle(
            key="claymation",
            label="Claymation",
            description=(
                "a stop-motion claymation still: modelling-clay surfaces with "
                "thumbprint texture, soft studio light, shallow miniature set"
            ),
        ),
    )
}

DEFAULT_STYLE = "storybook"
MAX_STYLE_NOTE_CHARS = 200


def resolve_style(options: dict | None, *, has_references: bool = False) -> IllustrationStyle:
    """The style for this job. An unknown key is the default, never an error:
    a stale chip in a stored proposal must not fail a run. With likeness
    references attached, a blocked (photographic) style degrades to the default
    for the same reason — the render path never refuses, it just never renders
    a photoreal picture of a real person (app/ai/likeness.py)."""
    key = (options or {}).get("style_preset")
    if not (isinstance(key, str) and key in STYLE_PRESETS):
        return STYLE_PRESETS[DEFAULT_STYLE]
    return STYLE_PRESETS[
        safe_style_key(key, has_references=has_references, fallback=DEFAULT_STYLE)
    ]


def compose_image_prompt(
    scene: str,
    options: dict | None,
    *,
    steer: str | None = None,
    has_references: bool = False,
) -> str:
    """scene + style + the couple's untrusted notes + the guardrails, in that
    order. The guardrails go LAST on purpose — they are the sentences a style
    note or steer must not be able to override.

    `has_references` = the couple attached consented photos of themselves (8.5d),
    which swaps the no-recognisable-people guardrail for the likeness direction:
    the two contradict each other, so exactly one of them is ever in the prompt.
    """
    style = resolve_style(options, has_references=has_references)
    note = (options or {}).get("style_note")
    parts = [f"{style.description.capitalize()}.", f"Scene: {scene.strip()}"]
    if isinstance(note, str) and note.strip():
        parts.append(f"Style note from the couple: {note.strip()[:MAX_STYLE_NOTE_CHARS]}")
    if steer:
        parts.append(f"Adjustment requested by the couple: {steer.strip()}")
    parts.append(
        LIKENESS_DIRECTION
        if has_references
        else (
            "No text, lettering or numerals anywhere in the image. No recognisable real "
            "people — any figures are small, stylised and faceless."
        )
    )
    return " ".join(parts)
