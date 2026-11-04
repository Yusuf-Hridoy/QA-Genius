"""The three tools QA-Genius offers an AI agent, and what they are called.

What a tool does lives in tools.py; what it looks like on the wire lives
here. Every shape an MCP client sees is built from the SDK's own types, so
the only hand-written part of this door is the dispatch, never the
vocabulary.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Callable

from mcp_types import Tool, ToolAnnotations
from pydantic import BaseModel

from qagenius.mcp_server import tools
from qagenius.mcp_server.schemas import (
    CodeIn,
    CodeOut,
    MatrixOut,
    MatrixPlanIn,
    RisksIn,
    RisksOut,
    ShipIn,
    ShipOut,
    StoryIn,
    TestsIn,
    ToolOut,
)

SERVER_NAME = "QA-Genius"
SERVER_TITLE = "QA-Genius"
FALLBACK_VERSION = "2.1.0"
_PYPROJECT = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"


def version() -> str:
    """The app's own version, read from pyproject.toml.

    A deployment that cannot read the file still answers, with the version
    this file was written beside: a handshake that fails over a version
    string is worse than a handshake with a slightly old one.
    """
    try:
        with open(_PYPROJECT, "rb") as handle:
            return str(tomllib.load(handle)["project"]["version"])
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return FALLBACK_VERSION


# What the agent on the other end should do with these tools. It is the
# only place to say "do not claim a check passed unless you ran it", and an
# agent that reads nothing else reads this.
INSTRUCTIONS = """\
QA-Genius checks QA work with code. There is no AI and no API key behind \
these tools: the same input always gives the same answer.

You write the criteria, the tests, the risks and the code yourself. \
QA-Genius checks them. The order:

1. Call check_story on the story as the team wrote it, and fix the words \
it says nobody can test.
2. Write the acceptance criteria and the test cases.
3. Call review_tests and fix every problem with level "high". Call it \
again until no high problems come back.
4. Write the risks and score them, then call score_risks. Add tests for \
every high risk with no test.
5. Use plan_matrix to work out which browsers and devices to run on.
6. If you write automation, call check_code.
7. Finish with ship_check. Show the user its report link and the \
ask_the_po questions.

Four rules:

- Never tell the user a check passed unless you ran it and read the \
answer. A check that says "not done yet" has not passed.
- Always show the user the questions in ask_the_po. They are the things no \
tool can decide, and guessing at them is how a suite ends up testing the \
wrong number.
- The tests in add_tests are already in the shape test_cases takes. Read \
them, keep the ones you agree with, and send them back in.
- Every answer carries a report_link. Pass it back as \
previous_report_link on your next call and the answer will tell you which \
problems you have fixed. Give the final link to the user — it is a page \
they can open, and nothing about it is stored anywhere.\
"""

# A text block is a glance. Everything past this is in structuredContent,
# which is where a client that can read it should be reading anyway.
MAX_TEXT_PROBLEMS = 10

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

CHECK_STORY_DESCRIPTION = """\
Read a user story before anyone writes a test, and say what is wrong with \
it. Finds words nobody can measure and says what to write instead, warns \
when the story is really several stories, says when nothing describes what \
happens if it fails, and lists limits nobody has decided. Use it first, on \
the story as the team wrote it, before you draft acceptance criteria — \
fixing a word here is cheaper than rewriting a suite later. Example: send \
{"story": "As a shopper I want the cart to update quickly so that I can \
check out"} and it reports that "quickly" is untestable and to say "within \
2 seconds" instead.\
"""

REVIEW_TESTS_DESCRIPTION = """\
Review acceptance criteria and the test cases written for them, the way a \
senior tester would. Finds tests that expect the opposite of the limit \
their criterion states, missing tests at the limits and for wrong input, \
two tests that are the same test, tests whose expected result cannot be \
judged true or false, and criteria that are too thinly tested. Hands back \
ready-written tests for the gaps, in the same shape you send tests in. Use \
it after you have drafted criteria and tests, fix every high problem, and \
call it again until none come back. Example: send a criterion "orders over \
$50 ship free" with one test using $60, and it reports that nobody says \
what happens at exactly $50.\
"""

SHIP_CHECK_DESCRIPTION = """\
Decide whether this work is ready to release, and say why. Runs every \
check at once over the story, criteria, tests and — if you send them — the \
risks and the test matrix, then gives a decision, a letter grade with the \
arithmetic behind it, every check with its status, and the list of things \
to do to reach ready. A check you sent nothing for comes back "not done \
yet", which never means fine. Use it last, after review_tests comes back \
with no high problems. Example: send story, criteria and tests with no \
risks, and the risk check reports "not done yet" and the decision says so.\
"""


SCORE_RISKS_DESCRIPTION = """\
Score a set of risks and say which ones no test reaches. You write the \
risks and the three scores — how bad, how likely, how hard to notice — and \
this works out each one's risk score out of 125, its level, and whether a \
test really covers it (a test that names the risk or does what it \
describes counts; a test merely claimed does not). It also names the \
classic failure modes this kind of feature usually has that nobody wrote \
down, and hands back ready tests for high risks with nothing covering \
them. Use it after review_tests comes back clean. Example: send a payment \
story with one risk "the card is charged twice" and no test for it, and it \
comes back high, "no test", with a question for the product owner.\
"""

