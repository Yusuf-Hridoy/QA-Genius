"""What a bug report has and what is still missing. Computed in code, never by AI."""

from dataclasses import dataclass

from qagenius.bug_report import BugInput, environment_text
from qagenius.models import BugReport

TITLE_MIN, TITLE_MAX = 10, 120
MIN_STEPS = 3
SEVERITIES = ("Critical", "High", "Medium", "Low")


@dataclass(frozen=True)
class Check:
    label: str
    ok: bool
    hint: str  # what to ask the reporter when not ok; "" when ok


def _normalise(text: str) -> str:
    """Lowercase with runs of whitespace collapsed, for comparing two sentences."""
    return " ".join((text or "").lower().split())


def _clear_title(report: BugReport, bug: BugInput) -> bool:
    title = (report.title or "").strip()
    if not TITLE_MIN <= len(title) <= TITLE_MAX:
        return False
    return _normalise(title) != _normalise(bug.notes[:TITLE_MAX])


def _enough_steps(report: BugReport) -> bool:
    return len([step for step in report.steps_to_reproduce if (step or "").strip()]) >= MIN_STEPS


def _actual_differs(report: BugReport) -> bool:
    actual = _normalise(report.actual_result)
    expected = _normalise(report.expected_result)
    return bool(actual) and bool(expected) and actual != expected


def _severity_set(report: BugReport) -> bool:
    return (report.severity or "").strip().title() in SEVERITIES


def check_report(report: BugReport, bug: BugInput) -> list[Check]:
    """One row per thing a good bug report needs, in the order the card shows them."""
    rows = (
        (
            "Clear title",
            _clear_title(report, bug),
            "Ask for a one-line summary of what breaks.",
        ),
        (
            "Steps to reproduce",
            _enough_steps(report),
            "Ask for the exact clicks or inputs before the bug.",
        ),
        (
            "Actual vs expected differ",
            _actual_differs(report),
            "Ask what they expected to happen instead.",
        ),
        (
            "Environment given",
            environment_text(bug) != "Not provided",
            "Ask for device, OS, browser and app version.",
        ),
        (
            "Reproducibility known",
            bug.total_attempts > 1,
            "Ask them to try again and count how often it happens.",
        ),
        (
            "Evidence attached",
            bug.has_screenshot,
            "Ask for a screenshot or screen recording.",
        ),
        (
            "Severity set",
            _severity_set(report),
            "Agree a severity with the reporter.",
        ),
    )
    return [Check(label=label, ok=ok, hint="" if ok else hint) for label, ok, hint in rows]


def quality_score(checks: list[Check]) -> int:
    """How many checks passed, as a percentage."""
    if not checks:
        return 0
    return round(100 * len([check for check in checks if check.ok]) / len(checks))
