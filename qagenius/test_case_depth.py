"""Per-criterion depth: how many cases cover each criterion, of which kinds, and whether it is thin."""

from dataclasses import dataclass

from qagenius.models import TestCaseList
from qagenius.test_cases import (
    CATEGORY_ORDER,
    Criterion,
    normalise_label,
    traced_ids,
)

DEPTH_KINDS = ("Negative", "Boundary")  # kinds every criterion should have
MIN_CASES = 2

NOT_COVERED = "no tests yet"
ONLY_ONE = "only one test"
NO_KIND = {"Negative": "no test for wrong input", "Boundary": "no test at the limits"}
# Each reason reads as the end of "4 have ...", so the summary sentence can be
# built from the same words the table shows.
REASON_ORDER = (NOT_COVERED, ONLY_ONE, NO_KIND["Negative"], NO_KIND["Boundary"])
# Two reasons is a sentence anyone can read in one go; the table below the
# line has the rest, per criterion.
MAX_REASONS_IN_LINE = 2


@dataclass(frozen=True)
class CriterionDepth:
    id: str
    text: str
    case_ids: list[str]
    kinds: list[str]
    reasons: list[str]
    thin: bool


@dataclass(frozen=True)
class DepthReport:
    rows: list[CriterionDepth]
    thin_ids: list[str]


def _ordered_kinds(categories: list[str]) -> list[str]:
    """Present categories, CATEGORY_ORDER first, then anything else alphabetically."""
    present = {normalise_label(category) for category in categories}
    present.discard("")
    kinds = [name for name in CATEGORY_ORDER if name in present]
    kinds.extend(sorted(name for name in present if name not in CATEGORY_ORDER))
    return kinds


def _reasons(case_count: int, kinds: list[str]) -> list[str]:
    if case_count == 0:
        return [NOT_COVERED]
    reasons = []
    if case_count < MIN_CASES:
        reasons.append(ONLY_ONE)
    for kind in DEPTH_KINDS:
        if kind not in kinds:
            reasons.append(NO_KIND[kind])
    return reasons


def compute_depth(result: TestCaseList, criteria: list[Criterion]) -> DepthReport:
    """How well each criterion is tested. Counted from the cases, never from the summary."""
    valid_ids = {criterion.id for criterion in criteria}
    cases_by_id: dict[str, list] = {criterion.id: [] for criterion in criteria}
    for test_case in result.test_cases:
        for ac_id in traced_ids(test_case, valid_ids):
            cases_by_id[ac_id].append(test_case)

    rows = []
    for criterion in criteria:
        cases = cases_by_id[criterion.id]
        kinds = _ordered_kinds([case.category for case in cases])
        reasons = _reasons(len(cases), kinds)
        rows.append(
            CriterionDepth(
                id=criterion.id,
                text=criterion.text,
                case_ids=[case.id for case in cases],
                kinds=kinds,
                reasons=reasons,
                thin=bool(reasons),
            )
        )
    return DepthReport(rows=rows, thin_ids=[row.id for row in rows if row.thin])


def reason_counts(report: DepthReport) -> list[tuple[str, int]]:
    """How many criteria each reason applies to, commonest first.

    A criterion can need more than one thing, so the counts are per reason and
    do not add up to the number of criteria.
    """
    counts = {reason: 0 for reason in REASON_ORDER}
    for row in report.rows:
        for reason in row.reasons:
            if reason in counts:
                counts[reason] += 1
    found = [(reason, count) for reason, count in counts.items() if count]
    return sorted(found, key=lambda pair: (-pair[1], REASON_ORDER.index(pair[0])))


def summary_line(report: DepthReport) -> str:
    """One sentence saying what is really missing, built from the rows.

    The old sentence said every thin criterion had no negative or boundary
    case, which a suite with twelve boundary cases makes a plain untruth.
    """
    total = len(report.rows)
    thin = len(report.thin_ids)
    if not total:
        return ""
    if not thin:
        return "Every criterion has a test for wrong input and one at the limits."
    parts = [
        f"{count} {'has' if count == 1 else 'have'} {reason}"
        for reason, count in reason_counts(report)[:MAX_REASONS_IN_LINE]
    ]
    word = "criterion" if total == 1 else "criteria"
    needs = "needs" if thin == 1 else "need"
    return f"{thin} of {total} {word} {needs} more tests — {', '.join(parts)}."
