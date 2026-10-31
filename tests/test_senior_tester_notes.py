"""Fix R5 Task 6: the senior tester compares like with like.

Two false disagreements from a real browser run:

S1  "TC-007 expects AC-1 to apply on the 5th try, TC-010 on the 11th" --
    TC-007 is a test about minutes whose setup happens to count to five.
S5  "TC-001 uses 1.57286e+06 bytes, but AC-3 needs 'larger than 2 MB' --
    this test can't pass" -- TC-001 is a valid-upload test for AC-1, which
    never mentions AC-3, and the number is a 1.5 MB photo.

Every test here failed before its fix. No network, no AI.
"""

import re

from qagenius.say_numbers import family_of, say_amount, say_money, say_size, say_time
from qagenius.shadow_qa.review import (
    limit_conflicts,
    precondition_notes,
    trigger_disagreements,
)
from qagenius.test_cases import number_criteria
from tests.factories import case

LOCKOUT = [
    "Given a shopper on the sign-in page, When they enter a wrong password "
    "5 times, Then the account is locked",
    "Given a locked account, When 10 minutes have passed, Then the shopper "
    "can sign in again",
]

PHOTO = [
    "Given the user is on the profile page, When the user selects a JPEG "
    "photo under 2 megabytes And uploads the photo, Then the photo is saved",
    "When the user selects a file in a format other than JPEG or PNG, "
    "Then the upload is rejected",
    "Given the user is on the profile page, When the user selects a photo "
    "larger than 2 megabytes And uploads the photo, Then the upload is rejected",
]


def _scientific(notes: list[str]) -> list[str]:
    return [one for one in notes if re.search(r"e[+-]\d", one)]


# ── S1: a test about minutes is not a test about tries ───────────────────


def test_a_test_about_minutes_is_never_compared_with_a_rule_about_tries():
    waiting = case(
        case_id="TC-007",
        title="Still locked before the wait is over",
        traceability="AC-1",
        steps=[
            "Lock the account with 5 wrong passwords",
            "Wait 9 minutes",
            "Try to sign in with the right password",
        ],
        expected_result="The sign-in is refused: the account is still locked",
    )
    counting = case(
        case_id="TC-010",
        title="The account locks on the sixth wrong password",
        traceability="AC-1",
        steps=["Enter a wrong password 11 times"],
        expected_result="The account is locked and the sign-in is refused",
    )
    notes = trigger_disagreements([waiting, counting])
    assert notes == []


def test_two_tests_that_really_do_count_differently_are_still_called_out():
    """The note this check exists for must survive the fix."""
    sixth = case(
        case_id="TC-001",
        traceability="AC-1",
        steps=["Enter a wrong password 6 times"],
        expected_result="The account is locked and the sign-in is refused",
    )
    fifth = case(
        case_id="TC-007",
        traceability="AC-1",
        steps=["Enter a wrong password 5 times"],
        expected_result="The account is locked and the sign-in is refused",
    )
    notes = trigger_disagreements([sixth, fifth])
    assert len(notes) == 1
    assert "TC-001 expects AC-1 to apply on the 6th try" in notes[0]
    assert "TC-007 on the 5th" in notes[0]


def test_two_tests_that_wait_different_times_are_compared_in_minutes():
    nine = case(
        case_id="TC-007",
        traceability="AC-2",
        steps=["Wait 9 minutes", "Try to sign in"],
        expected_result="The sign-in is refused",
    )
    eleven = case(
        case_id="TC-010",
        traceability="AC-2",
        steps=["Wait 11 minutes", "Try to sign in"],
        expected_result="The sign-in is refused",
    )
    notes = trigger_disagreements([nine, eleven])
    assert len(notes) == 1
    assert "9 minutes" in notes[0] and "11 minutes" in notes[0]
    assert _scientific(notes) == []
    assert "try" not in notes[0]


# ── S5: a test is only weighed against the criteria it covers ────────────


def test_a_valid_upload_test_is_not_held_against_a_rule_it_never_claimed():
    valid = case(
        case_id="TC-001",
        title="A 1.5 MB JPEG is saved",
        traceability="AC-1",
        steps=["Select a 1.5 MB JPEG photo", "Upload the photo"],
        test_data="photo=holiday.jpg, size=1.5 MB",
        expected_result="The photo is saved and shown on the profile",
    )
    criteria = number_criteria(PHOTO)
    assert precondition_notes(criteria, [valid]) == []
    assert [one for one in limit_conflicts(criteria, [valid]) if "TC-001" in one] == []


