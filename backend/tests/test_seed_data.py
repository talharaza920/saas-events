"""Guards the shape of the default seeded template content.

The frontend invite sections read these keys (frontend/lib/content.ts). This is a
data contract — if a key is renamed here without updating the parser, the section
silently degrades. These assertions catch that early. Copy/wording is intentionally
NOT asserted (it's editable); only the structure the components depend on is.
"""
from __future__ import annotations

from app.seed_data import CONTENT, EVENT_DETAILS


def test_story_beats_are_numbered_with_optional_images():
    beats = CONTENT["story"]["beats"]
    assert len(beats) >= 1
    # Every beat carries a stable bullet number; images are optional (the
    # neutral template ships text-only beats — owners upload their own art).
    assert [b["n"] for b in beats] == ["01", "02", "03", "04"]
    for b in beats:
        assert b["text"]
        if "image" in b:
            assert isinstance(b["image"], str) and b["image"]


def test_story_section_label_present():
    section = CONTENT["story_section"]
    assert section["label"]
    assert isinstance(section["visible"], bool)


def test_story_has_climax_with_cta():
    climax = CONTENT["story"]["climax"]
    assert climax["text"] and climax["cta"]
    if "image" in climax:
        assert isinstance(climax["image"], str) and climax["image"]


def test_nav_links_and_cta_present():
    nav = CONTENT["nav"]
    assert nav["cta"]
    assert all(l["label"] and l["href"].startswith("#") for l in nav["links"])


def test_rsvp_microcopy_shape():
    rsvp = CONTENT["rsvp"]
    for key in ("attend", "contacts", "guests", "extras", "review", "note"):
        assert rsvp["speech"][key]
    assert rsvp["choices"]["yes"]["title"] and rsvp["choices"]["no"]["title"]
    for key in ("yes_title", "yes_body", "no_title", "no_body"):
        assert rsvp["confirm"][key]


def test_rsvp_party_caps_and_labels():
    rsvp = CONTENT["rsvp"]
    party = rsvp["party"]
    # plus_family companion allowance: each group toggleable + capped, default 4.
    assert party["adults_enabled"] is True and party["kids_enabled"] is True
    assert party["max_adults"] == 4 and party["max_kids"] == 4
    # The add/remove ADULTS section reads these labels (mirrors the kids ones).
    for key in ("adults_prompt", "adult_name", "kids_prompt", "kid_name"):
        assert rsvp["labels"][key]


def test_default_questions_shape():
    from app.seed_data import DEFAULT_QUESTIONS

    by_prompt = {q["prompt"]: q for q in DEFAULT_QUESTIONS}
    # Dietary is a per-person multi-select asked of everyone.
    diet = by_prompt["Any dietary needs?"]
    assert diet["qtype"] == "multi_choice" and diet["scope"] == "person"
    assert diet["applies_to"] == "everyone" and diet["options"]
    # Age is a number question, required, asked of children only.
    age = by_prompt["Age"]
    assert age["qtype"] == "number" and age["scope"] == "person"
    assert age["applies_to"] == "children" and age["required"] is True


def test_faq_is_object_with_items():
    faq = CONTENT["faq"]
    assert faq["heading"]
    assert all(item["q"] and item["a"] for item in faq["items"])


def test_dress_swatches_and_getting_there():
    assert CONTENT["dress_code"]["swatches"]
    assert EVENT_DETAILS["getting_there"]
