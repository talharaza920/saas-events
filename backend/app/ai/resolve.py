"""Venue resolution — plain code, NO model (AI_WIZARD_PLAN pipeline step 3).

Extraction returns a venue NAME and the phrase that supports it; this module
turns the name into a real address via Google Places. The model cannot
confabulate a street number because it is never asked for one — that removal
of address hallucination is the whole point of this step being deterministic
HTTP rather than a tool the model holds.

Without a GOOGLE_PLACES_API_KEY the step resolves to None and the proposal
keeps the bare venue name — degraded, never invented.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

from app.config import Settings
from app.obs import log_event

logger = logging.getLogger("app.ai")

_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
# Restrict the response to exactly what the proposal needs (also keeps the
# per-request Places bill at the "Text Search (Basic)" rate).
_FIELD_MASK = "places.displayName,places.formattedAddress,places.location,places.googleMapsUri"


@dataclass(frozen=True)
class ResolvedVenue:
    name: str
    address: str
    lat: float | None
    lng: float | None
    maps_url: str | None

    def as_dict(self) -> dict:
        return asdict(self)


def resolve_venue(
    settings: Settings, venue_name: str, *, city: str | None = None
) -> ResolvedVenue | None:
    """Best-effort lookup. Any failure (no key, HTTP error, no result) is
    None — the pipeline continues with the couple's own words."""
    if not settings.ai_places_enabled or not venue_name.strip():
        return None
    query = f"{venue_name}, {city}" if city else venue_name
    try:
        import httpx

        resp = httpx.post(
            _SEARCH_URL,
            json={"textQuery": query, "pageSize": 1},
            headers={
                "X-Goog-Api-Key": settings.google_places_api_key,
                "X-Goog-FieldMask": _FIELD_MASK,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        places = resp.json().get("places") or []
    except Exception as exc:  # resolution is enrichment, never a blocker
        log_event(logger, "ai.resolve.failed", query=query, error=str(exc)[:200])
        return None
    if not places:
        return None
    place = places[0]
    location = place.get("location") or {}
    return ResolvedVenue(
        name=(place.get("displayName") or {}).get("text") or venue_name,
        address=place.get("formattedAddress") or "",
        lat=location.get("latitude"),
        lng=location.get("longitude"),
        maps_url=place.get("googleMapsUri"),
    )
