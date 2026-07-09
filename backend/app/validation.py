"""Contact (email + phone) normalization — pure and unit-tested.

Both the guest RSVP endpoint (app/routers/invite.py) and the admin guest CRUD /
spreadsheet import (app/routers/admin.py, app/export_import.py) funnel
guest-supplied contacts through here so storage is consistent: emails are
format-validated + lowercased, phones normalized to **E.164**. Blank input is
treated as "no value" (returns None) rather than an error, so an optional field
left empty never 422s.
"""
from __future__ import annotations

import phonenumbers
from email_validator import EmailNotValidError, validate_email

# Fallback region for interpreting a national phone number typed without a
# country code. Per wedding this comes from `settings["phone_region"]`
# (owner-editable via PATCH /settings) — see `wedding_phone_region`.
DEFAULT_REGION = "SG"


def is_supported_region(code: str) -> bool:
    """True if `code` is an ISO 3166-1 alpha-2 region phonenumbers can parse for."""
    return code in phonenumbers.SUPPORTED_REGIONS


def wedding_phone_region(wedding) -> str:
    """The region used to interpret this wedding's national-format phone numbers:
    `settings["phone_region"]` when it's a supported ISO code, else DEFAULT_REGION.
    Takes the Wedding model (or anything with a `.settings` dict)."""
    raw = (getattr(wedding, "settings", None) or {}).get("phone_region") or ""
    region = str(raw).strip().upper()
    return region if is_supported_region(region) else DEFAULT_REGION


class ContactError(ValueError):
    """A contact value failed validation (surfaced as a 422 by the routers)."""


def normalize_email(raw: str | None) -> str | None:
    """Validate + normalize an email, or None for blank input. Raises ContactError
    on an invalid address. Deliverability (MX) is NOT checked — offline + fast."""
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        result = validate_email(text, check_deliverability=False)
    except EmailNotValidError as exc:
        raise ContactError("Please enter a valid email address.") from exc
    return result.normalized


def normalize_phone(raw: str | None, region: str = DEFAULT_REGION) -> str | None:
    """Return an E.164 phone string, or None for blank input. Raises ContactError
    on an unparseable / invalid number. A national number (no leading +) is
    interpreted in `region`; an international one (+...) ignores the region."""
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        parsed = phonenumbers.parse(text, region)
    except phonenumbers.NumberParseException as exc:
        raise ContactError("Please enter a valid phone number.") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise ContactError("Please enter a valid phone number.")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
