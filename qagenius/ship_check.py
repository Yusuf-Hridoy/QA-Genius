"""Release verdict computed from the other tools' results. No AI.

Nothing here asks a model anything. Every status is worked out from the same
functions the tool pages already use -- compute_coverage, compute_depth,
score_risks, check_project -- so Ship check can never disagree with the page
a reader just came from.
"""

from dataclasses import dataclass, field, replace
from datetime import date

from qagenius.acceptance import Acceptance, note as acceptance_note, read as read_acceptance
from qagenius.automation_checks import check_project
from qagenius.models import (
    AmbiguityAnalysis,
    AutomationScript,
    DuelSummary,
    RiskAnalysis,
    TestCase,
    TestCaseList,
)
from qagenius.risk_radar import loose_risks, score_risks
from qagenius.shadow_qa.story_rules import epic_note, review_story
from qagenius.story_text import without_criteria_lines
from qagenius.shadow_qa.review import limit_conflicts, with_context
from qagenius.test_case_depth import compute_depth
from qagenius.test_cases import Criterion, compute_coverage, number_criteria
from qagenius.test_run_metrics import Insights

CHECK_IDS = (
    "clarity",
    "duel",
    "coverage",
    "depth",
    "risks",
    "automation",
    "matrix",
)
CORE_CHECKS = ("coverage", "risks")      # Ship is impossible while these are not checked

TITLES = {
    "clarity": "How clear the story is",
    "duel": "Two-reader check",
    "coverage": "Criteria with a test",
    "depth": "How well tested",
    "risks": "Risks with a test",
    "automation": "Automation",
    "matrix": "Test matrix",
}

LINKS = {
    "clarity": "/requirements/story",
    "duel": "/requirements/story",
    "coverage": "/requirements/test-cases",
    "depth": "/requirements/test-cases",
    "risks": "/risks",
    "automation": "/requirements/automation",
    "matrix": "/requirements/matrix",
}

# The name a reader would use for the desk a check came from.
TOOLS = {
    "clarity": "Story check",
    "duel": "Two-reader check",
    "coverage": "Test cases",
    "depth": "Test cases",
    "risks": "Risk radar",
    "automation": "Automation",
    "matrix": "Test matrix",
}

VERDICT_LABELS = {
    "ship": "Ready to release",
    "ship_with_risks": "Release with known risks",
    "dont_ship": "Not ready",
}

# A row of details is a glance, not a report. Everything past this is a count.
MAX_DETAILS = 8
# A written reason short enough to be a shrug is not a risk acceptance.
MIN_REASON, MAX_REASON = 10, 300
# A review date that has gone by is not an accepted risk any more: somebody
# said they would look again by then, and nobody has.
REVIEW_PASSED = "Review date passed — look at this again."

CLARITY_PASS, CLARITY_WARN = 70, 50
AGREEMENT_PASS = 70


@dataclass(frozen=True)
class ShipCheckItem:
    id: str
    title: str
    status: str                 # "pass" | "warn" | "fail" | "not_checked" | "accepted"
    summary: str                # one line, e.g. "2 high risks have no test"
    details: list[str]          # short lines, max 8
    link: str                   # where to fix it, e.g. "/risks"
    accepted_note: str = ""
    # Set when the browser says this check's inputs lag the latest work.
    stale_note: str = ""
    # Who owns the accepted risk and when they said they would look again.
    # Both are optional; neither changes the decision on its own.
    owner: str = ""
    review_date: str = ""
    review_passed: bool = False


@dataclass(frozen=True)
class ShipReport:
    verdict: str                # "ship" | "ship_with_risks" | "dont_ship"
    verdict_reason: str         # one sentence
    items: list[ShipCheckItem]  # in CHECK_IDS order
    counts: dict[str, int]      # pass, warn, fail, accepted, not_checked
    checked: int                # number of checks with data
    # True when at least one check was computed from work that has moved on.
    # The verdict itself is this minute's; some of what it read is not.
    stale: bool = False


