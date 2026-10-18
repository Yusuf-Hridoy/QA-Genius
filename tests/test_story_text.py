"""The two bits of tidying a story analysis needs before it is shown."""

from qagenius.story_text import (
    Said,
    split_confidence,
    strip_confidence,
    without_criteria_lines,
)


def test_a_trailing_tag_comes_off_and_the_level_comes_back() -> None:
    assert split_confidence("Add a lockout limit [HIGH CONFIDENCE]") == Said(
        "Add a lockout limit", "High"
    )


def test_the_case_of_the_tag_does_not_matter() -> None:
    for written in ("[low confidence]", "[Low Confidence]", "[LOW CONFIDENCE]"):
        assert split_confidence(f"No retry limit {written}").level == "Low"


def test_a_full_stop_after_the_tag_goes_too() -> None:
    said = split_confidence("Sessions are never ended [MEDIUM CONFIDENCE].")
    assert said == Said("Sessions are never ended", "Medium")


def test_a_line_without_a_tag_is_left_alone() -> None:
    assert split_confidence("No error handling specified") == Said(
        "No error handling specified", ""
    )


def test_a_tag_in_the_middle_is_not_a_tag() -> None:
    """Only a trailing tag is the model labelling its own answer."""
    text = "The phrase [HIGH CONFIDENCE] appears in their copy"
    assert split_confidence(text) == Said(text, "")


def test_confidence_is_not_invented_from_similar_words() -> None:
    assert split_confidence("Rated [HIGH RISK]").level == ""
    assert split_confidence("confidence").level == ""


def test_empty_and_missing_values_survive() -> None:
    assert split_confidence(None) == Said("", "")
    assert split_confidence("") == Said("", "")


def test_strip_gives_just_the_words() -> None:
    assert strip_confidence("Lock the account [HIGH CONFIDENCE]") == "Lock the account"


def test_criteria_lines_go_once_criteria_exist() -> None:
    missing = [
        "No acceptance criteria defined",
        "No error handling specified",
        "Acceptance Criteria are absent",
    ]
    assert without_criteria_lines(missing, True) == ["No error handling specified"]


def test_without_criteria_nothing_is_hidden() -> None:
    missing = ["No acceptance criteria defined", "No error handling specified"]
    assert without_criteria_lines(missing, False) == missing
