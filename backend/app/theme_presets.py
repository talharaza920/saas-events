"""Theme presets (AI_WIZARD_PLAN 8.5e) — the curated looks a couple can start from.

A preset is a NAMED `theme_tokens` patch. The couple picks one on the Theme tab,
it is COPIED onto their wedding, and from there every token stays editable — a
preset is a starting point, never a lock, and nothing links back to it. Editing
or deleting a preset in the console therefore cannot reach into a wedding that
already applied it. That is the whole reason apply copies instead of referencing.

**Platform-owned data, not code.** The catalogue lives in one
`platform_settings['theme_presets']` blob seeded from the code defaults below, so
curating it (add / edit / reorder / disable / delete) is a console action, not a
deploy. Same never-brick stance as the prompt registry and DEFAULT_ENTITLEMENTS:
a missing or structurally broken blob falls back to these defaults, and a single
malformed preset inside an otherwise good blob is skipped rather than 500ing the
Theme tab for every tenant.

**Presets are validated, and the validation is deliberately narrow.** The tokens
a preset may carry are colours (hex), the numeric knobs, and fonts CHOSEN FROM
THE FACES THE APP ACTUALLY LOADS. A font family is not really data: adding one
means registering it with next/font in `app/layout.tsx`, so an unbounded font
string in the console would be a promise the frontend can't keep — it would
silently render the fallback stack. The allowlist below is that constraint made
explicit, and it must be kept in step with `frontend/theme/defaultThemeConfig.ts`.
`shadows` are not preset-able for a related reason: the editor and the preview
don't cover them, so a preset couldn't show what it was doing.
"""
from __future__ import annotations

import logging
import re
from copy import deepcopy

from sqlalchemy.orm import Session

from app.models import PlatformSetting
from app.obs import log_event

logger = logging.getLogger("app.platform")

THEME_PRESETS_KEY = "theme_presets"

# Mirrors ThemeColors in frontend/theme/types.ts. A preset may set any subset:
# what it omits is inherited from the "Ever after" default by the same deep-merge
# that has always backed per-wedding overrides.
COLOR_KEYS = frozenset(
    {
        "paper", "paperAlt", "paperEdge", "ink", "inkSoft",
        "primary", "primaryDeep", "secondary", "accentSage", "accentLav",
        "yes", "no", "amber", "dream1", "dream2", "dream3", "dream4",
    }
)

# The three faces registered via next/font (frontend/app/layout.tsx). Values are
# the exact CSS stacks defaultThemeConfig.ts uses — a preset picks among these,
# it does not invent one. Adding a fourth face is a frontend code change AND a
# line here; that coupling is the point (see the module docstring).
FONT_DISPLAY = 'var(--font-display), "Baloo 2", system-ui, sans-serif'
FONT_STORY = 'var(--font-story), "Lora", Georgia, serif'
FONT_BODY = 'var(--font-body), "Plus Jakarta Sans", system-ui, -apple-system, sans-serif'
FONT_STACKS = frozenset({FONT_DISPLAY, FONT_STORY, FONT_BODY})
TYPOGRAPHY_KEYS = frozenset({"logo", "display", "story", "body"})

# The numeric knobs, with the range each is sane in.
NUMERIC_KEYS: dict[str, tuple[int, int]] = {
    "radius": (0, 64),
    "radiusLg": (0, 64),
    "spacingUnit": (4, 16),
    "storyFeather": (0, 25),
}

HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")

MAX_PRESETS = 40
# Which colours the swatch row shows when a preset doesn't name its own, in this
# order — the ones that carry a look at a glance.
SWATCH_ORDER = ("primary", "secondary", "accentSage", "accentLav", "paper", "ink")


def _colors(**kw: str) -> dict[str, str]:
    return dict(kw)


def _preset(
    preset_id: str,
    name: str,
    description: str,
    *,
    colors: dict[str, str],
    display: str = FONT_DISPLAY,
    body: str = FONT_BODY,
    story: str = FONT_STORY,
) -> dict:
    """One catalogue entry. The wordmark follows the heading face, exactly as the
    wedding's own Theme tab does it — a preset and a hand edit produce the same
    shape of patch."""
    return {
        "id": preset_id,
        "name": name,
        "description": description,
        "swatches": [],  # derived from the colours unless the console overrides
        "enabled": True,
        "tokens": {
            "colors": colors,
            "typography": {"display": display, "logo": display, "story": story, "body": body},
        },
    }


