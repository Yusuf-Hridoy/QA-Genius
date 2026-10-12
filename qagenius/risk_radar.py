"""Score the AI's failure modes.

The AI proposes failure modes and three 1-5 scores. Everything a reader then
acts on -- the RPN, the level, the heat map, the counts and whether a test
really covers a risk -- is computed here, never read back from the model.
"""

import re
from dataclasses import dataclass

from qagenius.models import RISK_CATEGORIES, FailureMode, RiskAnalysis, TestCase
from qagenius.test_case_diff import STOPWORDS
from qagenius.test_cases import Criterion

HIGH_RPN, MEDIUM_RPN = 40, 18
# More than this and the page stops being a list a team can work through.
MAX_RISKS = 15
# Below this the AI's coverage claim is treated as a guess, not a match.
MATCH_FLOOR = 0.08
# A test case carries "risk:R1" once someone has written it for that risk.
RISK_TAG = "risk:"

_WORDS = re.compile(r"[^a-z0-9]+")
_ID_NUMBER = re.compile(r"(\d+)")


@dataclass(frozen=True)
class ScoredRisk:
    risk: FailureMode
    rpn: int
    level: str  # "high" | "medium" | "low"
    coverage: str  # "verified" | "covered" | "weak" | "none"
    covered_tests: list[tuple[str, str, float]]  # (tc id, tc title, 0-1 match)


@dataclass(frozen=True)
class RiskReport:
    risks: list[ScoredRisk]
    heatmap: dict[tuple[int, int], list[str]]
    counts: dict[str, int]
    by_category: dict[str, int]


def risk_level(severity: int, likelihood: int, detectability: int) -> str:
    """A severe failure that is likely stays high however easy it is to spot."""
    rpn = severity * likelihood * detectability
    if rpn >= HIGH_RPN or (severity == 5 and likelihood >= 3):
        return "high"
    if rpn >= MEDIUM_RPN:
        return "medium"
    return "low"


def _tokens(text: str) -> set[str]:
    parts = _WORDS.split(str(text or "").lower())
    return {part for part in parts if len(part) >= 3 and part not in STOPWORDS}


def match_score(risk: FailureMode, case: TestCase) -> float:
    """How much of the two texts is the same words: 0 is nothing, 1 is all."""
    left = _tokens(" ".join([risk.title, risk.cause, risk.effect]))
    right = _tokens(
        " ".join([case.title, case.expected_result, " ".join(case.steps or [])])
    )
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _tagged_for(risk_id: str, cases: list[TestCase]) -> list[TestCase]:
    wanted = (RISK_TAG + str(risk_id or "")).strip().lower()
    return [
        case
        for case in cases
        if any(str(tag or "").strip().lower() == wanted for tag in case.tags or [])
    ]


def _claimed(risk: FailureMode, cases: list[TestCase]) -> list[TestCase]:
    """The cases the AI named, in the order it named them. Unknown ids drop out."""
    by_id = {str(case.id or "").strip().lower(): case for case in cases}
    found, seen = [], set()
    for claim in risk.covered_by or []:
        key = str(claim or "").strip().lower()
        if key in by_id and key not in seen:
            seen.add(key)
            found.append(by_id[key])
    return found


def _coverage(
    risk: FailureMode, cases: list[TestCase]
) -> tuple[str, list[tuple[str, str, float]]]:
    tagged = _tagged_for(risk.id, cases)
    tagged_ids = {str(case.id or "").strip().lower() for case in tagged}
    rows = [(case.id, case.title, 1.0) for case in tagged]
    scored = [
        (case.id, case.title, match_score(risk, case))
        for case in _claimed(risk, cases)
        if str(case.id or "").strip().lower() not in tagged_ids
    ]
    rows.extend(scored)
    if tagged:
        return "verified", rows
    if not scored:
        return "none", rows
    if any(score >= MATCH_FLOOR for _, _, score in scored):
        return "covered", rows
    # The AI claimed a test that talks about something else.
    return "weak", rows


def _id_key(risk_id: str) -> tuple[int, str]:
    numbers = _ID_NUMBER.findall(str(risk_id or ""))
    return (int(numbers[0]) if numbers else 0, str(risk_id or ""))