PLAN_MATRIX_DESCRIPTION = """\
Work out the fewest test runs that still put every allowed pair of values \
together. Send what varies — browser, device, language, role — and the \
pairs that can never happen, and it returns the runs to do, how many new \
pairs each one is the first to cover, the pairs your rules forbid, and \
which runs Playwright cannot drive so somebody has to do them by hand. Use \
it when you need to decide where to run a suite rather than what to put in \
it. Example: 4 browsers × 3 devices × 2 sign-in states is 24 combinations, \
and this returns about 12 runs that still cover every pair.\
"""

CHECK_CODE_DESCRIPTION = """\
Read automation code and say what a senior tester would send back. Finds \
tests left with `.only` or `fit` that silently skip the rest of the suite, \
tests that never actually check anything, fixed sleeps instead of waiting \
for a state, passwords and tokens written into the source, selectors that \
will break on the next redesign, and which of your test case ids the code \
never names. Python is parsed for real; TypeScript and JavaScript get a \
quick check that brackets and quotes match, which is not a full compile, \
and the answer says so. Nothing is ever run. Use it after you write or \
change automation. Example: send one Playwright spec with a leftover \
`test.only` and it comes back as a high problem on that line.\
"""


class Spec:
    """One tool: its wire definition and the function behind it."""

    def __init__(
        self,
        name: str,
        description: str,
        input_model: type[BaseModel],
        output_model: type[BaseModel],
        run: Callable[..., BaseModel],
    ) -> None:
        self.name = name
        self.description = description
        self.input_model = input_model
        self.output_model = output_model
        self.run = run

    def definition(self) -> Tool:
        """This tool as `tools/list` hands it to a client."""
        return Tool(
            name=self.name,
            title=self.name,
            description=self.description,
            inputSchema=self.input_model.model_json_schema(),
            outputSchema=self.output_model.model_json_schema(),
            annotations=READ_ONLY,
        )


SPECS: tuple[Spec, ...] = (
    Spec(
        "check_story",
        CHECK_STORY_DESCRIPTION,
        StoryIn,
        ToolOut,
        tools.check_story,
    ),
    Spec(
        "review_tests",
        REVIEW_TESTS_DESCRIPTION,
        TestsIn,
        ToolOut,
        tools.review_tests,
    ),
    Spec(
        "score_risks",
        SCORE_RISKS_DESCRIPTION,
        RisksIn,
        RisksOut,
        tools.score_risks,
    ),
    Spec(
        "plan_matrix",
        PLAN_MATRIX_DESCRIPTION,
        MatrixPlanIn,
        MatrixOut,
        tools.plan_matrix,
    ),
    Spec(
        "check_code",
        CHECK_CODE_DESCRIPTION,
        CodeIn,
        CodeOut,
        tools.check_code,
    ),
    Spec(
        "ship_check",
        SHIP_CHECK_DESCRIPTION,
        ShipIn,
        ShipOut,
        tools.ship_check,
    ),
)

BY_NAME = {spec.name: spec for spec in SPECS}


def definitions() -> list[Tool]:
    """Every tool, in a fixed order."""
    return [spec.definition() for spec in SPECS]


def text_summary(answer: BaseModel) -> str:
    """The short line for a client that only reads text.

    Not the whole answer repeated as prose: a client that reads text reads
    it to a person, and a person wants the headline and the count.
    """
    data = answer.model_dump()
    lines = [str(data.get("summary") or "")]
    problems = data.get("problems") or []
    for problem in problems[:MAX_TEXT_PROBLEMS]:
        lines.append(
            f"[{problem['level']}] {problem['id']} {problem['says']} "
            f"→ {problem['fix']}"
        )
    if len(problems) > MAX_TEXT_PROBLEMS:
        lines.append(f"…and {len(problems) - MAX_TEXT_PROBLEMS} more.")
    asked = data.get("ask_the_po") or []
    if asked:
        lines.append("Ask the product owner: " + " · ".join(asked))
    lines.append("The full answer is in structuredContent.")
    return "\n".join(line for line in lines if line)
