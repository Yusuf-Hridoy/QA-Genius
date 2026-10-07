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

NOT_COVERED = "not covered"
ONLY_ONE = "only 1 case"
NO_KIND = {"Negative": "no negative case", "Boundary": "no boundary case"}


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
