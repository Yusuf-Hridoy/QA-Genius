"""Build refine/strengthen prompts and merge strengthened results safely."""

import re

from qagenius.models import TestCaseList
from qagenius.test_case_depth import DepthReport
from qagenius.test_case_diff import TITLE_MATCH, title_score
from qagenius.test_cases import Criterion, traced_ids

MAX_CASES = 60
INSTRUCTION_LIMIT = 1000

_STRENGTHEN_HEAD = (
    "Add new test cases only. Do not change or remove any existing test case."
)
_STRENGTHEN_TAIL = (
    "Use exact values (counts, times, lengths) at and around every limit in the story."
)
_COVER_LINE = (
    "cover this criterion with at least one positive, one negative "
    "and one boundary case"
)
# A thin reason becomes the words asking for the case that is missing.
_REASON_PHRASES = (
    ("no negative case", "a negative case"),
    ("no boundary case", "a boundary case"),
    ("only 1 case", "at least one more case"),
)
_ID_NUMBER = re.compile(r"(\d+)")


def current_cases_block(current: TestCaseList, criteria: list[Criterion]) -> str:
    """The cases the AI must keep, one per line."""
    valid_ids = {criterion.id for criterion in criteria}
    lines = [
        "",
        "",
        "CURRENT TEST CASES (keep the id of every case you keep; to change a case "
        "keep its id; new cases get new ids that continue the numbering):",
    ]
    for test_case in current.test_cases:
        covers = ", ".join(traced_ids(test_case, valid_ids)) or "-"
        lines.append(
            " | ".join(
                [
                    test_case.id,
                    test_case.category,
                    test_case.priority,
                    covers,
                    test_case.title,
                ]
            )
        )
    return "\n".join(lines)


def _join_phrases(phrases: list[str]) -> str:
    if len(phrases) == 1:
        return phrases[0]
    return ", ".join(phrases[:-1]) + " and " + phrases[-1]


def strengthen_instruction(depth: DepthReport) -> str:
    """Ask for exactly the cases the thin criteria are missing."""
    lines = [_STRENGTHEN_HEAD]
    for row in depth.rows:
        if not row.thin:
            continue
        if "not covered" in row.reasons:
            lines.append(f"For {row.id}: {_COVER_LINE}.")
            continue
        phrases = [
            phrase for reason, phrase in _REASON_PHRASES if reason in row.reasons
        ]
        if phrases:
            lines.append(f"For {row.id}: add {_join_phrases(phrases)}.")
    lines.append(_STRENGTHEN_TAIL)
    return "\n".join(lines)


def refine_user_text(
    base_user_text: str,
    current: TestCaseList,
    criteria: list[Criterion],
    instruction: str,
) -> str:
    """The user prompt for a refine or strengthen run."""
    return (
        base_user_text
        + current_cases_block(current, criteria)
        + "\n\nREFINE INSTRUCTION:\n"
        + instruction
        + "\n\nReturn the COMPLETE updated list of test cases, not only the changes."
    )


def next_case_id(existing_ids: list[str]) -> str:
    """The id after the highest numbered one, e.g. TC-013."""
    highest = 0
    for case_id in existing_ids:
        numbers = _ID_NUMBER.findall(str(case_id or ""))
        if numbers:
            highest = max(highest, max(int(number) for number in numbers))
    return "TC-" + str(highest + 1).zfill(3)


def merge_strengthened(
    current: TestCaseList, proposed: TestCaseList
) -> TestCaseList:
    """Keep every current case exactly, and add only genuinely new proposed ones.

    Strengthen must be additive, so edits and deletions the AI made are dropped.
    """
    kept = list(current.test_cases)
    current_ids = {str(case.id or "").strip().lower() for case in kept}
    taken_ids = set(current_ids)
    known_titles = [case.title for case in kept]
    added = []
    for test_case in proposed.test_cases:
        case_id = str(test_case.id or "").strip().lower()
        # An id the current list already holds means the AI edited that case.
        if case_id in current_ids:
            continue
        if any(
            title_score(test_case.title, title) >= TITLE_MATCH
            for title in known_titles
        ):
            continue
        new_case = test_case
        # Two new cases claiming one id: the second gets the next free number.
        if not case_id or case_id in taken_ids:
            new_case = test_case.model_copy(
                update={"id": next_case_id([c.id for c in kept + added])}
            )
        taken_ids.add(str(new_case.id or "").strip().lower())
        known_titles.append(new_case.title)
        added.append(new_case)
    return TestCaseList(test_cases=kept + added, summary=proposed.summary)
