"""The report checks and the quality score. Computed in code, no AI."""

from qagenius.bug_report import BugInput
from qagenius.bug_report_checks import Check, check_report, quality_score
from tests.factories import bug_report

NOTES = "Checkout button does nothing on the second click in Safari, cart total shows 0"


def _full_input(**overrides) -> BugInput:
    values = {
        "notes": NOTES,
        "device": "Desktop",
        "os": "macOS 14",
        "browser": "Safari 17",
        "total_attempts": 5,
        "successful_attempts": 3,
        "has_screenshot": True,
    }
    values.update(overrides)
    return BugInput(**values)


def _row(report, bug, label: str) -> Check:
    return next(check for check in check_report(report, bug) if check.label == label)


def test_a_complete_report_passes_everything() -> None:
    checks = check_report(bug_report(), _full_input())
    assert [check.label for check in checks] == [
        "Clear title",
        "Steps to reproduce",
        "Actual vs expected differ",
        "Environment given",
        "Reproducibility known",
        "Evidence attached",
        "Severity set",
    ]
    assert all(check.ok for check in checks)
    assert all(check.hint == "" for check in checks)


def test_a_short_title_fails() -> None:
    check = _row(bug_report(title="Bug"), _full_input(), "Clear title")
    assert check.ok is False
    assert check.hint == "Ask for a one-line summary of what breaks."


def test_a_very_long_title_fails() -> None:
    assert _row(bug_report(title="x" * 121), _full_input(), "Clear title").ok is False


def test_a_title_that_just_repeats_the_notes_fails() -> None:
    assert _row(bug_report(title=NOTES), _full_input(), "Clear title").ok is False


def test_a_title_repeating_the_notes_in_another_case_fails() -> None:
    assert _row(bug_report(title=NOTES.upper()), _full_input(), "Clear title").ok is False


def test_two_steps_fail_and_three_pass() -> None:
    two = bug_report(steps_to_reproduce=["Open the cart", "Click Checkout"])
    assert _row(two, _full_input(), "Steps to reproduce").ok is False

    three = bug_report(steps_to_reproduce=["Open the cart", "Click Checkout", "Click again"])
    assert _row(three, _full_input(), "Steps to reproduce").ok is True


def test_blank_steps_do_not_count() -> None:
    report = bug_report(steps_to_reproduce=["Open the cart", "  ", "Click Checkout"])
    assert _row(report, _full_input(), "Steps to reproduce").ok is False


def test_matching_actual_and_expected_fails() -> None:
    report = bug_report(actual_result="Nothing happens", expected_result="nothing  happens")
    check = _row(report, _full_input(), "Actual vs expected differ")
    assert check.ok is False
    assert check.hint == "Ask what they expected to happen instead."


def test_an_empty_expected_result_fails() -> None:
    report = bug_report(expected_result="   ")
    assert _row(report, _full_input(), "Actual vs expected differ").ok is False


def test_a_missing_environment_fails() -> None:
    bug = _full_input(device="Not specified", os="", browser="", build="", url="")
    check = _row(bug_report(), bug, "Environment given")
    assert check.ok is False
    assert check.hint == "Ask for device, OS, browser and app version."


def test_a_single_attempt_leaves_reproducibility_unknown() -> None:
    check = _row(bug_report(), _full_input(total_attempts=1, successful_attempts=1),
                 "Reproducibility known")
    assert check.ok is False
    assert check.hint == "Ask them to try again and count how often it happens."


def test_no_screenshot_fails_evidence() -> None:
    check = _row(bug_report(), _full_input(has_screenshot=False), "Evidence attached")
    assert check.ok is False
    assert check.hint == "Ask for a screenshot or screen recording."


def test_an_unknown_severity_fails() -> None:
    check = _row(bug_report(severity="Spicy"), _full_input(), "Severity set")
    assert check.ok is False
    assert check.hint == "Agree a severity with the reporter."


def test_a_lowercase_severity_passes() -> None:
    assert _row(bug_report(severity="high"), _full_input(), "Severity set").ok is True
    assert _row(bug_report(severity="CRITICAL"), _full_input(), "Severity set").ok is True


def test_the_score_is_the_share_that_passed() -> None:
    assert quality_score(check_report(bug_report(), _full_input())) == 100

    bug = _full_input(
        device="Not specified", os="", browser="", build="", url="",
        total_attempts=1, successful_attempts=1, has_screenshot=False,
    )
    # Title, steps, actual-vs-expected and severity pass; the other three do not.
    four_of_seven = check_report(bug_report(), bug)
    assert len([check for check in four_of_seven if check.ok]) == 4
    assert quality_score(four_of_seven) == 57


def test_an_empty_check_list_scores_zero() -> None:
    assert quality_score([]) == 0
