"""Pure split-row parsing logic (app/export_import.py). No DB."""
from __future__ import annotations

from types import SimpleNamespace

from app.export_import import (
    BASE_COLUMNS,
    _slug_from_link,
    columns,
    escape_formula,
    list_columns,
    parse_records,
    typed_answer,
)


def _rec(row, **kw):
    base = {c: "" for c in BASE_COLUMNS}
    base.update(kw)
    base["__row__"] = row
    return base


def test_columns_appends_question_prompts():
    cols = columns(["Main course", "Song?"])
    assert cols[: len(BASE_COLUMNS)] == BASE_COLUMNS
    assert cols[-2:] == ["Main course", "Song?"]


def test_id_is_first_column():
    assert BASE_COLUMNS[0] == "Id"


def test_parse_reads_id_and_answers():
    recs = [
        _rec(2, Id="abc-123", Person="Primary", Name="Hasaan", Greeting="Hasaan",
             Attending="yes", **{"Song?": "Levitating"}),
        _rec(3, Person="Child", Name="Leo", **{"Age": "6"}),
    ]
    [g] = parse_records(recs)
    assert g.guest_id == "abc-123"
    assert g.answers == {"Song?": "Levitating"}
    assert g.companions[0].answers == {"Age": "6"}


def test_parse_invite_sent_optional():
    """Invite Sent parses to True/False, blank = None (leave unchanged, never wipes)."""
    [yes] = parse_records([_rec(2, Name="A", Greeting="A", **{"Invite Sent": "yes"})])
    assert yes.invite_sent is True
    [no] = parse_records([_rec(2, Name="B", Greeting="B", **{"Invite Sent": "no"})])
    assert no.invite_sent is False
    [blank] = parse_records([_rec(2, Name="C", Greeting="C")])
    assert blank.invite_sent is None
    # It's a known base column (a strict yes/no dropdown), never a question column.
    assert "Invite Sent" in BASE_COLUMNS
    assert list_columns([])["Invite Sent"].strict


def test_typed_answer_by_type():
    assert typed_answer("text", [], "hi") == ({"text": "hi"}, None)
    assert typed_answer("number", [], "6") == ({"number": 6}, None)
    assert typed_answer("number", [], "six")[0] is None
    assert typed_answer("yesno", [], "Yes") == ({"yesno": True}, None)
    assert typed_answer("choice", ["A", "B"], "a") == ({"choice": "A"}, None)  # case-insensitive
    assert typed_answer("choice", ["A", "B"], "C")[0] is None
    assert typed_answer("multi_choice", ["Halal", "Vegan"], "vegan, halal") == (
        {"choices": ["Vegan", "Halal"]},
        None,
    )
    assert typed_answer("text", [], "") == (None, None)  # blank → skip, no error


def test_list_columns_strictness():
    qs = [
        SimpleNamespace(prompt="Diet", qtype="multi_choice", options=["Halal", "Vegan"]),
        SimpleNamespace(prompt="Side?", qtype="choice", options=["A", "B"]),
        SimpleNamespace(prompt="Note", qtype="text", options=[]),
    ]
    specs = list_columns(qs)
    assert specs["Attending"].values == ["yes", "no"] and specs["Attending"].strict
    assert specs["Tier"].strict and specs["Person"].strict
    assert specs["Side?"].strict  # single-choice = strict
    assert specs["Diet"].strict is False  # multi-select = non-strict
    assert "Note" not in specs  # free text gets no dropdown


def test_slug_from_link():
    assert _slug_from_link("/i/hasaan-ab12cd") == "hasaan-ab12cd"
    assert _slug_from_link("https://x.app/i/may-99ff00?utm=1") == "may-99ff00"
    assert _slug_from_link("") is None


def test_parse_primary_with_companions():
    recs = [
        _rec(2, Link="/i/hasaan-ab12", Person="Primary", Name="Hasaan",
             Greeting="Hasaan", Email="h@x.com", Tier="plus_family", Attending="yes"),
        _rec(3, Person="Adult", Name="May"),
        _rec(4, Person="Child", Name="Leo"),
    ]
    [g] = parse_records(recs)
    assert g.errors == []
    assert g.link_slug == "hasaan-ab12"
    assert g.tier == "plus_family"
    assert g.attending is True
    assert len(g.companions) == 2
    adult = next(c for c in g.companions if c.kind == "adult")
    child = next(c for c in g.companions if c.kind == "child")
    assert adult.name == "May"
    assert child.name == "Leo"


def test_parse_accepts_guest_and_adult_person_labels():
    """The companion row label is now 'Guest'; 'Adult' is still accepted (older sheets).
    Both map to the structural kind 'adult'."""
    recs = [
        _rec(2, Person="Primary", Name="Lead", Greeting="Lead", Tier="plus_family"),
        _rec(3, Person="Guest", Name="New Label"),
        _rec(4, Person="Adult", Name="Old Label"),
        _rec(5, Person="Child", Name="Kid"),
    ]
    [g] = parse_records(recs)
    assert g.errors == []
    adults = [c for c in g.companions if c.kind == "adult"]
    assert sorted(a.name for a in adults) == ["New Label", "Old Label"]
    assert [c.name for c in g.companions if c.kind == "child"] == ["Kid"]


