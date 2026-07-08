"""Schema integration test on a real (SQLite) engine — no Supabase needed.

Verifies models, enums, JSON columns, tenant FKs, relationships and cascades all
work against an actual DB, de-risking the Postgres migration run.
"""
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    Answer,
    Companion,
    CompanionKind,
    Guest,
    InviteTier,
    Question,
    QuestionApplies,
    QuestionScope,
    QuestionType,
    Rsvp,
    Wedding,
    Wish,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")  # in-memory
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)


def test_full_tenant_graph_persists_and_cascades(session):
    w = Wedding(
        slug="alex-and-sam",
        couple_names="Alex & Sam",
        event_details={"venue": "The Garden Hall", "date_iso": "2027-01-01"},
        content={"cover": {"tagline": "Ever after"}},
    )
    session.add(w)
    session.flush()

    guest = Guest(
        wedding_id=w.id,
        slug="jordan-abc123",
        name="Jordan",
        greeting_name="Jordan",
        side="Alex",
        invite_tier=InviteTier.plus_family,
    )
    session.add(guest)
    session.flush()

    rsvp = Rsvp(wedding_id=w.id, guest_id=guest.id, attending=True, notes="see you there")
    kid = Companion(wedding_id=w.id, kind=CompanionKind.child, name="Kid")
    rsvp.companions.append(kid)
    session.add(rsvp)
    session.flush()

    # An invitee-scope text question (party answer) and a per-person question
    # answered for the child (companion_id set).
    q_song = Question(
        wedding_id=w.id, prompt="Song request?", qtype=QuestionType.text, sort_order=1
    )
    q_age = Question(
        wedding_id=w.id,
        prompt="Age",
        qtype=QuestionType.number,
        scope=QuestionScope.person,
        applies_to=QuestionApplies.children,
        sort_order=2,
    )
    session.add_all([q_song, q_age])
    session.flush()
    session.add(Answer(wedding_id=w.id, rsvp_id=rsvp.id, question_id=q_song.id, value={"text": "Anything anime"}))
    session.add(
        Answer(
            wedding_id=w.id,
            rsvp_id=rsvp.id,
            question_id=q_age.id,
            companion_id=kid.id,
            value={"number": 6},
        )
    )
    session.add(Wish(wedding_id=w.id, guest_id=guest.id, name="Jordan", message="Congrats!"))
    session.commit()

    # Reload and assert the graph.
    got = session.query(Wedding).filter_by(slug="alex-and-sam").one()
    assert got.event_details["venue"] == "The Garden Hall"
    assert len(got.guests) == 1
    g = got.guests[0]
    assert g.invite_tier is InviteTier.plus_family
    assert g.rsvp.notes == "see you there"
    assert g.rsvp.companions[0].kind is CompanionKind.child
    # Party answer (companion_id None) vs the child's per-person answer.
    party = [a for a in g.rsvp.answers if a.companion_id is None]
    child_ans = g.rsvp.companions[0].answers
    assert party[0].value == {"text": "Anything anime"}
    assert child_ans[0].value == {"number": 6}
    assert isinstance(g.id, uuid.UUID)

    # Cascade: deleting the wedding removes all tenant rows.
    session.delete(got)
    session.commit()
    assert session.query(Guest).count() == 0
    assert session.query(Rsvp).count() == 0
    assert session.query(Companion).count() == 0
    assert session.query(Answer).count() == 0
    assert session.query(Wish).count() == 0
