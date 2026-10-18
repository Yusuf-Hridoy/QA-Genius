"""What the principal QA asks for before the AI call, and adds after it.

Everything here is plain Python over the rule packs: deterministic, no AI, no
key, no network, and fast enough to sit inside the request the user already
started. Nothing the AI wrote is ever modified — only added to.
"""

import re
from dataclasses import dataclass

from qagenius.automation_checks import Finding, ProjectFile
from qagenius.models import (
    AutomationScript,
    FailureMode,
    RiskAnalysis,
    TestCase,
    TestCaseList,
)
from qagenius.shadow_qa.boundaries import Boundary, case_text, find_boundaries, missing_values
from qagenius.shadow_qa.detect import PackHit, detect_hits, mentions, story_text
from qagenius.shadow_qa.packs import SEVERITY_RANK, Check, PackRisk
from qagenius.test_case_diff import STOPWORDS, title_score
from qagenius.test_case_refine import next_case_id
from qagenius.test_cases import Criterion

# A result the reader can still take in. Everything past this is a list of ideas.
MAX_ADDED = 8
MAX_CHECKLIST_LINES = 12
# Boundaries print last but are reserved room first: a list filled with ideas
# and no numbers is the list the AI was already going to write.
MAX_CHECKLIST_BOUNDARIES = 4
MAX_ADDED_BOUNDARIES = 3
MAX_QUALITY_NOTES = 6
MAX_ADDED_RISKS = 4
# Two risks this alike are the same risk said twice.
RISK_TITLE_MATCH = 0.4
# Two cases this alike are the same case written twice.
DUPLICATE_TITLE_MATCH = 0.8

PRINCIPAL_TAG = "principal-qa"
CHECK_TAG = "qa:"
PACK_TAG = "pack:"

CHECKLIST_HEAD = (
    "PRINCIPAL QA CHECKLIST — also cover each item with at least one test case "
    'and put its id in that test case\'s tags as "qa:<id>":'
)

# An expected result built only from these says nothing a tester can check.
_EMPTY_OUTCOME_WORDS = (
    "work", "works", "working", "correct", "correctly", "success",
    "successful", "successfully", "as expected", "expected", "properly",
    "proper", "fine", "ok", "okay", "good", "valid", "no issue", "no issues",
    "without issue", "without issues", "no error", "no errors", "pass", "passes",
)
_QUOTED = re.compile(r"[\"'“”‘’]")
_HAS_NUMBER = re.compile(r"\d")
_WORDS = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class Gap:
    check_id: str  # "login.email_case" or "boundary:AC-11:6 attempts"
    title: str
    severity: str
    why: str


@dataclass(frozen=True)
class CaseReview:
    added: list[TestCase]  # Principal QA cases added to the result (max 8)
    more: list[Gap]  # further gaps not added (shown as a list)
    quality: list[str]  # notes about weak AI cases
    covered: list[str]  # check ids the AI already covered


# ──────────────────────────────────────────────────────────────────────────────
# Before the AI call
# ──────────────────────────────────────────────────────────────────────────────


def _ordered_checks(active: list[PackHit]) -> list[Check]:
    """Every active pack's checks, worst first.

    Severity decides first. Then a pack the story named out loud comes before
    one found only in a criterion: "upload an avatar" in the story is the
    feature, "the file name is shown" in AC-7 is a detail of something else.
    """
    rank = {
        hit.pack.id: (0 if hit.in_story else 1, index)
        for index, hit in enumerate(active)
    }
    checks = [check for hit in active for check in hit.pack.checks]
    return sorted(
        checks,
        key=lambda check: (SEVERITY_RANK[check.severity], *rank[check.pack_id]),
    )


def checklist_block(story: str, criteria: list[Criterion]) -> tuple[str, list[str]]:
    """The lines appended to the user prompt, and the check ids they ask for."""
    text = story_text(story, criteria)
    boundaries = find_boundaries(criteria)[:MAX_CHECKLIST_BOUNDARIES]
    room = MAX_CHECKLIST_LINES - len(boundaries)
    lines: list[str] = []
    ids: list[str] = []
    for check in _ordered_checks(detect_hits(text, story)):
        if len(lines) >= room:
            break
        lines.append(f"- [{check.id}] {check.title}")
        ids.append(check.id)
    for boundary in boundaries:
        tag = f"boundary:{boundary.source}"
        lines.append(f"- [{tag}] {boundary.label}")
        ids.append(tag)
    if not lines:
        return "", []
    return "\n\n\n" + CHECKLIST_HEAD + "\n" + "\n".join(lines), ids


