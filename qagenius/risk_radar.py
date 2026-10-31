"""Score the AI's failure modes.

The AI proposes failure modes and three 1-5 scores. Everything a reader then
acts on -- the RPN, the level, the heat map, the counts and whether a test
really covers a risk -- is computed here, never read back from the model.
"""

import re
from dataclasses import dataclass

from qagenius.models import RISK_CATEGORIES, FailureMode, RiskAnalysis, TestCase
from qagenius.shadow_qa.detect import mentions
from qagenius.test_case_diff import STOPWORDS
from qagenius.test_cases import Criterion

HIGH_RPN, MEDIUM_RPN = 40, 18
# More than this and the page stops being a list a team can work through.
MAX_RISKS = 15
# Below this the AI's coverage claim is treated as a guess, not a match. A real
# run called R3 "Focus trap inside expanded mobile overlay" covered by a test
# that only shared the words "focus" and "keyboard", so the floor went up.
MATCH_FLOOR = 0.12
# Enough shared words to judge the claim by, not a word cloud.
MAX_MATCHED_WORDS = 6
# What a risk is about is what goes wrong, not what the screen is called.
# Two texts sharing "link", "page" and "bar" share furniture; two sharing
# "refused", "lost" or "locked" share a behaviour. A real run matched
# "permissions only hidden in the UI" to a test about opening a page, and
# missed the one that asks for the URL directly and expects a refusal.
ACTION_WORDS = frozenset(
    """
    lost lose loses losing missing gone disappears disappear
    refused refuse refuses rejected reject rejects denied deny declined
    blocked block blocks forbidden unauthorized unauthorised
    locked lock locks lockout
    overwrite overwritten overwrites overwriting
    leak leaks leaked exposed exposes disclosed
    crash crashes crashed hangs frozen stuck broken breaks
    bypass bypassed bypasses skipped ignored
    twice duplicate duplicated double
    expired expires expire stale timeout timed
    deleted delete deletes removed
    corrupt corrupted truncated mismatch
    reset revoked revoke charged refunded
    fails fail failed failure wrong incorrect
    trap trapped traps
    """.split()
)


def _stem(word: str) -> str:
    """"trapped" and "trap" are the same behaviour, so they match."""
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            base = word[: -len(suffix)]
            # "trapped" -> "trapp" -> "trap".
            if len(base) > 3 and base[-1] == base[-2] and base[-1] not in "aeiou":
                base = base[:-1]
            return base
    return word


_ACTION_STEMS = frozenset(_stem(word) for word in ACTION_WORDS)
# A test case carries "risk:R1" once someone has written it for that risk.
RISK_TAG = "risk:"
# Risks the rule packs added know the words that mean a test reaches them.
PRINCIPAL_SOURCE = "principal-qa"

_WORDS = re.compile(r"[^a-z0-9]+")
_ID_NUMBER = re.compile(r"(\d+)")


@dataclass(frozen=True)
class ScoredRisk:
    risk: FailureMode
    rpn: int
    level: str  # "high" | "medium" | "low"
    coverage: str  # "verified" | "covered" | "weak" | "none"
    # (tc id, tc title, 0-1 match, the words the two texts share)
    covered_tests: list[tuple[str, str, float, list[str]]]


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


def match_score(risk: FailureMode, case: TestCase) -> tuple[float, list[str]]:
    """How much of the two texts is the same words, and which words those are.

    The words are the evidence. "matched on: focus, keyboard" lets a reader see
    in one glance that the two texts share vocabulary and not behaviour, which
    is the whole difference between a covered risk and a guess.
    """
    left = _tokens(" ".join([risk.title, risk.cause, risk.effect]))
    right = _tokens(
        " ".join([case.title, case.expected_result, " ".join(case.steps or [])])
    )
    if not left or not right:
        return 0.0, []
    shared = left & right
    return len(shared) / len(left | right), sorted(shared)[:MAX_MATCHED_WORDS]


def risk_tags(case: TestCase) -> set[str]:
    """The risks a case was written for, by id, upper case.

    A case carries this tag because code put it there when the case was
    written from a risk's own button -- never because the words matched.
    """
    found = set()
    for tag in case.tags or []:
        text = str(tag or "").strip()
        if text.lower().startswith(RISK_TAG):
            found.add(text[len(RISK_TAG) :].strip().upper())
    return {one for one in found if one}


def _tagged_for(risk_id: str, cases: list[TestCase]) -> list[TestCase]:
    wanted = str(risk_id or "").strip().upper()
    return [case for case in cases if wanted and wanted in risk_tags(case)]


def _spoken_for(risk_id: str, case: TestCase) -> bool:
    """True when this case was written for a different risk.

    "Write a test" on R6 added TC-014 and the page then showed it under R1,
    because R1's words happened to overlap. A test that says which risk it
    is for is never handed to another one on a word match.
    """
    tags = risk_tags(case)
    return bool(tags) and str(risk_id or "").strip().upper() not in tags


def _case_words(case: TestCase) -> str:
    """Everything of a case a risk's own words could turn up in."""
    return " ".join(
        [
            str(case.title or ""),
            " ".join(case.steps or []),
            str(case.expected_result or ""),
            str(case.test_data or ""),
        ]
    )


