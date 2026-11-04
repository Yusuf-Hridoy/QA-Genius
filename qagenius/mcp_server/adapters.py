"""Turn what an agent sends into the models the engine already runs on.

Weak input is never an error here. A test with no test data is a finding —
"TC-3 has no test data" — not a refusal: an agent that gets a 400 learns
nothing, and an agent that gets a finding fixes the test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from qagenius.mcp_server.schemas import (
    CriterionIn,
    MatrixIn,
    RiskIn,
    TestIn,
)
from qagenius.models import (
    FailureMode,
    RiskAnalysis,
    TestCase,
    TestCaseList,
    TestSuiteSummary,
)
from qagenius.ship_check import MatrixRun
from qagenius.test_cases import Criterion

# An agent sends a kind in its own words; the engine counts categories.
KIND_TO_CATEGORY = {
    "normal": "Functional",
    "wrong input": "Negative",
    "at the limit": "Boundary",
    "unusual": "Edge Case",
}
CATEGORY_TO_KIND = {value: key for key, value in KIND_TO_CATEGORY.items()}

# What an agent never sends, because it would be asking it to care about
# fields that change nothing in any check it is calling.
DEFAULT_PRIORITY = "Medium"
DEFAULT_FEASIBILITY = "Medium"
DEFAULT_EFFORT = "Medium"


# The only id shape the engine reads. compute_coverage, compute_depth and
# every traceability rule look for "AC-<number>" and nothing else, so an id
# of any other shape would match no test and report the criterion as
# uncovered — silently, which is the worst way for a tool to be wrong.
AC_SHAPE = re.compile(r"^AC-\d+$", re.IGNORECASE)

RENUMBERED_NOTE = (
    "Your criterion ids were renumbered to AC-1…AC-{count} for this answer, "
    "because that is the only shape the checks read. The mapping is: {pairs}."
)


@dataclass(frozen=True)
class Naming:
    """What the agent calls each criterion, and what the engine calls it."""

    criteria: list[Criterion]           # as the engine holds them: AC-1..n
    to_engine: dict[str, str]           # "PAY-7" -> "AC-1"
    renumbered: bool = False

    def note(self) -> str:
        """The line telling the agent its ids were changed, when they were."""
        if not self.renumbered:
            return ""
        pairs = ", ".join(
            f"{given} → {engine}" for given, engine in self.to_engine.items()
        )
        return RENUMBERED_NOTE.format(count=len(self.criteria), pairs=pairs)


def naming_from(items: list[CriterionIn]) -> Naming:
    """Criteria as the engine holds them, plus how to get back to the agent's ids.

    An id already shaped "AC-7" is kept, so an agent that numbers its own
    criteria the usual way sees its own ids back. Anything else — "PAY-7",
    "story-3" — is renumbered by position and the agent is told, because
    leaving it alone would mean reporting every criterion as untested.
    """
    given = [str(item.id or "").strip() for item in items]
    keep = all(not one or AC_SHAPE.match(one) for one in given)

    criteria: list[Criterion] = []
    to_engine: dict[str, str] = {}
    for index, item in enumerate(items, start=1):
        engine_id = given[index - 1].upper() if (keep and given[index - 1]) else f"AC-{index}"
        criteria.append(Criterion(id=engine_id, text=str(item.text or "").strip()))
        if given[index - 1]:
            to_engine[given[index - 1]] = engine_id
    return Naming(
        criteria=criteria,
        to_engine=to_engine,
        renumbered=not keep and any(given),
    )


def criteria_from(items: list[CriterionIn]) -> list[Criterion]:
    """Criteria as the engine holds them. The ids alone, for callers that
    do not need to translate anything back."""
    return naming_from(items).criteria


def _traceability(covers: list[str], naming: Naming | None = None) -> str:
    """The ids a case covers, as the engine reads them: "AC-1, AC-3".

    Translated through the same mapping the criteria went through, so a
    test that says it covers "PAY-7" still reaches the criterion that was
    renumbered to AC-1.
    """
    translate = naming.to_engine if naming else {}
    names = []
    for one in covers:
        name = str(one).strip()
        if name:
            names.append(translate.get(name, name))
    return ", ".join(names)


def case_from(test: TestIn, naming: Naming | None = None) -> TestCase:
    """One agent test as the engine's TestCase.

    Everything the agent did not send is filled with a value that changes no
    check: a priority, an automation guess, no tags. Nothing is invented
    about the test itself.
    """
    return TestCase(
        id=str(test.id or "").strip(),
        title=str(test.title or "").strip(),
        category=KIND_TO_CATEGORY.get(test.kind, "Functional"),
        pre_conditions="",
        steps=[str(step) for step in test.steps],
        expected_result=str(test.expected or "").strip(),
        priority=DEFAULT_PRIORITY,
        test_data=str(test.test_data or ""),
        bdd_scenario=None,
        automation_feasibility=DEFAULT_FEASIBILITY,
        automation_effort=DEFAULT_EFFORT,
        tags=[],
        traceability=_traceability(test.covers, naming),
    )


def _summary(count: int) -> TestSuiteSummary:
    """A summary nothing reads. Every count the tools report is recomputed."""
    return TestSuiteSummary(
        total_generated=count,
        category_breakdown=[],
        priority_breakdown=[],
        automation_coverage_potential="",
        coverage_gaps=[],
        recommendations=[],
    )


def suite_from(tests: list[TestIn], naming: Naming | None = None) -> TestCaseList:
    """An agent's tests as the engine's suite."""
    cases = [case_from(test, naming) for test in tests]
    return TestCaseList(test_cases=cases, summary=_summary(len(cases)))


def test_out(case: TestCase) -> TestIn:
    """One engine TestCase back in the shape an agent sends.

    What comes out of add_tests can go straight back in, which is the whole
    point: the agent does not have to translate anything.
    """
    return TestIn(
        id=str(case.id or ""),
        title=str(case.title or ""),
        steps=[str(step) for step in (case.steps or [])] or [""],
        expected=str(case.expected_result or ""),
        test_data=str(case.test_data or ""),
        covers=_covers_of(case),
        kind=CATEGORY_TO_KIND.get(str(case.category or ""), "normal"),
    )


def _covers_of(case: TestCase) -> list[str]:
    """The criterion ids a case names, in order, no duplicates."""
    seen: list[str] = []
    for part in str(case.traceability or "").split(","):
        name = part.strip()
        if name and name not in seen:
            seen.append(name)
    return seen


def risks_from(items: list[RiskIn]) -> RiskAnalysis | None:
    """The agent's risks as the engine's analysis, or None when it sent none.

    None matters: a risk check with nothing to check says "not done yet",
    and must never say "fine".
    """
    if not items:
        return None
    modes: list[FailureMode] = []
    for index, item in enumerate(items, start=1):
        modes.append(
            FailureMode(
                id=str(item.id or "").strip() or f"R{index}",
                title=str(item.title or "").strip(),
                category=str(item.category or "functional"),
                effect=str(item.effect or ""),
                cause=str(item.cause or ""),
                severity=item.how_bad,
                likelihood=item.how_likely,
                detectability=item.how_hard_to_notice,
                related_criteria=[str(one) for one in item.linked_criteria],
                covered_by=[str(one) for one in item.tested_by],
                test_idea=str(item.test_idea or ""),
            )
        )
    return RiskAnalysis(failure_modes=modes)


def matrix_from(summary: MatrixIn | None) -> MatrixRun | None:
    """The agent's matrix as the engine's, or None when it sent none."""
    if summary is None:
        return None
    return MatrixRun(
        runs=summary.runs,
        valid_pairs=summary.valid_pairs,
        covered_pairs=summary.covered_pairs,
        manual_only=summary.manual_only,
        factors=[str(one) for one in summary.factors],
    )
