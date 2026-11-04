"""The six tools, as plain functions over the service layer.

Nothing here calls an AI, reads a key, stores anything or reaches the
network. Each one takes an input model and returns an output model, so the
same input gives byte-identical output every time it is called.
"""

from __future__ import annotations

import re

from qagenius.acceptance import Acceptance
from qagenius.automation_checks import ProjectFile
from qagenius.mcp_server import adapters, report_link
from qagenius.mcp_server.schemas import (
    MAX_SCORE,
    CheckOut,
    CodeFindingOut,
    CodeIn,
    CodeOut,
    GradeOut,
    MatrixOut,
    MatrixPlanIn,
    MatrixRuleIn,
    Problem,
    RiskOut,
    RisksIn,
    RisksOut,
    RunOut,
    ShipIn,
    ShipOut,
    StoryIn,
    TestsIn,
    ToolOut,
    problem_id,
)
from qagenius.pairwise import Factor, Rule
from qagenius.services.code_review import review_code, syntax_words
from qagenius.services.matrix_plan import plan_matrix as plan_matrix_service
from qagenius.services.release_decision import decide_release, release_grade
from qagenius.services.risk_review import coverage_word, review_risk_list
from qagenius.services.story_review import review_story_text
from qagenius.services.test_review import review_tests as review_tests_service
from qagenius.ship_check import ShipInputs
from qagenius.test_case_depth import NO_KIND, NOT_COVERED, ONLY_ONE

# The decision words an agent reads, out of the three the engine uses.
DECISION_WORDS = {
    "ship": "ready",
    "ship_with_risks": "ready with known risks",
    "dont_ship": "not ready",
}

# A risk id sent as accepted needs a written reason to count, and the agent
# did not send one. This is that reason: honest about where it came from.
ACCEPTED_REASON = "Accepted by the calling agent through the MCP door."


def finish(answer, payload, host: str, extra: dict | None = None):
    """Give an answer its report link and say what changed since last time.

    Every tool ends here, so the six of them cannot drift about what a
    report link holds or how a round is counted. What goes in the link is
    the answer plus whatever the page needs to draw it — never more.
    """
    now = [problem.id for problem in answer.problems]
    rounds = report_link.compare(getattr(payload, "previous_report_link", ""), now)
    answer.fixed_since_last_check = rounds.fixed
    answer.still_open = rounds.still_open

    packed = answer.model_dump(mode="json")
    packed.pop("report_link", None)
    packed.pop("report_note", None)
    # What each fixed problem used to say. The agent gets the ids; the page
    # a person opens gets the sentences, because "L-ff63 · Fixed" on its
    # own is a row nobody can check.
    if rounds.fixed_said:
        packed["fixed_said"] = rounds.fixed_said
    label = str(getattr(payload, "story_label", "") or "").strip()
    if label:
        packed["story_label"] = label
    packed.update(extra or {})
    link, note = report_link.link_for(host, packed)
    answer.report_link = link
    answer.report_note = note
    return answer


def _shown(payload) -> dict:
    """The inputs a report page needs to show the findings in context."""
    kept: dict = {}
    for name in ("story", "context"):
        value = getattr(payload, name, "")
        if value:
            kept[name] = value
    for name in ("criteria", "test_cases", "risks"):
        value = getattr(payload, name, None)
        if value:
            kept[name] = [one.model_dump(mode="json") for one in value]
    return kept


def _problem(
    kind: str,
    level: str,
    says: str,
    fix: str,
    criteria: list[str] | None = None,
    tests: list[str] | None = None,
) -> Problem:
    """One problem with its id already worked out."""
    criteria = list(criteria or [])
    tests = list(tests or [])
    return Problem(
        id=problem_id(kind, says, criteria, tests),
        kind=kind,
        level=level,
        says=says,
        fix=fix,
        criteria=criteria,
        tests=tests,
    )


def _worst_first(problems: list[Problem]) -> list[Problem]:
    """High, then medium, then low. Order inside a level is left alone."""
    rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(problems, key=lambda one: rank.get(one.level, 3))