def _by_words(risk: FailureMode, cases: list[TestCase]) -> list[TestCase]:
    """Cases a risk names its own words in.

    The AI guesses which test covers which risk and is checked on shared
    words. A risk from the rule packs does not guess: it was written with the
    words that mean the test exists, so finding one of them is the match.

    An AI risk carries those words only when it turned out to be the same
    risk as one of the packs' and the reviewer lent them to it, so a risk
    that swallowed a pack risk can still be matched to the test that covers
    them both.
    """
    if not risk.covered_if:
        return []
    found = []
    for case in cases:
        if _spoken_for(risk.id, case):
            continue
        text = _case_words(case)
        if any(mentions(text, word) for word in risk.covered_if):
            found.append(case)
    return found


def _claimed(risk: FailureMode, cases: list[TestCase]) -> list[TestCase]:
    """The cases the AI named, in the order it named them. Unknown ids drop out."""
    by_id = {
        str(case.id or "").strip().lower(): case
        for case in cases
        if not _spoken_for(risk.id, case)
    }
    found, seen = [], set()
    for claim in risk.covered_by or []:
        key = str(claim or "").strip().lower()
        if key in by_id and key not in seen:
            seen.add(key)
            found.append(by_id[key])
    return found


def action_overlap(risk: FailureMode, case: TestCase) -> list[str]:
    """Words for the thing going wrong that the risk and the case both use.

    Read from the risk's cause and effect, because that is where a risk
    says what happens; the title is often only the name of a screen.
    """
    said = " ".join([risk.cause, risk.effect, risk.title])
    wanted = {_stem(word) for word in _tokens(said)} & _ACTION_STEMS
    return sorted(wanted & {_stem(word) for word in _tokens(_case_words(case))})


def _coverage(
    risk: FailureMode, cases: list[TestCase]
) -> tuple[str, list[tuple[str, str, float, list[str]]]]:
    tagged = _tagged_for(risk.id, cases)
    tagged_ids = {str(case.id or "").strip().lower() for case in tagged}
    # A tagged case was written for this risk, so there is nothing to evidence.
    rows = [(case.id, case.title, 1.0, []) for case in tagged]
    named = [
        (case.id, case.title, 1.0, [])
        for case in _by_words(risk, cases)
        if str(case.id or "").strip().lower() not in tagged_ids
    ]
    named_ids = {str(case_id or "").strip().lower() for case_id, _, _, _ in named}
    rows.extend(named)
    claimed = [
        case
        for case in _claimed(risk, cases)
        if str(case.id or "").strip().lower() not in tagged_ids | named_ids
    ]
    # Shared words alone are not evidence. A claim counts when the case also
    # says what the risk says goes wrong, and the case that says most of it
    # leads the list, because the first row is the one the page shows.
    judged = [
        (case, *match_score(risk, case), action_overlap(risk, case))
        for case in claimed
    ]
    judged.sort(key=lambda one: (len(one[3]), one[1]), reverse=True)
    scored = [(case.id, case.title, score, words) for case, score, words, _ in judged]
    rows.extend(scored)
    if tagged:
        return "verified", rows
    if named:
        return "covered", rows
    if not judged:
        return "none", rows
    if any(score >= MATCH_FLOOR and actions for _, score, _, actions in judged):
        return "covered", rows
    # The AI claimed a test that talks about something else -- or about the
    # same furniture, without ever doing the thing that goes wrong.
    return "weak", rows


# A risk is only really tested when a test reaches it. "none" is nothing at
# all; "weak" is the AI naming a test whose words are about something else.
# Both leave the risk untested, and every desk counts them the same way.
LOOSE_COVERAGE = ("none", "weak")


def loose_risks(risks: list[ScoredRisk], level: str) -> list[ScoredRisk]:
    """Risks at this level that no test really reaches.

    Risk radar's "untested high" count and Ship check's high bucket are the
    same question, so they are the same function: a run showed 1 on one desk
    and 2 on the other, from the same analysis.
    """
    return [
        one for one in risks if one.level == level and one.coverage in LOOSE_COVERAGE
    ]


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
        "untested_high": len(loose_risks(scored, "high")),
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


def risk_key(risk: FailureMode) -> str:
    """What stays the same about a risk when the list is renumbered.

    Risk ids are positions: R6 becomes R5 the moment a risk above it is
    dropped. The title is the risk, so it is what a tag is followed by.
    """
    return _flat(str(risk.title or "")).lower()


def renumbered(before: RiskAnalysis, after: RiskAnalysis) -> dict[str, str]:
    """Old risk id -> new risk id, matched on what the risk is about."""
    was = {risk_key(risk): str(risk.id or "") for risk in before.failure_modes}
    moved = {}
    for risk in after.failure_modes:
        old = was.get(risk_key(risk), "")
        new = str(risk.id or "")
        if old and new and old != new:
            moved[old.upper()] = new.upper()
    return moved


def retag(cases: list[TestCase], moved: dict[str, str]) -> list[TestCase]:
    """Point every risk:Rn tag at the risk it was written for, after a renumber."""
    if not moved:
        return list(cases)
    out = []
    for case in cases:
        tags = list(case.tags or [])
        changed = False
        for at, tag in enumerate(tags):
            text = str(tag or "").strip()
            if not text.lower().startswith(RISK_TAG):
                continue
            old = text[len(RISK_TAG) :].strip().upper()
            if old in moved:
                tags[at] = RISK_TAG + moved[old]
                changed = True
        out.append(case.model_copy(update={"tags": tags}) if changed else case)
    return out


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