# --- The catalogue that ships in code ---------------------------------------
# Ten looks, each a complete palette (including the `dream*` hero wash and the
# `amber` pending colour — a preset that left those at the cream template's
# values would look broken the moment you picked a dark or cool one).
DEFAULT_THEME_PRESETS: list[dict] = [
    _preset(
        "ever-after", "Ever after", "The template: cream paper, sunset terracotta",
        colors=_colors(
            paper="#F3EEE3", paperAlt="#ECE4D4", paperEdge="#E3D9C5",
            ink="#1A1714", inkSoft="#5B534A",
            primary="#D98C6A", primaryDeep="#B5704F", secondary="#8E9BB3",
            accentSage="#9DAE8E", accentLav="#C9BBD6",
            yes="#6FA38A", no="#B0796E", amber="#CDA15B",
            dream1="#CDBFE0", dream2="#F3C9C0", dream3="#CFE0D6", dream4="#F6E3B8",
        ),
    ),
    _preset(
        "blush-garden", "Blush garden", "Rose, ivory and a soft green stem",
        colors=_colors(
            paper="#FBF2F0", paperAlt="#F5E6E4", paperEdge="#EBD5D2",
            ink="#3A2A2C", inkSoft="#7A6467",
            primary="#D98395", primaryDeep="#B96579", secondary="#B3A2C4",
            accentSage="#A8BFA4", accentLav="#DCC4DA",
            yes="#7BA98D", no="#C27C7C", amber="#DDAE70",
            dream1="#F4CBD6", dream2="#F7DDD3", dream3="#DCE7DC", dream4="#F6E7C9",
        ),
    ),
    _preset(
        "sage-linen", "Sage & linen", "Natural linen with a quiet green",
        colors=_colors(
            paper="#F4F2EA", paperAlt="#E9E7DB", paperEdge="#DCD9C9",
            ink="#232720", inkSoft="#5E6358",
            primary="#7E9A76", primaryDeep="#5F7B59", secondary="#A9B7A2",
            accentSage="#8FA687", accentLav="#C6C3D8",
            yes="#6F9A78", no="#B27D6C", amber="#C8A45E",
            dream1="#D9E3D2", dream2="#EFE7CF", dream3="#CFDDD3", dream4="#E7EBD5",
        ),
        story=FONT_STORY,
    ),
    _preset(
        "midnight-gold", "Midnight & gold", "Deep navy night, warm gold letters",
        colors=_colors(
            paper="#141A2E", paperAlt="#1D2440", paperEdge="#2C3557",
            ink="#F2ECDF", inkSoft="#B9BFD4",
            primary="#D9B26A", primaryDeep="#BC9450", secondary="#7E8BB8",
            accentSage="#7FA894", accentLav="#A99AD1",
            yes="#6FB295", no="#C97F7F", amber="#E0B764",
            dream1="#2A3358", dream2="#3B3060", dream3="#24405A", dream4="#4A3E68",
        ),
    ),
    _preset(
        "coastal-blue", "Coastal", "Sea blues over pale sand",
        colors=_colors(
            paper="#F1F4F5", paperAlt="#E2E9EC", paperEdge="#CFDBE0",
            ink="#17262E", inkSoft="#4F6672",
            primary="#4E87A6", primaryDeep="#376C89", secondary="#8FB3C4",
            accentSage="#8FBAAE", accentLav="#B6C2DE",
            yes="#4E9E8C", no="#C0796F", amber="#D2A462",
            dream1="#C6DCE6", dream2="#E3EEF0", dream3="#CDE5DD", dream4="#F0E4C8",
        ),
    ),
    _preset(
        "terracotta-desert", "Desert", "Clay, ochre and dry heat",
        colors=_colors(
            paper="#F6EFE6", paperAlt="#EDE0D0", paperEdge="#E0CDB6",
            ink="#2E211A", inkSoft="#6B5747",
            primary="#C56E4C", primaryDeep="#A2543A", secondary="#B79470",
            accentSage="#A3A276", accentLav="#CBB0AC",
            yes="#8AA06A", no="#B36A5E", amber="#D79B4C",
            dream1="#EDD3B8", dream2="#F1C7AE", dream3="#DBDCBD", dream4="#F7E2B5",
        ),
    ),
    _preset(
        "lavender-dusk", "Lavender dusk", "Lilac, plum and late light",
        colors=_colors(
            paper="#F5F1F7", paperAlt="#EAE3EF", paperEdge="#DBD1E4",
            ink="#2B2333", inkSoft="#635870",
            primary="#9A7BBE", primaryDeep="#7A5E9C", secondary="#9CA7CF",
            accentSage="#9FB9A8", accentLav="#C7B2E0",
            yes="#7BA891", no="#B57596", amber="#CBA268",
            dream1="#DCCBEC", dream2="#F0D6E6", dream3="#D2E1DC", dream4="#EFE0C6",
        ),
    ),
    _preset(
        "ink-and-paper", "Ink & paper", "Monochrome, one red line",
        colors=_colors(
            paper="#FAFAF8", paperAlt="#F0F0EE", paperEdge="#E0E0DC",
            ink="#14161A", inkSoft="#5C6068",
            primary="#C0433C", primaryDeep="#9C332E", secondary="#8A8F98",
            accentSage="#9AA39B", accentLav="#B7B6C2",
            yes="#4E8C6A", no="#C0433C", amber="#C39A4E",
            dream1="#E6E6E4", dream2="#EFE0DE", dream3="#E2E8E4", dream4="#F1EBD9",
        ),
        display=FONT_BODY,
        body=FONT_BODY,
    ),
    _preset(
        "citrus-summer", "Citrus", "Coral and lemon, high summer",
        colors=_colors(
            paper="#FEF6E9", paperAlt="#FBEAD2", paperEdge="#F3DAB8",
            ink="#31231A", inkSoft="#6F5B48",
            primary="#E8703E", primaryDeep="#C4562B", secondary="#5FA9A0",
            accentSage="#9CBE6E", accentLav="#E4B7C6",
            yes="#63A86C", no="#D8624F", amber="#F0B03E",
            dream1="#FBD9A8", dream2="#FAC6AA", dream3="#CFE6C8", dream4="#FDEEC0",
        ),
    ),
    _preset(
        "forest-emerald", "Forest", "Deep green, cream and brass",
        colors=_colors(
            paper="#F2F1E7", paperAlt="#E4E5D8", paperEdge="#D2D5C3",
            ink="#18231C", inkSoft="#4D5B50",
            primary="#2F6B52", primaryDeep="#21503D", secondary="#87A392",
            accentSage="#6E9078", accentLav="#B9BDD3",
            yes="#3F8A66", no="#AE6E63", amber="#C9A257",
            dream1="#CFE0D2", dream2="#EBE3C9", dream3="#C4DACB", dream4="#E9E7C7",
        ),
        story=FONT_STORY,
    ),
]


