"""Per-criterion depth: how many cases cover each criterion, of which kinds, and whether it is thin."""

import re
from dataclasses import dataclass

from qagenius.models import TestCaseList
from qagenius.shadow_qa.boundaries import find_boundaries
from qagenius.shadow_qa.detect import phrase_pattern
from qagenius.test_case_diff import normalised_words, word_form
from qagenius.test_cases import (
    CATEGORY_ORDER,
    Criterion,
    normalise_label,
    traced_ids,
)

DEPTH_KINDS = ("Negative", "Boundary")  # kinds every criterion should have
MIN_CASES = 2
# A criterion with nothing to look at but the way it looks is answered by
# one test. Asking for three is how a tool loses the reader's trust.
VISUAL_CASES = 1

# A criterion asks for a test at the limits only when it states a limit:
# a number with a unit ("5 attempts", "15 minutes"), or one of these words
# saying how much ("over 5 MB", "below 768 pixels").
LIMIT_PHRASES = (
    "at least", "at most", "up to", "maximum", "minimum", "below", "above",
    "under", "over", "within", "more than", "less than",
)
# A limit word on its own is just a word: a reader moves the mouse cursor
# over a link without any limit being near. The number has to follow it.
WORDS_AFTER_A_LIMIT = 3
_A_NUMBER = re.compile(r"\d")
# ... and for a wrong-input test only when somebody can put something in, or
# a rule can turn them away. A breadcrumb trail can do neither.
INPUT_WORDS = (
    "enter", "type", "fill", "select", "choose", "upload", "submit",
    "password", "code", "field", "form", "file", "permission", "role",
    "admin", "rights", "allowed", "denied", "invalid", "wrong", "limit",
)
# A criterion about how something looks, which one test answers.
VISUAL_WORDS = ("color", "colour", "bold", "hover", "icon", "highlight", "style")

_INPUT_FORMS = frozenset(word_form(word) for word in INPUT_WORDS)
_VISUAL_FORMS = frozenset(word_form(word) for word in VISUAL_WORDS)


def _says_how_much(said: str, phrase: str) -> bool:
    """Is this limit word followed, soon enough, by the amount it limits?"""
    for found in phrase_pattern(phrase).finditer(said):
        after = said[found.end():].split()[:WORDS_AFTER_A_LIMIT]
        if any(_A_NUMBER.search(word) for word in after):
            return True
    return False


def needs_limit_test(text: str) -> bool:
    """Does this criterion state a limit worth testing either side of?"""
    said = str(text or "")
    if any(_says_how_much(said, phrase) for phrase in LIMIT_PHRASES):
        return True
    # The same reader of numbers the senior tester's limit cases use, so the
    # two never disagree about what a limit is.
    return bool(find_boundaries([Criterion(id="AC-0", text=said)]))


def needs_wrong_input_test(text: str) -> bool:
    """Can a reader put something in here, or be turned away?"""
    return bool(normalised_words(text) & _INPUT_FORMS)


def is_visual(text: str) -> bool:
    """Is this criterion only about the way something looks?"""
    return bool(normalised_words(text) & _VISUAL_FORMS)

NOT_COVERED = "no tests yet"
ONLY_ONE = "only one test"
NO_KIND = {"Negative": "no test for wrong input", "Boundary": "no test at the limits"}
# Each reason reads as the end of "4 have ...", so the summary sentence can be
# built from the same words the table shows.
REASON_ORDER = (NOT_COVERED, ONLY_ONE, NO_KIND["Negative"], NO_KIND["Boundary"])
# Two reasons is a sentence anyone can read in one go; the table below the
# line has the rest, per criterion.
MAX_REASONS_IN_LINE = 2


@dataclass(frozen=True)
class CriterionDepth:
    id: str
    text: str
    case_ids: list[str]
    kinds: list[str]
    reasons: list[str]
    thin: bool
    # What this criterion asks for, which is not the same for all of them.
    needs_wrong_input: bool = False
    needs_limit: bool = False


