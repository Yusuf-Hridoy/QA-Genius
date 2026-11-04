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
    ShipIn,
    ShipOut,
    StoryIn,
    TestsIn,
    ToolOut,
)

SERVER_NAME = "QA-Genius"
SERVER_TITLE = "QA-Genius"
FALLBACK_VERSION = "2.0.0"
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

You write the acceptance criteria and the test cases yourself. Then:

1. Call check_story on the story before you write anything, and fix the \
words it says nobody can test.
2. Write the criteria and the tests.
3. Call review_tests. Fix every problem with level "high", then call it \
again. Repeat until no high problems come back.
4. Call ship_check last.

Three rules:

- Never tell the user a check passed unless you ran it and read the answer. \
A check that says "not done yet" has not passed.
- Always show the user the questions in ask_the_po. They are the things no \
tool can decide, and guessing at them is how a suite ends up testing the \
wrong number.
- The tests in add_tests are already in the shape test_cases takes. Read \
them, keep the ones you agree with, and send them back in.\
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


class Spec:
    """One tool: its wire definition and the function behind it."""

    def __init__(
        self,
        name: str,
        description: str,
        input_model: type[BaseModel],
        output_model: type[BaseModel],
        run: Callable[[BaseModel], BaseModel],
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
        lambda payload: tools.check_story(payload),
    ),
    Spec(
        "review_tests",
        REVIEW_TESTS_DESCRIPTION,
        TestsIn,
        ToolOut,
        lambda payload: tools.review_tests(payload),
    ),
    Spec(
        "ship_check",
        SHIP_CHECK_DESCRIPTION,
        ShipIn,
        ShipOut,
        lambda payload: tools.ship_check(payload),
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
