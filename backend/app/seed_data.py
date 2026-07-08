"""Default wedding content — the neutral starter template.

Stored as DATA on the wedding row (event_details + content) so it's editable
per-wedding. Keep prose here, not hardcoded in components.

IMPORTANT (multi-tenant): this is the PLACEHOLDER template every new wedding
starts from ("Alex & Sam"). The invite components are generic and render
whatever the wedding's content row provides. Keep this copy tasteful but
obviously replaceable — owners edit everything in the admin dashboard.

Narration text supports a tiny markup: wrap a phrase in **double asterisks** to
bold it. The frontend parses this safely (no raw HTML). Story beats may include
an `image` URL (uploaded via admin → Supabase Storage); beats without one render
as an empty feathered panel, so the template ships text-only beats.
"""

WEDDING_SLUG = "alex-and-sam"
COUPLE_NAMES = "Alex & Sam"

EVENT_DETAILS = {
    "title": "The Reception",
    "venue": "The Garden Hall",
    "address": "1 Example Avenue",
    "area": "Riverside · Example City",
    # ISO + display. Placeholder date — owners set the real one in the admin.
    "date_iso": "2027-01-01",
    "start_time": "18:00",
    "end_time": "22:00",
    "date_display": "Friday, 1 January 2027",
    "time_display": "6:00 – 10:00 PM",
    "timezone": "Asia/Singapore",
    "map_url": "https://maps.google.com/?q=The+Garden+Hall",
    "dress_code": "Garden evening — smart & comfortable",
    "getting_there": "Parking on-site",
}