@dataclass(frozen=True)
class MatrixRun:
    """The matrix the Requirements desk left in the run, as Ship check reads it."""

    runs: int = 0
    valid_pairs: int = 0
    covered_pairs: int = 0
    manual_only: int = 0
    factors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ShipInputs:
    # The story itself, so the Principal QA rules can be run over it again here.
    story: str = ""
    # What the story page was told about the feature. Limits live in here as
    # often as they live in a criterion.
    context: str = ""
    story_analysis: AmbiguityAnalysis | None = None
    duel: DuelSummary | None = None
    test_cases: TestCaseList | None = None
    criteria: list[str] = field(default_factory=list)
    risk_analysis: RiskAnalysis | None = None
    # The cases the risk page was scored against. The run's own test cases win
    # when it has them; these are the fallback for a risk analysis that arrived
    # on its own.
    risk_cases: list[TestCase] = field(default_factory=list)
    automation_script: AutomationScript | None = None
    automation_selected_ids: list[str] = field(default_factory=list)
    insights: Insights | None = None
    matrix: "MatrixRun | None" = None
    # A written reason, in any of the shapes a browser may have saved.
    acceptances: dict[str, Acceptance | dict | str] = field(default_factory=dict)
    # Risks accepted on the Risk radar, by risk id. Same shapes, same
    # rule: a reason is required, an owner and a date are not.
    risk_acceptances: dict[str, Acceptance | dict | str] = field(
        default_factory=dict
    )
    # The day the report is worked out. Only a review date is read against
    # it, and tests hand it their own day.
    today: date | None = None
    # Check ids the browser believes were built from older work.
    stale_inputs: list[str] = field(default_factory=list)   # check id -> reason


LEVEL_WORDS = {"high": "High", "medium": "Medium", "low": "Low"}
# Why a claimed test does not count: the AI named it, the words do not match.
RISK_WEAK_NOTE = "AI claim doesn't match its test"


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _criteria_count(count: int) -> str:
    return "1 criterion" if count == 1 else f"{count} criteria"


def _listed(ids: list[str]) -> str:
    """The ids in brackets, trimmed so one long list cannot run off the line."""
    shown = ids[:MAX_DETAILS]
    text = ", ".join(shown)
    if len(ids) > len(shown):
        text += f", +{len(ids) - len(shown)} more"
    return text


def _trim(lines: list[str]) -> list[str]:
    if len(lines) <= MAX_DETAILS:
        return lines
    kept = lines[: MAX_DETAILS - 1]
    kept.append(f"…and {len(lines) - len(kept)} more")
    return kept


NOT_CHECKED_LINES = {
    "matrix": "No test matrix yet — build one to know which browsers and devices to run.",
}


def _not_checked(check_id: str) -> ShipCheckItem:
    return ShipCheckItem(
        id=check_id,
        title=TITLES[check_id],
        status="not_checked",
        summary=NOT_CHECKED_LINES.get(
            check_id, f"Not run yet — open {TOOLS[check_id]} to include it."
        ),
        details=[],
        link=LINKS[check_id],
    )


def _item(check_id: str, status: str, summary: str, details: list[str]) -> ShipCheckItem:
    return ShipCheckItem(
        id=check_id,
        title=TITLES[check_id],
        status=status,
        summary=summary,
        details=_trim(details),
        link=LINKS[check_id],
    )


# ──────────────────────────────────────────────────────────────────────────────
# One function per check. Each one owns its thresholds and its wording.
# ──────────────────────────────────────────────────────────────────────────────


def _clarity(inputs: ShipInputs, criteria: list[Criterion]) -> ShipCheckItem:
    analysis = inputs.story_analysis
    if analysis is None:
        return _not_checked("clarity")
    # The Story page shows clarity, not ambiguity; the two must agree.
    clarity = 100 - analysis.ambiguity_score
    if clarity >= CLARITY_PASS:
        status = "pass"
    elif clarity >= CLARITY_WARN:
        status = "warn"
    else:
        status = "fail"

    vague = analysis.vague_phrases
    summary = f"How clear: {clarity} of 100"
    if vague:
        summary += f", {_plural(len(vague), 'unclear word')}"
    details = [f"{phrase.phrase} — {phrase.severity}" for phrase in vague]
    missing = analysis.missing_elements
    # The story page hides the same lines, so the two desks agree.
    missing = without_criteria_lines(missing, bool(criteria))

    # A real run scored a story 42 and refused to ship it, while four concrete
    # criteria (200 ms, 768 px, focus rings) already pinned the behaviour down.
    # Written criteria are the stronger evidence, so they cap the damage - but
    # they never turn a vague story into a clear one, so warn is as far as the
    # score can climb.
    if criteria:
        if status == "fail":
            status = "warn"
            count = len(criteria)
            pinned = (
                "1 acceptance criterion pins it down"
                if count == 1
                else f"{count} acceptance criteria pin it down"
            )
            summary = f"How clear: {clarity} of 100 — unclear, but {pinned}"

    details += [f"Missing: {item}" for item in missing]

    # A story that is really seven features is the first thing to say about
    # its clarity, whatever the score was.
    epic = epic_note(
        review_story(inputs.story, [item.text for item in criteria], inputs.context)
    )
    if epic is not None:
        details.insert(0, f"Senior tester: {epic.title} — {epic.detail}")
        if status == "pass":
            status = "warn"
    return _item("clarity", status, summary, details)


