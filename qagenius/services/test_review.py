"""The senior tester's read of a suite: what is missing, weak or wrong.

No AI. Everything here is the same plain code the Test cases page runs, so
the website and an agent calling over MCP get the same answer for the same
suite.
"""

from dataclasses import dataclass, field

from qagenius.models import TestCaseList
from qagenius.shadow_qa.review import CaseReview, review_test_cases
from qagenius.test_case_depth import DepthReport, compute_depth, summary_line
from qagenius.test_cases import (
    Counts,
    Coverage,
    Criterion,
    compute_counts,
    compute_coverage,
    number_criteria,
)


@dataclass(frozen=True)
class TestReview:
    """One suite, read every way the page reads it."""

    # Its name starts with "Test", so pytest tries to collect it as a suite.
    # Not a field: a bare attribute with no annotation is invisible to the
    # dataclass machinery.
    __test__ = False

    # The AI's cases plus the ones the senior tester added. Every count below
    # is taken from this, never from the AI's own summary.
    suite: TestCaseList
    criteria: list[Criterion]
    review: CaseReview
    coverage: Coverage
    counts: Counts
    depth: DepthReport
    depth_line: str = ""
    # The cases the senior tester added, on their own, for a caller that
    # wants to show them apart from the suite.
    added: list = field(default_factory=list)
    # The same two readings over the suite exactly as it was handed in.
    #
    # The website merges the added cases into the result the reader takes
    # away, so merged is what it should count. An agent has not added them
    # yet — they are still a proposal — so telling it the gaps are filled
    # would be telling it the opposite of the truth. Both readings are here
    # and each door takes the one that matches what its reader is holding.
    given_coverage: Coverage | None = None
    given_depth: DepthReport | None = None
    given_depth_line: str = ""


def as_criteria(criteria) -> list[Criterion]:
    """Criteria from whichever shape the caller holds them in.

    The web route already has them numbered; an agent sends plain strings.
    Both end up as AC-1..n in the order they arrived.
    """
    items = list(criteria or [])
    if items and isinstance(items[0], Criterion):
        return items
    return number_criteria([str(one or "") for one in items])


def merged_suite(result: TestCaseList, review: CaseReview) -> TestCaseList:
    """The AI's cases plus the ones it missed, in that order."""
    return TestCaseList(
        test_cases=list(result.test_cases) + list(review.added),
        summary=result.summary,
    )


def review_tests(
    story: str,
    context: str = "",
    criteria=None,
    test_cases: TestCaseList | None = None,
) -> TestReview:
    """Read a suite the way the Test cases page reads it. No AI, no key.

    The context counts as a criterion: "orders of at least $50" is a limit
    whether somebody wrote it as AC-6 or as a line about the feature.
    """
    story = str(story or "")
    context = str(context or "")
    numbered = as_criteria(criteria)
    suite = test_cases or TestCaseList(
        test_cases=[],
        summary=_empty_summary(),
    )

    review = review_test_cases(story, numbered, suite, context)
    merged = merged_suite(suite, review)
    depth = compute_depth(merged, numbered)
    given_depth = compute_depth(suite, numbered)
    return TestReview(
        suite=merged,
        criteria=numbered,
        review=review,
        coverage=compute_coverage(merged, numbered),
        counts=compute_counts(merged),
        depth=depth,
        depth_line=summary_line(depth),
        added=list(review.added),
        given_coverage=compute_coverage(suite, numbered),
        given_depth=given_depth,
        given_depth_line=summary_line(given_depth),
    )


def _empty_summary():
    """A summary for a suite with no cases in it. Nothing reads these numbers."""
    from qagenius.models import TestSuiteSummary

    return TestSuiteSummary(
        total_generated=0,
        category_breakdown=[],
        priority_breakdown=[],
        automation_coverage_potential="",
        coverage_gaps=[],
        recommendations=[],
    )
