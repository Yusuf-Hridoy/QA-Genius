"""Markdown and Jira output. Empty sections are left out and Jira markup is escaped."""

import json
import pathlib
import re

from qagenius.bug_report import BugInput
from qagenius.bug_report_checks import check_report
from qagenius.bug_report_exports import jira_escape, to_jira, to_markdown
from qagenius.models import BugReport
from tests.factories import bug_report

SAMPLE = json.loads(
    (pathlib.Path("qagenius/samples/bug_report.json")).read_text(encoding="utf-8")
)


def _sample() -> tuple[BugReport, list]:
    report = BugReport.model_validate(SAMPLE["report"])
    bug = BugInput(**SAMPLE["input"])
    return report, check_report(report, bug)


def test_markdown_starts_with_the_title_and_the_summary_line() -> None:
    report, checks = _sample()
    text = to_markdown(report, checks)
    lines = text.splitlines()

    assert lines[0] == "## " + report.title
    assert lines[2] == "**Severity:** High · **Reproducibility:** Often"


def test_markdown_numbers_the_steps_and_keeps_the_main_sections() -> None:
    report, checks = _sample()
    text = to_markdown(report, checks)

    assert "### Environment" in text
    assert "### Steps to reproduce" in text
    assert "1. Sign in to Aurora Storefront on Safari 17 and add two items to the cart" in text
    assert "5. Read the cart total in the order summary panel" in text
    assert "### Actual result" in text
    assert "### Expected result" in text


def test_markdown_writes_investigation_steps_as_a_checklist() -> None:
    report, checks = _sample()
    text = to_markdown(report, checks)
    assert "- [ ] Check the browser console for an unhandled promise rejection" in text


def test_markdown_writes_labels_as_inline_code() -> None:
    report, checks = _sample()
    assert "`checkout` `safari`" in to_markdown(report, checks)


def test_markdown_reports_what_is_still_missing() -> None:
    report, checks = _sample()
    text = to_markdown(report, checks)
    assert "### Still missing" in text
    assert "- Evidence attached — Ask for a screenshot or screen recording." in text


def test_markdown_leaves_empty_sections_out() -> None:
    report = bug_report(
        workaround=None,
        suggested_fix="   ",
        related_areas=[],
        jira_labels=None,
        investigation_steps=[],
        screenshot_annotations=None,
        related_issues=[],
        suspected_pattern=None,
        business_impact=None,
        affected_users=None,
        regression_risk=None,
    )
    text = to_markdown(report, [])

    for heading in (
        "### Workaround",
        "### Suggested fix",
        "### Related areas",
        "### Labels",
        "### Investigation steps",
        "### Screenshot notes",
        "### Related issues",
        "### Suspected pattern",
        "### Still missing",
    ):
        assert heading not in text
    assert "### Steps to reproduce" in text


def test_jira_uses_wiki_headings_and_numbered_steps() -> None:
    report, _ = _sample()
    text = to_jira(report)
    lines = text.splitlines()

    assert lines[0].startswith("h2. ")
    assert "h3. Steps to reproduce" in text
    assert "# Sign in to Aurora Storefront on Safari 17 and add two items to the cart" in text
    assert "* Check the browser console for an unhandled promise rejection" in text
    assert "{noformat}" in text
    assert "*Severity:* High" in text


def test_jira_escapes_markup_in_a_title() -> None:
    report = bug_report(title="*bold* [link|x] {code} _under_")
    text = to_jira(report)

    assert text.splitlines()[0] == (
        "h2. \\*bold\\* \\[link\\|x\\] \\{code\\} \\_under\\_"
    )
    assert "h2. *bold*" not in text


def test_jira_escapes_markup_in_steps_and_results() -> None:
    report = bug_report(
        steps_to_reproduce=["Click [Checkout|here]", "Watch *total* go to {0}"],
        actual_result="Total shows [0]",
    )
    text = to_jira(report)

    assert "# Click \\[Checkout\\|here\\]" in text
    assert "# Watch \\*total\\* go to \\{0\\}" in text
    assert "Total shows \\[0\\]" in text


def test_jira_does_not_escape_its_own_markup() -> None:
    report, _ = _sample()
    text = to_jira(report)
    assert "\\h2." not in text
    assert "\\{noformat\\}" not in text
    assert "\\*Severity:\\*" not in text


def test_escaping_a_plain_sentence_changes_nothing() -> None:
    assert jira_escape("The checkout button does nothing.") == (
        "The checkout button does nothing."
    )


def test_both_texts_end_with_one_newline() -> None:
    report, checks = _sample()
    markdown = to_markdown(report, checks)
    jira = to_jira(report)
    assert markdown.endswith("\n") and not markdown.endswith("\n\n")
    assert jira.endswith("\n") and not jira.endswith("\n\n")


def test_environment_text_cannot_close_the_jira_noformat_block() -> None:
    report = bug_report(environment_details="Safari {noformat} 17 {NOFORMAT}")
    text = to_jira(report)

    assert len(re.findall(r"\{noformat\}", text, re.IGNORECASE)) == 2
    assert "Safari { noformat } 17 { NOFORMAT }" in text
