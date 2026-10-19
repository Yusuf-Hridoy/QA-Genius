"""Pack detection, boundary values and the story rules. No AI, no network."""

import json
from pathlib import Path

from tests.factories import (
    BIG_STORY,
    COUPON_CONTEXT,
    COUPON_CRITERIA,
    COUPON_STORY,
    LOCKOUT_CRITERIA,
    NAVBAR_STORY,
    LOCKOUT_STORY,
    PROFILE_CRITERIA,
    PROFILE_STORY,
    case,
)

from qagenius.shadow_qa.boundaries import (
    MAX_BOUNDARIES,
    boundary_covered,
    cap_boundary,
    find_boundaries,
    missing_values,
)
from qagenius.shadow_qa.detect import detect_hits, detect_packs, mentions, story_text
from qagenius.shadow_qa.packs import load_packs
from qagenius.shadow_qa.review import applies
from qagenius.shadow_qa.story_rules import count_capabilities, epic_note, review_story
from qagenius.test_cases import Criterion, number_criteria


def _ids(text: str, story: str | None = None) -> list[str]:
    return [pack.id for pack, _ in detect_packs(text, story)]


def _criteria(texts):
    return number_criteria(texts)


# ── matching ──────────────────────────────────────────────────────────────────


def test_matching_is_whole_word_and_case_insensitive():
    assert mentions("The user can LOG IN again", "log in")
    assert mentions("Sign-in is refused", "sign-in")
    assert not mentions("research the catalogue", "search")
    assert not mentions("the account is unlocked", "lock")


def test_a_phrase_ending_in_punctuation_matches_inside_a_word():
    # "USER@" has to be findable inside USER@EXAMPLE.COM.
    assert mentions("Enter USER@EXAMPLE.COM and submit", "USER@")


# ── detection ─────────────────────────────────────────────────────────────────


def test_every_pack_is_detected_by_a_realistic_sentence():
    sentences = {
        "login": "The shopper types their password to sign in.",
        "password_change": "The user can change password from the security page.",
        "two_factor": "Enabling 2FA asks for a verification code from the authenticator app.",
        "sessions": "The page lists active sessions on other devices and can revoke one.",
        "oauth": "The user links their account to Google using OAuth.",
        "profile_form": "The profile holds a full name, a phone number and a bio.",
        "file_upload": "The user can upload an avatar image.",
        "rate_limiting": "Too many attempts trigger a lockout.",
        "account_deletion": "The user can request account deletion at any time.",
        "preferences_autosave": "Each preferences toggle auto-saves, including dark mode.",
        "navigation": "The sidebar navigation highlights the current route.",
        "search": "The shopper can search and filter the catalogue.",
        "payment": "Checkout takes a card payment and shows the invoice.",
        "datetime": "The deadline is shown in the user's timezone.",
        "permissions": "Only the admin role has permission to open this page.",
        "notifications_email": "A confirmation email is sent and a push notification fires.",
        "list_paging": "The table shows one page of results with pagination.",
    }
    for pack_id, sentence in sentences.items():
        assert pack_id in _ids(sentence), f"{pack_id} not detected by: {sentence}"


def test_detection_reports_the_trigger_words_that_matched():
    found = dict(detect_packs("The shopper types a password to log in."))
    pack = next(pack for pack in found if pack.id == "login")
    assert "password" in found[pack] and "log in" in found[pack]


def test_the_profile_story_activates_at_least_seven_packs():
    packs = _ids(story_text(PROFILE_STORY, PROFILE_CRITERIA))
    assert len(packs) >= 7
    for expected in (
        "login",
        "password_change",
        "two_factor",
        "sessions",
        "oauth",
        "profile_form",
        "file_upload",
        "account_deletion",
        "preferences_autosave",
    ):
        assert expected in packs


def test_the_lockout_story_activates_login_and_rate_limiting_only():
    # "Wrong passwords" alone is not a sign-in story; the criteria say so.
    assert _ids(story_text(LOCKOUT_STORY, LOCKOUT_CRITERIA), LOCKOUT_STORY) == [
        "login",
        "rate_limiting",
    ]


def test_a_settings_story_that_only_says_password_gets_no_login_pack():
    assert "login" not in _ids(BIG_STORY)
    assert "password_change" in _ids(BIG_STORY)


# ── boundaries ────────────────────────────────────────────────────────────────