CONTENT = {
    "nav": {
        "brand": "Alex & Sam",
        "links": [
            {"label": "Our story", "href": "#story"},
            {"label": "The day", "href": "#day"},
            {"label": "Dress", "href": "#dress"},
            {"label": "FAQ", "href": "#faq"},
        ],
        "cta": "RSVP",
    },
    "cover": {
        "kicker": "Our story · The next chapter",
        # "Dear {name}," — {name} is replaced with the guest's first name.
        "greeting": "Dear {name},",
        "invite_line": "would like to invite you to their wedding!",
        "tagline": "Every love story is lovely — come hear ours in person.",
    },
    "brand": {
        # The circular wordmark that rotates around the cover icon.
        "wordmark_text": "Alex & Sam",
        # Center icon: "default" = the built-in mascot glyph, "custom" = an
        # uploaded square image (icon_url), "none" = ring text with no icon.
        "icon_mode": "default",
        "icon_url": None,
    },
    "landing": {
        # The public "no link" page — shown when someone visits the site root
        # without their personal invite link. Editable in the admin Details tab.
        # `visible` off hides the text (just the brand dot remains).
        "visible": True,
        "heading": "Alex & Sam",
        "tagline": "We're getting married!",
        "body": "The invitation lives at your personal link — check your "
        "message from us for the address.",
    },
    "story_section": {
        # A small label sitting above the whole story section (e.g. "Our story").
        # Owner-editable: clear the label OR flip `visible` off to hide it entirely.
        "visible": True,
        "label": "Our story",
    },
    "story": {
        "kicker": "Our story · The next chapter",
        "heading": "How we got here",
        "intro": "The short version of a long and happy story — add your own "
        "chapters and pictures in the dashboard.",
        "beats": [
            {
                "n": "01",
                "wide": True,
                "text": "Once upon a time, **Alex** and **Sam** met — and the rest "
                "refused to stay history.",
            },
            {
                "n": "02",
                "text": "There were adventures, questionable haircuts, and a lot "
                "of very good meals.",
            },
            {
                "n": "03",
                "text": "One day, one of them asked a very important question…",
            },
            {
                "n": "04",
                "text": "…and the other said **yes** before the sentence was even "
                "finished.",
            },
        ],
        # The climax beat leads into the RSVP.
        "climax": {
            "label": "The next chapter",
            "text": "Now there's one more page to write —\n**and you're invited.**",
            "cta": "Will you be there?",
        },
    },
    "day": {
        "kicker": "The day",
        "heading": "One evening together",
        "intro": "An evening of good food and better company. Come hungry, "
        "stay late.",
        "map_cta": "Open in maps",
    },
    "dress_code": {
        "kicker": "Dress code",
        "heading": "Smart & comfortable",
        "body": "Think soft colours and shoes you can dance in — we'd rather "
        "you comfortable than formal.",
        # Token names from theme/types.ts ThemeColors (never raw hex).
        "swatches": ["paperEdge", "primary", "secondary", "accentSage", "accentLav"],
        # Colours to steer clear of (same token vocabulary). Empty by default.
        "swatches_avoid": [],
        # Captions for the two swatch rows (shown only when that row renders).
        "wear_label": "Lovely on the day",
        "avoid_label": "Best avoided",
    },
    "faq": {
        "kicker": "Good to know",
        "heading": "Questions, answered",
        "items": [
            {
                "q": "Are there dietary options?",
                "a": "Yes — note any dietary needs right in your RSVP and the "
                "kitchen will take care of you.",
            },
            {
                "q": "Can I bring my kids?",
                "a": "Little ones are welcome if your invitation includes them — your "
                "RSVP will show the option if so.",
            },
            {
                "q": "When should I RSVP by?",
                "a": "As early as you can, please — it really helps us plan with the "
                "venue. We'll confirm the final cut-off in your invite.",
            },
            {
                "q": "Where exactly is the venue?",
                "a": "Tap “Open in maps” above for directions and parking.",
            },
        ],
    },
    "rsvp": {
        "kicker": "The RSVP",
        "heading": "Will you join us?",
        # {name} -> guest's full name.
        "intro": "This invitation is for {name}. It takes about a minute — "
        "we'll walk you through.",
        "speech": {
            "attend": "The big question first: are you coming?",
            "contacts": "How do we reach you when it's nearly time?",
            "guests": "Bringing your people? Let's get everyone's details on the list.",
            "extras": "A couple more bits — so the kitchen knows what to prep.",
            "review": "One last look, then we'll deliver it.",
            "note": "Aww. Want to leave a little note?",
        },
        "choices": {
            "yes": {"emoji": "🎉", "title": "Joyfully accepts", "sub": "Count me in"},
            "no": {"emoji": "🥲", "title": "Regretfully declines", "sub": "Can't this time"},
        },
        # Dietary / how-you-know / song are admin-defined questions (see
        # DEFAULT_QUESTIONS below), not hardcoded here.
        "note_placeholder": "A message for the couple… (optional)",
        "confirm": {
            "yes_title": "You're on the list!",
            "yes_body": "Your RSVP is in. We can't wait to celebrate "
            "with you — we'll be in touch closer to the day.",
            "no_title": "Thank you for letting us know",
            "no_body": "We'll miss you dearly — thank you for replying. You'll be "
            "there in spirit.",
        },
        # Step headers, review-row labels, buttons and inline labels. Mirrors
        # frontend RSVP_DEFAULTS (lib/content.ts) so a freshly seeded wedding shows
        # the current wording in the admin editor; the frontend parser also
        # defaults these, so an older row without them still renders fine.
        "steps": {
            "attend": {"lead": "The big question…", "title": "Can you make it?"},
            "contacts": {"lead": "Staying in touch", "title": "How can we reach you?"},
            "guests": {"lead": "Your party", "title": "Who's coming?"},
            "extras": {"lead": "A few details", "title": "Help us plan"},
            "review": {"lead": "Almost there", "title": "Look good?"},
            "note": {"lead": "We'll miss you", "title": "Leave a note?"},
        },
        "review_labels": {
            "attending": "Attending",
            "attending_value": "Yes — joyfully 🎉",
            "plus_one": "Plus one",
            "adults": "Guests",
            "children": "Children",
        },
        "buttons": {
            "back": "← Back",
            "next": "Next",
            "send": "Send my RSVP",
            "send_decline": "Send reply",
            "sending": "Sending…",
            "edit": "Edit my response",
        },
        "labels": {
            "validate_attend": "Pick an answer first 🎉",
            "validate_plus_one": "Add your guest's name (or toggle them off).",
            "plus_one_toggle": "I'm bringing a +1",
            "plus_one_name": "Your guest's name",
            "plus_one_placeholder": "e.g. Jamie Tan",
            "adults_prompt": "Bringing other guests?",
            "adult_name": "Guest's name",
            "kids_prompt": "Bringing little ones?",
            "kid_name": "Child's name (optional)",
            "your_details": "Your details",
            "validate_required": "Please answer all required questions.",
            "contact_prompt": "How can we reach you?",
            "email_label": "Email",
            "phone_label": "Phone",
            "validate_email": "Please add your email.",
            "validate_phone": "Please add your phone number.",
        },
        # Which contact fields the RSVP collects (owner-editable in the Details tab).
        # Companion dietary is now a per-person question, so it's no longer a toggle.
        "fields": {
            "collect_email": True,
            "email_required": True,
            "collect_phone": True,
            "phone_required": False,
        },
        # plus_family companion allowance (owner-editable in the Details tab). Each
        # group can be switched off and capped; both default to 4. The Adults group
        # renders as an add/remove list (multiple extra adults), not a single +1.
        "party": {
            "adults_enabled": True,
            "max_adults": 4,
            "kids_enabled": True,
            "max_kids": 4,
        },
    },
    "footer": {"hashtag": "#AlexAndSam", "signoff": "With love — Alex & Sam"},
    "wishes": {
        "heading": "Leave us a wish",
        "intro": "A note for the couple.",
        "name_label": "Your name",
        "message_label": "Your message",
        "button": "Add my wish",
        # Wishes are held for the couple to approve, so the wall only shows ones
        # they've okayed — the success note sets that expectation.
        "success": "Thank you! Your wish has been sent — it'll appear on the wall once the couple says yes.",
    },
}