def _duel(inputs: ShipInputs) -> ShipCheckItem:
    duel = inputs.duel
    if duel is None:
        return _not_checked("duel")
    agreement = duel.agreement_pct
    high = [fork for fork in duel.forks if fork.severity == "high"]
    medium = [fork for fork in duel.forks if fork.severity == "medium"]
    # Two AI readers reading a story differently is a flag to look at, never
    # proof the build is broken, so this check warns at worst and can never
    # hold a release on its own.
    if high or medium or agreement < AGREEMENT_PASS:
        status = "warn"
    else:
        status = "pass"

    summary = f"The two readers agree {agreement}% of the time"
    if duel.forks:
        summary += f", {_plural(len(duel.forks), 'place')} they disagree"
        counted = []
        if high:
            counted.append(f"{len(high)} bad")
        if medium:
            counted.append(f"{len(medium)} medium")
        if counted:
            summary += " (" + ", ".join(counted) + ")"
    else:
        summary += ", and nothing they read differently"
    details = [f"{fork.topic} — {fork.severity}" for fork in duel.forks]
    return _item("duel", status, summary, details)


def _criteria(inputs: ShipInputs) -> list[Criterion]:
    """The run's criteria, numbered the way every other page numbers them."""
    return number_criteria(inputs.criteria)


def _coverage(inputs: ShipInputs, criteria: list[Criterion]) -> ShipCheckItem:
    if inputs.test_cases is None or not criteria:
        return _not_checked("coverage")
    coverage = compute_coverage(inputs.test_cases, criteria)
    text_by_id = {criterion.id: criterion.text for criterion in criteria}
    if not coverage.uncovered:
        return _item(
            "coverage",
            "pass",
            f"All {_criteria_count(len(criteria))} covered "
            f"by {_plural(len(inputs.test_cases.test_cases), 'test case')}",
            [],
        )
    summary = (
        f"{len(coverage.uncovered)} of {len(criteria)} criteria have no test "
        f"({_listed(coverage.uncovered)})"
    )
    details = [
        f"{ac_id} {text_by_id[ac_id].splitlines()[0]} — no test case lists it"
        for ac_id in coverage.uncovered
    ]
    return _item("coverage", "fail", summary, details)


def _depth(inputs: ShipInputs, criteria: list[Criterion]) -> ShipCheckItem:
    if inputs.test_cases is None or not criteria:
        return _not_checked("depth")
    depth = compute_depth(inputs.test_cases, criteria)
    thin = depth.thin_ids
    total = len(depth.rows)
    # A case that expects the opposite of the limit its criterion states is
    # worth more than any count: one of the two is wrong, and the suite
    # cannot say which.
    conflicts = limit_conflicts(
        with_context(criteria, inputs.context), list(inputs.test_cases.test_cases)
    )
    if not thin:
        return _item(
            "depth",
            "warn" if conflicts else "pass",
            f"All {_criteria_count(total)} have the tests they need",
            conflicts,
        )
    # "More than half" is the point where the suite stops being a safety net.
    status = "fail" if len(thin) * 2 > total else "warn"
    # The grouped reasons are the detail lines; a summary stays glanceable.
    needs = "needs" if len(thin) == 1 else "need"
    summary = f"{len(thin)} of {total} criteria {needs} more tests ({_listed(thin)})"
    details = conflicts + [
        f"{row.id} — {', '.join(row.reasons)}" for row in depth.rows if row.thin
    ]
    return _item("depth", status, summary, details)


def accepted_risk_ids(
    acceptances: dict[str, Acceptance | dict | str],
    today: date | None = None,
) -> set[str]:
    """Risk ids someone accepted in writing, and whose review date still holds.

    A review date that has gone by takes the risk back out of this set: it
    counts as untested again until somebody looks at it.
    """
    found = set()
    for risk_id, raw in (acceptances or {}).items():
        one = read_acceptance(raw)
        if one is not None and not one.passed(today):
            found.add(str(risk_id).upper())
    return found