def test_parse_family_with_multiple_adults():
    """A plus_family invite can carry several Adult rows (mum, wife, …) plus kids —
    the split-row parser collapses them all onto the one invitee."""
    recs = [
        _rec(2, Link="/i/adam-9f", Person="Primary", Name="Adam",
             Greeting="Adam", Tier="plus_family", Attending="yes"),
        _rec(3, Person="Adult", Name="Mum"),
        _rec(4, Person="Adult", Name="Wife"),
        _rec(5, Person="Child", Name="Kid 1"),
        _rec(6, Person="Child", Name="Kid 2"),
    ]
    [g] = parse_records(recs)
    assert g.errors == []
    adults = [c for c in g.companions if c.kind == "adult"]
    children = [c for c in g.companions if c.kind == "child"]
    assert [a.name for a in adults] == ["Mum", "Wife"]
    assert [c.name for c in children] == ["Kid 1", "Kid 2"]


def test_tier_aliases_and_unknown():
    [g1] = parse_records([_rec(2, Name="A", Greeting="A", Tier="+1")])
    assert g1.tier == "plus_one" and g1.errors == []
    [g2] = parse_records([_rec(2, Name="B", Greeting="B", Tier="vip")])
    assert g2.tier is None and any("unknown tier" in e for e in g2.errors)


def test_expected_party_size_parsing():
    # Valid whole number in range.
    [ok] = parse_records([_rec(2, Name="A", Greeting="A", Expected="4")])
    assert ok.expected_party_size == 4 and ok.errors == []
    # Blank → unchanged (None), no error.
    [blank] = parse_records([_rec(2, Name="B", Greeting="B", Expected="")])
    assert blank.expected_party_size is None and blank.errors == []
    # Non-numeric and out-of-range are flagged (and value left None).
    [bad] = parse_records([_rec(2, Name="C", Greeting="C", Expected="lots")])
    assert bad.expected_party_size is None and bad.errors
    [over] = parse_records([_rec(2, Name="D", Greeting="D", Expected="99")])
    assert over.expected_party_size is None and over.errors


def test_greeting_is_invitee_level_primary_only():
    # Greeting is read from the Primary row only; a value on a companion row is not a
    # field (it lands in that companion's raw answers, never on the invitee).
    recs = [
        _rec(2, Person="Primary", Name="John", Greeting="John & Jane"),
        _rec(3, Person="Adult", Name="Jane", Greeting="ignored"),
    ]
    [g] = parse_records(recs)
    assert g.greeting_name == "John & Jane"
    assert len(g.companions) == 1 and g.companions[0].name == "Jane"


def test_greeting_in_base_columns():
    assert "Greeting" in BASE_COLUMNS


def test_greeting_is_required_on_primary():
    # Greeting is the invite's mandatory label — a Primary row without one errors.
    [g] = parse_records([_rec(2, Name="Solo", Greeting="")])
    assert g.greeting_name is None
    assert any("Greeting is required" in e for e in g.errors)


def test_primary_name_is_optional_when_greeting_present():
    # Name is optional now: a Primary row identified only by its Greeting is a valid
    # invite (name stays blank, no fallback to the Invitee label).
    [g] = parse_records([_rec(2, Person="Primary", Greeting="John & Jane", Tier="plus_one")])
    assert g.name == "" and g.greeting_name == "John & Jane" and g.errors == []


def test_attending_parsing():
    assert parse_records([_rec(2, Name="A", Attending="yes")])[0].attending is True
    assert parse_records([_rec(2, Name="B", Attending="no")])[0].attending is False
    assert parse_records([_rec(2, Name="C", Attending="")])[0].attending is None


def test_orphan_companion_is_flagged():
    [g] = parse_records([_rec(2, Person="Child", Name="Lost")])
    assert g.name == "Lost"
    assert any("no invitee above it" in e for e in g.errors)


def test_blank_link_means_new_guest():
    [g] = parse_records([_rec(2, Name="Fresh", Greeting="Fresh", Tier="solo")])
    assert g.link_slug is None and g.errors == []


def test_escape_formula_neutralizes_injection():
    # Guest-supplied cells that start with a formula trigger get a leading quote.
    assert escape_formula('=HYPERLINK("http://evil","x")') == "'=HYPERLINK(\"http://evil\",\"x\")"
    assert escape_formula("+1+1") == "'+1+1"
    assert escape_formula("-2") == "'-2"
    assert escape_formula("@SUM(A1)") == "'@SUM(A1)"
    assert escape_formula("\tTab") == "'\tTab"
    # Ordinary values (incl. a "+65..." phone is still escaped — safe, it stays text)
    # are untouched unless they lead with a trigger.
    assert escape_formula("May Tan") == "May Tan"
    assert escape_formula("hasaan@example.com") == "hasaan@example.com"  # @ not leading
    assert escape_formula("") == ""
    # Non-strings pass through unchanged.
    assert escape_formula(None) is None
    assert escape_formula(5) == 5
