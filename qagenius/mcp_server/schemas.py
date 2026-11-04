"""What goes in and what comes out of every QA-Genius tool.

Every description in here is written for an AI reader, because that is who
reads them: an agent decides what to send from these words alone. Keep them
short, concrete and free of QA jargon.

The output shape is the same for all three tools, so an agent that can read
one answer can read all of them. ship_check adds four fields of its own and
changes nothing else.
"""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"

# The sizes the door accepts. They are here, beside the fields, so the
# schema an agent reads and the limit the server enforces cannot drift.
STORY_MAX = 3000
CONTEXT_MAX = 2000
MAX_CRITERIA = 60
MAX_TESTS = 300

TestKind = Literal["normal", "wrong input", "at the limit", "unusual"]
ProblemKind = Literal[
    "limit", "gap", "copy", "weak", "depth", "clarity", "epic", "missing"
]
Level = Literal["high", "medium", "low"]
Decision = Literal["ready", "ready with known risks", "not ready"]

# How a problem id is built, so the same problem keeps the same id between
# calls: the first letter of its kind, then four hex of a hash of what the
# problem is actually about.
ID_HEX = 4
_SPACES = re.compile(r"\s+")


def normalised(text: str) -> str:
    """One line, lower case, single spaces. Only used for building ids."""
    return _SPACES.sub(" ", str(text or "")).strip().lower()


