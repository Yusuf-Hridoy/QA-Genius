"""Risks as the Risk radar reads them: scored, levelled and checked for tests.

No AI. The scores come from whoever wrote the risks; everything else —
the risk score, the level, whether a test really reaches it, and which
classic failure modes this kind of feature is missing — is plain code.
"""

from dataclasses import dataclass, field

from qagenius.models import FailureMode, RiskAnalysis, TestCase
from qagenius.risk_radar import RiskReport, ScoredRisk, loose_risks, score_risks
from qagenius.shadow_qa.review import review_risks
from qagenius.test_cases import Criterion

# What the three scores multiply up to at worst: 5 × 5 × 5.
MAX_SCORE = 125

# The words each coverage answer is said in, for a reader who has never
# seen this tool before. The engine's own four become three, because
# "verified" and "covered" are one answer to the question being asked.
COVERAGE_WORDS = {
    "verified": "tested",
    "covered": "tested",
    "weak": "probably tested",
    "none": "no test",
}


@dataclass(frozen=True)
class RiskReview:
    """One set of risks, read every way the risk page reads them."""

    report: RiskReport
    # The classic failure modes for this kind of feature that nobody wrote.
    missing: list[FailureMode] = field(default_factory=list)
    # High risks that no test really reaches.
    untested_high: list[ScoredRisk] = field(default_factory=list)
    # Medium risks in the same position. Worth a look, never a blocker.
    untested_medium: list[ScoredRisk] = field(default_factory=list)


def coverage_word(coverage: str) -> str:
    """The plain answer to "does a test reach this?"."""
    return COVERAGE_WORDS.get(str(coverage or ""), "no test")


def review_risk_list(
    story: str,
    context: str = "",
    criteria: list[Criterion] | None = None,
    test_cases: list[TestCase] | None = None,
    risks: RiskAnalysis | None = None,
) -> RiskReview:
    """Score a set of risks and say what is missing. No AI, no key.

    The criteria are read for two things only: which classic risks this
    kind of feature has, and the words a test might reach a risk by.
    """
    analysis = risks or RiskAnalysis(failure_modes=[])
    cases = list(test_cases or [])
    texts = [one.text for one in (criteria or [])]

    # The classic risks come first: review_risks lends its own words to any
    # risk that turns out to be one of them, and scoring has to see those.
    missing = review_risks(str(story or ""), texts + [str(context or "")], analysis)
    report = score_risks(analysis, cases)
    return RiskReview(
        report=report,
        missing=missing,
        untested_high=loose_risks(report.risks, "high"),
        untested_medium=loose_risks(report.risks, "medium"),
    )
