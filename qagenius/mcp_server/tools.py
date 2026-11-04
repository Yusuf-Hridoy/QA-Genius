"""The three tools, as plain functions over the service layer.

Nothing here calls an AI, reads a key, stores anything or reaches the
network. Each one takes an input model and returns an output model, so the
same input gives byte-identical output every time it is called.
"""

from __future__ import annotations

from qagenius.acceptance import Acceptance
from qagenius.mcp_server import adapters
from qagenius.mcp_server.schemas import (
    CheckOut,
    GradeOut,
    Problem,
    ShipIn,
    ShipOut,
    StoryIn,
    TestsIn,
    ToolOut,
    problem_id,
)
from qagenius.services.release_decision import decide_release, release_grade
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


def check_story(payload: StoryIn) -> ToolOut:
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
    return ToolOut(
        tool="check_story",
        summary=summary,
        problems=problems,
        add_tests=[],
        ask_the_po=_story_questions(review),
        notes=_story_notes(review),
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


def review_tests(payload: TestsIn) -> ToolOut:
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
    return ToolOut(
        tool="review_tests",
        summary=summary,
        problems=problems,
        add_tests=[adapters.test_out(case) for case in reviewed.added],
        ask_the_po=list(reviewed.review.conflicts),
        notes=_test_notes(reviewed, naming),
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


def ship_check(payload: ShipIn) -> ShipOut:
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
    return ShipOut(
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
