"""The bug-report request text and the form validation. No AI, no network."""

from qagenius.bug_report import (
    DEVICE_ERROR,
    FIELD_ERROR,
    HAPPENED_ERROR,
    NOTES_ERROR,
    SCREENSHOT_NOTE,
    TOTAL_ERROR,
    URL_ERROR,
    BugInput,
    build_user_text,
    environment_text,
    reproducibility_text,
    validate_bug_input,
)

NOTES = "Checkout button does nothing on the second click in Safari."


def test_every_attempt_reproducing_is_always() -> None:
    assert reproducibility_text(5, 5) == "Always"
    assert reproducibility_text(1, 1) == "Always"


def test_some_attempts_reproducing_is_intermittent() -> None:
    assert reproducibility_text(5, 3) == "Intermittent (3 of 5)"


def test_no_attempt_reproducing_is_not_reproduced_yet() -> None:
    assert reproducibility_text(5, 0) == "Not reproduced yet"


def test_environment_with_every_field() -> None:
    bug = BugInput(
        notes=NOTES,
        device="Desktop",
        os="macOS 14",
        browser="Safari 17",
        build="2.8.1",
        url="https://staging.aurora-shop.dev/checkout",
    )
    assert environment_text(bug) == (
        "Device: Desktop; OS: macOS 14; Browser/App: Safari 17; "
        "Build/Env: 2.8.1; URL: https://staging.aurora-shop.dev/checkout"
    )


def test_environment_with_some_fields_keeps_the_order() -> None:
    bug = BugInput(notes=NOTES, os="Windows 11", url="https://shop.example.com")
    assert environment_text(bug) == "OS: Windows 11; URL: https://shop.example.com"


def test_a_device_of_not_specified_is_left_out() -> None:
    bug = BugInput(notes=NOTES, device="Not specified", os="iOS 17")
    assert environment_text(bug) == "OS: iOS 17"


def test_environment_with_nothing_filled_in() -> None:
    assert environment_text(BugInput(notes=NOTES)) == "Not provided"


def test_user_text_without_a_screenshot() -> None:
    bug = BugInput(
        notes=NOTES,
        device="Desktop",
        os="macOS 14",
        total_attempts=5,
        successful_attempts=3,
    )
    assert build_user_text("Raw bug notes:\n" + NOTES, bug) == (
        "Raw bug notes:\n" + NOTES + "\n"
        "\n"
        "Environment Details: Device: Desktop; OS: macOS 14\n"
        "Reproducibility: Intermittent (3 of 5)\n"
        "Total Attempts: 5\n"
        "Times It Happened: 3"
    )


def test_user_text_with_a_screenshot_adds_the_rule() -> None:
    bug = BugInput(notes=NOTES, total_attempts=2, successful_attempts=2, has_screenshot=True)
    text = build_user_text("Raw bug notes:\n" + NOTES, bug)

    assert text.endswith("Times It Happened: 2\n" + SCREENSHOT_NOTE)
    assert "Environment Details: Not provided" in text
    assert "Reproducibility: Always" in text
    assert "do not invent UI elements that are not shown." in text


def test_valid_form_values_become_a_bug_input() -> None:
    bug = validate_bug_input(
        notes="  " + NOTES + "  ",
        device="Desktop",
        os="macOS 14",
        total_attempts=5,
        successful_attempts=3,
    )
    assert isinstance(bug, BugInput)
    assert bug.notes == NOTES
    assert bug.total_attempts == 5
    assert bug.successful_attempts == 3


def test_short_notes_are_refused() -> None:
    assert validate_bug_input(notes="too short") == NOTES_ERROR


def test_empty_notes_are_refused() -> None:
    assert validate_bug_input(notes="   ") == NOTES_ERROR


def test_very_long_notes_are_refused() -> None:
    assert validate_bug_input(notes="x" * 3001) == NOTES_ERROR


def test_an_unknown_device_is_refused() -> None:
    assert validate_bug_input(notes=NOTES, device="Fridge") == DEVICE_ERROR


def test_a_long_environment_field_is_refused() -> None:
    assert validate_bug_input(notes=NOTES, browser="x" * 101) == FIELD_ERROR
    assert validate_bug_input(notes=NOTES, os="x" * 101) == FIELD_ERROR
    assert validate_bug_input(notes=NOTES, build="x" * 101) == FIELD_ERROR


def test_a_javascript_url_is_refused() -> None:
    assert validate_bug_input(notes=NOTES, url="javascript:alert(1)") == URL_ERROR


def test_a_very_long_url_is_refused() -> None:
    assert validate_bug_input(notes=NOTES, url="https://x.dev/" + "a" * 500) == URL_ERROR


def test_an_empty_url_is_fine() -> None:
    assert isinstance(validate_bug_input(notes=NOTES, url=""), BugInput)


def test_zero_or_too_many_attempts_are_refused() -> None:
    assert validate_bug_input(notes=NOTES, total_attempts=0) == TOTAL_ERROR
    assert validate_bug_input(notes=NOTES, total_attempts=101) == TOTAL_ERROR


def test_more_hits_than_attempts_is_refused() -> None:
    assert (
        validate_bug_input(notes=NOTES, total_attempts=3, successful_attempts=4)
        == HAPPENED_ERROR
    )


def test_a_negative_hit_count_is_refused() -> None:
    assert (
        validate_bug_input(notes=NOTES, total_attempts=3, successful_attempts=-1)
        == HAPPENED_ERROR
    )
