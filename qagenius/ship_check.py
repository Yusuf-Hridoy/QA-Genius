"""Release verdict computed from the other tools' results. No AI.

Nothing here asks a model anything. Every status is worked out from the same
functions the tool pages already use -- compute_coverage, compute_depth,
score_risks, check_project -- so Ship check can never disagree with the page
a reader just came from.
"""

from dataclasses import dataclass, field, replace

from qagenius.automation_checks import check_project
from qagenius.models import (
    AmbiguityAnalysis,
    AutomationScript,
    DuelSummary,
    RiskAnalysis,
    TestCase,
    TestCaseList,
)
from qagenius.risk_radar import score_risks
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
    "clarity": "Story clarity",
    "duel": "Ambiguity duel",
    "coverage": "Criteria coverage",
    "depth": "Test depth",
    "risks": "Risk coverage",
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
    "duel": "Ambiguity duel",
    "coverage": "Test cases",
    "depth": "Test cases",
    "risks": "Risk radar",
    "automation": "Automation",
    "matrix": "Test matrix",
}

VERDICT_LABELS = {
    "ship": "Ship",
    "ship_with_risks": "Ship with risks",
    "dont_ship": "Don't ship",
}

# A row of details is a glance, not a report. Everything past this is a count.
MAX_DETAILS = 8
# A written reason short enough to be a shrug is not a risk acceptance.
MIN_REASON, MAX_REASON = 10, 300

CLARITY_PASS, CLARITY_WARN = 70, 50
AGREEMENT_PASS, AGREEMENT_WARN = 70, 40


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


@dataclass(frozen=True)
class ShipReport:
    verdict: str                # "ship" | "ship_with_risks" | "dont_ship"
    verdict_reason: str         # one sentence
    items: list[ShipCheckItem]  # in CHECK_IDS order
    counts: dict[str, int]      # pass, warn, fail, accepted, not_checked
    checked: int                # number of checks with data


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
    acceptances: dict[str, str] = field(default_factory=dict)
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
    summary = f"Clarity {clarity}"
    if vague:
        summary += f", {_plural(len(vague), 'vague phrase')}"
    details = [f"{phrase.phrase} — {phrase.severity}" for phrase in vague]
    missing = analysis.missing_elements

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
            summary = f"Clarity {clarity} — vague story, but {pinned}"
        missing = [
            item for item in missing if "acceptance criteria" not in str(item).lower()
        ]

    details += [f"Missing: {item}" for item in missing]
    return _item("clarity", status, summary, details)


def _duel(inputs: ShipInputs) -> ShipCheckItem:
    duel = inputs.duel
    if duel is None:
        return _not_checked("duel")
    agreement = duel.agreement_pct
    high = [fork for fork in duel.forks if fork.severity == "high"]
    medium = [fork for fork in duel.forks if fork.severity == "medium"]
    if high or agreement < AGREEMENT_WARN:
        status = "fail"
    elif medium or agreement < AGREEMENT_PASS:
        status = "warn"
    else:
        status = "pass"

    summary = f"Agreement {agreement}%"
    if duel.forks:
        summary += f", {_plural(len(duel.forks), 'fork')}"
        counted = []
        if high:
            counted.append(f"{len(high)} high")
        if medium:
            counted.append(f"{len(medium)} medium")
        if counted:
            summary += " (" + ", ".join(counted) + ")"
    else:
        summary += ", no forks"
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
    if not thin:
        return _item(
            "depth",
            "pass",
            f"All {_criteria_count(total)} have a negative and a boundary case",
            [],
        )
    # "More than half" is the point where the suite stops being a safety net.
    status = "fail" if len(thin) * 2 > total else "warn"
    summary = f"{len(thin)} of {total} criteria thin ({_listed(thin)})"
    details = [
        f"{row.id} — {', '.join(row.reasons)}" for row in depth.rows if row.thin
    ]
    return _item("depth", status, summary, details)


def _risks(inputs: ShipInputs) -> ShipCheckItem:
    analysis = inputs.risk_analysis
    if analysis is None:
        return _not_checked("risks")
    cases = list(inputs.test_cases.test_cases) if inputs.test_cases else []
    if not cases:
        cases = list(inputs.risk_cases)
    report = score_risks(analysis, cases)

    def pick(level: str, coverage: str) -> list:
        return [
            one for one in report.risks if one.level == level and one.coverage == coverage
        ]

    high_none, high_weak = pick("high", "none"), pick("high", "weak")
    medium_none, medium_weak = pick("medium", "none"), pick("medium", "weak")
    # A real run said "1 high risk has no test" while five medium ones were
    # untested or only weakly claimed. Both halves are counted now.
    medium_loose = len(medium_none) + len(medium_weak)
    medium_part = (
        f"{_plural(medium_loose, 'medium risk')} untested or weak" if medium_loose else ""
    )

    if high_none:
        status = "fail"
        summary = f"{_plural(len(high_none), 'high risk')} ha" + (
            "s no test" if len(high_none) == 1 else "ve no test"
        )
        if medium_part:
            summary += f" · {medium_part}"
    elif medium_none or high_weak:
        status = "warn"
        parts = []
        if high_weak:
            parts.append(f"{_plural(len(high_weak), 'high risk')} only weakly covered")
        if medium_part:
            parts.append(medium_part)
        summary = " · ".join(parts)
    else:
        status = "pass"
        summary = (
            f"Every high and medium risk has a test "
            f"({_plural(report.counts['total'], 'risk')} scored)"
        )

    # Worst first, and each line says which level it belongs to: the old list
    # was five unlabelled rows under a summary that mentioned one risk.
    details = [
        f"{LEVEL_WORDS[one.level]} · {one.risk.id} {one.risk.title} — "
        + ("no test" if one.coverage == "none" else RISK_WEAK_NOTE)
        for one in high_none + high_weak + medium_none + medium_weak
    ]
    return _item("risks", status, summary, details)


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


def _accepted(item: ShipCheckItem, acceptances: dict[str, str]) -> ShipCheckItem:
    """A written reason turns a fail into an accepted risk. Nothing else."""
    if item.status != "fail":
        return item
    reason = str(acceptances.get(item.id) or "").strip()
    if not MIN_REASON <= len(reason) <= MAX_REASON:
        return item
    return ShipCheckItem(
        id=item.id,
        title=item.title,
        status="accepted",
        summary=item.summary,
        details=item.details,
        link=item.link,
        accepted_note=reason,
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
STALE_SUFFIX = " (some inputs are out of date)"


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
        return "ship_with_risks", f"Not enough evidence: {titles} not checked yet."

    attention = [item for item in items if item.status in ("warn", "accepted")]
    if attention:
        count = len(attention)
        return "ship_with_risks", (
            f"No blockers, but {count} item{'' if count == 1 else 's'} "
            f"need{'s' if count == 1 else ''} attention."
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
    items = [_accepted(built[check_id], inputs.acceptances) for check_id in CHECK_IDS]
    items = _with_stale_notes(items, inputs.stale_inputs)

    counts = {
        name: sum(1 for item in items if item.status == name)
        for name in ("pass", "warn", "fail", "accepted", "not_checked")
    }
    verdict, reason = _verdict(items)
    # A verdict computed from older material says so in its own line.
    if any(item.stale_note for item in items):
        reason += STALE_SUFFIX
    return ShipReport(
        verdict=verdict,
        verdict_reason=reason,
        items=items,
        counts=counts,
        checked=sum(1 for item in items if item.status != "not_checked"),
    )