def test_counts_and_durations_in_one_criterion():
    criteria = _criteria(
        [
            "The account locks when a user exceeds 5 failed verification attempts "
            "within a 15-minute window, and the lock lasts for 30 minutes"
        ]
    )
    found = find_boundaries(criteria)
    by_kind = {(b.kind, b.values[1]): b for b in found}
    assert by_kind[("count", "5 attempts")].values == [
        "4 attempts",
        "5 attempts",
        "6 attempts",
    ]
    assert by_kind[("duration", "15 minutes")].values == [
        "14 minutes",
        "15 minutes",
        "16 minutes",
    ]
    assert by_kind[("duration", "30 minutes")].values == [
        "29 minutes",
        "30 minutes",
        "31 minutes",
    ]
    assert by_kind[("count", "5 attempts")].phrase == "5 failed verification attempts"
    assert all(b.source == "AC-1" for b in found)


def test_a_size_gets_just_under_exactly_and_just_over():
    found = find_boundaries(_criteria(["The avatar must be under 5MB"]))
    assert [b.values for b in found] == [["4.99 MB", "5 MB", "5.01 MB"]]
    assert found[0].kind == "size"


def test_a_digit_count_gets_one_fewer_and_one_more():
    found = find_boundaries(_criteria(["The user enters a 6-digit verification code"]))
    assert found[0].kind == "digits"
    assert found[0].values == ["5 digits", "6 digits", "7 digits"]


def test_a_length_gets_the_characters_either_side():
    found = find_boundaries(_criteria(["The bio accepts at most 160 characters"]))
    assert found[0].values == ["159 characters", "160 characters", "161 characters"]
    assert found[0].kind == "length"


def test_milliseconds_step_by_a_tenth_not_by_one():
    found = find_boundaries(_criteria(["The page responds within 500ms"]))
    assert found[0].values == ["450 ms", "500 ms", "550 ms"]


def test_ids_versions_and_years_are_not_boundaries():
    found = find_boundaries(
        _criteria(["As described in AC-11, release 2.1.3 shipped in 2024"])
    )
    assert found == []


def test_the_boundary_label_reads_as_the_checklist_writes_it():
    found = find_boundaries(_criteria(["within a 15-minute window"]))
    assert found[0].label == "14 / 15 / 16 minutes"
    assert found[0].id == "boundary:AC-1:14 minutes"


def test_at_most_twelve_boundaries():
    texts = [f"The limit is {number} items" for number in range(3, 40)]
    assert len(find_boundaries(_criteria(texts))) == MAX_BOUNDARIES


def test_the_same_value_is_not_reported_twice():
    found = find_boundaries(
        _criteria(["The lock lasts 30 minutes", "After 30 minutes the lock lifts"])
    )
    assert len(found) == 1


def test_boundary_covered_finds_the_values_a_case_mentions():
    boundary = find_boundaries(_criteria(["after 5 failed attempts"]))[0]
    cases = [
        case(
            case_id="TC-001",
            title="Lock after 5 attempts",
            steps=["Fail 4 attempts and sign in", "Fail 5 attempts"],
            expected_result="The account locks",
            test_data="attempts=5",
        )
    ]
    assert boundary_covered(boundary, cases) == ["4 attempts", "5 attempts"]
    assert missing_values(boundary, cases) == ["6 attempts"]


def test_a_size_over_the_limit_counts_as_covered_when_written_as_one_byte_over():
    boundary = find_boundaries(_criteria(["files under 5MB"]))[0]
    cases = [
        case(
            case_id="TC-001",
            title="Upload at the limit",
            steps=["Upload a file of exactly 5 MB", "Upload the same file one byte over"],
            expected_result="The first uploads and the second is refused",
            test_data="5 MB file",
        )
    ]
    assert "5.01 MB" in boundary_covered(boundary, cases)


