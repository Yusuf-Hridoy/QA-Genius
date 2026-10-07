"""Build test-case prompts and compute traceability and coverage from AI output."""

import re
from dataclasses import dataclass

from qagenius.models import TestCase, TestCaseList

COVERAGE_FOCUS_OPTIONS = ("Functional", "Negative", "Boundary", "Edge Case")
CATEGORY_ORDER = ("Functional", "Negative", "Boundary", "Edge Case")
PRIORITY_ORDER = ("High", "Medium", "Low")
AC_ID = re.compile(r"\bAC-(\d+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Criterion:
    id: str  # "AC-1"
    text: str


def number_criteria(texts: list[str]) -> list[Criterion]:
    """Strip blanks, drop empty items, assign AC-1..n by position."""
    criteria: list[Criterion] = []
    for text in texts:
        cleaned = text.strip()
        if not cleaned:
            continue
        criteria.append(Criterion(id=f"AC-{len(criteria) + 1}", text=cleaned))
    return criteria


def _one_line(text: str) -> str:
    """A criterion on a single prompt line: newlines become ' / '."""
    parts = [line.strip() for line in text.splitlines()]
    return " / ".join(part for part in parts if part)


def criteria_block(criteria: list[Criterion]) -> str:
    """The acceptance criteria appended to the user prompt, one per line."""
    lines = [
        "",
        "",
        'Acceptance criteria (put the ids each test case covers in "traceability", '
        'e.g. "AC-2" or "AC-1, AC-3"; every criterion must be covered by at least '
        "one test case):",
    ]
    lines.extend(f"{criterion.id}: {_one_line(criterion.text)}" for criterion in criteria)
    return "\n".join(lines)


def build_user_text(
    base_user_text: str, coverage_focus: list[str], criteria: list[Criterion]
) -> str:
    """base + coverage focus line + criteria block (block only if criteria not empty)."""
    focus = list(coverage_focus) or list(COVERAGE_FOCUS_OPTIONS)
    text = base_user_text + "\n\nTest Coverage Focus: " + ", ".join(focus)
    if criteria:
        text += criteria_block(criteria)
    return text


def traced_ids(test_case: TestCase, valid_ids: set[str]) -> list[str]:
    """The AC ids a case claims, in order, no duplicates, known ids only."""
    found: list[str] = []
    for match in AC_ID.finditer(test_case.traceability or ""):
        ac_id = match.group(0).upper()
        if ac_id in valid_ids and ac_id not in found:
            found.append(ac_id)
    return found


@dataclass(frozen=True)
class Coverage:
    covered: list[str]  # ids covered by >= 1 case, in criteria order
    uncovered: list[str]  # ids covered by no case, in criteria order
    percent: int
    cases_per_id: dict[str, int]


def compute_coverage(result: TestCaseList, criteria: list[Criterion]) -> Coverage:
    """Which criteria the AI's cases actually reach. Never reads the AI's summary."""
    valid_ids = {criterion.id for criterion in criteria}
    cases_per_id = {criterion.id: 0 for criterion in criteria}
    for test_case in result.test_cases:
        for ac_id in traced_ids(test_case, valid_ids):
            cases_per_id[ac_id] += 1
    covered = [c.id for c in criteria if cases_per_id[c.id] > 0]
    uncovered = [c.id for c in criteria if cases_per_id[c.id] == 0]
    percent = 100 if not criteria else round(100 * len(covered) / len(criteria))
    return Coverage(
        covered=covered,
        uncovered=uncovered,
        percent=percent,
        cases_per_id=cases_per_id,
    )


@dataclass(frozen=True)
class Counts:
    total: int
    by_category: dict[str, int]
    by_priority: dict[str, int]


def normalise_label(value: str) -> str:
    """'edge case ' -> 'Edge Case'."""
    return " ".join(str(value or "").split()).title()


def _tally(values: list[str], first: tuple[str, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        name = normalise_label(value)
        if not name:
            continue
        counts[name] = counts.get(name, 0) + 1
    ordered = {name: counts[name] for name in first if name in counts}
    for name in sorted(name for name in counts if name not in first):
        ordered[name] = counts[name]
    return ordered


def compute_counts(result: TestCaseList) -> Counts:
    """Totals per category and priority, counted from the cases themselves."""
    cases = result.test_cases
    return Counts(
        total=len(cases),
        by_category=_tally([case.category for case in cases], CATEGORY_ORDER),
        by_priority=_tally([case.priority for case in cases], PRIORITY_ORDER),
    )