def _count(number: int, word: str) -> str:
    return f"{number} {word}" if number == 1 else f"{number} {word}s"


def _criteria_count(number: int) -> str:
    return "1 criterion" if number == 1 else f"{number} criteria"


def _to_fix(problems: list[Problem]) -> str:
    highs = sum(1 for one in problems if one.level == "high")
    if not problems:
        return "nothing to fix"
    if highs:
        return f"{len(problems)} to fix ({highs} high)"
    return f"{len(problems)} to fix"


# ──────────────────────────────────────────────────────────────────────────────
# check_story
# ──────────────────────────────────────────────────────────────────────────────


def check_story(payload: StoryIn, host: str = "") -> ToolOut:
    """Read a story before anyone writes a test. Code only, no AI."""
    review = review_story_text(payload.story, payload.context, payload.story_type)

    problems: list[Problem] = []
    if review.epic is not None:
        features = list(review.epic.features)
        named = ", ".join(features) if features else ""
        says = review.epic.title + (f": {named}" if named else "")
        if review.epic.more:
            says += f", and {review.epic.more} more"
        problems.append(
            _problem(
                "epic",
                "high",
                says,
                "Split it into one story per feature, or accept that each part "
                "gets only a few tests.",
            )
        )

    for word in review.unclear:
        problems.append(
            _problem(
                "clarity",
                "medium",
                f"“{word.word}” is not something anyone can test.",
                f"Say {word.say_instead} instead.",
            )
        )

    for note in review.notes:
        problems.append(
            _problem(
                "missing" if note.level == "warn" else "clarity",
                "high" if note.level == "warn" else "low",
                note.title + ".",
                note.detail,
            )
        )

    for note in review.limit_notes:
        problems.append(_problem("limit", "high", note, "Decide the number and write it into a criterion."))

    problems = _worst_first(problems)
    unclear = len(review.unclear)
    summary = " · ".join(
        [
            _to_fix(problems),
            _count(unclear, "unclear word"),
            "reads as several stories" if review.epic else "reads as one story",
        ]
    )
    return finish(
        ToolOut(
            tool="check_story",
            summary=summary,
            problems=problems,
            add_tests=[],
            ask_the_po=_story_questions(review),
            notes=_story_notes(review),
        ),
        payload,
        host,
        _shown(payload),
    )


def _story_questions(review) -> list[str]:
    """What nobody but the product owner can answer."""
    asked: list[str] = []
    for word in review.unclear:
        asked.append(f"“{word.word}”: what is the real number or rule here?")
    for note in review.limit_notes:
        asked.append(note)
    return asked


def _story_notes(review) -> list[str]:
    notes: list[str] = []
    if review.epic is not None and review.epic.features:
        notes.append(
            "Features found in the story: " + ", ".join(review.epic.features) + "."
        )
    if not review.unclear:
        notes.append("No untestable words found.")
    return notes


# ──────────────────────────────────────────────────────────────────────────────
# review_tests
# ──────────────────────────────────────────────────────────────────────────────