def _risks(inputs: ShipInputs) -> ShipCheckItem:
    analysis = inputs.risk_analysis
    if analysis is None:
        return _not_checked("risks")
    cases = list(inputs.test_cases.test_cases) if inputs.test_cases else []
    if not cases:
        cases = list(inputs.risk_cases)
    report = score_risks(analysis, cases)
    # A risk the team accepted in writing is not an untested risk any more.
    # It is still on the page, with its reason, owner and date beside it.
    accepted = accepted_risk_ids(inputs.risk_acceptances, inputs.today)

    def pick(level: str, coverage: str) -> list:
        return [
            one
            for one in report.risks
            if one.level == level
            and one.coverage == coverage
            and str(one.risk.id).upper() not in accepted
        ]

    # Risk radar's "untested high" count and this bucket are one function, so
    # a risk whose only evidence is an AI claim the words do not back is high
    # and untested on both desks. A run showed 1 here and 2 there.
    high_loose = [
        one
        for one in loose_risks(report.risks, "high")
        if str(one.risk.id).upper() not in accepted
    ]
    high_none, high_weak = pick("high", "none"), pick("high", "weak")
    medium_none, medium_weak = pick("medium", "none"), pick("medium", "weak")
    # A real run said "1 high risk has no test" while five medium ones were
    # untested or only weakly claimed. Both halves are counted now.
    medium_loose = len(medium_none) + len(medium_weak)
    medium_part = (
        f"{_plural(medium_loose, 'medium risk')} untested or weak" if medium_loose else ""
    )

    if high_loose:
        status = "fail"
        if not high_weak:
            summary = f"{_plural(len(high_none), 'high risk')} ha" + (
                "s no test" if len(high_none) == 1 else "ve no test"
            )
        else:
            summary = f"{_plural(len(high_loose), 'high risk')} untested or weak"
        if medium_part:
            summary += f" · {medium_part}"
    elif medium_none:
        status = "warn"
        summary = medium_part
    else:
        # Nothing is left untested -- but if that is only true because the
        # team signed something off, this check is "accepted", not "fine".
        # A written reason is not a test, and the grade must not read as if
        # it were.
        status = "accepted" if accepted else "pass"
        summary = (
            f"Every high and medium risk has a test "
            f"({_plural(report.counts['total'], 'risk')} scored)"
        )
        if accepted:
            summary += f" · {_plural(len(accepted), 'risk')} accepted in writing"

    # Worst first, and each line says which level it belongs to: the old list
    # was five unlabelled rows under a summary that mentioned one risk.
    details = [
        f"{LEVEL_WORDS[one.level]} · {one.risk.id} {one.risk.title} — "
        + ("no test" if one.coverage == "none" else RISK_WEAK_NOTE)
        for one in high_none + high_weak + medium_none + medium_weak
    ]
    item = _item("risks", status, summary, details)
    if status == "accepted":
        note = _accepted_risk_note(inputs.risk_acceptances, accepted)
        item = replace(item, accepted_note=note)
    return item


def _accepted_risk_note(
    acceptances: dict[str, Acceptance | dict | str], ids: set[str]
) -> str:
    """Who accepted what, in the order the risks were written down."""
    lines = []
    for risk_id, raw in (acceptances or {}).items():
        if str(risk_id).upper() not in ids:
            continue
        one = read_acceptance(raw)
        if one is None:
            continue
        lines.append(f"{risk_id}: {acceptance_note(one)}")
    return " · ".join(lines)


def _automation(inputs: ShipInputs) -> ShipCheckItem:
    script = inputs.automation_script
    if script is None:
        return _not_checked("automation")
    report = check_project(script, list(inputs.automation_selected_ids))
    errors = [finding for finding in report.findings if finding.level == "error"]
    warnings = [finding for finding in report.findings if finding.level == "warning"]
    selected = len(report.traced) + len(report.missing)

    if errors:
        status = "fail"
        summary = f"{_plural(len(errors), 'syntax error')} in the generated code"
    elif report.missing or warnings:
        status = "warn"
        parts = []
        if report.missing:
            parts.append(
                f"{len(report.missing)} of {selected} selected cases not in the code "
                f"({_listed(report.missing)})"
            )
        if warnings:
            parts.append(f"{_plural(len(warnings), 'fixed wait')}")
        summary = ", ".join(parts)
    else:
        status = "pass"
        summary = f"All {_plural(selected, 'selected case')} traced, no syntax errors"

    details = [
        f"{finding.file}:{finding.line} — {finding.message}" if finding.line
        else f"{finding.file} — {finding.message}"
        for finding in errors + warnings
    ]
    details += [f"{case_id} — not found in the test code" for case_id in report.missing]
    return _item("automation", status, summary, details)