@dataclass(frozen=True)
class DepthReport:
    rows: list[CriterionDepth]
    thin_ids: list[str]


def _ordered_kinds(categories: list[str]) -> list[str]:
    """Present categories, CATEGORY_ORDER first, then anything else alphabetically."""
    present = {normalise_label(category) for category in categories}
    present.discard("")
    kinds = [name for name in CATEGORY_ORDER if name in present]
    kinds.extend(sorted(name for name in present if name not in CATEGORY_ORDER))
    return kinds


def _reasons(
    text: str, case_count: int, kinds: list[str], wants: dict[str, bool]
) -> list[str]:
    """What this one criterion is still missing, and nothing it never needed.

    A breadcrumb trail has no wrong input to give it and no limit to stand
    either side of. Asking for those two anyway filled the table with work
    nobody should do, and buried the criteria that really were thin.
    """
    if case_count == 0:
        return [NOT_COVERED]
    reasons = []
    enough = VISUAL_CASES if is_visual(text) else MIN_CASES
    if case_count < enough:
        reasons.append(ONLY_ONE)
    for kind in DEPTH_KINDS:
        if wants[kind] and kind not in kinds:
            reasons.append(NO_KIND[kind])
    return reasons


def compute_depth(result: TestCaseList, criteria: list[Criterion]) -> DepthReport:
    """How well each criterion is tested. Counted from the cases, never from the summary."""
    valid_ids = {criterion.id for criterion in criteria}
    cases_by_id: dict[str, list] = {criterion.id: [] for criterion in criteria}
    for test_case in result.test_cases:
        for ac_id in traced_ids(test_case, valid_ids):
            cases_by_id[ac_id].append(test_case)

    rows = []
    for criterion in criteria:
        cases = cases_by_id[criterion.id]
        kinds = _ordered_kinds([case.category for case in cases])
        wants = {
            "Negative": needs_wrong_input_test(criterion.text),
            "Boundary": needs_limit_test(criterion.text),
        }
        reasons = _reasons(criterion.text, len(cases), kinds, wants)
        rows.append(
            CriterionDepth(
                id=criterion.id,
                text=criterion.text,
                case_ids=[case.id for case in cases],
                kinds=kinds,
                reasons=reasons,
                thin=bool(reasons),
                needs_wrong_input=wants["Negative"],
                needs_limit=wants["Boundary"],
            )
        )
    return DepthReport(rows=rows, thin_ids=[row.id for row in rows if row.thin])


def reason_counts(report: DepthReport) -> list[tuple[str, int]]:
    """How many criteria each reason applies to, commonest first.

    A criterion can need more than one thing, so the counts are per reason and
    do not add up to the number of criteria.
    """
    counts = {reason: 0 for reason in REASON_ORDER}
    for row in report.rows:
        for reason in row.reasons:
            if reason in counts:
                counts[reason] += 1
    found = [(reason, count) for reason, count in counts.items() if count]
    return sorted(found, key=lambda pair: (-pair[1], REASON_ORDER.index(pair[0])))


def summary_line(report: DepthReport) -> str:
    """One sentence saying what is really missing, built from the rows.

    The old sentence said every thin criterion had no negative or boundary
    case, which a suite with twelve boundary cases makes a plain untruth.
    """
    total = len(report.rows)
    thin = len(report.thin_ids)
    if not total:
        return ""
    if not thin:
        return "Every criterion has the tests it needs."
    parts = [
        f"{count} {'has' if count == 1 else 'have'} {reason}"
        for reason, count in reason_counts(report)[:MAX_REASONS_IN_LINE]
    ]
    word = "criterion" if total == 1 else "criteria"
    needs = "needs" if thin == 1 else "need"
    return f"{thin} of {total} {word} {needs} more tests — {', '.join(parts)}."
