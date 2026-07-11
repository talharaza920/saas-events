"""Allowlist-rebuild sanitiser for LLM-authored glyph SVG (AI_WIZARD_PLAN 8.3 §4).

Rendering model-authored SVG inline is exactly the shape of a stored-XSS bug,
so this never *filters* the input — it parses with defusedxml and REBUILDS a
fresh tree containing only allowlisted elements and attributes, then
re-serialises that. Anything not allowlisted simply doesn't exist in the
output: <script>, event handlers, <style>, hrefs, url() references, text
nodes, comments, namespaces — dropped by construction, not pattern-matched.
(Do not regex-strip <script> — allowlist-rebuild or nothing. The CSP from
Phase 0 is the backstop, not the fix.)

Only the sanitised form is ever stored or rendered: the glyph pipeline step
runs this before the proposal is built (so the review UI never sees raw model
output), and apply runs it again before writing content.brand.icon_svg —
defence in depth, and it keeps the invariant local to both call sites.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET  # serialisation only, of elements WE build

from defusedxml import ElementTree as SafeET  # parsing: DTD/entity attacks rejected


class SvgSanitizationError(ValueError):
    """The glyph couldn't be reduced to a safe, non-empty mark."""


# The glyph prompt's own contract (prompts.py) — enforced here, because the
# prompt does not trust its own output.
ALLOWED_ELEMENTS = frozenset({"g", "path", "polygon", "circle", "ellipse", "rect"})
_GEOMETRY_ATTRS = frozenset(
    {"d", "points", "cx", "cy", "r", "rx", "ry", "x", "y", "width", "height", "transform"}
)
_FILL_RULE_VALUES = frozenset({"nonzero", "evenodd"})
# Path/point/transform syntax and nothing else: no quotes, angle brackets,
# colons (javascript:), ampersands, '#' or '/' (url(#ref), protocol-relative).
_SAFE_VALUE_RE = re.compile(r"^[a-zA-Z0-9\s,.\-+()]{1,2000}$")

MAX_NODES = 64
MAX_DEPTH = 6
MAX_OUTPUT_CHARS = 4000


def _local(name: str) -> str:
    """Strip any XML-namespace prefix ('{http://…}circle' → 'circle')."""
    return name.rsplit("}", 1)[-1]


def _rebuild(node, depth: int, budget: list) -> ET.Element | None:
    if depth > MAX_DEPTH:
        raise SvgSanitizationError("glyph nesting too deep")
    if _local(node.tag) not in ALLOWED_ELEMENTS:
        return None  # drop the whole subtree — nothing inside a foreign element survives
    budget[0] -= 1
    if budget[0] < 0:
        raise SvgSanitizationError("glyph has too many elements")

    tag = _local(node.tag)
    clean = ET.Element(tag)
    for raw_name, raw_value in node.attrib.items():
        name = _local(raw_name)
        value = raw_value.strip()
        if name == "fill":
            # The one permitted paint. Any other value (a hex, a url(#ref))
            # is dropped and the shape inherits currentColor from the wrapper.
            if value == "currentColor":
                clean.set("fill", "currentColor")
        elif name == "fill-rule":
            if value in _FILL_RULE_VALUES:
                clean.set("fill-rule", value)
        elif name in _GEOMETRY_ATTRS and _SAFE_VALUE_RE.match(value):
            clean.set(name, value)
        # everything else — on*, style, stroke, class, id, href… — never copied
    # Text and tail content are never copied: shapes carry no text.
    for child in node:
        rebuilt = _rebuild(child, depth + 1, budget)
        if rebuilt is not None:
            clean.append(rebuilt)
    if tag == "g" and len(clean) == 0:
        return None  # a group whose children were all dropped is noise
    return clean


def sanitize_glyph(svg_children: str) -> str:
    """Model-authored SVG children (100×100 viewBox) → sanitised children.

    Raises SvgSanitizationError when the input doesn't parse, exceeds bounds,
    or nothing drawable survives — the caller treats that as a failed
    generation (pipeline: step fails and refunds; apply: 422), never as
    something to render anyway.
    """
    try:
        root = SafeET.fromstring(f"<svg>{svg_children}</svg>")
    except Exception as exc:
        raise SvgSanitizationError(f"glyph SVG failed to parse: {exc}") from None
    budget = [MAX_NODES]
    parts: list[str] = []
    for child in root:
        rebuilt = _rebuild(child, 1, budget)
        if rebuilt is not None:
            parts.append(ET.tostring(rebuilt, encoding="unicode"))
    out = "".join(parts)
    if not out:
        raise SvgSanitizationError("no drawable shapes survived sanitisation")
    if len(out) > MAX_OUTPUT_CHARS:
        raise SvgSanitizationError("glyph SVG too large after sanitisation")
    return out
