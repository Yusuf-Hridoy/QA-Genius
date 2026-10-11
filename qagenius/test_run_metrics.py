"""Turn parsed runs into the numbers the Quality insights page shows.

Code computes every number here. The AI only ever sees what this module found.
"""

import re
from dataclasses import asdict, dataclass
from typing import Any

from qagenius.report_parsers import RunReport, TestResult, strip_ansi

SIGNATURE_LIMIT = 160
MESSAGE_LIMIT = 300
DETAILS_LIMIT = 1500
GROUP_TESTS_LIMIT = 20
SLOWEST_COUNT = 5
NO_MESSAGE = "(no message)"

RETRIED = "retried and passed"
CROSS_RUN = "passed in one run, failed in another"

_URL = re.compile(r"https?://\S+")
_FILE = re.compile(r"\S+\.(?:py|ts|js|tsx|jsx|java|cs|rb)(?::\d+)+")
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"|`[^`]*`")
_HEX = re.compile(r"0x[0-9a-f]+|\b[0-9a-f]{8,}\b", re.IGNORECASE)
_NUMBER = re.compile(r"\d+")
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True)
class RunSummary:
    label: str
    total: int
    passed: int
    failed: int
    skipped: int
    flaky: int
    pass_rate: int
    duration_s: float


@dataclass(frozen=True)
class FailureGroup:
    id: str
    signature: str
    example_message: str
    example_details: str
    tests: list[str]
    count: int
    runs: list[str]


@dataclass(frozen=True)
class FlakyTest:
    name: str
    suite: str
    reason: str
    runs: list[str]


@dataclass(frozen=True)
class Insights:
    runs: list[RunSummary]
    overall: RunSummary
    groups: list[FailureGroup]
    flaky: list[FlakyTest]
    slowest: list[tuple[str, float]]


def normalise_signature(message: str) -> str:
    """The same failure cause from two runs must come out as the same text."""
    text = ""
    for line in strip_ansi(message or "").splitlines():
        if line.strip():
            text = line
            break
    text = _URL.sub("<url>", text)
    text = _FILE.sub("<file>", text)
    text = _QUOTED.sub('"…"', text)
    text = _HEX.sub("<hex>", text)
    text = _NUMBER.sub("N", text)
    text = _SPACES.sub(" ", text).strip()
    return text[:SIGNATURE_LIMIT] or NO_MESSAGE


def _pass_rate(passed: int, flaky: int, total: int, skipped: int) -> int:
    ran = total - skipped
    if ran <= 0:
        return 100
    return round(100 * (passed + flaky) / ran)


def _summary(label: str, tests: list[TestResult]) -> RunSummary:
    counts = {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}
    for test in tests:
        if test.status in counts:
            counts[test.status] += 1
    return RunSummary(
        label=label,
        total=len(tests),
        passed=counts["passed"],
        failed=counts["failed"],
        skipped=counts["skipped"],
        flaky=counts["flaky"],
        pass_rate=_pass_rate(
            counts["passed"], counts["flaky"], len(tests), counts["skipped"]
        ),
        duration_s=round(sum(test.duration_s for test in tests), 3),
    )


def _groups(pairs: list[tuple[str, TestResult]]) -> list[FailureGroup]:
    """One group per normalised message, largest first, ties by first appearance."""
    order: list[str] = []
    found: dict[str, dict[str, Any]] = {}
    for label, test in pairs:
        if test.status != "failed":
            continue
        signature = normalise_signature(test.message)
        group = found.get(signature)
        if group is None:
            order.append(signature)
            group = {
                "count": 0,
                "message": "",
                "details": "",
                "tests": [],
                "runs": [],
            }
            found[signature] = group
        group["count"] += 1
        if not group["message"] and test.message.strip():
            group["message"] = test.message.strip()[:MESSAGE_LIMIT]
        if not group["details"] and test.details.strip():
            group["details"] = test.details.strip()[:DETAILS_LIMIT]
        if test.name not in group["tests"]:
            group["tests"].append(test.name)
        if label not in group["runs"]:
            group["runs"].append(label)

    seen_at = {signature: index for index, signature in enumerate(order)}
    ranked = sorted(
        order, key=lambda signature: (-found[signature]["count"], seen_at[signature])
    )
    return [
        FailureGroup(
            id=f"G{number}",
            signature=signature,
            example_message=found[signature]["message"],
            example_details=found[signature]["details"],
            tests=found[signature]["tests"][:GROUP_TESTS_LIMIT],
            count=found[signature]["count"],
            runs=found[signature]["runs"],
        )
        for number, signature in enumerate(ranked, start=1)
    ]


def _flaky(pairs: list[tuple[str, TestResult]]) -> list[FlakyTest]:
    order: list[str] = []
    seen: dict[str, dict[str, Any]] = {}
    for label, test in pairs:
        if test.status == "skipped":
            continue
        entry = seen.get(test.test_id)
        if entry is None:
            order.append(test.test_id)
            entry = {
                "name": test.name,
                "suite": test.suite,
                "statuses": [],
            }
            seen[test.test_id] = entry
        entry["statuses"].append((label, test.status))

    out: list[FlakyTest] = []
    for test_id in order:
        entry = seen[test_id]
        statuses = entry["statuses"]
        retried = [label for label, status in statuses if status == "flaky"]
        if retried:
            reason, runs = RETRIED, retried
        elif any(status in ("passed", "flaky") for _, status in statuses) and any(
            status == "failed" for _, status in statuses
        ):
            reason, runs = CROSS_RUN, [label for label, _ in statuses]
        else:
            continue
        out.append(
            FlakyTest(
                name=entry["name"],
                suite=entry["suite"],
                reason=reason,
                runs=list(dict.fromkeys(runs)),
            )
        )
    return out


