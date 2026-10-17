"""Measured against budgeted, and the two exports a CI job can use. No AI.

Which number a line is judged on is a decision in itself, so every result
carries where its measurement came from: real users beat the lab, and INP has
no lab value at all, so it is judged by a proxy that is named as one.
"""

import json
from dataclasses import dataclass

from qagenius.pagespeed import Measurement
from qagenius.performance_budget import METRICS, Budget, BudgetLine

# Real-user data is what the budget is really about; the lab is the stand-in.
FIELD_FROM = "real users (28 days)"
LAB_FROM = "lab"
# Lighthouse cannot measure INP without a human, so TBT stands in for it.
TBT_FROM = "lab proxy: TBT"
FIELD_FIRST = ("lcp", "inp", "cls")

LIGHTHOUSE_METRICS = {  # budget line -> Lighthouse budget.json timing metric
    "lcp": "largest-contentful-paint",
    "cls": "cumulative-layout-shift",
    "fcp": "first-contentful-paint",
    # Lighthouse has no INP timing; the INP limit is asserted through TBT.
    "inp": "total-blocking-time",
}


@dataclass(frozen=True)
class BudgetResult:
    line: BudgetLine
    measured: float | None
    measured_from: str  # "real users (28 days)" | "lab" | "lab proxy: TBT" | ""
    status: str  # "within" | "over" | "not_measured" | "not_measurable"


def _measured_for(line: BudgetLine, m: Measurement) -> tuple[float | None, str]:
    """The number this line is judged on, and where it came from."""
    if line.id in FIELD_FIRST and line.id in m.field:
        return m.field[line.id], FIELD_FROM
    if line.id == "inp":
        # No lab INP exists. Total blocking time is the closest honest stand-in.
        if "tbt" in m.lab:
            return m.lab["tbt"], TBT_FROM
        return None, ""
    if line.id in m.lab:
        return m.lab[line.id], LAB_FROM
    return None, ""


def compare(budget: Budget, m: Measurement | None) -> list[BudgetResult]:
    """One result per budget line, in the budget's own order."""
    results: list[BudgetResult] = []
    for line in budget.lines:
        if not line.measurable:
            results.append(BudgetResult(line, None, "", "not_measurable"))
            continue
        if m is None:
            results.append(BudgetResult(line, None, "", "not_measured"))
            continue
        measured, source = _measured_for(line, m)
        if measured is None or line.limit is None:
            results.append(BudgetResult(line, measured, source, "not_measured"))
            continue
        status = "within" if measured <= line.limit else "over"
        results.append(BudgetResult(line, measured, source, status))
    return results


def _limits(budget: Budget) -> dict[str, float]:
    """Budget line -> limit, falling back to the published default."""
    found = {
        line.id: line.limit
        for line in budget.lines
        if line.measurable and line.limit is not None
    }
    for metric_id, (_label, _unit, default, _measurable) in METRICS.items():
        found.setdefault(metric_id, default)
    return found


def lighthouse_budget_json(budget: Budget) -> str:
    """budget.json in Lighthouse's own format, for `lighthouse --budget-path`.

    Timing budgets are in milliseconds and resource sizes in kilobytes, which
    is the unit the page weight line already uses.
    """
    limits = _limits(budget)
    timings = [
        {"metric": LIGHTHOUSE_METRICS[metric_id], "budget": limits[metric_id]}
        for metric_id in ("lcp", "cls", "fcp", "inp")
    ]
    document = [
        {
            "path": "/*",
            "timings": timings,
            "resourceSizes": [{"resourceType": "total", "budget": limits["weight"]}],
        }
    ]
    return json.dumps(document, indent=2) + "\n"


def k6_thresholds(budget: Budget) -> str:
    """A k6 options block. k6 drives requests, so it owns the server timings."""
    limits = _limits(budget)
    ttfb = limits["ttfb"]
    return (
        "// QA-Genius performance budget, built from your acceptance criteria\n"
        "// and risks. Browser metrics (LCP, CLS, INP) are not something k6\n"
        "// measures — those live in the Lighthouse budget.json export.\n"
        "export const options = {\n"
        "  thresholds: {\n"
        f"    http_req_duration: ['p(95)<{ttfb:g}'],\n"
        "    http_req_failed: ['rate<0.01'],\n"
        "  },\n"
        "};\n"
    )