def review_tests(payload: TestsIn, host: str = "") -> ToolOut:
    """The senior tester's review of a suite. Code only, no AI."""
    naming = adapters.naming_from(payload.criteria)
    criteria = naming.criteria
    suite = adapters.suite_from(payload.test_cases, naming)
    reviewed = review_tests_service(payload.story, payload.context, criteria, suite)

    problems: list[Problem] = []

    # A test that expects the opposite of the limit its criterion states is
    # the most valuable thing on this card, so it is said first.
    for line in reviewed.review.conflicts:
        problems.append(
            _problem(
                "limit",
                "high",
                line,
                "Settle the number in the criterion, then make the test agree with it.",
            )
        )

    for gap in reviewed.review.more:
        problems.append(
            _problem(
                "gap",
                gap.severity if gap.severity in ("high", "medium", "low") else "medium",
                f"{gap.title}: {gap.why}",
                "Write a test for it.",
            )
        )

    for line in reviewed.review.quality:
        problems.append(
            _problem(
                "copy" if _is_copy(line) else "weak",
                "medium",
                line,
                "Rewrite it so the expected result can only be true or false, "
                "and say the exact values it uses.",
                tests=_ids_in(line, {case.id for case in suite.test_cases}),
            )
        )

    # The depth of the suite the agent actually sent. The added tests are a
    # proposal it has not taken yet, so counting them here would report the
    # gaps as already filled.
    for row in reviewed.given_depth.rows:
        if not row.reasons:
            continue
        kind = "missing" if NOT_COVERED in row.reasons else "depth"
        level = "high" if NOT_COVERED in row.reasons else "medium"
        problems.append(
            _problem(
                kind,
                level,
                f"{row.id} has {', '.join(row.reasons)}.",
                _depth_fix(row),
                criteria=[row.id],
                tests=list(row.case_ids),
            )
        )

    problems = _worst_first(problems)
    summary = " · ".join(
        [
            _to_fix(problems),
            _criteria_count(len(criteria)),
            _count(len(payload.test_cases), "test"),
        ]
    )
    return finish(
        ToolOut(
            tool="review_tests",
            summary=summary,
            problems=problems,
            add_tests=[adapters.test_out(case) for case in reviewed.added],
            ask_the_po=list(reviewed.review.conflicts),
            notes=_test_notes(reviewed, naming),
        ),
        payload,
        host,
        _shown(payload),
    )


def _is_copy(line: str) -> bool:
    """Is this quality note about two tests being the same test?"""
    said = line.lower()
    return "same" in said or "duplicate" in said or "copy" in said


def _ids_in(line: str, known: set[str]) -> list[str]:
    """The test ids a note names, in the order it names them."""
    found: list[str] = []
    for word in str(line or "").replace(",", " ").replace(":", " ").split():
        name = word.strip("“”\"'().;")
        if name in known and name not in found:
            found.append(name)
    return found


def _depth_fix(row) -> str:
    """What to add for one thin criterion, in the words of what it is missing.

    The reasons are compared against the engine's own constants, never
    against copies of their wording: a reworded reason would otherwise stop
    matching here in silence, and every thin criterion would get the vague
    fallback instead of the thing it actually needs.
    """
    wants: list[str] = []
    if NOT_COVERED in row.reasons:
        return f"Write at least one test that covers {row.id}."
    if ONLY_ONE in row.reasons:
        wants.append("a second test")
    if row.needs_wrong_input and NO_KIND["Negative"] in row.reasons:
        wants.append("a test for wrong input")
    if row.needs_limit and NO_KIND["Boundary"] in row.reasons:
        wants.append("a test at the limit, using the exact value")
    if not wants:
        return f"Add the missing tests for {row.id}."
    return f"Add {', '.join(wants)} for {row.id}."


def _test_notes(reviewed, naming=None) -> list[str]:
    # Every number here is about the suite as it was sent, not the suite it
    # would become once add_tests were taken.
    notes = [reviewed.given_depth_line] if reviewed.given_depth_line else []
    # Said first when it applies: every id in every line below is the new
    # one, and a reader who does not know that reads the whole answer wrong.
    if naming is not None and naming.note():
        notes.insert(0, naming.note())
    covered = len(reviewed.review.covered)
    if covered:
        thing = "thing" if covered == 1 else "things"
        notes.append(
            f"Already covered: {covered} {thing} a senior tester checks for "
            "this kind of story."
        )
    notes.append(
        f"{reviewed.given_coverage.percent}% of criteria have at least one test."
    )
    if reviewed.added:
        notes.append(
            f"{_count(len(reviewed.added), 'ready test')} in add_tests — send "
            "them back in test_cases when you have added them."
        )
    return notes


# ──────────────────────────────────────────────────────────────────────────────
# ship_check
# ──────────────────────────────────────────────────────────────────────────────


