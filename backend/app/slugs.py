"""Wedding-slug rules — format + the reserved-word blocklist.

The wedding slug is a public URL segment (`/{wedding-slug}/admin`,
`/{wedding-slug}/i/{guestSlug}`), so it must never collide with the platform's
own routes (frontend pages, API prefixes, static assets). Enforced at wedding
creation; existing slugs are never rewritten.
"""
from __future__ import annotations

import re

# Lowercase letters/digits, single hyphens between runs; 3–63 chars.
_SLUG_RE = re.compile(r"^[a-z0-9](?:-?[a-z0-9]){2,62}$")

# Platform routes + prefixes a wedding slug must never shadow. Keep this list
# ahead of the frontend's static routes (Next static routes beat the dynamic
# `[weddingSlug]` segment, but the API + links must agree).
RESERVED_SLUGS = frozenset(
    {
        "admin", "api", "app", "assets", "auth", "blog", "create", "dashboard",
        "docs", "favicon", "health", "help", "i", "invite", "invites", "login",
        "logout", "media", "next", "_next", "platform", "privacy", "public",
        "settings", "signin", "signup", "static", "status", "support", "terms",
        "w", "wedding", "weddings", "www",
    }
)


def slug_error(slug: str) -> str | None:
    """Why `slug` is not an acceptable wedding slug, or None if it is fine.
    (Uniqueness is checked separately against the DB.)"""
    if not slug or not _SLUG_RE.fullmatch(slug):
        return (
            "Use 3–63 lowercase letters, numbers and single hyphens "
            "(e.g. 'alex-and-sam')"
        )
    if slug in RESERVED_SLUGS:
        return "That address is reserved — pick another"
    return None


def suggest_slug(couple_names: str) -> str:
    """A URL-safe slug suggestion from the couple names ('Alex & Sam' →
    'alex-and-sam'). May still collide/reserve — callers validate + uniquify."""
    s = couple_names.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return s[:63]
