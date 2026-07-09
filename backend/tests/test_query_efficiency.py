"""Query-count guards for the hot admin endpoints (REVIEW_BACKLOG P0-1).

The guest list / responses / summary serializers walk rsvp → companions →
answers per row; without eager loading that's an N+1 storm (~3–5 queries per
guest) that the serverless → Supabase pooler hop turns into seconds. These
tests pin the SELECT count to a constant regardless of guest count, so a
future query regression fails loudly instead of shipping slow.
"""
from __future__ import annotations

from sqlalchemy import event

from app.models import (
    Answer,
    Companion,
    CompanionKind,
    InviteTier,
    Question,
    QuestionType,
    Rsvp,
)
from tests.helpers import add_guest, make_member, make_wedding, user_auth

OWNER = "owner@example.com"
N_GUESTS = 12  # enough that an N+1 would blow well past the caps below


def _seed(db):
    w = make_wedding(db, "query-count")
    make_member(db, w, OWNER)
    q = Question(
        wedding_id=w.id, prompt="Dietary", qtype=QuestionType.text, options=[], required=False
    )
    db.add(q)
    db.flush()
    for i in range(N_GUESTS):
        g = add_guest(db, w, f"qc-guest-{i}", name=f"Guest {i}", tier=InviteTier.plus_family)
        r = Rsvp(wedding_id=w.id, guest_id=g.id, attending=True)
        db.add(r)
        db.flush()
        c = Companion(wedding_id=w.id, rsvp_id=r.id, kind=CompanionKind.adult, name="Plus One")
        db.add(c)
        db.flush()
        db.add(Answer(wedding_id=w.id, rsvp_id=r.id, question_id=q.id, value={"text": "veg"}))
        db.add(
            Answer(
                wedding_id=w.id, rsvp_id=r.id, question_id=q.id,
                companion_id=c.id, value={"text": "kids meal"},
            )
        )
    db.commit()
    return w


def _count_selects(db, fn):
    counter = {"n": 0}

    def before(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            counter["n"] += 1

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", before)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", before)
    return result, counter["n"]


def _bounded(client, db_session, path, cap):
    _seed(db_session)
    headers = user_auth(OWNER)
    # Warm-up request creates the caller's profile row so the measured request
    # is the steady state.
    assert client.get("/api/w/query-count/admin/me", headers=headers).status_code == 200
    resp, selects = _count_selects(
        db_session, lambda: client.get(f"/api/w/query-count/admin{path}", headers=headers)
    )
    assert resp.status_code == 200
    assert selects <= cap, (
        f"{path} ran {selects} SELECTs for {N_GUESTS} guests (cap {cap}) — "
        "smells like an N+1 (missing selectinload?)"
    )
    return resp


def test_guest_list_query_count_is_bounded(client, db_session):
    resp = _bounded(client, db_session, "/guests", cap=14)
    body = resp.json()
    assert len(body) == N_GUESTS
    # Sanity: the eager-loaded shape still serializes fully.
    assert body[0]["companions"][0]["answers"][0]["value"] == {"text": "kids meal"}


def test_responses_query_count_is_bounded(client, db_session):
    resp = _bounded(client, db_session, "/responses", cap=14)
    assert len(resp.json()) == N_GUESTS


def test_summary_query_count_is_bounded(client, db_session):
    _bounded(client, db_session, "/summary", cap=18)


def test_export_query_count_is_bounded(client, db_session):
    _bounded(client, db_session, "/export.xlsx", cap=16)