def ship_check(payload: ShipIn, host: str = "") -> ShipOut:
    """The release decision. Code only, no AI."""
    naming = adapters.naming_from(payload.criteria)
    criteria = naming.criteria
    suite = adapters.suite_from(payload.test_cases, naming)
    accepted = {
        str(one).strip(): Acceptance(reason=ACCEPTED_REASON)
        for one in payload.accepted
        if str(one).strip()
    }
    report = decide_release(
        ShipInputs(
            story=payload.story,
            context=payload.context,
            test_cases=suite,
            criteria=[one.text for one in criteria],
            risk_analysis=adapters.risks_from(payload.risks),
            matrix=adapters.matrix_from(payload.matrix_summary),
            risk_acceptances=accepted,
        )
    )
    grade = release_grade(report)

    problems: list[Problem] = []
    for item in report.items:
        if item.status in ("pass", "not_checked"):
            continue
        level = {"fail": "high", "warn": "medium", "accepted": "low"}[item.status]
        problems.append(
            _problem(
                _check_kind(item.id),
                level,
                f"{item.title}: {item.summary}",
                item.instruction or f"Open {item.title} and fix what it lists.",
                criteria=_criteria_in(item, criteria),
            )
        )

    problems = _worst_first(problems)
    answer = ShipOut(
        tool="ship_check",
        summary=" · ".join(
            [
                DECISION_WORDS[report.verdict],
                f"grade {grade.letter}" if grade else "no grade yet",
                f"{report.checked} of {len(report.items)} checks run",
            ]
        ),
        problems=problems,
        add_tests=[],
        ask_the_po=_ship_questions(report),
        notes=(
            ([naming.note()] if naming.note() else [])
            + [report.verdict_reason]
            + _ship_notes(report)
        ),
        decision=DECISION_WORDS[report.verdict],
        grade=(
            GradeOut(
                letter=grade.letter,
                points=grade.points,
                max=grade.max_points,
                lines=list(grade.lines),
            )
            if grade
            else None
        ),
        checks=[
            CheckOut(
                id=item.id,
                title=item.title,
                status=item.status,
                summary=item.summary,
                details=list(item.details),
            )
            for item in report.items
        ],
        path_to_ready=_path_to_ready(report),
    )
    return finish(answer, payload, host, _shown(payload))


# Which kind of problem each failing check is, in the words of the output.
CHECK_KINDS = {
    "clarity": "clarity",
    "duel": "clarity",
    "coverage": "missing",
    "depth": "depth",
    "risks": "gap",
    "automation": "weak",
    "matrix": "gap",
}


def _check_kind(check_id: str) -> str:
    return CHECK_KINDS.get(check_id, "gap")


def _criteria_in(item, criteria) -> list[str]:
    """The criterion ids a check's own lines name."""
    known = {one.id for one in criteria}
    found: list[str] = []
    for line in [item.summary, *item.details]:
        for word in str(line or "").replace(",", " ").replace(":", " ").split():
            name = word.strip("“”\"'().;")
            if name in known and name not in found:
                found.append(name)
    return found


# What an agent can do about a check that did not run, said in terms of
# what it would have to send. Three of the seven cannot be run from here at
# all, and saying so is better than asking for something that cannot arrive.
SEND_INSTEAD = {
    "risks": "Score the risks and send them in `risks` so this check can run.",
    "matrix": (
        "Plan the test matrix and send it in `matrix_summary` so this check "
        "can run."
    ),
}
NOT_FROM_HERE = {
    "clarity": "the story clarity score",
    "duel": "the two-reader comparison",
    "automation": "a generated automation project",
}
NOT_FROM_HERE_LINE = (
    "{title}: needs {thing}, which comes from the QA-Genius website and "
    "cannot be sent to this tool. It is counted as not done, never as fine."
)


def _ship_questions(report) -> list[str]:
    """What a person has to decide before this can move."""
    asked: list[str] = []
    for item in report.items:
        if item.status == "not_checked" and item.id in SEND_INSTEAD:
            asked.append(
                f"{item.title}: nothing was sent for this, so it is not done "
                "yet — should it be done before release?"
            )
        if item.status == "accepted" and item.accepted_note:
            asked.append(f"{item.title}: still accepted? {item.accepted_note}")
    return asked