def test_a_value_counts_however_the_case_chose_to_write_it():
    """The ways a tester really writes the limit, from the big-story run."""
    written = {
        "a 6-digit code": ("Enabling two-factor needs a 6-digit code", "6 digits"),
        "a quoted code": ("The code '12345' is refused", "5 digits"),
        "no space": ("Upload 5MB", "5 MB"),
        "the long unit": ("Upload exactly 5.00 megabytes", "5 MB"),
        "another unit": ("Upload 5120 KB", "5 MB"),
        "a byte over": ("Upload the file +1 byte over", "5.01 MB"),
        "a number in words": ("Fail four attempts", "4 attempts"),
        "a short unit": ("Wait 14 min", "14 minutes"),
        "a clock": ("The lock still reads 14:00", "14 minutes"),
    }
    limits = {
        "5 digits": "Enabling two-factor shows a 6-digit verification code",
        "6 digits": "Enabling two-factor shows a 6-digit verification code",
        "5 MB": "An avatar must be under 5MB",
        "5.01 MB": "An avatar must be under 5MB",
        "4 attempts": "The account locks after 5 failed attempts",
        "14 minutes": "A locked account stays locked for 15 minutes",
    }
    for how, (sentence, value) in written.items():
        boundary = find_boundaries(_criteria([limits[value]]))[0]
        covered = boundary_covered(boundary, [case(case_id="TC-001", title=sentence)])
        assert value in covered, f"{how}: {sentence!r} did not count as {value}"


def test_nothing_is_covered_when_the_cases_are_about_something_else():
    boundary = find_boundaries(_criteria(["after 5 failed attempts"]))[0]
    cases = [case(case_id="TC-001", title="Sign in with a correct password")]
    assert boundary_covered(boundary, cases) == []


# ── story rules ───────────────────────────────────────────────────────────────


def test_the_profile_story_gets_the_epic_warning():
    notes = review_story(PROFILE_STORY, PROFILE_CRITERIA)
    note = epic_note(notes)
    assert note is not None
    assert note.level == "warn"
    assert len(note.features) >= 7
    # The title counts what the pills name: one list, one number.
    assert note.title == f"This story is really {len(note.features) + note.more} features"
    assert "This is too much for one story" in note.detail
    assert notes[0] is note  # the epic warning always comes first


def test_the_lockout_story_gets_no_epic_warning():
    assert epic_note(review_story(LOCKOUT_STORY, LOCKOUT_CRITERIA)) is None


def test_ten_criteria_alone_make_it_an_epic():
    texts = [f"The page shows field {number}" for number in range(10)]
    assert epic_note(review_story("As a user, I want a page so that I can read it.", texts))


def test_a_missing_actor_and_benefit_are_reported():
    titles = [note.title for note in review_story("The page shows a list.", [])]
    assert "No actor" in titles
    assert "No benefit" in titles


def test_an_actor_and_benefit_are_not_reported():
    titles = [
        note.title
        for note in review_story(
            "As a shopper, I want a basket so that I can buy things.", []
        )
    ]
    assert "No actor" not in titles
    assert "No benefit" not in titles


def test_criteria_without_a_negative_one_are_warned_about():
    notes = review_story(
        "As a shopper, I want a basket so that I can buy things.",
        ["The basket shows the total", "The basket shows each line"],
    )
    warning = next(note for note in notes if "goes wrong" in note.title)
    assert warning.level == "warn"


def test_one_negative_criterion_is_enough():
    notes = review_story(
        "As a shopper, I want a basket so that I can buy things.",
        ["The basket shows the total", "An invalid quantity is rejected"],
    )
    assert not any("goes wrong" in note.title for note in notes)


def test_capabilities_are_counted_after_want_to():
    story = (
        "As a user, I want to edit my profile, upload an avatar, change my "
        "password, revoke a session, link a provider, and delete my account "
        "so that I stay in control."
    )
    assert count_capabilities(story) >= 6
    assert epic_note(review_story(story, []))


# ── strong and weak triggers ──────────────────────────────────────────────────


def _lockout_sample() -> tuple[str, list[str]]:
    sample = json.loads(
        Path("qagenius/samples/test_cases.json").read_text(encoding="utf-8")
    )
    return sample["story"], sample["criteria"]


def test_the_lockout_sample_activates_only_login_and_rate_limiting():
    story, criteria = _lockout_sample()
    # "admin console" sits in AC-5 and nowhere else, so one weak word buried
    # in a criterion must not turn this into a permissions story.
    assert _ids(story_text(story, criteria), story) == ["login", "rate_limiting"]


def test_a_duration_on_its_own_activates_nothing():
    # Durations are the boundary rules' job, not the date pack's.
    assert _ids("Then the report loads within 2 minutes") == []
    assert _ids("The job finishes within 3 hours") == []


def test_one_weak_word_is_never_enough_wherever_it_is_said():
    # In the story, in a criterion, it makes no difference: one weak word is
    # a coincidence.
    assert _ids("An email is sent within 1 hour") == []
    assert _ids("An admin can see the report") == []


