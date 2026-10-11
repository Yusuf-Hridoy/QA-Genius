"""The facts the AI is allowed to see, the prompt, and a guard on what it says back.

The AI never sees an uploaded file. It only reads the text facts_text builds from
numbers compute_insights worked out, and none of its numbers reach the page.
"""

from qagenius.models import QualityInsightSummary
from qagenius.test_run_metrics import Insights

MAX_GROUPS = 15
MAX_FLAKY = 20
MAX_GROUP_TESTS = 5
DETAILS_IN_FACTS = 600

SYSTEM = (
    "You are a senior QA lead reviewing automated test results. You only see facts "
    "that were computed from the report files; do not invent numbers, tests or groups."
    "\n\nFor each failure group, decide if it is most likely a product bug, a test "
    "issue (flaky locator, timing, bad test data, test code error) or an environment "
    "problem (network, CI machine, service down, browser install), or unknown. Base "
    "this on the message and details. Explain the likely cause in one or two sentences "
    "and give one concrete next action."
    "\n\nOnly use group ids that appear in the facts (G1, G2, ...). Keep the headline "
    "to one sentence. Do not repeat the numbers back unless they matter for a decision."
)


def _seconds(value: float) -> str:
    return f"{value:.1f} s"


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def facts_text(ins: Insights) -> str:
    """Every line here is a number or a message code computed from the files."""
    lines = [f"Runs: {len(ins.runs)}"]
    for run in ins.runs:
        lines.append(
            f'Run "{run.label}": {run.total} tests, {run.passed} passed, '
            f"{run.failed} failed, {run.skipped} skipped, {run.flaky} flaky, "
            f"pass rate {run.pass_rate}%, {_seconds(run.duration_s)}"
        )
    lines.append(
        f"All runs: {ins.overall.total} results, pass rate {ins.overall.pass_rate}%"
    )

    lines.append("")
    if not ins.groups:
        lines.append("Failure groups: none")
    else:
        lines.append("Failure groups (largest first):")
        for group in ins.groups[:MAX_GROUPS]:
            lines.append(
                f"{group.id} — {_plural(group.count, 'failure')} in "
                f"{_plural(len(group.runs), 'run')} — signature: {group.signature}"
            )
            if group.example_message:
                lines.append(f"  Example message: {group.example_message}")
            shown = group.tests[:MAX_GROUP_TESTS]
            extra = len(group.tests) - len(shown)
            tests = "; ".join(shown) + (f" (+{extra} more)" if extra > 0 else "")
            if shown:
                lines.append(f"  Tests: {tests}")
            if group.example_details:
                lines.append(
                    "  Example details (trimmed): "
                    + group.example_details[:DETAILS_IN_FACTS]
                )
        hidden = len(ins.groups) - MAX_GROUPS
        if hidden > 0:
            lines.append(f"(+{hidden} more groups not shown)")

    lines.append("")
    if not ins.flaky:
        lines.append("Flaky tests: none")
    else:
        lines.append("Flaky tests:")
        for test in ins.flaky[:MAX_FLAKY]:
            lines.append(
                f"- {test.name} ({test.reason}) in {', '.join(test.runs)}"
            )
        hidden = len(ins.flaky) - MAX_FLAKY
        if hidden > 0:
            lines.append(f"(+{hidden} more flaky tests not shown)")

    lines.append("")
    if ins.slowest:
        slowest = "; ".join(f"{name} {_seconds(seconds)}" for name, seconds in ins.slowest)
        lines.append(f"Slowest tests: {slowest}")
    else:
        lines.append("Slowest tests: none")

    return "\n".join(lines)


def insights_prompt(facts: str) -> tuple[str, str]:
    return SYSTEM, "Test run facts:\n\n" + facts


def clean_summary(
    summary: QualityInsightSummary, ins: Insights
) -> tuple[QualityInsightSummary, list[str]]:
    """Drop explanations for groups the code never found, and repeat explanations."""
    known = {group.id for group in ins.groups}
    notes: list[str] = []
    kept = []
    seen: set[str] = set()
    for insight in summary.groups:
        group_id = insight.group_id.strip()
        if group_id not in known:
            notes.append(f"Removed an explanation for unknown group {group_id}.")
            continue
        if group_id in seen:
            notes.append(f"Removed a second explanation for group {group_id}.")
            continue
        seen.add(group_id)
        kept.append(insight.model_copy(update={"group_id": group_id}))
    return summary.model_copy(update={"groups": kept}), notes