def _ship_notes(report) -> list[str]:
    counts = report.counts
    notes = [
        " · ".join(
            f"{name.replace('_', ' ')}: {counts[name]}"
            for name in ("pass", "warn", "fail", "accepted", "not_checked")
        ),
        "A check with nothing sent for it reads “not done yet”, never “fine”.",
    ]
    for item in report.items:
        if item.status == "not_checked" and item.id in NOT_FROM_HERE:
            notes.append(
                NOT_FROM_HERE_LINE.format(
                    title=item.title, thing=NOT_FROM_HERE[item.id]
                )
            )
    return notes


def _path_to_ready(report) -> list[str]:
    """What to do, worst first, to turn this into ready.

    Only steps the caller can actually take. A check that needs the website
    is said in `notes`, because putting it here would be a list with an
    instruction in it that nobody reading this can follow.
    """
    order = {"fail": 0, "warn": 1, "accepted": 2, "not_checked": 3}
    steps: list[str] = []
    for item in sorted(report.items, key=lambda one: order.get(one.status, 4)):
        if item.status == "pass":
            continue
        if item.status == "not_checked":
            if item.id in SEND_INSTEAD:
                steps.append(f"{item.title}: {SEND_INSTEAD[item.id]}")
            continue
        steps.append(item.instruction or f"Fix {item.title}: {item.summary}")
    return steps


# ──────────────────────────────────────────────────────────────────────────────
# score_risks
# ──────────────────────────────────────────────────────────────────────────────

# How a classic risk nobody wrote down is worded as a problem.
MISSING_RISK_FIX = (
    "Add it to your risks with your own scores, then call score_risks again."
)


def score_risks(payload: RisksIn, host: str = "") -> RisksOut:
    """Score a set of risks and say which ones no test reaches. No AI."""
    naming = adapters.naming_from(payload.criteria)
    suite = adapters.suite_from(payload.test_cases, naming)
    reviewed = review_risk_list(
        payload.story,
        payload.context,
        naming.criteria,
        list(suite.test_cases),
        adapters.risks_from(payload.risks),
    )

    problems: list[Problem] = []
    for scored in reviewed.untested_high:
        problems.append(
            _problem(
                "gap",
                "high",
                f"{scored.risk.id} {scored.risk.title}: "
                f"{coverage_word(scored.coverage)} "
                f"(score {scored.rpn} of {MAX_SCORE}).",
                "Write a test that does what this risk describes, or say in "
                "writing why you are accepting it.",
                criteria=[str(one) for one in scored.risk.related_criteria],
            )
        )
    for scored in reviewed.untested_medium:
        problems.append(
            _problem(
                "gap",
                "medium",
                f"{scored.risk.id} {scored.risk.title}: "
                f"{coverage_word(scored.coverage)} "
                f"(score {scored.rpn} of {MAX_SCORE}).",
                "Worth a test before release.",
                criteria=[str(one) for one in scored.risk.related_criteria],
            )
        )
    for risk in reviewed.missing:
        problems.append(
            _problem(
                "missing",
                "medium",
                "Nobody wrote down a classic risk for this kind of feature: "
                f"{risk.title} — {risk.effect}",
                MISSING_RISK_FIX,
            )
        )

    problems = _worst_first(problems)
    counts = reviewed.report.counts
    answer = RisksOut(
        tool="score_risks",
        summary=" · ".join(
            [
                _to_fix(problems),
                _count(counts["total"], "risk"),
                f"{counts['untested_high']} high without a test",
            ]
        ),
        problems=problems,
        add_tests=[
            adapters.test_out(case) for case in _tests_for_risks(payload, naming, reviewed)
        ],
        ask_the_po=_risk_questions(reviewed),
        notes=_risk_notes(reviewed, naming),
        risks=[
            RiskOut(
                id=str(scored.risk.id or ""),
                title=str(scored.risk.title or ""),
                category=str(scored.risk.category or ""),
                score=scored.rpn,
                max_score=MAX_SCORE,
                level=scored.level,
                coverage=coverage_word(scored.coverage),
                tested_by=[str(row[0]) for row in scored.covered_tests],
            )
            for scored in reviewed.report.risks
        ],
        untested_high=[str(one.risk.id or "") for one in reviewed.untested_high],
    )
    return finish(answer, payload, host, _shown(payload))