def test_one_weak_word_in_a_criterion_alone_is_not_enough():
    story = "As a shopper, I want to buy a lamp so that my desk is lit."
    criteria = ["The confirmation shows an email address"]
    assert "notifications_email" not in _ids(story_text(story, criteria), story)


def test_two_different_weak_words_in_the_criteria_are_enough():
    story = "As a shopper, I want to buy a lamp so that my desk is lit."
    criteria = ["The order list is shown", "The table holds one row per order"]
    assert "list_paging" in _ids(story_text(story, criteria), story)


def test_two_weak_words_in_the_story_activate_the_pack():
    assert _ids("An email reminder is sent within 1 hour") == ["notifications_email"]
    assert _ids("The admin role can delete users") == ["permissions"]


def test_the_same_weak_word_twice_is_still_one_word():
    story = "As a shopper, I want to buy a lamp so that my desk is lit."
    criteria = ["The order list is shown", "The archive list is shown too"]
    assert "list_paging" not in _ids(story_text(story, criteria), story)


def test_a_strong_word_in_a_criterion_alone_is_enough():
    story = "As a shopper, I want to buy a lamp so that my desk is lit."
    criteria = ["The results are shown with pagination"]
    assert "list_paging" in _ids(story_text(story, criteria), story)


def test_the_navbar_story_activates_only_navigation():
    assert _ids(NAVBAR_STORY) == ["navigation"]


def test_a_delete_in_passing_is_not_an_account_deletion_story():
    # "delete" is one weak word; the sentence is about who may do it.
    assert "account_deletion" not in _ids("The admin role can delete users")
    assert "account_deletion" in _ids("The user can request account deletion")


def test_the_word_link_no_longer_wakes_the_oauth_pack():
    pack = next(one for one in load_packs() if one.id == "oauth")
    assert "link" not in pack.weak_triggers and "links" not in pack.weak_triggers
    assert set(pack.weak_triggers) == {"linking", "provider", "providers"}
    assert "oauth" not in _ids("Each row has a link and a provider column")


def test_a_date_pack_still_fires_on_the_words_that_matter():
    assert "datetime" in _ids("The deadline is shown in the user's timezone")
    assert "datetime" in _ids("Entries are scheduled against the calendar in UTC")


def test_permissions_needs_more_than_the_word_admin_in_a_criterion():
    story = "As a shopper, I want to buy a lamp so that my desk is lit."
    assert "permissions" not in _ids(
        story_text(story, ["Support staff unlock it from the admin console"]), story
    )
    assert "permissions" in _ids("Only the admin role may open this page")
    assert "permissions" in _ids("The endpoint is forbidden without permission")


def test_detection_says_whether_the_story_named_the_pack():
    story = "As a user, I want to upload an avatar so that my profile looks right."
    criteria = ["The account locks after 5 failed sign-in attempts"]
    hits = {hit.pack.id: hit.in_story for hit in detect_hits(story_text(story, criteria), story)}
    assert hits["file_upload"] is True
    assert hits["rate_limiting"] is False
    assert hits["login"] is False
    # "Profile" names the page this sits on, not a form full of fields.
    assert "profile_form" not in hits


def test_the_word_profile_alone_is_not_a_profile_form():
    """Test B: a story about uploading a photo asked for bio and two-tab tests."""
    story = (
        "As a registered user, I want to upload a profile photo so that other "
        "users can recognise me."
    )
    context = (
        "Profile page. Accepted formats: JPEG and PNG. Maximum size 2 MB. "
        "The photo is cropped to a square."
    )
    criteria = [
        "The user can select a JPEG photo under 2 megabytes and upload it",
        "The user can select a PNG photo under 2 megabytes and upload it",
        "A photo larger than 2 megabytes is rejected with a message",
        "A file in a format other than JPEG or PNG is rejected with a message",
    ]
    whole = story_text("\n".join([story, context]), criteria)
    assert _ids(whole, story) == ["file_upload"]


def test_a_story_about_the_fields_themselves_is_a_profile_form():
    story = (
        "As a user, I want to edit my full name and bio on my profile so that "
        "it is up to date."
    )
    assert "profile_form" in _ids(story)


# ── money ─────────────────────────────────────────────────────────────────────


def test_a_money_limit_gets_the_cent_either_side():
    boundary = find_boundaries(_criteria(["The cart must be worth at least $50"]))[0]
    assert boundary.kind == "money"
    assert boundary.values == ["$49.99", "$50.00", "$50.01"]