def score_risks(analysis: RiskAnalysis, cases: list[TestCase]) -> RiskReport:
    """Every number on the risk page comes from here."""
    cases = list(cases or [])
    scored = []
    for risk in analysis.failure_modes:
        rpn = risk.severity * risk.likelihood * risk.detectability
        coverage, covered_tests = _coverage(risk, cases)
        scored.append(
            ScoredRisk(
                risk=risk,
                rpn=rpn,
                level=risk_level(risk.severity, risk.likelihood, risk.detectability),
                coverage=coverage,
                covered_tests=covered_tests,
            )
        )
    scored.sort(key=lambda s: (-s.rpn, -s.risk.severity, _id_key(s.risk.id)))

    heatmap: dict[tuple[int, int], list[str]] = {
        (severity, likelihood): []
        for severity in range(1, 6)
        for likelihood in range(1, 6)
    }
    for item in scored:
        heatmap[(item.risk.severity, item.risk.likelihood)].append(item.risk.id)

    counts = {
        "total": len(scored),
        "high": sum(1 for item in scored if item.level == "high"),
        "medium": sum(1 for item in scored if item.level == "medium"),
        "low": sum(1 for item in scored if item.level == "low"),
        "untested_high": sum(
            1
            for item in scored
            if item.level == "high" and item.coverage in ("none", "weak")
        ),
    }
    by_category = {
        name: sum(1 for item in scored if item.risk.category == name)
        for name in RISK_CATEGORIES
    }
    return RiskReport(
        risks=scored,
        heatmap=heatmap,
        counts=counts,
        by_category={name: n for name, n in by_category.items() if n},
    )


# ──────────────────────────────────────────────────────────────────────────────
# What goes to the AI, and what comes back
# ──────────────────────────────────────────────────────────────────────────────


def _flat(text: str) -> str:
    """One line: a criterion written as a Gherkin block keeps its parts."""
    return " / ".join(part.strip() for part in str(text or "").splitlines() if part.strip())


def criteria_lines(criteria: list[Criterion]) -> str:
    """The acceptance criteria as "AC-1: text", one per line."""
    return "\n".join(f"{item.id}: {_flat(item.text)}" for item in criteria)


def case_lines(cases: list[TestCase]) -> str:
    """The existing test cases as "TC-001 | Functional | title", one per line."""
    if not cases:
        return "(none yet)"
    return "\n".join(
        " | ".join([str(case.id or ""), str(case.category or ""), _flat(case.title)])
        for case in cases
    )


def _known(wanted: list[str], known: set[str]) -> tuple[list[str], int]:
    """Keep the ids that exist, in the AI's order, written the way we write them."""
    canonical = {str(one or "").strip().lower(): one for one in known}
    kept, dropped, seen = [], 0, set()
    for claim in wanted or []:
        key = str(claim or "").strip().lower()
        if key not in canonical:
            dropped += 1
            continue
        if key in seen:
            continue
        seen.add(key)
        kept.append(canonical[key])
    return kept, dropped


def clean_analysis(
    analysis: RiskAnalysis, criteria_ids: set[str], case_ids: set[str]
) -> tuple[RiskAnalysis, list[str]]:
    """Cap, renumber and strip every id the AI invented. Never mutates the input."""
    notes: list[str] = []
    modes = list(analysis.failure_modes)
    if len(modes) > MAX_RISKS:
        notes.append(f"Kept the first {MAX_RISKS} failure modes.")
        modes = modes[:MAX_RISKS]

    kept: list[FailureMode] = []
    untitled, repeated, lost_criteria, lost_cases = 0, 0, 0, 0
    titles: set[str] = set()
    for risk in modes:
        title = str(risk.title or "").strip()
        if not title:
            untitled += 1
            continue
        if title.lower() in titles:
            repeated += 1
            continue
        titles.add(title.lower())
        criteria, missed_criteria = _known(risk.related_criteria, criteria_ids)
        cases, missed_cases = _known(risk.covered_by, case_ids)
        lost_criteria += missed_criteria
        lost_cases += missed_cases
        kept.append(
            risk.model_copy(
                update={
                    "id": f"R{len(kept) + 1}",
                    "title": title,
                    "related_criteria": criteria,
                    "covered_by": cases,
                }
            )
        )

    if untitled:
        notes.append(f"Dropped {untitled} failure modes without a title.")
    if repeated:
        notes.append(f"Removed {repeated} repeated failure modes.")
    if lost_criteria:
        notes.append(
            f"Removed {lost_criteria} unknown acceptance criteria ids "
            "from the AI's list."
        )
    if lost_cases:
        notes.append(
            f"Removed {lost_cases} unknown test case ids from the AI's coverage claims."
        )
    return RiskAnalysis(failure_modes=kept), notes
