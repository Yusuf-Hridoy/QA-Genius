"""Write a bug report out as GitHub-flavoured Markdown or Jira wiki markup."""

import re

from qagenius.bug_report_checks import Check
from qagenius.models import BugReport

# Characters Jira reads as markup. Escaped so AI or user text cannot break the page.
_JIRA_SPECIAL = re.compile(r"([{}\[\]|*_])")

# Markers that close a {noformat} or {code} block. Spaced out in any text put inside one.
_JIRA_BLOCK_MARKER = re.compile(r"\{\s*(?:noformat|code)(?::[^}\n]*)?\s*\}", re.IGNORECASE)


def jira_escape(text: str) -> str:
    """Backslash-escape the characters Jira treats as markup."""
    return _JIRA_SPECIAL.sub(r"\\\1", text or "")


def jira_block_safe(text: str) -> str:
    """Defuse the markers that would let text close the block it sits in."""
    return _JIRA_BLOCK_MARKER.sub(lambda m: "{ " + m.group(0)[1:-1].strip() + " }", text or "")


def _clean(text: str) -> str:
    return (text or "").strip()


def _filled(values: list[str] | None) -> list[str]:
    return [_clean(value) for value in (values or []) if _clean(value)]


def to_markdown(report: BugReport, checks: list[Check]) -> str:
    """The report as Markdown for GitHub or GitLab. Empty sections are left out."""
    lines = [f"## {_clean(report.title)}", ""]
    lines.append(
        f"**Severity:** {_clean(report.severity)} · "
        f"**Reproducibility:** {_clean(report.reproducibility_rate)}"
    )
    lines += ["", "### Environment", "", _clean(report.environment_details) or "Not provided"]

    steps = _filled(report.steps_to_reproduce)
    if steps:
        lines += ["", "### Steps to reproduce", ""]
        lines += [f"{number}. {step}" for number, step in enumerate(steps, start=1)]

    lines += ["", "### Actual result", "", _clean(report.actual_result)]
    lines += ["", "### Expected result", "", _clean(report.expected_result)]

    for heading, value in (
        ("Suspected pattern", report.suspected_pattern),
        ("Suggested fix", report.suggested_fix),
        ("Workaround", report.workaround),
        ("Business impact", report.business_impact),
        ("Affected users", report.affected_users),
        ("Regression risk", report.regression_risk),
    ):
        if _clean(value):
            lines += ["", f"### {heading}", "", _clean(value)]

    investigation = _filled(report.investigation_steps)
    if investigation:
        lines += ["", "### Investigation steps", ""]
        lines += [f"- [ ] {step}" for step in investigation]

    for heading, values in (
        ("Related areas", report.related_areas),
        ("Related issues", report.related_issues),
        ("Screenshot notes", report.screenshot_annotations),
    ):
        items = _filled(values)
        if items:
            lines += ["", f"### {heading}", ""]
            lines += [f"- {item}" for item in items]

    labels = _filled(report.jira_labels)
    if labels:
        lines += ["", "### Labels", "", " ".join(f"`{label}`" for label in labels)]

    missing = [check.label for check in checks if not check.ok]
    if missing:
        lines += ["", "### Still missing", ""]
        lines += [
            f"- {check.label} — {check.hint}" for check in checks if not check.ok
        ]

    return "\n".join(lines).rstrip() + "\n"


def to_jira(report: BugReport) -> str:
    """The report as Jira wiki markup. Every value is escaped, the markup is not."""
    lines = [f"h2. {jira_escape(_clean(report.title))}", ""]
    lines.append(
        f"*Severity:* {jira_escape(_clean(report.severity))} | "
        f"*Reproducibility:* {jira_escape(_clean(report.reproducibility_rate))}"
    )
    lines += [
        "",
        "h3. Environment",
        "{noformat}",
        jira_block_safe(_clean(report.environment_details)) or "Not provided",
        "{noformat}",
    ]

    steps = _filled(report.steps_to_reproduce)
    if steps:
        lines += ["", "h3. Steps to reproduce", ""]
        lines += [f"# {jira_escape(step)}" for step in steps]

    lines += ["", "h3. Actual result", "", jira_escape(_clean(report.actual_result))]
    lines += ["", "h3. Expected result", "", jira_escape(_clean(report.expected_result))]

    for heading, value in (
        ("Suspected pattern", report.suspected_pattern),
        ("Suggested fix", report.suggested_fix),
        ("Workaround", report.workaround),
        ("Business impact", report.business_impact),
        ("Affected users", report.affected_users),
        ("Regression risk", report.regression_risk),
    ):
        if _clean(value):
            lines += ["", f"h3. {heading}", "", jira_escape(_clean(value))]

    for heading, values in (
        ("Investigation steps", report.investigation_steps),
        ("Related areas", report.related_areas),
        ("Related issues", report.related_issues),
        ("Screenshot notes", report.screenshot_annotations),
        ("Labels", report.jira_labels),
    ):
        items = _filled(values)
        if items:
            lines += ["", f"h3. {heading}", ""]
            lines += [f"* {jira_escape(item)}" for item in items]

    return "\n".join(lines).rstrip() + "\n"