class PresetError(ValueError):
    """A preset the catalogue may not hold. Message is shown to the console."""


def _validate_tokens(tokens: object, where: str) -> dict:
    if not isinstance(tokens, dict) or not tokens:
        raise PresetError(f"{where}: needs a non-empty tokens object")
    unknown = set(tokens) - {"colors", "typography"} - set(NUMERIC_KEYS)
    if unknown:
        raise PresetError(
            f"{where}: a preset can't set {', '.join(sorted(unknown))} "
            f"(colours, fonts and {', '.join(NUMERIC_KEYS)} only)"
        )
    out: dict = {}

    colors = tokens.get("colors")
    if colors is not None:
        if not isinstance(colors, dict):
            raise PresetError(f"{where}: colors must be an object")
        bad_keys = set(colors) - COLOR_KEYS
        if bad_keys:
            raise PresetError(f"{where}: unknown colour {', '.join(sorted(bad_keys))}")
        for key, value in colors.items():
            if not isinstance(value, str) or not HEX_RE.match(value):
                raise PresetError(f"{where}: {key} must be a hex colour like #D98C6A")
        out["colors"] = dict(colors)

    typography = tokens.get("typography")
    if typography is not None:
        if not isinstance(typography, dict):
            raise PresetError(f"{where}: typography must be an object")
        bad_keys = set(typography) - TYPOGRAPHY_KEYS
        if bad_keys:
            raise PresetError(f"{where}: unknown font slot {', '.join(sorted(bad_keys))}")
        for key, value in typography.items():
            if value not in FONT_STACKS:
                raise PresetError(
                    f"{where}: {key} must be one of the fonts the app loads "
                    "(adding a face is a frontend change)"
                )
        out["typography"] = dict(typography)

    for key, (low, high) in NUMERIC_KEYS.items():
        if key in tokens:
            value = tokens[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PresetError(f"{where}: {key} must be a number")
            if not low <= value <= high:
                raise PresetError(f"{where}: {key} must be between {low} and {high}")
            out[key] = value

    if not out:
        raise PresetError(f"{where}: needs a non-empty tokens object")
    return out


def validate_preset(raw: object, *, index: int = 0) -> dict:
    """One catalogue entry, normalised — or PresetError saying what's wrong.

    The same function guards the console's PUT (where a failure is a 422 the
    admin reads) and the read path (where a failure means skip this one and keep
    serving the rest). Two dispositions, one definition of "valid"."""
    where = f"preset #{index + 1}"
    if not isinstance(raw, dict):
        raise PresetError(f"{where}: must be an object")

    preset_id = raw.get("id")
    if not isinstance(preset_id, str) or not ID_RE.match(preset_id):
        raise PresetError(f"{where}: id must be a slug like 'blush-garden'")
    where = f"'{preset_id}'"

    name = raw.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 40:
        raise PresetError(f"{where}: needs a name (1–40 characters)")

    description = raw.get("description") or ""
    if not isinstance(description, str) or len(description) > 120:
        raise PresetError(f"{where}: the description can't be longer than 120 characters")

    swatches = raw.get("swatches") or []
    if not isinstance(swatches, list) or len(swatches) > 6:
        raise PresetError(f"{where}: up to 6 swatches")
    for value in swatches:
        if not isinstance(value, str) or not HEX_RE.match(value):
            raise PresetError(f"{where}: every swatch must be a hex colour")

    return {
        "id": preset_id,
        "name": name.strip(),
        "description": description.strip(),
        "swatches": list(swatches),
        "enabled": bool(raw.get("enabled", True)),
        "tokens": _validate_tokens(raw.get("tokens"), where),
    }


def validate_presets(raw: object) -> list[dict]:
    """The whole catalogue for a console save: every entry valid, ids unique."""
    if not isinstance(raw, list):
        raise PresetError("presets must be a list")
    if len(raw) > MAX_PRESETS:
        raise PresetError(f"at most {MAX_PRESETS} presets")
    out: list[dict] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        preset = validate_preset(item, index=i)
        if preset["id"] in seen:
            raise PresetError(f"'{preset['id']}': two presets can't share an id")
        seen.add(preset["id"])
        out.append(preset)
    return out


def swatches_for(preset: dict) -> list[str]:
    """What the Theme tab shows as the preset's colour dots: the console's own
    swatches, else the colours that carry the look."""
    if preset.get("swatches"):
        return list(preset["swatches"])
    colors = (preset.get("tokens") or {}).get("colors") or {}
    return [colors[key] for key in SWATCH_ORDER if key in colors][:6]


def get_theme_presets(db: Session) -> list[dict]:
    """The whole catalogue, enabled and disabled, in console order.

    Falls back to the code defaults when the row is missing or structurally
    broken; drops (and logs) individual entries that don't validate. An admin who
    deliberately empties the catalogue gets an empty catalogue — that is a stored
    list, not a broken one."""
    row = db.get(PlatformSetting, THEME_PRESETS_KEY)
    stored = row.value if row is not None else None
    if not isinstance(stored, dict) or not isinstance(stored.get("presets"), list):
        if row is not None:
            log_event(logger, "theme.presets.malformed", key=THEME_PRESETS_KEY)
        # deepcopy, not dict(): a shallow copy would hand every caller the SAME
        # nested `tokens` dict as the module constant, so one mutation would
        # recolour the shipped catalogue for every tenant in the process.
        return deepcopy(DEFAULT_THEME_PRESETS)

    out: list[dict] = []
    for i, item in enumerate(stored["presets"]):
        try:
            out.append(validate_preset(item, index=i))
        except PresetError as exc:
            log_event(logger, "theme.preset.skipped", reason=str(exc))
    return out


def active_theme_presets(db: Session) -> list[dict]:
    """What a couple may choose from — the disabled ones aren't offered."""
    return [p for p in get_theme_presets(db) if p.get("enabled")]


def find_active_preset(db: Session, preset_id: str) -> dict | None:
    return next((p for p in active_theme_presets(db) if p["id"] == preset_id), None)


def set_theme_presets(db: Session, presets: list[dict]) -> list[dict]:
    """Replace the catalogue (uncommitted — the caller commits). A whole-list PUT
    is what makes reorder, disable and delete one operation instead of four."""
    row = db.get(PlatformSetting, THEME_PRESETS_KEY)
    value = {"presets": presets}
    if row is None:
        db.add(PlatformSetting(key=THEME_PRESETS_KEY, value=value))
    else:
        row.value = value
    return presets
