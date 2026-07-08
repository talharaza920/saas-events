"""Pure helpers for the scoped/typed question engine — which questions a given
person is asked, and validating a set of submitted answers against them.

A question's `scope` is `invitee` (asked once for the party) or `person` (asked of
each attending person). For person-scope questions, `applies_to` narrows WHO is
asked: everyone, adults only, or children only. The primary invitee counts as an
adult. These helpers are DB-free so both the guest RSVP submit (app/routers/invite.py)
and the admin companion edit (app/routers/admin.py) can reuse the same rules.
"""
from __future__ import annotations

from app.models import Question, QuestionApplies, QuestionScope


def person_question_applies(q: Question, *, is_child: bool) -> bool:
    """Is this `person`-scope question asked of a person of this kind?

    `is_child=False` covers both the primary invitee and adult companions.
    """
    if q.scope is not QuestionScope.person:
        return False
    if q.applies_to is QuestionApplies.everyone:
        return True
    if q.applies_to is QuestionApplies.adults:
        return not is_child
    return is_child  # children


def is_party_question(q: Question) -> bool:
    """Questions answered on the primary/party answer list: every invitee-scope
    question, plus person-scope questions that apply to the primary (an adult)."""
    return q.scope is QuestionScope.invitee or person_question_applies(q, is_child=False)