def _tests_for_risks(payload: RisksIn, naming, reviewed) -> list:
    """Ready tests for the gaps, when a high risk has nothing reaching it.

    The senior tester's own suite review writes them: a risk with no test
    is a gap in the suite, and the suite is where the gap gets filled.
    """
    if not reviewed.untested_high:
        return []
    asked = review_tests_service(
        payload.story,
        payload.context,
        naming.criteria,
        adapters.suite_from(payload.test_cases, naming),
    )
    return list(asked.added)


def _risk_questions(reviewed) -> list[str]:
    return [
        f"{scored.risk.id} {scored.risk.title} is a high risk with no test. "
        "Is the team accepting it, and who owns that?"
        for scored in reviewed.untested_high
    ]


def _risk_notes(reviewed, naming) -> list[str]:
    notes = [naming.note()] if naming.note() else []
    counts = reviewed.report.counts
    notes.append(
        " · ".join(f"{name}: {counts[name]}" for name in ("high", "medium", "low"))
    )
    weak = [one for one in reviewed.report.risks if one.coverage == "weak"]
    if weak:
        names = ", ".join(str(one.risk.id or "") for one in weak)
        notes.append(
            f"Only probably tested: {names}. A test was named for each, but its "
            "words do not say what the risk says goes wrong."
        )
    notes.append(
        f"A score is how bad × how likely × how hard to notice, out of {MAX_SCORE}."
    )
    return notes


# ──────────────────────────────────────────────────────────────────────────────
# plan_matrix
# ──────────────────────────────────────────────────────────────────────────────

_SIDE = re.compile(r"^\s*(?P<factor>[^=]+?)\s*=\s*(?P<option>.+?)\s*$")


def _rule_from(rule: MatrixRuleIn) -> Rule | None:
    """One "Browser=Firefox" / "Device=Phone" pair as the engine's Rule."""
    left, right = _SIDE.match(rule.a or ""), _SIDE.match(rule.b or "")
    if left is None or right is None:
        return None
    return Rule(
        if_factor=left.group("factor"),
        if_value=left.group("option"),
        then_factor=right.group("factor"),
        then_value=right.group("option"),
        reason=str(rule.reason or ""),
        source="ai",
    )


def plan_matrix(payload: MatrixPlanIn, host: str = "") -> MatrixOut:
    """Plan the fewest runs that still cover every allowed pair. No AI."""
    factors = [
        Factor(name=str(one.name or ""), values=tuple(str(x) for x in one.options))
        for one in payload.factors
    ]
    rules: list[Rule] = []
    problems: list[Problem] = []
    for rule in payload.rules:
        made = _rule_from(rule)
        if made is None:
            problems.append(
                _problem(
                    "clarity",
                    "high",
                    f"A rule is not readable: {rule.a!r} with {rule.b!r}.",
                    'Write each side as "Factor=option", such as "Browser=Firefox".',
                )
            )
            continue
        rules.append(made)

    plan = None
    if not problems:
        plan = plan_matrix_service(factors, rules, [dict(one) for one in payload.pinned])
        for line in plan.problems:
            problems.append(
                _problem(
                    "clarity",
                    "high",
                    line,
                    "Fix the factors or the rules and call plan_matrix again.",
                )
            )

    ok = plan is not None and not plan.problems
    answer = MatrixOut(
        tool="plan_matrix",
        summary=plan.summary if ok else _to_fix(_worst_first(problems)),
        problems=_worst_first(problems),
        ask_the_po=[],
        notes=_matrix_notes(plan) if ok else [],
        runs=(
            [
                RunOut(
                    values=dict(run.values),
                    new_pairs=run.new_pairs,
                    manual_only=run.manual_only,
                    manual_reason=run.manual_reason,
                )
                for run in plan.runs
            ]
            if ok
            else []
        ),
        combinations=plan.combinations if ok else 0,
        pairs_possible=plan.pairs_possible if ok else 0,
        pairs_covered=plan.pairs_covered if ok else 0,
        impossible_pairs=(
            [
                f"{pair[0]}={pair[1]} + {pair[2]}={pair[3]}"
                for pair in plan.impossible_pairs
            ]
            if ok
            else []
        ),
        manual_only=plan.manual_only if ok else 0,
    )
    return finish(
        answer, payload, host, {"matrix_input": payload.model_dump(mode="json")}
    )


