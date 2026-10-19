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


def test_the_sentence_keeps_its_full_stop() -> None:
    said = split_confidence("Sessions are never ended [MEDIUM CONFIDENCE].")
    assert said == Said("Sessions are never ended.", "Medium")


def test_a_line_without_a_tag_is_left_alone() -> None:
    assert split_confidence("No error handling specified") == Said(
        "No error handling specified", ""
    )


def test_a_tag_in_the_middle_goes_as_well() -> None:
    """Models drop the label mid-sentence too, and it reads as nonsense there."""
    said = split_confidence("The limit [Confidence: HIGH] is never stated.")
    assert said == Said("The limit is never stated.", "High")


def test_every_shape_a_model_writes_the_label_in() -> None:
    written = (
        "No lockout limit [HIGH CONFIDENCE]",
        "No lockout limit [Confidence: HIGH]",
        "No lockout limit (confidence: high)",
        "No lockout limit. Confidence: High.",
    )
    for line in written:
        said = split_confidence(line)
        assert said.level == "High", line
        assert "confidence" not in said.text.lower(), line
        assert said.text.startswith("No lockout limit"), line


def test_the_sentence_before_a_bare_label_keeps_one_full_stop() -> None:
    assert split_confidence("The code can be replayed. Confidence: High.") == Said(
        "The code can be replayed.", "High"
    )


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


def test_a_bare_bracket_level_is_a_label_too() -> None:
    """Test B: the model dropped the word "confidence" and kept the brackets."""
    assert split_confidence("No lockout limit [HIGH]") == Said("No lockout limit", "High")
    assert split_confidence("The crop is not described (low)") == Said(
        "The crop is not described", "Low"
    )
    said = split_confidence("The avatar limit is unclear [Medium].")
    assert said == Said("The avatar limit is unclear.", "Medium")
    # Mid-sentence, the sentence closes up behind it.
    assert split_confidence("No format list [HIGH] is given").text == (
        "No format list is given"
    )


def test_the_confidence_label_phrase_goes_with_the_comma_that_led_into_it() -> None:
    assert split_confidence(
        "The photo size is not stated, with confidence label HIGH."
    ) == Said("The photo size is not stated.", "High")
    assert split_confidence(
        "The photo size is not stated with confidence label high"
    ) == Said("The photo size is not stated", "High")


def test_a_level_and_confidence_at_the_end_is_a_label() -> None:
    assert split_confidence("The crop rule is missing. High confidence.") == Said(
        "The crop rule is missing.", "High"
    )
    assert split_confidence("The crop rule is missing — Medium confidence") == Said(
        "The crop rule is missing", "Medium"
    )


def test_a_sentence_that_is_really_about_confidence_is_left_alone() -> None:
    kept = (
        "We are confident the limit is 2 MB.",
        "High confidence is not the same as proof.",
        "Rated [HIGH RISK]",
    )
    for line in kept:
        assert split_confidence(line) == Said(line, ""), line