def _slowest(pairs: list[tuple[str, TestResult]]) -> list[tuple[str, float]]:
    """Top 5 by the slowest single result; a test run twice is listed once."""
    best: dict[str, float] = {}
    seen_at: dict[str, int] = {}
    for _, test in pairs:
        seen_at.setdefault(test.name, len(seen_at))
        if test.duration_s > best.get(test.name, -1.0):
            best[test.name] = test.duration_s
    names = sorted(best, key=lambda name: (-best[name], seen_at[name]))
    return [(name, round(best[name], 3)) for name in names[:SLOWEST_COUNT]]


def compute_insights(reports: list[RunReport]) -> Insights:
    pairs: list[tuple[str, TestResult]] = [
        (report.label, test) for report in reports for test in report.tests
    ]
    return Insights(
        runs=[_summary(report.label, report.tests) for report in reports],
        overall=_summary("All runs", [test for _, test in pairs]),
        groups=_groups(pairs),
        flaky=_flaky(pairs),
        slowest=_slowest(pairs),
    )


# ---------- round trip through the page ----------


def insights_to_dict(insights: Insights) -> dict:
    """Plain JSON for the hidden field the Explain button posts back."""
    return asdict(insights)


def _summary_from_dict(raw: Any) -> RunSummary:
    return RunSummary(
        label=str(raw["label"]),
        total=int(raw["total"]),
        passed=int(raw["passed"]),
        failed=int(raw["failed"]),
        skipped=int(raw["skipped"]),
        flaky=int(raw["flaky"]),
        pass_rate=int(raw["pass_rate"]),
        duration_s=float(raw["duration_s"]),
    )


def _str_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        raise ValueError("expected a list of strings")
    return [str(item) for item in raw]


def insights_from_dict(raw: Any) -> Insights:
    """Rebuild Insights from the page's JSON. Raises ValueError on anything odd."""
    if not isinstance(raw, dict):
        raise ValueError("expected an object")
    try:
        return Insights(
            runs=[_summary_from_dict(run) for run in raw["runs"]],
            overall=_summary_from_dict(raw["overall"]),
            groups=[
                FailureGroup(
                    id=str(group["id"]),
                    signature=str(group["signature"]),
                    example_message=str(group["example_message"]),
                    example_details=str(group["example_details"]),
                    tests=_str_list(group["tests"]),
                    count=int(group["count"]),
                    runs=_str_list(group["runs"]),
                )
                for group in raw["groups"]
            ],
            flaky=[
                FlakyTest(
                    name=str(test["name"]),
                    suite=str(test["suite"]),
                    reason=str(test["reason"]),
                    runs=_str_list(test["runs"]),
                )
                for test in raw["flaky"]
            ],
            slowest=[
                (str(item[0]), float(item[1]))
                for item in raw["slowest"]
                if len(item) == 2
            ],
        )
    except (KeyError, TypeError, IndexError, ValueError) as e:
        raise ValueError(f"not a computed insights object: {e}") from e


def _md_seconds(value: float) -> str:
    return f"{value:.1f} s"


def insights_markdown(ins: Insights) -> str:
    """The Copy summary button's text. Code-computed numbers only, no AI words."""
    overall = ins.overall
    lines = [
        "## Test run summary",
        "",
        f"Pass rate {overall.pass_rate}% · {overall.total} results · "
        f"{overall.passed} passed · {overall.failed} failed · {overall.flaky} flaky · "
        f"{overall.skipped} skipped · {_md_seconds(overall.duration_s)}",
    ]

    if len(ins.runs) > 1:
        lines += [
            "",
            "| Run | Tests | Passed | Failed | Flaky | Skipped | Pass rate | Duration |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for run in ins.runs:
            lines.append(
                f"| {run.label} | {run.total} | {run.passed} | {run.failed} | "
                f"{run.flaky} | {run.skipped} | {run.pass_rate}% | "
                f"{_md_seconds(run.duration_s)} |"
            )

    lines += ["", "### Failure groups", ""]
    if not ins.groups:
        lines.append("No failures.")
    for group in ins.groups:
        lines += [
            f"**{group.id} — {group.count} failing "
            f"{'result' if group.count == 1 else 'results'} in "
            f"{len(group.runs)} {'run' if len(group.runs) == 1 else 'runs'}**",
            "",
            f"- Signature: `{group.signature}`",
        ]
        if group.example_message:
            lines.append(f"- Example message: {group.example_message}")
        if group.tests:
            lines.append(f"- Tests: {'; '.join(group.tests)}")
        lines.append("")

    lines += ["### Flaky tests", ""]
    if not ins.flaky:
        lines.append("None found.")
    for test in ins.flaky:
        lines.append(f"- {test.name} — {test.reason} ({', '.join(test.runs)})")

    lines += ["", "### Slowest tests", ""]
    if not ins.slowest:
        lines.append("No timings in these reports.")
    for name, seconds in ins.slowest:
        lines.append(f"- {name} — {_md_seconds(seconds)}")

    lines += ["", "All numbers were computed from the report files by code."]
    return "\n".join(lines).rstrip() + "\n"