def test_a_test_whose_own_data_really_does_break_its_own_rule_is_called_out():
    """The note this check exists for must survive the fix."""
    small = case(
        case_id="TC-008",
        title="The discount on a small cart",
        traceability="AC-1",
        steps=["Enter the coupon code"],
        test_data="cart_total=19.99",
        expected_result="The discount is applied",
    )
    criteria = number_criteria(
        [
            "Given a cart of at least $50.00, When a valid coupon is entered, "
            "Then the discount is applied"
        ]
    )
    notes = precondition_notes(criteria, [small])
    assert len(notes) == 1
    assert "TC-008 uses $19.99" in notes[0]
    assert "can't pass" in notes[0]


def test_no_note_ever_writes_a_number_in_scientific_notation():
    big = case(
        case_id="TC-004",
        title="A photo over the size limit",
        traceability="AC-3",
        steps=["Select a photo of 1.5 MB", "Upload the photo"],
        test_data="size=1.5 MB",
        expected_result="The upload is rejected",
    )
    criteria = number_criteria(PHOTO)
    notes = precondition_notes(criteria, [big]) + limit_conflicts(criteria, [big])
    assert _scientific(notes) == [], notes
    assert all("bytes" not in one or "MB" in one for one in notes)


# ── a test that settles an open question says so ─────────────────────────


def test_a_test_that_decides_an_open_value_says_so_instead_of_disagreeing():
    """Nobody says what happens at exactly $50, and TC-014 just decided."""
    criteria = number_criteria(
        [
            "Given a cart of more than $50.00, When a valid coupon is entered, "
            "Then the discount is applied",
            "Given a cart of less than $50.00, When a valid coupon is entered, "
            "Then the coupon is refused",
        ]
    )
    decider = case(
        case_id="TC-014",
        title="A coupon on a cart of exactly fifty",
        traceability="AC-1",
        steps=["Enter the coupon code on a cart of $50.00"],
        test_data="cart_total=50.00",
        expected_result="The discount is applied",
    )
    notes = limit_conflicts(criteria, [decider])
    said = [one for one in notes if one.startswith("TC-014")]
    assert said == ["TC-014 decides $50 is accepted while that question is still open."]
    # And the gap itself is still reported, because nobody has written it down.
    assert any("Nobody says what happens at exactly $50" in one for one in notes)


# ── one formatter, by unit ───────────────────────────────────────────────


def test_amounts_are_written_the_way_a_person_writes_them():
    assert say_amount("bytes", 1572864) == "1.5 MB"
    assert say_amount("bytes", 2097153) == "2 MB + 1 byte"
    assert say_amount("bytes", 2097152) == "2 MB"
    assert say_amount("bytes", 900) == "900 bytes"
    assert say_amount("seconds", 660) == "11 minutes"
    assert say_amount("seconds", 60) == "1 minute"
    assert say_amount("seconds", 30) == "30 seconds"
    assert say_amount("$", 49.99) == "$49.99"
    assert say_amount("digits", 6) == "6 digits"
    assert say_amount("attempts", 5) == "5 attempts"
    assert say_amount("loose-count", 5) == "5"


def test_the_formatter_never_reaches_for_scientific_notation():
    for amount in (1, 999, 1572864, 2097153, 1073741824, 9999999999):
        for unit in ("bytes", "seconds", "loose-count"):
            assert not re.search(r"e[+-]\d", say_amount(unit, amount))


def test_each_unit_belongs_to_one_family_and_only_compares_inside_it():
    assert family_of("bytes") == "size"
    assert family_of("seconds") == "time"
    assert family_of("$") == "money"
    assert family_of("money") == "money"
    assert family_of("digits") == "length"
    assert family_of("attempts") == "count"
    assert family_of("loose-count") == "count"
    assert family_of("bytes") != family_of("seconds")


def test_the_three_pieces_of_the_formatter_stand_on_their_own():
    assert say_size(1024) == "1 KB"
    assert say_size(1024**3) == "1 GB"
    assert say_time(86400) == "1 day"
    assert say_time(7200) == "2 hours"
    assert say_money(50, "$") == "$50.00"
    assert say_money(50) == "50.00"