def _accepted(
    item: ShipCheckItem,
    acceptances: dict[str, Acceptance | dict | str],
    today: date | None = None,
) -> ShipCheckItem:
    """A written reason turns a fail into an accepted risk. Nothing else.

    A review date that has gone by takes it back to "check this": the team
    agreed to look again by then, so the acceptance has run out.
    """
    if item.status != "fail":
        return item
    # Strings, dicts and Acceptance objects all arrive here: a run saved
    # before owners existed must still open.
    one = read_acceptance(acceptances.get(item.id))
    if one is None:
        return item
    passed = one.passed(today)
    return ShipCheckItem(
        id=item.id,
        title=item.title,
        status="warn" if passed else "accepted",
        summary=item.summary,
        details=item.details,
        link=item.link,
        accepted_note=acceptance_note(one, today),
        owner=one.owner,
        review_date=one.review_date,
        review_passed=passed,
    )


def _matrix(inputs: ShipInputs) -> ShipCheckItem:
    run = inputs.matrix
    if run is None or not run.runs:
        return _not_checked("matrix")

    covered = run.covered_pairs == run.valid_pairs and run.valid_pairs > 0
    runs = _plural(run.runs, "run")
    details = [
        f"{runs} cover {run.covered_pairs} of {run.valid_pairs} pairs",
    ]
    if run.factors:
        details.append("Factors: " + ", ".join(run.factors))

    # A matrix never blocks a release: it tells you where to point the effort.
    if not covered:
        return _item(
            "matrix",
            "warn",
            f"{runs} planned, {run.covered_pairs} of {run.valid_pairs} pairs covered",
            details,
        )
    if run.manual_only:
        details.append(f"{run.manual_only} cannot be driven by Playwright")
        return _item(
            "matrix",
            "warn",
            f"{runs} cover every pair; {run.manual_only} of them must be tested by hand",
            details,
        )
    return _item("matrix", "pass", f"{runs} cover every pair of values", details)


# A check whose inputs the browser says are older than the latest work. The
# status still stands; the reader is told it was computed from stale material.
STALE_NOTE = "Built from older work — update {desk} for an accurate result."
STALE_DESKS = {
    "risks": "Risk radar",
    "matrix": "Test matrix",
    "coverage": "Test cases",
    "depth": "Test cases",
    "automation": "Automation",
}
# Said in the header rather than tacked onto the reason: the verdict was
# worked out just now, and only its inputs are older.
STALE_HEADER = "Worked out just now — some inputs are older"


def _with_stale_notes(
    items: list[ShipCheckItem], stale: list[str]
) -> list[ShipCheckItem]:
    wanted = [one for one in stale if one in CHECK_IDS]
    if not wanted:
        return items
    return [
        replace(item, stale_note=STALE_NOTE.format(desk=STALE_DESKS.get(item.id, item.title)))
        if item.id in wanted
        else item
        for item in items
    ]


def _verdict(items: list[ShipCheckItem]) -> tuple[str, str]:
    failed = [item for item in items if item.status == "fail"]
    if failed:
        titles = ", ".join(item.title for item in failed)
        return "dont_ship", (
            f"{len(failed)} check{'' if len(failed) == 1 else 's'} failed: {titles}."
        )

    missing_core = [
        item for item in items if item.id in CORE_CHECKS and item.status == "not_checked"
    ]
    if missing_core:
        titles = ", ".join(item.title for item in missing_core)
        return "ship_with_risks", f"Not enough to go on: {titles} not done yet."

    attention = [item for item in items if item.status in ("warn", "accepted")]
    if attention:
        count = len(attention)
        return "ship_with_risks", (
            f"Nothing blocks the release, but {count} thing"
            f"{'' if count == 1 else 's'} still need"
            f"{'s' if count == 1 else ''} a look."
        )
    return "ship", "All checks passed."


def compute_ship_report(inputs: ShipInputs) -> ShipReport:
    """The whole verdict, in CHECK_IDS order, from code alone."""
    criteria = _criteria(inputs)
    built = {
        "clarity": _clarity(inputs, criteria),
        "duel": _duel(inputs),
        "coverage": _coverage(inputs, criteria),
        "depth": _depth(inputs, criteria),
        "risks": _risks(inputs),
        "automation": _automation(inputs),
        "matrix": _matrix(inputs),
    }
    items = [
        _accepted(built[check_id], inputs.acceptances, inputs.today)
        for check_id in CHECK_IDS
    ]
    items = _with_stale_notes(items, inputs.stale_inputs)

    counts = {
        name: sum(1 for item in items if item.status == name)
        for name in ("pass", "warn", "fail", "accepted", "not_checked")
    }
    verdict, reason = _verdict(items)
    return ShipReport(
        verdict=verdict,
        verdict_reason=reason,
        items=items,
        counts=counts,
        checked=sum(1 for item in items if item.status != "not_checked"),
        # A verdict computed from older material says so in its own line.
        stale=any(item.stale_note for item in items),
    )