def problem_id(kind: str, says: str, criteria: list[str], tests: list[str]) -> str:
    """A stable id for one problem.

    The same problem found in two calls gets the same id, so an agent can
    say "I fixed L-3f9a" and mean something. The id is built from what the
    problem is about, never from where it happened to sit in a list.
    """
    seed = "|".join(
        [
            normalised(kind),
            ",".join(sorted(str(one) for one in criteria)),
            ",".join(sorted(str(one) for one in tests)),
            normalised(says),
        ]
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    letter = (str(kind or "x")[:1] or "x").upper()
    return f"{letter}-{digest[:ID_HEX]}"


class Strict(BaseModel):
    """Every model here refuses a field it does not know.

    A typo in a field name is a quiet half-request otherwise: the agent
    thinks it sent the steps and the server never saw them.
    """

    model_config = ConfigDict(extra="forbid")


# ──────────────────────────────────────────────────────────────────────────────
# Inputs
# ──────────────────────────────────────────────────────────────────────────────


class CriterionIn(Strict):
    """One acceptance criterion: one rule the feature has to obey."""

    id: str = Field(
        default="",
        description=(
            'Your id for this criterion. Use the shape "AC-1" and it is kept '
            "exactly. Leave it out and ids are given in order: AC-1, AC-2, "
            "AC-3. Any other shape is renumbered to AC-1…AC-n by position — "
            "the answer says so in notes, and the ids in your test cases' "
            '"covers" are renumbered to match.'
        ),
        max_length=40,
    )
    text: str = Field(
        description=(
            "The rule in one sentence, with the real numbers in it. "
            '"The account locks for 30 minutes after 5 wrong passwords" — '
            'not "the account locks quickly".'
        ),
        max_length=1000,
    )


class TestIn(Strict):
    """One test case."""

    # Its name starts with "Test", so pytest tries to collect it as a suite.
    __test__ = False

    id: str = Field(
        description='Your id for this test, such as "TC-04".', max_length=40
    )
    title: str = Field(
        description="What this test proves, in one line.", max_length=300
    )
    steps: list[str] = Field(
        description="What the tester does, one action per step. At least one.",
        min_length=1,
        max_length=50,
    )
    expected: str = Field(
        description=(
            "What must be true afterwards, worded so it can only be true or "
            'false. "The page shows: Locked for 30 minutes" — not "it works".'
        ),
        max_length=1000,
    )
    test_data: str = Field(
        default="",
        description=(
            "The exact values this test uses: the amount, the file size, the "
            'number of tries. Say "$50.00", not "an order over the limit".'
        ),
        max_length=1000,
    )
    covers: list[str] = Field(
        default_factory=list,
        description=(
            'The criterion ids this test proves, such as ["AC-1", "AC-3"]. '
            "Use the same ids you sent in criteria. A criterion no test "
            "names is reported as having no tests."
        ),
        max_length=MAX_CRITERIA,
    )
    kind: TestKind = Field(
        default="normal",
        description=(
            'What kind of test this is. "normal" is the path that works; '
            '"wrong input" is bad data or no permission; "at the limit" uses '
            'the exact boundary value; "unusual" is everything rarer.'
        ),
    )


class StoryIn(Strict):
    """A story to check, on its own."""

    story: str = Field(
        description="The user story or the bug, in the words the team wrote.",
        max_length=STORY_MAX,
    )
    context: str = Field(
        default="",
        description=(
            "Anything else that decides the answer: limits, rules, what the "
            "feature already does. Limits live here as often as in a criterion."
        ),
        max_length=CONTEXT_MAX,
    )
    story_type: Literal["user story", "bug", "feature"] = Field(
        default="user story",
        description="What kind of thing this is. It changes nothing in the check.",
    )


class TestsIn(Strict):
    """A story, its criteria and the tests written for them."""

    __test__ = False

    story: str = Field(
        description="The user story or the bug, in the words the team wrote.",
        max_length=STORY_MAX,
    )
    context: str = Field(
        default="",
        description=(
            "Anything else that decides the answer: limits, rules, what the "
            "feature already does."
        ),
        max_length=CONTEXT_MAX,
    )
    criteria: list[CriterionIn] = Field(
        description="The acceptance criteria, in order.",
        max_length=MAX_CRITERIA,
    )
    test_cases: list[TestIn] = Field(
        description="The tests you wrote for those criteria.",
        max_length=MAX_TESTS,
    )


class RiskIn(Strict):
    """One way the feature could fail, scored the way an FMEA scores it."""

    id: str = Field(
        default="", description='Your id for this risk, such as "R1".', max_length=40
    )
    title: str = Field(description="The failure, in one line.", max_length=300)
    category: str = Field(
        default="functional",
        description=(
            "One of: security, performance, reliability, data, usability, "
            "accessibility, functional. Anything else is read as functional."
        ),
        max_length=40,
    )
    effect: str = Field(
        default="", description="What the user suffers when it happens.", max_length=600
    )
    cause: str = Field(
        default="", description="Why it would happen.", max_length=600
    )
    severity: int = Field(
        default=3, description="How bad it is, 1 to 5.", ge=1, le=5
    )
    likelihood: int = Field(
        default=3, description="How likely it is, 1 to 5.", ge=1, le=5
    )
    detectability: int = Field(
        default=3,
        description="How hard it is to notice, 1 to 5. 5 means nobody would.",
        ge=1,
        le=5,
    )
    related_criteria: list[str] = Field(
        default_factory=list,
        description='The criterion ids this risk belongs to, such as ["AC-2"].',
        max_length=MAX_CRITERIA,
    )
    covered_by: list[str] = Field(
        default_factory=list,
        description=(
            "The test ids you believe already reach this risk. The check "
            "reads the tests themselves and will disagree if the words do not."
        ),
        max_length=MAX_TESTS,
    )
    test_idea: str = Field(
        default="",
        description="One line saying what a test for this would do.",
        max_length=600,
    )


class MatrixIn(Strict):
    """How much of a test matrix the planned runs actually cover."""

    runs: int = Field(default=0, description="How many runs are planned.", ge=0)
    valid_pairs: int = Field(
        default=0, description="How many pairs of values are worth covering.", ge=0
    )
    covered_pairs: int = Field(
        default=0, description="How many of those pairs the runs reach.", ge=0
    )
    manual_only: int = Field(
        default=0, description="How many runs nobody can automate.", ge=0
    )
    factors: list[str] = Field(
        default_factory=list,
        description='What varies between runs, such as ["browser", "device"].',
        max_length=40,
    )


class ShipIn(Strict):
    """Everything the release decision is made from."""

    story: str = Field(
        description="The user story or the bug, in the words the team wrote.",
        max_length=STORY_MAX,
    )
    context: str = Field(
        default="",
        description="Anything else that decides the answer: limits, rules.",
        max_length=CONTEXT_MAX,
    )
    criteria: list[CriterionIn] = Field(
        description="The acceptance criteria, in order.", max_length=MAX_CRITERIA
    )
    test_cases: list[TestIn] = Field(
        description="The tests written for those criteria.", max_length=MAX_TESTS
    )
    risks: list[RiskIn] = Field(
        default_factory=list,
        description=(
            "The risks, if you scored any. Leave it out and the risk check "
            'comes back "not done yet" — never "fine".'
        ),
        max_length=200,
    )
    matrix_summary: MatrixIn | None = Field(
        default=None,
        description=(
            "The test matrix, if you planned one. Leave it out and the matrix "
            'check comes back "not done yet".'
        ),
    )
    accepted: list[str] = Field(
        default_factory=list,
        description=(
            "Risk ids the team has accepted in writing. An accepted risk is "
            "still shown, with its id, but it no longer counts as untested."
        ),
        max_length=200,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Output
# ──────────────────────────────────────────────────────────────────────────────


class Problem(Strict):
    """One thing that is wrong, and what to do about it."""

    id: str = Field(
        description=(
            "A stable id for this problem. The same problem keeps the same id "
            "between calls, so you can say which one you fixed."
        )
    )
    kind: ProblemKind = Field(
        description=(
            "limit: a number two places disagree about, or nobody decided. "
            "gap: something a senior tester always checks that no test does. "
            "copy: two tests that are the same test. "
            "weak: a test whose expected result cannot be judged true or false. "
            "depth: a criterion without enough tests, or without the kinds it "
            "needs. clarity: a word nobody can test. epic: the story is really "
            "several stories. missing: a criterion with no test at all."
        )
    )
    level: Level = Field(
        description=(
            "high: fix this before writing more. medium: fix it before release. "
            "low: worth a look."
        )
    )
    says: str = Field(description="What is wrong, in one sentence.")
    fix: str = Field(description="What to do about it, as an instruction.")
    criteria: list[str] = Field(
        default_factory=list, description="The criterion ids this is about."
    )
    tests: list[str] = Field(
        default_factory=list, description="The test ids this is about."
    )


class ToolOut(Strict):
    """What every QA-Genius tool answers with."""

    schema_version: str = Field(
        default=SCHEMA_VERSION,
        description="The shape of this answer. It changes only when fields do.",
    )
    tool: str = Field(description="Which tool answered.")
    summary: str = Field(
        description=(
            'One line for a human to read, such as "6 to fix · 5 criteria · '
            '14 tests". Show it; do not parse it.'
        )
    )
    problems: list[Problem] = Field(
        default_factory=list,
        description=(
            "Everything wrong, worst first. Fix every high one and call the "
            "tool again."
        ),
    )
    add_tests: list[TestIn] = Field(
        default_factory=list,
        description=(
            "Ready-written tests for gaps nothing covered. They are already in "
            "the shape this tool takes back, so you can send them straight in."
        ),
    )
    ask_the_po: list[str] = Field(
        default_factory=list,
        description=(
            "Questions no tool can answer because nobody has decided yet. "
            "Show these to the user — do not guess the answers."
        ),
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Anything else worth knowing that is not a problem.",
    )


class GradeOut(Strict):
    """A letter for the release, and the arithmetic behind it."""

    letter: str = Field(description='The grade, such as "B+" or "F".')
    points: int = Field(description="Points scored by the checks that ran.")
    max: int = Field(description="Points those checks were worth.")
    lines: list[str] = Field(
        default_factory=list,
        description="One line per check, saying what it scored and why.",
    )


class CheckOut(Strict):
    """One of the release checks."""

    id: str = Field(description="Which check this is.")
    title: str = Field(description="Its name, for a human.")
    status: Literal["pass", "warn", "fail", "accepted", "not_checked"] = Field(
        description=(
            'pass: fine. warn: look at it. fail: blocks the release. accepted: '
            'signed off in writing. not_checked: you sent nothing for it — '
            "this never means fine."
        )
    )
    summary: str = Field(description="What this check found, in one line.")
    details: list[str] = Field(
        default_factory=list, description="The short lines underneath it."
    )


class ShipOut(ToolOut):
    """The release answer: everything above, plus the decision itself."""

    decision: Decision = Field(
        description=(
            "ready: nothing to do. ready with known risks: it can go, and "
            "somebody should look at what is listed. not ready: a check failed."
        )
    )
    grade: GradeOut | None = Field(
        default=None,
        description="The letter, or null when no check had anything to score.",
    )
    checks: list[CheckOut] = Field(
        default_factory=list, description="Every check, in a fixed order."
    )
    path_to_ready: list[str] = Field(
        default_factory=list,
        description="What to do, in order, to turn this into ready.",
    )


# Every model whose JSON Schema is saved in tests/contracts, by file name.
CONTRACTS: dict[str, type[BaseModel]] = {
    "criterion_in": CriterionIn,
    "test_in": TestIn,
    "story_in": StoryIn,
    "tests_in": TestsIn,
    "risk_in": RiskIn,
    "matrix_in": MatrixIn,
    "ship_in": ShipIn,
    "problem": Problem,
    "tool_out": ToolOut,
    "grade_out": GradeOut,
    "check_out": CheckOut,
    "ship_out": ShipOut,
}
