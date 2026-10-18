"""Pack detection, boundary values and the story rules. No AI, no network."""

from tests.factories import (
    LOCKOUT_CRITERIA,
    LOCKOUT_STORY,
    PROFILE_CRITERIA,
    PROFILE_STORY,
    case,
)

from qagenius.shadow_qa.boundaries import (
    MAX_BOUNDARIES,
    boundary_covered,
    find_boundaries,
    missing_values,
)
from qagenius.shadow_qa.detect import detect_packs, mentions, story_text
from qagenius.shadow_qa.story_rules import count_capabilities, epic_note, review_story
from qagenius.test_cases import number_criteria


def _ids(text: str) -> list[str]:
    return [pack.id for pack, _ in detect_packs(text)]


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
    assert _ids(LOCKOUT_STORY) == ["login", "rate_limiting"]


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
    assert "Test cases will be shallow" in note.detail
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
