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

# The couple's region, used to interpret a national phone number typed without a
# country code (e.g. a local SG mobile). Multi-tenant TODO: make this a per-wedding
# setting; SG is correct for v1 (Alex & Sam).
DEFAULT_REGION = "SG"


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