def _matrix_notes(plan) -> list[str]:
    notes = [
        f"Every one of the {plan.pairs_possible} possible pairs is covered by "
        f"{len(plan.runs)} runs."
    ]
    if plan.impossible_pairs:
        notes.append(
            f"{len(plan.impossible_pairs)} pairs your rules forbid were left out."
        )
    if plan.manual_only:
        notes.append(
            f"{plan.manual_only} of the runs cannot be driven by Playwright and "
            "have to be done by hand."
        )
    return notes


# ──────────────────────────────────────────────────────────────────────────────
# check_code
# ──────────────────────────────────────────────────────────────────────────────

# An error stops the suite being worth running; a warning is what hurts
# three months later.
CODE_LEVELS = {"error": "high", "warning": "medium"}
CODE_KINDS = (
    ("`.only`", "gap"),
    ("hard-coded secret", "weak"),
    ("expect", "weak"),
    ("wait", "weak"),
)


def _code_kind(message: str) -> str:
    said = str(message or "").lower()
    for word, kind in CODE_KINDS:
        if word.lower() in said:
            return kind
    return "weak"


def check_code(payload: CodeIn, host: str = "") -> CodeOut:
    """Read automation code and say what a senior tester would send back.

    Nothing in the files is ever run.
    """
    files = [
        ProjectFile(name=str(one.path or ""), code=str(one.content or ""))
        for one in payload.files
    ]
    wanted = [str(one.id or "") for one in payload.test_cases if str(one.id or "")]
    reviewed = review_code(payload.framework, files, wanted)

    problems: list[Problem] = []
    for finding in reviewed.findings:
        where = f"{finding.file}:{finding.line}" if finding.line else finding.file
        problems.append(
            _problem(
                _code_kind(finding.message),
                CODE_LEVELS.get(finding.level, "medium"),
                f"{where} — {finding.message}",
                "Fix it in the file and call check_code again.",
            )
        )
    if reviewed.missing:
        problems.append(
            _problem(
                "missing",
                "high",
                "No file names these test cases: " + ", ".join(reviewed.missing) + ".",
                "Put the test case id in the test name or a comment, so the code "
                "and the suite can be matched up.",
                tests=list(reviewed.missing),
            )
        )

    problems = _worst_first(problems)
    answer = CodeOut(
        tool="check_code",
        summary=" · ".join(
            [
                _to_fix(problems),
                _count(len(files), "file"),
                (
                    f"{len(reviewed.traced)} of {len(wanted)} test cases found"
                    if wanted
                    else "no test case ids sent"
                ),
            ]
        ),
        problems=problems,
        ask_the_po=[],
        notes=_code_notes(reviewed),
        language=reviewed.language,
        syntax={name: syntax_words(status) for name, status in reviewed.syntax.items()},
        findings=[
            CodeFindingOut(
                file=finding.file,
                line=finding.line,
                level=finding.level,
                says=finding.message,
            )
            for finding in reviewed.findings
        ],
        traced=list(reviewed.traced),
        untraced=list(reviewed.missing),
    )
    return finish(
        answer, payload, host, {"code_files": [one.path for one in payload.files]}
    )


def _code_notes(reviewed) -> list[str]:
    notes = []
    if reviewed.language:
        notes.append(f"Read as {reviewed.language}.")
    quick = [
        name for name, status in reviewed.syntax.items() if status == "basic check passed"
    ]
    if quick:
        notes.append(
            "Quick check only on "
            + ", ".join(quick)
            + ": brackets and quotes match, which is not a full compile."
        )
    notes.append("Nothing in these files was run. Every answer comes from reading them.")
    return notes