def test_money_is_read_however_the_criterion_writes_it():
    written = ("at least $50", "at least $50.00", "at least 50 dollars",
               "at least USD 50", "at least €50", "at least £50", "at least 50 EUR")
    for text in written:
        found = find_boundaries(_criteria([f"The cart is worth {text}"]))
        assert found, text
        assert found[0].kind == "money", text
        assert found[0].values[1].endswith("50.00"), text


def test_an_amount_that_is_not_a_limit_is_not_a_boundary():
    """"The order total is $200" is an example, not a rule."""
    assert find_boundaries(_criteria(["When the order total is $200"])) == []


def test_the_coupon_criteria_give_the_fifty_and_the_cap_boundaries():
    """The $150 where a 20% coupon stops growing is written down nowhere."""
    found = find_boundaries(_criteria(COUPON_CRITERIA))
    values = [one.values for one in found]
    assert ["$49.99", "$50.00", "$50.01"] in values
    assert ["$149.99", "$150.00", "$150.01"] in values
    cap = next(one for one in found if one.values[1] == "$150.00")
    assert cap.source == "AC-3"
    assert cap.phrase == "the $30 cap starts at a $150 order (20% of $150 = $30)"


def test_the_cap_can_be_read_from_the_context_and_the_rate_from_a_criterion():
    criteria = _criteria(["Given a coupon gives 20% off When a code is entered"])
    criteria.append(Criterion(id="Context", text="Coupons give up to $30 off."))
    cap = cap_boundary(criteria)
    assert cap is not None
    assert cap.values == ["$149.99", "$150.00", "$150.01"]
    assert cap.source == "AC-1"


def test_a_case_covers_a_money_value_however_it_writes_it():
    boundary = find_boundaries(_criteria(["The cart must be worth at least $50"]))[0]
    for written in ("$50", "50.00", "50 dollars", "cart_total=50.00"):
        covered = boundary_covered(boundary, [case(case_id="TC-001", title=f"Cart of {written}")])
        assert "$50.00" in covered, written


# ── coupons ───────────────────────────────────────────────────────────────────


def test_the_coupon_story_activates_the_coupon_pack():
    whole = story_text("\n".join([COUPON_STORY, COUPON_CONTEXT]), COUPON_CRITERIA)
    assert "coupon" in _ids(whole, COUPON_STORY)
    assert "coupon" in _ids("The shopper enters a promo code at the till")
    assert "coupon" in _ids("A voucher takes 10% off")


def test_a_discount_on_its_own_is_not_a_coupon_feature():
    """"Discount" is a word every shop says; a coupon is a thing you type."""
    assert "coupon" not in _ids("The sale page shows a discount on every item")


def test_the_guest_check_waits_for_a_story_that_mentions_guests():
    pack = next(one for one in load_packs() if one.id == "coupon")
    guest = next(one for one in pack.checks if one.short_id == "guest_reuse")
    assert applies(guest, "Guests can use coupons too.")
    assert not applies(guest, "A signed-in shopper enters a coupon code.")


def test_every_coupon_check_is_a_test_somebody_could_run():
    pack = next(one for one in load_packs() if one.id == "coupon")
    assert len(pack.checks) == 10
    for check in pack.checks:
        assert len(check.test.steps) >= 2, check.short_id
        assert check.test.test_data.strip(), check.short_id
        assert check.test.expected_result.strip().endswith("."), check.short_id


def test_a_coupon_story_is_not_a_payment_story():
    """It says "pay less" and "before payment" and never touches a card."""
    whole = story_text("\n".join([COUPON_STORY, COUPON_CONTEXT]), COUPON_CRITERIA)
    assert "payment" not in _ids(whole, COUPON_STORY)


def test_paying_by_card_is_still_a_payment_story():
    assert "payment" in _ids(
        "As a shopper, I want to pay by card at checkout so that I get my order."
    )
    assert "payment" in _ids("Checkout takes a card payment and shows the invoice.")
    assert "payment" in _ids("A refund puts the money back on the card.")


def test_no_pack_is_switched_on_by_a_word_that_names_a_place():
    """Checkout, cart, order, profile: every story near them says them."""
    flow_words = {
        "checkout", "cart", "carts", "order", "orders", "basket", "profile",
        "profiles", "settings", "dashboard", "account", "accounts", "page",
    }
    for pack in load_packs():
        strong = {word.lower() for word in pack.triggers} & flow_words
        assert not strong, f"{pack.id}: {sorted(strong)}"
