"""Write a ship report out as Markdown, to paste into a release thread."""

from datetime import date

from qagenius.ship_check import VERDICT_LABELS, ShipReport
from qagenius.ship_grade import grade_for

# What a status looks like at a glance, and what it is called.
STATUS_ICONS = {
    "pass": "✅",
    "warn": "⚠️",
    "fail": "❌",
    "accepted": "🟡",
    "not_checked": "⚪",
}
STATUS_LABELS = {
    "pass": "Pass",
    "warn": "Warn",
    "fail": "Fail",
    "accepted": "Accepted",
    "not_checked": "Not checked",
}

STORY_IN_HEADER = 200


def _cell(text: str) -> str:
    """A pipe in a summary would start a new column, so it is escaped."""
    return " ".join(str(text or "").split()).replace("|", r"\|")


def _status(item) -> str:
    return f"{STATUS_ICONS[item.status]} {STATUS_LABELS[item.status]}"


def _summary(item) -> str:
    if item.status == "accepted" and item.accepted_note:
        return f'{item.summary} — accepted: "{item.accepted_note}"'
    return item.summary


def to_markdown(report: ShipReport, story: str) -> str:
    """The whole verdict as one Markdown block. Nothing here is AI text."""
    total = len(report.items)
    lines = [
        f"# Ship check — {VERDICT_LABELS[report.verdict]}",
        report.verdict_reason,
        "",
        f"**Story:** {_cell(story)[:STORY_IN_HEADER]}",
        f"**Checked:** {report.checked} of {total} · {date.today().isoformat()}",
    ]
    # The grade is arithmetic on the rows above, so it travels with them.
    grade = grade_for(report)
    if grade is not None:
        lines.append(
            f"**Grade:** {grade.letter} — {grade.points} of {grade.max_points} points"
        )
    lines += [
        "",
        "| Check | Status | Summary |",
        "|---|---|---|",
    ]
    for item in report.items:
        lines.append(
            f"| {_cell(item.title)} | {_status(item)} | {_cell(_summary(item))} |"
        )

    # Why that letter, before the per-check detail: it explains the table
    # just above it.
    if grade is not None:
        lines += ["", "## Why that grade"]
        lines += [f"- {line}" for line in grade.lines]

    detailed = [item for item in report.items if item.status != "pass"]
    if detailed:
        lines += ["", "## Details"]
        for item in detailed:
            lines += ["", f"### {item.title} — {STATUS_LABELS[item.status]}"]
            for line in item.details or [item.summary]:
                lines.append(f"- {line}")
            if item.status == "accepted" and item.accepted_note:
                lines.append(f'- Accepted: "{item.accepted_note}"')
            if item.owner:
                lines.append(f"- Owner: {item.owner}")
            if item.review_date:
                word = "Review date passed" if item.review_passed else "Review by"
                lines.append(f"- {word}: {item.review_date}")

    return "\n".join(lines) + "\n"