def _arc_content_from_story(story: dict) -> dict:
    """Derive a StoryArc `content` blob from the legacy `content.story` shape.

    Beats are numbered by POSITION on render now, so the stored bullet `n` is
    dropped — only `image`, `text`, `wide`, `onoma` are kept per beat.
    """
    return {
        "kicker": story.get("kicker"),
        "heading": story.get("heading"),
        "intro": story.get("intro"),
        "beats": [
            {k: v for k, v in beat.items() if k != "n"} for beat in story.get("beats", [])
        ],
        "climax": story.get("climax"),
    }


# Default admin-defined RSVP questions. Everything a guest answers beyond their
# Name is a question now. `scope`: invitee (asked once for the party) | person
# (asked of each attendee). `applies_to` (person scope only): everyone | adults |
# children — `children` + `required` is how "age, mandatory for kids" is expressed.
DEFAULT_QUESTIONS = [
    {
        "prompt": "Any dietary needs?",
        "qtype": "multi_choice",
        "options": ["Halal", "Vegetarian", "Vegan", "No beef", "Nut allergy", "Gluten-free"],
        "required": False,
        "scope": "person",
        "applies_to": "everyone",
        "sort_order": 0,
    },
    {
        "prompt": "Age",
        "qtype": "number",
        "options": [],
        "required": True,
        "scope": "person",
        "applies_to": "children",
        "sort_order": 1,
    },
    {
        "prompt": "How do you know the lucky two?",
        "qtype": "choice",
        "options": ["Alex's side", "Sam's side", "We go way back", "It's complicated"],
        "required": False,
        "scope": "invitee",
        "applies_to": "everyone",
        "sort_order": 2,
    },
    {
        "prompt": "A song that'll get you dancing?",
        "qtype": "text",
        "options": [],
        "required": False,
        "scope": "invitee",
        "applies_to": "everyone",
        "sort_order": 3,
    },
]


# v1 seeds exactly one visible arc, built from the story content above.
STORY_ARCS = [
    {
        "title": "The next chapter",
        "visible": True,
        "sort_order": 0,
        "content": _arc_content_from_story(CONTENT["story"]),
    }
]
