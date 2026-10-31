"""Build refine/strengthen prompts and merge strengthened results safely."""

import re

from qagenius.models import TestCaseList
from qagenius.risk_radar import RISK_TAG, ScoredRisk
from qagenius.test_case_depth import NO_KIND, NOT_COVERED, ONLY_ONE, DepthReport
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
_COVER_LINE = "cover this criterion with at least {kinds} case"
# A reason becomes the words asking for the case that is missing. The screen
# says "no test for wrong input"; the prompt keeps the QA words the AI knows.
_REASON_PHRASES = (
    (NO_KIND["Negative"], "a negative case"),
    (NO_KIND["Boundary"], "a boundary case"),
    (ONLY_ONE, "at least one more case"),
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
        if NOT_COVERED in row.reasons:
            # Only the kinds this criterion can really have: a criterion with
            # nothing to type into has no negative case to write.
            kinds = ["one positive"]
            if row.needs_wrong_input:
                kinds.append("one negative")
            if row.needs_limit:
                kinds.append("one boundary")
            lines.append(f"For {row.id}: {_COVER_LINE.format(kinds=_join_phrases(kinds))}.")
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


_RISK_HEAD = (
    'Write at least one test case for each of these risks. Put the risk id in '
    'the test case\'s tags as "risk:R1" (exactly this format).'
)
_RISK_TAIL = (
    "Use exact values (counts, times, sizes) and include at least one negative "
    "or boundary case per risk where it makes sense."
)
# "R2" written anywhere the AI could put it.
_RISK_ID = re.compile(r"\bR\d+\b", re.IGNORECASE)


def risk_instruction(risks: list[ScoredRisk]) -> str:
    """Ask for one test per untested risk, each tagged with its risk id."""
    lines = [_STRENGTHEN_HEAD, _RISK_HEAD]
    for item in risks:
        risk = item.risk
        line = f"{risk.id} ({risk.category}): {risk.title}"
        if risk.test_idea:
            line += f" — Test idea: {risk.test_idea}"
        lines.append(line)
    lines.append(_RISK_TAIL)
    return "\n".join(lines)


def add_risk_tags(
    current: TestCaseList, proposed: TestCaseList, risk_ids: list[str]
) -> TestCaseList:
    """Tag every new case with the risk it was written for.

    Write a test on R6 added TC-014 and the page then showed it under R1:
    nothing in the case said which risk it was for, so the desk guessed
    from the words. Code says so instead.

    One risk was asked for, so every new case belongs to it. Several, and
    the case is tagged with the risk it names -- in its tags, its title or
    its traceability line.
    """
    known = {str(one or "").strip().upper() for one in risk_ids if str(one or "").strip()}
    only = next(iter(known)) if len(known) == 1 else ""
    current_ids = {str(case.id or "").strip().lower() for case in current.test_cases}
    cases = []
    for case in proposed.test_cases:
        if str(case.id or "").strip().lower() in current_ids:
            cases.append(case)
            continue
        tags = list(case.tags or [])
        have = {str(tag or "").strip().lower() for tag in tags}
        text = " ".join(
            [case.traceability or "", case.title or "", " ".join(case.tags or [])]
        )
        wanted = [
            found.upper() for found in _RISK_ID.findall(text) if found.upper() in known
        ]
        # Nothing in the case names a risk, and only one was asked for: it
        # is that one, and no word matching has any say in it.
        if not wanted and only:
            wanted = [only]
        added = False
        for risk_id in wanted:
            tag = RISK_TAG + risk_id
            if tag.lower() not in have:
                tags.append(tag)
                have.add(tag.lower())
                added = True
        cases.append(case.model_copy(update={"tags": tags}) if added else case)
    return TestCaseList(test_cases=cases, summary=proposed.summary)