# ──────────────────────────────────────────────────────────────────────────────
# After the AI call: the test cases
# ──────────────────────────────────────────────────────────────────────────────


def _tags(case: TestCase) -> set[str]:
    return {str(tag or "").strip().lower() for tag in case.tags or []}


def _tagged(case_id: str, cases: list[TestCase]) -> bool:
    wanted = (CHECK_TAG + case_id).strip().lower()
    return any(wanted in _tags(case) for case in cases)


def _check_covered(check: Check, cases: list[TestCase], texts: list[str]) -> bool:
    if _tagged(check.id, cases):
        return True
    return any(mentions(text, word) for text in texts for word in check.covered_if)


def _tokens(text: str) -> set[str]:
    parts = _WORDS.split(str(text or "").lower())
    return {part for part in parts if len(part) >= 3 and part not in STOPWORDS}


def _jaccard(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _traceability(
    subject: str, pack_id: str, criteria: list[Criterion], hits: list[PackHit]
) -> str:
    """The criterion this case belongs to: most shared words, else the pack's own."""
    if not criteria:
        return ""
    best = max(criteria, key=lambda item: _jaccard(subject, item.text))
    if _jaccard(subject, best.text) > 0:
        return best.id
    for hit in hits:
        if hit.pack.id != pack_id:
            continue
        for criterion in criteria:
            if any(mentions(criterion.text, word) for word in hit.triggers):
                return criterion.id
    return criteria[0].id


def _case_from_check(
    check: Check, case_id: str, criteria: list[Criterion], hits: list[PackHit]
) -> TestCase:
    template = check.test
    return TestCase(
        id=case_id,
        title=template.title,
        category=template.category,
        pre_conditions=template.pre_conditions,
        steps=list(template.steps),
        expected_result=template.expected_result,
        priority=template.priority,
        test_data=template.test_data,
        bdd_scenario=None,
        automation_feasibility="Medium",
        automation_effort="Medium",
        tags=[PRINCIPAL_TAG, CHECK_TAG + check.id, PACK_TAG + check.pack_id],
        traceability=_traceability(
            f"{check.title} {check.test.title}", check.pack_id, criteria, hits
        ),
    )


def _case_from_boundary(boundary: Boundary, case_id: str, missing: list[str]) -> TestCase:
    listed = ", ".join(missing)
    return TestCase(
        id=case_id,
        title=f"Boundary values at {boundary.label} ({boundary.source})",
        category="Boundary",
        pre_conditions=(
            f"The system is set up with the limit {boundary.source} states: "
            f"{boundary.phrase}"
        ),
        steps=[
            f"Exercise the behaviour at {boundary.values[0]}",
            f"Exercise it again at exactly {boundary.values[1]}",
            f"Exercise it once more at {boundary.values[2]}",
        ],
        expected_result=(
            f"The limit takes effect at exactly {boundary.values[1]} and not before it; "
            f"{boundary.values[0]} behaves as under the limit and {boundary.values[2]} "
            f"as over it."
        ),
        priority="High",
        test_data=f"Values to use: {listed}",
        bdd_scenario=None,
        automation_feasibility="High",
        automation_effort="Low",
        tags=[PRINCIPAL_TAG, CHECK_TAG + f"boundary:{boundary.source}", "pack:boundary"],
        traceability=boundary.source,
    )


def _has_checkable_outcome(expected: str) -> bool:
    """Does the expected result name anything a tester could look at?"""
    text = str(expected or "").strip()
    if not text:
        return False
    if _QUOTED.search(text) or _HAS_NUMBER.search(text):
        return True
    words = [word for word in _WORDS.split(text.lower()) if word]
    meaningful = [
        word
        for word in words
        if word not in STOPWORDS and word not in _EMPTY_OUTCOME_WORDS
    ]
    # "The feature works correctly" leaves nothing but the subject behind.
    return len(meaningful) >= 3


def _looks_like_input(case: TestCase) -> bool:
    """Does this case type, paste, upload or choose anything?"""
    verbs = ("enter", "type", "paste", "fill", "upload", "select", "choose", "submit", "search")
    text = " ".join(case.steps or []).lower()
    return any(verb in text for verb in verbs)


def _quality_notes(cases: list[TestCase]) -> list[str]:
    notes: list[str] = []
    for index, case in enumerate(cases):
        if len(notes) >= MAX_QUALITY_NOTES:
            break
        if not _has_checkable_outcome(case.expected_result):
            notes.append(f"{case.id}: expected result has no checkable outcome")
            continue
        if len(case.steps or []) < 2:
            notes.append(f"{case.id}: fewer than 2 steps")
            continue
        if not str(case.test_data or "").strip() and _looks_like_input(case):
            notes.append(f"{case.id}: the steps enter data but no test data is given")
            continue
        twin = next(
            (
                other
                for other in cases[:index]
                if title_score(case.title, other.title) >= DUPLICATE_TITLE_MATCH
            ),
            None,
        )
        if twin is not None:
            notes.append(f"{case.id}: near-duplicate of {twin.id}")
    return notes[:MAX_QUALITY_NOTES]


def review_test_cases(
    story: str, criteria: list[Criterion], result: TestCaseList
) -> CaseReview:
    """What a principal QA would add to the AI's suite, and what is weak in it."""
    text = story_text(story, criteria)
    hits = detect_hits(text, story)
    cases = list(result.test_cases)
    texts = [case_text(case) for case in cases]

    covered: list[str] = []
    gaps: list[tuple[Gap, Check]] = []
    for check in _ordered_checks(hits):
        if _check_covered(check, cases, texts):
            covered.append(check.id)
            continue
        gaps.append(
            (Gap(check.id, check.title, check.severity, check.why), check)
        )

    boundary_gaps: list[tuple[Gap, Boundary, list[str]]] = []
    for boundary in find_boundaries(criteria):
        missing = missing_values(boundary, cases)
        if not missing:
            covered.append(f"boundary:{boundary.source}")
            continue
        boundary_gaps.append(
            (
                Gap(
                    boundary.id,
                    f"{boundary.label} for {boundary.phrase} ({boundary.source})",
                    "high",
                    "The limit is where this breaks, and no case uses "
                    + ", ".join(missing)
                    + ".",
                ),
                boundary,
                missing,
            )
        )

    added: list[TestCase] = []
    more: list[Gap] = []
    taken = [case.id for case in cases]
    reserved = min(len(boundary_gaps), MAX_ADDED_BOUNDARIES)
    for gap, check in gaps:
        if len(added) >= MAX_ADDED - reserved:
            more.append(gap)
            continue
        case_id = next_case_id(taken)
        taken.append(case_id)
        added.append(_case_from_check(check, case_id, criteria, hits))
    for gap, boundary, missing in boundary_gaps:
        if len(added) >= MAX_ADDED:
            more.append(gap)
            continue
        case_id = next_case_id(taken)
        taken.append(case_id)
        added.append(_case_from_boundary(boundary, case_id, missing))

    return CaseReview(
        added=added,
        more=more,
        quality=_quality_notes(cases),
        covered=covered,
    )


def is_principal(case: TestCase) -> bool:
    return PRINCIPAL_TAG in _tags(case)


def reason_for(case: TestCase) -> str:
    """The why line shown under a Principal QA case."""
    from qagenius.shadow_qa.packs import check_by_id

    for tag in case.tags or []:
        name = str(tag or "").strip()
        if not name.lower().startswith(CHECK_TAG):
            continue
        check = check_by_id(name[len(CHECK_TAG):])
        if check is not None:
            return check.why
    if case.category == "Boundary":
        return (
            "The limit is where this breaks, and no case from the AI used the "
            "values either side of it."
        )
    return ""


# ──────────────────────────────────────────────────────────────────────────────
# After the AI call: the automation project
# ──────────────────────────────────────────────────────────────────────────────

CODING_RULES = (
    "\n\nPRINCIPAL QA CODING RULES (follow all of them):\n"
    "- No fixed waits: wait for an element, a response or a state.\n"
    "- Every test ends in at least one expect/assert.\n"
    "- Prefer role, label or test-id selectors over CSS or XPath chains.\n"
    "- Read every password, token or key from an environment variable.\n"
    "- Never leave .only or fit( in the code."
)

# `test.only(` and `test.fixme(` are still tests; `test.describe(` and the
# hooks are not, and counting them would ask a before-block to assert.
_NOT_A_TEST = (
    "describe|beforeEach|afterEach|beforeAll|afterAll|step|use|extend|slow|setTimeout|info|expect"
)
_JS_TEST = re.compile(r"(?<![\w.$])(?:test|it)(?:\.(?!" + _NOT_A_TEST + r")\w+)*\s*\(")
_PY_TEST = re.compile(r"^\s*(?:async\s+)?def\s+(test_\w+)", re.MULTILINE)
_ONLY = re.compile(r"(?<![\w.$])(?:test|describe|it)\.only\s*\(|(?<![\w.$])fit\s*\(")
_ASSERTION = re.compile(r"(?<![\w.$])(?:expect|assert|should|verify)\b")
_SECRET_NAME = re.compile(
    r"(?<![\w.$])([\w$]*(?:password|passwd|token|secret|apikey|api_key)[\w$]*)"
    r"\s*[:=]\s*(?:f|r|b|u)?[\"'`]([^\"'`\n]{1,200})[\"'`]",
    re.IGNORECASE,
)
_ENV_READ = re.compile(r"process\.env|os\.environ|os\.getenv|Deno\.env", re.IGNORECASE)
_BRITTLE = (
    (re.compile(r"nth-child", re.IGNORECASE), "nth-child selector — breaks when the list changes"),
    (re.compile(r":nth-of-type", re.IGNORECASE), "nth-of-type selector — breaks when the markup changes"),
    (re.compile(r"/html/body", re.IGNORECASE), "absolute XPath — breaks on any layout change"),
)
# Any quoted string could be a selector or could be a sentence, so a literal
# only counts when every part of it is selector-shaped (see _is_selector).
_SELECTOR_LITERAL = re.compile(r"[\"'`]([A-Za-z.#\[][^\"'`\n]{3,160})[\"'`]")
# > + ~ and a plain space are all combinators; four of them is three levels
# too many to survive a change to the markup.
_COMBINATOR = re.compile(r"\s*[>+~]\s*|\s+")
MIN_COMBINATORS = 4
# A part that carries one of these is unambiguously CSS, not a word.
_MARKED_PART = re.compile(r"^[A-Za-z][\w-]*(?=[.#\[:])|^[.#\[:]")
# A bare part is only CSS if it is the name of an element.
_HTML_TAGS = frozenset(
    """html body head div span p a ul ol li dl dt dd table thead tbody tfoot tr
    td th caption form input button label select option optgroup textarea
    fieldset legend h1 h2 h3 h4 h5 h6 img picture source figure figcaption
    section article nav header footer main aside svg path g rect circle iframe
    video audio canvas pre code strong em small b i u br hr details summary
    dialog template slot menu output progress meter time mark""".split()
)
_SIMPLE_PART = re.compile(
    r"^(?:[A-Za-z][\w-]*)?"  # optional element name
    r"(?:[.#][\w-]+|\[[^\]\s]*\]|::?[\w-]+(?:\([^)]*\))?)*$"
)

PRINCIPAL_PREFIX = "Principal QA: "


def _line_of(code: str, index: int) -> int:
    return code.count("\n", 0, index) + 1


def _finding(file: ProjectFile, index: int, message: str, level: str) -> Finding:
    return Finding(
        file=file.name,
        line=_line_of(file.code, index),
        message=PRINCIPAL_PREFIX + message,
        level=level,
    )


def _test_chunks(code: str) -> list[tuple[int, str]]:
    """Each test in the file as (offset of its first line, its body text)."""
    starts = [match.start() for match in _JS_TEST.finditer(code)]
    starts += [match.start() for match in _PY_TEST.finditer(code)]
    starts.sort()
    chunks = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(code)
        chunks.append((start, code[start:end]))
    return chunks


def _assertion_findings(file: ProjectFile) -> list[Finding]:
    findings = []
    for start, body in _test_chunks(file.code):
        if _ASSERTION.search(body) is None:
            findings.append(
                _finding(file, start, "this test never asserts anything", "error")
            )
    return findings


def _only_findings(file: ProjectFile) -> list[Finding]:
    return [
        _finding(
            file,
            match.start(),
            "`.only` leaves the rest of the suite unrun in CI",
            "error",
        )
        for match in _ONLY.finditer(file.code)
    ]


def _secret_findings(file: ProjectFile) -> list[Finding]:
    findings = []
    for match in _SECRET_NAME.finditer(file.code):
        if _ENV_READ.search(match.group(2)):
            continue
        findings.append(
            _finding(
                file,
                match.start(),
                f"`{match.group(1)}` is a hard-coded secret: read it from an "
                "environment variable",
                "warning",
            )
        )
    return findings


def _is_selector(parts: list[str]) -> bool:
    """Is this chain CSS, or is it an English sentence in quotes?

    Every part has to be selector-shaped, and each one has to either carry a
    class, id, attribute or pseudo marker or be the name of an HTML element.
    Five ordinary words in a row never pass.
    """
    for part in parts:
        if not _SIMPLE_PART.match(part):
            return False
        if _MARKED_PART.search(part):
            continue
        if part.lower() not in _HTML_TAGS:
            return False
    return True


def _selector_findings(file: ProjectFile) -> list[Finding]:
    findings = []
    for pattern, message in _BRITTLE:
        for match in pattern.finditer(file.code):
            findings.append(_finding(file, match.start(), message, "warning"))
    for match in _SELECTOR_LITERAL.finditer(file.code):
        selector = match.group(1).strip()
        parts = [part for part in _COMBINATOR.split(selector) if part]
        if len(parts) - 1 >= MIN_COMBINATORS and _is_selector(parts):
            findings.append(
                _finding(
                    file,
                    match.start(),
                    f"selector chain `{selector[:60]}` is {len(parts)} levels deep — "
                    "prefer a role, label or test-id",
                    "warning",
                )
            )
    return findings


def review_automation(script: AutomationScript, files: list[ProjectFile]) -> list[Finding]:
    """What a principal QA would send back on this project. Adds to the existing checks."""
    findings: list[Finding] = []
    for file in files or []:
        findings.extend(_only_findings(file))
        findings.extend(_assertion_findings(file))
        findings.extend(_secret_findings(file))
        findings.extend(_selector_findings(file))
    findings.sort(key=lambda one: (one.file, one.line, one.message))
    return findings


# ──────────────────────────────────────────────────────────────────────────────
# After the AI call: the risks
# ──────────────────────────────────────────────────────────────────────────────

PRINCIPAL_SOURCE = "principal-qa"


def pack_risks(text: str, story: str | None = None) -> list[PackRisk]:
    """Every active pack's typical failure modes, worst first.

    A pack the story named out loud wins a tie, for the same reason its
    checks do.
    """
    risks = [
        (0 if hit.in_story else 1, risk)
        for hit in detect_hits(text, story)
        for risk in hit.pack.risks
    ]
    risks.sort(key=lambda item: (-item[1].rpn, item[0]))
    return [risk for _, risk in risks]


def risk_titles(story: str, criteria: list[str], limit: int = 6) -> list[str]:
    """The titles that go into the Risk radar prompt, worst first."""
    return [risk.title for risk in pack_risks(story_text(story, criteria), story)][:limit]


def review_risks(
    story: str, criteria: list[str], analysis: RiskAnalysis
) -> list[FailureMode]:
    """The classic failure modes this analysis is missing. Never edits the AI's."""
    existing = list(analysis.failure_modes)
    added: list[FailureMode] = []
    for risk in pack_risks(story_text(story, criteria), story):
        if len(added) >= MAX_ADDED_RISKS:
            break
        twins = existing + added
        if any(title_score(risk.title, other.title) >= RISK_TITLE_MATCH for other in twins):
            continue
        added.append(
            FailureMode(
                id="",
                title=risk.title,
                category=risk.category,
                effect=risk.effect,
                cause=risk.cause,
                severity=risk.severity,
                likelihood=risk.likelihood,
                detectability=risk.detectability,
                severity_reason="Principal QA rule pack: typical for this kind of feature.",
                likelihood_reason="Principal QA rule pack: seen on most builds of this feature.",
                detectability_reason="Principal QA rule pack: rarely visible until it is reported.",
                source=PRINCIPAL_SOURCE,
            )
        )
    return added
