"""What the principal QA asks for before the AI call, and adds after it.

Everything here is plain Python over the rule packs: deterministic, no AI, no
key, no network, and fast enough to sit inside the request the user already
started. Nothing the AI wrote is ever modified — only added to.
"""

import re
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from functools import lru_cache

from qagenius.automation_checks import Finding, ProjectFile
from qagenius.models import (
    AutomationScript,
    FailureMode,
    RiskAnalysis,
    TestCase,
    TestCaseList,
)
from qagenius.shadow_qa.boundaries import (
    COUNT_UNIT_NAMES,
    CURRENCIES,
    LOOSE_COUNT,
    MONEY_ANY,
    Boundary,
    case_text,
    find_boundaries,
    missing_values,
    over_in,
    scan,
    states,
    states_value,
    value_quantity,
)
from qagenius.shadow_qa.detect import PackHit, detect_hits, mentions, story_text
from qagenius.shadow_qa.packs import SEVERITY_RANK, Check, PackRisk
from qagenius.test_case_diff import STOPWORDS, normalised_words, title_score
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
# How many of a pack risk's own words an AI risk has to say, in its effect or
# its cause, before the two are treated as one risk. One word is a coincidence.
MIN_SHARED_RISK_WORDS = 2
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
    # Cases that expect the opposite of the limit their criterion states.
    # The most valuable thing on the card, so it is shown first.
    conflicts: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Before the AI call
# ──────────────────────────────────────────────────────────────────────────────


def applies(check: Check, text: str) -> bool:
    """Is this check about anything the story actually mentions?

    Most checks apply to every build of their feature. A few are about one
    narrow thing -- the language an email is written in, rounding a second
    currency -- and asking for a test of it when the story never raised it
    wastes a case and makes the reviewer look like it is not reading.
    """
    if not check.only_if:
        return True
    return any(mentions(text, word) for word in check.only_if)


def _ordered_checks(active: list[PackHit], text: str) -> list[Check]:
    """Every active pack's checks that this story is about, worst first.

    Severity decides first. Then a pack the story named out loud comes before
    one found only in a criterion: "upload an avatar" in the story is the
    feature, "the file name is shown" in AC-7 is a detail of something else.
    """
    rank = {
        hit.pack.id: (0 if hit.in_story else 1, index)
        for index, hit in enumerate(active)
    }
    checks = [
        check
        for hit in active
        for check in hit.pack.checks
        if applies(check, text)
    ]
    return sorted(
        checks,
        key=lambda check: (SEVERITY_RANK[check.severity], *rank[check.pack_id]),
    )


def about_the_feature(story: str, criteria: list[Criterion], context: str = "") -> str:
    """Everything said about this feature: the story, the context, the criteria.

    The context is where a feature is described -- "guests can use coupons",
    "used once per account" -- and a rule that waits for those words never
    hears them if only the story and the criteria are read.
    """
    said = str(context or "").strip()
    return story_text("\n".join([str(story or ""), said]) if said else story, criteria)


def checklist_block(
    story: str, criteria: list[Criterion], context: str = ""
) -> tuple[str, list[str]]:
    """The lines appended to the user prompt, and the check ids they ask for."""
    text = about_the_feature(story, criteria, context)
    boundaries = find_boundaries(criteria)[:MAX_CHECKLIST_BOUNDARIES]
    room = MAX_CHECKLIST_LINES - len(boundaries)
    lines: list[str] = []
    ids: list[str] = []
    for check in _ordered_checks(detect_hits(text, story), text):
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


def _check_covered(check: Check, cases: list[TestCase], whole: str) -> bool:
    """Did the AI already write a case for this check?

    The cases are searched as one body of text: a word that means the check
    is covered means it wherever it turns up, and one search over the suite
    beats one search per case while a user waits for the answer.
    """
    if _tagged(check.id, cases):
        return True
    return any(mentions(whole, word) for word in check.covered_if)


def _tokens(text: str) -> set[str]:
    parts = _WORDS.split(str(text or "").lower())
    return {part for part in parts if len(part) >= 3 and part not in STOPWORDS}


def _jaccard(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _most_words(criteria: list[Criterion], words) -> str | None:
    """The criterion saying most of these words, or None if none says any.

    Counting beats first-match: a lock-duration check shares "minutes" with
    the criterion about failed attempts and shares "lock duration" *and*
    "minutes" with the one that is actually about the duration. Criteria
    arrive in AC order, so a tie lands on the lower number.
    """
    best_id, best_score = None, 0
    for criterion in criteria:
        score = sum(1 for word in words if mentions(criterion.text, word))
        if score > best_score:
            best_id, best_score = criterion.id, score
    return best_id


def _traceability(check: Check, criteria: list[Criterion], hits: list[PackHit]) -> str:
    """Which criterion this added case belongs to.

    Shared words alone put "Attempts from two devices count against the same
    account" against the criterion about unlocking, because both sentences say
    "account". The check's own words come first, then the words that made its
    pack active, and only then raw overlap. Criteria are in AC order, so a tie
    always lands on the lower number.
    """
    if not criteria:
        return ""
    best = _most_words(criteria, check.covered_if)
    if best is not None:
        return best
    # Trigger words belong to the pack, not to this check, so counting them
    # only rewards a wordy criterion. First match, lowest AC number.
    triggers = next(
        (hit.triggers for hit in hits if hit.pack.id == check.pack_id), []
    )
    for criterion in criteria:
        if any(mentions(criterion.text, word) for word in triggers):
            return criterion.id
    subject = f"{check.title} {check.test.title}"
    best = max(criteria, key=lambda item: _jaccard(subject, item.text))
    if _jaccard(subject, best.text) > 0:
        return best.id
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
        traceability=_traceability(check, criteria, hits),
    )


# ── a limit case written from the criterion's own words ──────────────────────

# What a criterion asks the user to do. The test is built from the first of
# these it says, so the steps are the criterion's own actions.
_ACTIONS = (
    "upload", "select", "choose", "attach", "add", "enter", "type", "submit",
    "send", "pick", "set", "drag", "paste", "crop",
)
_ACTION_RE = re.compile(
    r"(?<![\w-])(?:" + "|".join(_ACTIONS) + r")(?:s|es|ing)?(?![\w-])",
    re.IGNORECASE,
)
# The words a limit is introduced by, swapped out with the limit itself for
# the value under test: "under 2 megabytes" becomes "of 1.99 MB".
_LIMIT_LEAD = (
    r"(?:of\s+|under\s+|over\s+|below\s+|above\s+|within\s+|up\s+to\s+|"
    r"at\s+most\s+|at\s+least\s+|no\s+more\s+than\s+|no\s+fewer\s+than\s+|"
    r"larger\s+than\s+|bigger\s+than\s+|smaller\s+than\s+|more\s+than\s+|"
    r"less\s+than\s+|fewer\s+than\s+|exactly\s+|maximum\s+of\s+|minimum\s+of\s+)?"
)
# Where the thing being acted on stops and the rest of the sentence begins.
_OBJECT_END = re.compile(
    r"(?<![\w-])(?:under|over|below|above|larger|bigger|smaller|more|less|"
    r"fewer|at|up|within|no|maximum|minimum|with|that|which|and|or|from|into|"
    r"when|if|then|is|are|of|to|in|on|for)(?![\w-])",
    re.IGNORECASE,
)
_ARTICLE = re.compile(r"^(?:a|an|the|their|its|his|her|your|my)\s+", re.IGNORECASE)
# A page is named for the thing it holds, not by "the", "this" or "next".
_PAGE_NAME = re.compile(r"(?<![\w-])([a-z][\w-]*)\s+page(?![\w-])", re.IGNORECASE)
_NOT_A_PAGE = frozenset(
    """the a an this that these those next last first same one per each other
    every any some no new old whole entire second third single""".split()
)
# A criterion that says what happens when the limit is passed.
_REFUSES = (
    "reject", "rejects", "rejected", "refuse", "refuses", "refused",
    "declined", "denied", "blocked", "not allowed", "not accepted",
    "too large", "too big", "too long", "too many", "error",
)


@dataclass(frozen=True)
class Setting:
    """What the whole run knows that one criterion does not: where this is."""

    page: str  # "the profile page", or "" when nothing says
    criteria: list[Criterion]
    # How each criterion reads its own limit value, and the values the
    # criteria argue about. Written "LimitRule" because the rules are read
    # further down the file than the case that needs them.
    rules: "tuple[LimitRule, ...]" = ()
    disputed: frozenset[str] = frozenset()


def page_in(texts: list[str]) -> str:
    """The page these sentences keep naming, if they name one.

    The story rarely says where a criterion happens, but the AI's own cases
    almost always do ("Open the profile page"), so they are read too.
    """
    counts: dict[str, int] = {}
    for text in texts:
        for found in _PAGE_NAME.finditer(str(text or "")):
            word = found.group(1).lower()
            if word in _NOT_A_PAGE:
                continue
            counts[word] = counts.get(word, 0) + 1
    if not counts:
        return ""
    best = max(counts.items(), key=lambda pair: (pair[1], -len(pair[0])))
    return f"the {best[0]} page"


def _action_phrase(text: str) -> str:
    """The criterion from its first action onwards, or nothing."""
    found = _ACTION_RE.search(str(text or ""))
    return str(text or "")[found.start():].strip(" .;,") if found else ""


def _object_of(action: str) -> str:
    """What the action is done to: "select a JPEG photo …" -> "JPEG photo"."""
    rest = action.split(None, 1)[1] if " " in action else ""
    end = _OBJECT_END.search(rest)
    words = (rest[: end.start()] if end else rest).strip(" ,.;:")
    words = _ARTICLE.sub("", words)
    return words if 1 <= len(words.split()) <= 4 else ""


def _says_limit(line: str, limit: str) -> bool:
    """Does this line state the limit, with or without its leading words?"""
    return bool(
        re.search(_LIMIT_LEAD + re.escape(limit), str(line or ""), re.IGNORECASE)
    )


def _at_value(action: str, limit: str, value: str) -> str:
    """The criterion's action with the limit swapped for the value tested."""
    swap = re.compile(_LIMIT_LEAD + re.escape(limit), re.IGNORECASE)
    if swap.search(action):
        return swap.sub(f"of {value}", action, count=1)
    return f"{action} at {value}"


def _sentence(text: str) -> str:
    text = str(text or "").strip()
    if not text:
        return ""
    text = text[0].upper() + text[1:]
    return text if text.endswith((".", "!", "?")) else text + "."


def _refusing_criterion(
    boundary: Boundary, setting: Setting
) -> Criterion | None:
    """The criterion that says what happens past this limit, if there is one."""
    for criterion in setting.criteria:
        if criterion.id == boundary.source:
            continue
        if not any(mentions(criterion.text, word) for word in _REFUSES):
            continue
        if states_value(criterion.text, boundary.values[1]):
            return criterion
    return None


# A criterion written as Given / When / Then, with each "and" continuing the
# part it follows. Most criteria are one sentence; the ones that are not are
# already the test, written out, and worth following exactly.
_GWT_WORD = re.compile(r"(?<![\w-])(given|when|then|and|but)(?![\w-])", re.IGNORECASE)
MIN_WHEN_WORDS = 3
# "The user selects…" -> "Select…": who does it is not a step.
_DOER = re.compile(
    r"^\s*(?:the\s+|a\s+|an\s+)?(?:user|users|shopper|shoppers|reader|readers|"
    r"customer|customers|admin|admins|visitor|tester|they|he|she|system)\s+"
    r"(?:can\s+|may\s+|must\s+|should\s+|is\s+able\s+to\s+|are\s+able\s+to\s+|"
    r"will\s+|then\s+)?",
    re.IGNORECASE,
)


def given_when_then(text: str) -> tuple[list[str], list[str], list[str]]:
    """The criterion's parts, one line each, "and" lines kept where they fell."""
    parts: dict[str, list[str]] = {"given": [], "when": [], "then": []}
    said = str(text or "")
    current: str | None = None
    position = 0
    pieces: list[tuple[str, str]] = []
    for found in _GWT_WORD.finditer(said):
        word = found.group(1).lower()
        if word in ("and", "but"):
            # An "and" before any keyword is just a conjunction in a sentence.
            if current is None:
                continue
            pieces.append((current, said[position:found.start()]))
        else:
            if current is not None:
                pieces.append((current, said[position:found.start()]))
            current = word
        position = found.end()
    if current is not None:
        pieces.append((current, said[position:]))
    for key, chunk in pieces:
        line = chunk.strip().strip(",;:. ")
        if line:
            parts[key].append(line)
    if len(" ".join(parts["when"]).split()) < MIN_WHEN_WORDS:
        parts["when"] = []
    return parts["given"], parts["when"], parts["then"]


def _imperative(line: str) -> str:
    """One Given/When line as a step: "the user selects x" -> "Select x"."""
    said = _DOER.sub("", str(line or "").strip())
    if not said:
        return ""
    head, _, tail = said.partition(" ")
    # "selects" -> "select", "uploads" -> "upload". Only a plain "s" comes
    # off, so "address" and "process" are left alone.
    if head.lower().endswith("s") and not head.lower().endswith("ss"):
        head = head[:-1]
    return _sentence(" ".join(filter(None, [head, tail])))


def _subject_of(text: str, phrase: str) -> str:
    """What the criterion is about, from in front of the limit it states."""
    found = re.search(re.escape(phrase), str(text or ""), re.IGNORECASE)
    lead = (text[: found.start()] if found else str(text or "")).strip()
    words = lead.split()
    if not words:
        return ""
    # The last few words before the limit are the thing being limited.
    kept = " ".join(words[-3:]).strip(" ,.;:")
    kept = _LIMIT_LEAD_WORDS.sub("", kept).strip()
    kept = _ARTICLE.sub("", kept)
    return kept if 1 <= len(kept.split()) <= 3 else ""


_LIMIT_LEAD_WORDS = re.compile(
    r"(?:is|are|of|at|to|than|no|not)?\s*(?:under|over|below|above|larger|"
    r"bigger|smaller|more|less|fewer|within|up|most|least|maximum|minimum|"
    r"exactly|than)\s*$",
    re.IGNORECASE,
)


_A_NUMBER_IN = re.compile(r"\d")


_THE_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _phrase_at(boundary: Boundary, value: str) -> str:
    """The criterion's own phrase with the value's number in it."""
    number = value.split(" ", 1)[0]
    return _THE_NUMBER.sub(number, boundary.phrase, count=1)


def _then_outcome(criterion: Criterion | None) -> str:
    """What the criterion says should happen, in its own words."""
    if criterion is None:
        return ""
    _, _, then = given_when_then(criterion.text)
    return "; ".join(then)


DISPUTED_OUTCOME = "Not decided yet — see the note above."


def _accepting_criterion(boundary: Boundary, setting: Setting) -> Criterion | None:
    """A criterion that says what happens when a value inside the limit is used."""
    for rule in setting.rules:
        if rule.source == boundary.source or rule.rejects_over:
            continue
        if rule.value != boundary.values[1]:
            continue
        found = next(
            (one for one in setting.criteria if one.id == rule.source), None
        )
        if found is not None and _then_outcome(found):
            return found
    return None


def _goes_through(boundary: Boundary, value: str, setting: Setting) -> str:
    """What the criterion says happens when the value is inside the limit."""
    rule = _rule_for(boundary, setting)
    # A criterion written from the refusing side -- "larger than 2 MB is
    # rejected" -- says what happens past the limit, never what happens
    # inside it. Its own words would be the opposite of this answer.
    if rule is None or not rule.rejects_over:
        mine = next(
            (one for one in setting.criteria if one.id == boundary.source), None
        )
        said = _then_outcome(mine)
        if said:
            return said
    other = _accepting_criterion(boundary, setting)
    if other is not None:
        return f"{_then_outcome(other)} ({other.id})"
    if rule is not None and rule.rejects_over:
        return f"{value} is inside the limit {boundary.source} states, so it is accepted"
    return f"{boundary.source} still holds at {value}"


def _is_refused(
    boundary: Boundary, value: str, setting: Setting, at_limit: bool = False
) -> str:
    """What happens when the value is outside it, from the criterion that says so."""
    refuses = _refusing_criterion(boundary, setting)
    if refuses is not None:
        said = _then_outcome(refuses)
        if said:
            return f"{said} ({refuses.id})"
        tail = refuses.text.strip().rstrip(".")
        return f"{refuses.id} applies at {value}: {tail[0].lower() + tail[1:]}"
    rule = _rule_for(boundary, setting)
    # At the limit itself, the criterion's own words say why it is refused.
    if at_limit and rule is not None:
        return f'{value} is refused: {boundary.source} says "{rule.phrase}"'
    # A minimum is missed from underneath, not passed from above.
    short = rule is not None and rule.accepts_above
    where = "below" if short else "past"
    return f"{value} is {where} the limit {boundary.source} states, so it is refused"


def _rule_for(boundary: Boundary, setting: Setting) -> "LimitRule | None":
    """How the criterion that states this limit reads its own limit value."""
    return next(
        (
            one
            for one in setting.rules
            if one.source == boundary.source and one.value == boundary.values[1]
        ),
        None,
    )


def _at_the_limit(boundary: Boundary, value: str, setting: Setting) -> str:
    """What should happen at the limit value itself.

    The criterion decides, and it is read exactly as the conflict notes read
    it: "up to 2 MB" accepts a 2 MB photo, "under 2 megabytes" refuses one.
    Asking for a test that expects the wrong one is the mistake this whole
    reviewer exists to catch, so it must not make it itself.
    """
    if boundary.values[1] in setting.disputed:
        return DISPUTED_OUTCOME
    rule = _rule_for(boundary, setting)
    if rule is None:
        return f"{boundary.source} still holds at exactly {value}"
    if rule.allowed:
        return _goes_through(boundary, value, setting)
    return _is_refused(boundary, value, setting, at_limit=True)


CENT = Decimal("0.01")


def _plain(amount: float) -> str:
    """20.0 -> "20", 12.5 -> "12.5": a rate said the way a coupon says it."""
    return f"{amount:g}"


def _to_the_cent(amount: Decimal, rounding: str) -> str:
    return f"{amount.quantize(CENT, rounding=rounding):f}"


def _every_digit(amount: Decimal) -> str:
    """The amount with every digit it really has, and never fewer than cents.

    $29.998 is the number the argument is about, and writing it as $30.00
    here would hide the very cent the test is being asked to settle.
    """
    whole, _, cents = format(amount.normalize(), "f").partition(".")
    return f"{whole}.{cents.ljust(2, '0')}"


def _cap_outcome(boundary: Boundary, value: str) -> str:
    """What a capped percentage really takes off at this one order total.

    The three values around a cap are the one place the checklist can do the
    sum itself instead of asking a tester to, and the cent it rounds to is
    the half of the sum two systems can disagree about.
    """
    symbol = value[:1]
    rate = Decimal(_plain(boundary.rate)) / 100
    cap = Decimal(_plain(boundary.cap))
    raw = rate * Decimal(value[1:])
    percent = f"{_plain(boundary.rate)}%"
    if raw > cap:
        return (
            f"{percent} is {symbol}{_every_digit(raw)}, so the cap applies "
            f"and the discount stays {symbol}{_every_digit(cap)}"
        )
    if raw == cap:
        return f"{percent} is exactly {symbol}{_every_digit(raw)} — the cap"
    up = _to_the_cent(raw, ROUND_HALF_UP)
    down = _to_the_cent(raw, ROUND_DOWN)
    if up == down:
        return f"{percent} is {symbol}{up}, so the discount is {symbol}{up}"
    return (
        f"{percent} is {symbol}{_every_digit(raw)}, so the discount is "
        f"{symbol}{up} after rounding to the cent — check the shop rounds "
        f"this way (it could also be {symbol}{down})"
    )


# The words that turn a stretch of time into a window the rule watches:
# "5 wrong passwords within 10 minutes".
_WINDOW_LEAD = re.compile(
    r"(?:with ?in|inside|over|during|across|in)\s+"
    r"(?:a\s+|an\s+|the\s+|any\s+|each\s+|every\s+|the\s+last\s+|"
    r"a\s+rolling\s+|a\s+single\s+)?$",
    re.IGNORECASE,
)
_WINDOW_WORD = re.compile(r"(?<![\w-])window(?![\w-])", re.IGNORECASE)
# "the account is locked" -> "the account is NOT locked".
_TO_NEGATE = re.compile(r"(?<![\w-])(is|are|was|were|gets|get|becomes)(?![\w-])")


@lru_cache(maxsize=256)
def _counts_something(text: str) -> bool:
    """Does this criterion count a number of things, as well as name a time?"""
    return any(
        one.kind == "count" for one in find_boundaries([Criterion("x", text)])
    )


def _consequence(text: str) -> str:
    """What a one-sentence criterion says happens, when it has no Then.

    "After 5 wrong passwords within 10 minutes, the account is locked" never
    says "then", and the clause after the comma is the whole point of it.
    """
    _, comma, tail = str(text or "").strip().rstrip(".").rpartition(",")
    said = tail.strip()
    return said if comma and len(said.split()) >= 3 else ""


def is_window(boundary: Boundary, text: str) -> bool:
    """Is this duration the stretch a count is measured over?

    A limit bites past its number; a window stops applying past its own.
    "5 wrong passwords within 10 minutes" locks the account, and the same
    five spread over 11 minutes do not, because the rule never reaches
    them. Only a duration that a count is counted inside is read this way,
    so "the page loads in 2 seconds" stays the limit it is.
    """
    if boundary.kind != "duration":
        return False
    said = str(text or "")
    if not _counts_something(said):
        return False
    if _WINDOW_WORD.search(said):
        return True
    for found in re.finditer(re.escape(boundary.phrase), said, re.IGNORECASE):
        if _WINDOW_LEAD.search(said[: found.start()]):
            return True
    return False


# A state with an end, and whether the thing works while it holds. A lock
# ending lets the shopper in; a validity ending shuts them out, so the
# sense of the state has to travel with its name.
_STATES: dict[str, bool] = {
    "locked": False, "blocked": False, "suspended": False, "disabled": False,
    "frozen": False, "banned": False, "barred": False, "restricted": False,
    "paused": False, "hidden": False, "unavailable": False, "throttled": False,
    "valid": True, "active": True, "available": True, "usable": True,
    "enabled": True, "unlocked": True, "live": True, "open": True,
}
# What the same states are called as a thing rather than a state, for
# "the lock lasts 30 minutes".
_STATE_NOUNS = {
    "lock": "locked", "lockout": "locked", "block": "blocked",
    "suspension": "suspended", "ban": "banned", "freeze": "frozen",
    "validity": "valid", "pause": "paused",
}
# "locked for 15 minutes", "stays valid for 30 days".
_LASTS_FOR = re.compile(
    r"(?<![\w-])(" + "|".join(_STATES) + r")\b"
    r"(?:\s+[\w-]+){0,2}?\s+for\s+(?:a\s+|an\s+|the\s+)?$",
    re.IGNORECASE,
)
# "expires after 30 days": whatever it is was valid until then.
_EXPIRES_AFTER = re.compile(
    r"(?<![\w-])expir(?:es|e|ed|ing)\s+(?:after|in)\s+(?:a\s+|an\s+|the\s+)?$",
    re.IGNORECASE,
)
# "the lock lasts 30 minutes": the state is named elsewhere in the sentence.
_LASTS = re.compile(
    r"(?<![\w-])lasts?\s+(?:for\s+)?(?:a\s+|an\s+|the\s+)?$", re.IGNORECASE
)
# "30 minutes have not yet passed": the same stretch said from the other
# side, with the state named in the same sentence ("a locked account").
_PASSES_AFTER = re.compile(
    r"^\s*(?:have|has)\s+(?:not\s+yet\s+|not\s+|yet\s+)?(?:passed|elapsed|gone\b)",
    re.IGNORECASE,
)
_LOOK_BACK_FOR_A_STATE = 40
# A criterion about the moment a state runs out, rather than about the state.
_ENDED_WORDS = (
    "passed", "elapsed", "expired", "expires", "over", "ends", "ended",
    "later", "afterwards", "once", "has passed", "have passed",
)


def _state_named_in(text: str) -> tuple[str, bool] | None:
    """The state a sentence names, as a state word and what it allows."""
    for word, allows in _STATES.items():
        if mentions(text, word):
            return word, allows
    for noun, word in _STATE_NOUNS.items():
        if mentions(text, noun):
            return word, _STATES[word]
    return None


def lasting_state(boundary: Boundary, text: str) -> tuple[str, bool] | None:
    """The state this duration says how long lasts, and what it allows.

    "locked for 15 minutes" and "valid for 30 days" both name a state with
    an end, not a limit on a value: before the number the state holds, at
    it the state runs out, and after it the state is over. That is the
    opposite of a limit, where past the number is where the rule bites.
    """
    if boundary.kind != "duration":
        return None
    said = str(text or "")
    for found in re.finditer(re.escape(boundary.phrase), said, re.IGNORECASE):
        before = said[max(0, found.start() - _LOOK_BACK_FOR_A_STATE): found.start()]
        named = _LASTS_FOR.search(before)
        if named is not None:
            word = named.group(1).lower()
            return word, _STATES[word]
        if _EXPIRES_AFTER.search(before):
            return "valid", True
        if _LASTS.search(before) or _PASSES_AFTER.match(said[found.end():]):
            state = _state_named_in(said)
            if state is not None:
                return state
    return None


def _ending_criterion(boundary: Boundary, setting: Setting) -> Criterion | None:
    """The criterion that says what happens once the duration has passed."""
    for criterion in setting.criteria:
        if criterion.id == boundary.source:
            continue
        if not states_value(criterion.text, boundary.values[1]):
            continue
        if not any(mentions(criterion.text, word) for word in _ENDED_WORDS):
            continue
        if _then_outcome(criterion):
            return criterion
    return None


def _duration_outcome(
    boundary: Boundary, value: str, index: int, setting: Setting
) -> str | None:
    """What a "lasts for N" duration says at this value, or None.

    A run asked for a test expecting a locked account to be refused at 31
    minutes of a 30-minute lock, which is the one minute at which the lock
    is over.
    """
    mine = next(
        (one for one in setting.criteria if one.id == boundary.source), None
    )
    if mine is None:
        return None
    found = lasting_state(boundary, mine.text)
    if found is None:
        return None
    state, allows = found
    limit = boundary.values[1]

    if index == 0:
        # While it holds, the criterion's own words say what that means --
        # unless they only say the state again, which tells a tester nothing
        # they could not read off the row above.
        said = _then_outcome(mine) or _consequence(mine.text)
        if said and mentions(said, state) and states_value(said, limit):
            said = ""
        said = said or ("it still works" if allows else "it is refused")
        return (
            f"{value} is inside the {limit} it stays {state}, so it is still "
            f"{state}: {said}"
        )

    ends = _ending_criterion(boundary, setting)
    over = _then_outcome(ends) if ends is not None else ""
    if index == 1:
        if over:
            return f"At exactly {limit} it stops being {state} ({ends.id}): {over}"
        # Nobody wrote the end down, so nobody can say which side of it
        # the moment itself falls on.
        return (
            f"Check what happens at exactly {limit} — the criteria do not say "
            f"whether it is still {state} the moment the time runs out"
        )
    said = over or ("it is refused" if allows else "it works again")
    return (
        f"{value} is past the {limit} it stays {state}, so it is no longer "
        f"{state}: {said}"
    )


def _not_happening(said: str) -> str:
    """The criterion's own outcome, said as the thing that does not happen."""
    found = _TO_NEGATE.search(said)
    if found:
        return said[: found.end()] + " NOT" + said[found.end():]
    return f"none of that happens ({said})"


def _window_outcome(
    boundary: Boundary, value: str, index: int, setting: Setting
) -> str | None:
    """What a window really says at this value, or None when it is not one."""
    mine = next(
        (one for one in setting.criteria if one.id == boundary.source), None
    )
    if mine is None or not is_window(boundary, mine.text):
        return None
    said = _then_outcome(mine) or _consequence(mine.text)
    limit = boundary.values[1]
    if index == 2:
        tail = f": {_not_happening(said)}" if said else ""
        return (
            f"{value} is outside the {limit} window {boundary.source} states, "
            f"so the rule does not apply{tail}"
        )
    tail = f": {said}" if said else ""
    where = "inside" if index == 0 else "the far edge of"
    return (
        f"{value} is {where} the {limit} window {boundary.source} states, "
        f"so the rule applies{tail}"
    )


def _boundary_outcome(boundary: Boundary, value: str, setting: Setting) -> str:
    """What should happen at this one value, in the criteria's own words."""
    # A cap boundary has no criterion to quote: nobody wrote its number down,
    # so the arithmetic that found it is also the answer.
    if boundary.rate is not None and boundary.cap is not None:
        return _cap_outcome(boundary, value)
    index = boundary.values.index(value)
    # Two durations are not limits at all: a stretch a count is measured
    # inside, and a stretch a state lasts. Past either number the rule
    # stops rather than bites, so both are answered before the limit logic.
    # A state that says how long it lasts goes first: "locked for 15
    # minutes" inside a criterion that also counts attempts is the lock,
    # not the window the attempts are counted in.
    lasting = _duration_outcome(boundary, value, index, setting)
    if lasting is not None:
        return lasting
    windowed = _window_outcome(boundary, value, index, setting)
    if windowed is not None:
        return windowed
    if index == 1:
        return _at_the_limit(boundary, value, setting)
    # Which end of the number works. A maximum -- "a photo under 2 MB" --
    # takes the value below and turns the one above away; a minimum -- "an
    # order of at least $50" -- does it the other way round, and writing a
    # $49.99 order down as a success is the mistake this file is here to stop.
    rule = _rule_for(boundary, setting)
    if (index == 2) == bool(rule is not None and rule.accepts_above):
        return _goes_through(boundary, value, setting)
    return _is_refused(boundary, value, setting)


def _boundary_expected(
    boundary: Boundary, missing: list[str], setting: Setting
) -> str:
    """What should happen, said once per value when there is more than one."""
    said = [_boundary_outcome(boundary, value, setting) for value in missing]
    if len(missing) == 1:
        return _sentence(said[0])
    # An outcome that opens with the value says which one it is already;
    # "At 29 minutes: 29 minutes is inside…" says it twice.
    return " ".join(
        _sentence(one if one.startswith(value) else f"At {value}: {one}")
        for value, one in zip(missing, said)
    )


def _boundary_steps(
    boundary: Boundary,
    missing: list[str],
    setting: Setting,
    criterion: Criterion | None,
) -> list[str]:
    """Steps anybody can run, out of the criterion's own words.

    The criterion is the test, written in English: its When lines are the
    steps and its Given lines are what has to be true first. Only a
    criterion that describes no doing at all falls back to a generic line,
    and never for a size, a count, a length or a time.
    """
    text = criterion.text if criterion else ""
    _, when, _ = given_when_then(text)
    if when:
        # Only the line that states the limit takes the value; "upload the
        # photo" is the same step whatever the photo weighs.
        steps = [
            step
            for value in missing
            for line in when
            if (
                step := _imperative(
                    _at_value(line, boundary.phrase, value)
                    if _says_limit(line, boundary.phrase)
                    else line
                )
            )
        ]
        if steps:
            return [*steps, "Check the result."]

    action = _action_phrase(text)
    if action:
        opening = (
            f"Open {setting.page}."
            if setting.page
            else f"Open the page {boundary.source} is about."
        )
        return [
            opening,
            *[_sentence(_at_value(action, boundary.phrase, value)) for value in missing],
            "Check the result.",
        ]

    # Nothing is done to a duration: it passes. Waiting it out is the step.
    if boundary.kind == "duration":
        return [*[f"Wait {value}." for value in missing], "Check the result."]

    # The criterion's own words for the limit, with the value in them:
    # "5 failed sign-in attempts" becomes "Reach 4 failed sign-in attempts."
    if _A_NUMBER_IN.search(boundary.phrase):
        return [
            *[_sentence(f"Reach {_phrase_at(boundary, value)}") for value in missing],
            "Check the result.",
        ]
    return [
        f"Set up the behaviour {boundary.source} describes",
        *[f"Exercise it at {value}" for value in missing],
    ]


def _case_from_boundary(
    boundary: Boundary, case_id: str, missing: list[str], setting: Setting
) -> TestCase:
    """A case for the values the AI left out -- and for no others.

    Naming all three when the AI already wrote two of them is how the
    reviewer ends up asking for a test that is already in the suite. And a
    step reading "exercise it at 1.99 MB" is not a test anybody can run, so
    the steps are written out of the criterion's own action and object.
    """
    criterion = next(
        (one for one in setting.criteria if one.id == boundary.source), None
    )
    text = criterion.text if criterion else ""
    thing = _object_of(_action_phrase(text))
    given, _, _ = given_when_then(text)
    listed = ", ".join(missing)
    return TestCase(
        id=case_id,
        title=(
            f"Boundary value{'s' if len(missing) > 1 else ''} at {' / '.join(missing)} "
            f"({boundary.source})"
        ),
        category="Boundary",
        # What has to be true first: the criterion's own Given lines when it
        # has them, the limit it states when it does not.
        pre_conditions=_sentence("; ".join(given))
        if given
        else (
            f"The system is set up with the limit {boundary.source} states: "
            f"{boundary.phrase}"
        ),
        steps=_boundary_steps(boundary, missing, setting, criterion),
        expected_result=_boundary_expected(boundary, missing, setting),
        priority="High",
        # The card already says "Data to use", so the values say themselves.
        test_data=f"{listed} ({thing})" if thing else listed,
        bdd_scenario=None,
        automation_feasibility="High",
        automation_effort="Low",
        tags=[PRINCIPAL_TAG, CHECK_TAG + f"boundary:{boundary.source}", "pack:boundary"],
        traceability=boundary.source,
    )


# ── a test that disagrees with the limit its criterion states ────────────────

# Words that take the limit value in with everything on its side...
_LIMIT_INCLUDES = (
    "up to", "at most", "maximum", "maximum of", "max", "no more than",
    "no larger than", "no bigger than", "no longer than", "or less",
    "or fewer", "or under", "at least", "no fewer than", "no less than",
    "minimum", "or more", "≤", "<=", "≥", ">=",
)
# Of those, the ones that count upwards from the value: everything at or over
# it is on the rule's side, and everything under it is not.
_LIMIT_INCLUDES_UP = (
    "at least", "no fewer than", "no less than", "minimum", "or more",
    "≥", ">=",
)
# ... and words that stop short of it, from below ...
_LIMIT_UNDER = (
    "under", "below", "less than", "fewer than", "smaller than",
    "shorter than", "<",
)
# ... or from above.
_LIMIT_OVER = (
    "more than", "over", "above", "larger than", "bigger than",
    "greater than", "longer than", "exceeds", "exceed", ">",
)
# What a case, or a criterion, says it expects to happen.
_EXPECTS_YES = (
    "accepted", "accept", "accepts", "saved", "saves", "succeeds", "succeed",
    "successful", "success", "uploaded", "uploads", "allowed", "shown",
    "created", "goes through", "applied", "applies", "works", "work",
)
_EXPECTS_NO = _REFUSES + ("fails", "failure", "message about", "not saved")

# The context is a rule-maker too, and it is quoted by its own name.
CONTEXT_ID = "Context"


@dataclass(frozen=True)
class LimitRule:
    """One limit a criterion states, and what it means at the value itself.

    A limit has two halves, and the words are only one of them: "more than
    $50" says nothing on its own. With "the discount is applied" after it, it
    means a $50 order gets nothing; with "the coupon is refused" after it, it
    means a $50 order is fine.
    """

    source: str  # "AC-1"
    value: str  # "$50.00"
    phrase: str  # "more than $50"
    thing: str  # "valid coupon code", or ""
    # "includes" takes the value in, "under" and "over" stop short of it.
    side: str
    # What the criterion says happens on its own side: accepted | refused | ""
    outcome: str

    @property
    def plain(self) -> str:
        """The value the way a person says it: "$50", not "$50.00"."""
        written = self.value
        return written[:-3] if written.endswith(".00") else written

    @property
    def rejects_over(self) -> bool:
        """Written from the refusing side: "larger than 2 MB is rejected"."""
        return self.side == "over" and self.outcome == "refused"

    @property
    def covers(self) -> bool:
        """Does the rule's own wording take the limit value in?"""
        return self.side == "includes"

    @property
    def counts_up(self) -> bool:
        """Is the rule's own side above the value, or below it?

        "more than $50" and "at least $50" are about the orders over the
        number; "under 2 MB" and "up to 2 MB" are about the files under it.
        """
        if self.side == "over":
            return True
        if self.side == "under":
            return False
        return any(mentions(self.phrase, word) for word in _LIMIT_INCLUDES_UP)

    @property
    def accepts_above(self) -> bool:
        """Is it the values over the limit that go through, or the ones under?

        The wording is only half of it. "More than $50 and the discount is
        applied" and "less than 2 MB and the upload is rejected" both point
        upwards; the same words with the other ending point down.
        """
        return not self.counts_up if self.outcome == "refused" else self.counts_up

    @property
    def verdict(self) -> str:
        """What this rule means happens at exactly the limit value."""
        if not self.outcome:
            return ""
        if self.covers:
            return self.outcome
        # It stops short of the value, so the value gets the other answer.
        return "refused" if self.outcome == "accepted" else "accepted"

    @property
    def allowed(self) -> bool:
        return self.verdict == "accepted"


def _limit_side(text: str) -> str:
    """Does the wording take the limit value in, or stop short of it?"""
    if any(mentions(text, word) for word in _LIMIT_INCLUDES):
        return "includes"
    if any(mentions(text, word) for word in _LIMIT_UNDER):
        return "under"
    if any(mentions(text, word) for word in _LIMIT_OVER):
        return "over"
    return ""


def _limit_outcome(criterion: Criterion) -> str:
    """Does this criterion end in the thing working, or being turned away?

    Almost every criterion describes the path that works, so a criterion
    whose words say neither is read that way: "a photo up to 2 MB can be
    uploaded" is a rule about what is allowed, not about what is refused.
    """
    _, _, then = given_when_then(criterion.text)
    return _expects_in(" ".join(then) if then else criterion.text) or "accepted"


_ALL_LIMIT_WORDS = tuple(
    sorted(_LIMIT_UNDER + _LIMIT_INCLUDES + _LIMIT_OVER, key=len, reverse=True)
)
_LOOK_BACK_FOR_A_LIMIT = 30


def _limit_phrase(text: str, boundary: Boundary) -> str:
    """The criterion's own words for the limit: "more than $50".

    The word that counts is the one in front of the number, not any limit
    word in the sentence: AC-2 says "less than $50" and then quotes a
    message that says "at least $50", and only the first one is its rule.
    """
    for found in re.finditer(re.escape(boundary.phrase), text, re.IGNORECASE):
        before = text[max(0, found.start() - _LOOK_BACK_FOR_A_LIMIT): found.start()]
        for word in _ALL_LIMIT_WORDS:
            lead = re.search(
                re.escape(word) + r"\s+(?:a\s+|an\s+|the\s+)?$", before, re.IGNORECASE
            )
            if lead:
                return (before[lead.start():] + found.group(0)).strip()
    return boundary.phrase


def with_context(criteria: list[Criterion], context: str) -> list[Criterion]:
    """The criteria the rules read: the written ones, and the context.

    The context is where the real limits often live -- "orders of at least
    $50" -- and a criterion that says something else about the same number
    is worth knowing about before anybody writes a test from either.
    """
    said = str(context or "").strip()
    if not said:
        return list(criteria or [])
    return [*(criteria or []), Criterion(id=CONTEXT_ID, text=said)]


def limit_rules(criteria: list[Criterion]) -> list[LimitRule]:
    """Every limit the criteria state, with what each means at the value."""
    rules: list[LimitRule] = []
    for criterion in criteria or []:
        side = _limit_side(criterion.text)
        if not side:
            continue
        outcome = _limit_outcome(criterion)
        thing = _object_of(_action_phrase(criterion.text))
        for boundary in find_boundaries([criterion]):
            phrase = _limit_phrase(criterion.text, boundary)
            rules.append(
                LimitRule(
                    source=criterion.id,
                    value=boundary.values[1],
                    phrase=phrase,
                    thing=thing,
                    # The words in front of this number, not the ones in
                    # front of some other number in the same sentence.
                    side=_limit_side(phrase) or side,
                    outcome=outcome,
                )
            )
    return rules


# One sentence ends and the next begins. A step is a sentence of its own.
_SENTENCE_END = re.compile(r"(?<=[.!?;])\s+|\n+")


def _sentences(parts: list[str]) -> list[str]:
    """Everything a case says, one sentence at a time."""
    said: list[str] = []
    for part in parts:
        for one in _SENTENCE_END.split(str(part or "")):
            line = one.strip()
            if line:
                said.append(line)
    return said


def _expects_in(sentence: str) -> str:
    """Does this sentence expect the thing to go through, or be turned away?"""
    yes = any(mentions(sentence, word) for word in _EXPECTS_YES)
    no = any(mentions(sentence, word) for word in _EXPECTS_NO)
    if yes and not no:
        return "accepted"
    if no and not yes:
        return "refused"
    return ""


def _plural(thing: str) -> str:
    return thing if not thing or thing.endswith("s") else thing + "s"


def gap_pairs(rules: list[LimitRule]) -> list[tuple[LimitRule, LimitRule]]:
    """Values that one rule steps over and another stops short of.

    "More than $50 works" and "less than $50 is refused" leave exactly $50
    in neither. Nobody wrote the answer down, so nobody can test it, and the
    first shopper with a $50 cart finds out what the code happens to do.
    """
    pairs: list[tuple[LimitRule, LimitRule]] = []
    settled: set[str] = set()
    for over in [one for one in rules if one.side == "over" and one.outcome == "accepted"]:
        if over.value in settled:
            continue
        under = next(
            (
                one
                for one in rules
                if one.side == "under"
                and one.outcome == "refused"
                and one.value == over.value
                and one.source != over.source
            ),
            None,
        )
        if under is None:
            continue
        settled.add(over.value)
        pairs.append((over, under))
    return pairs


def disputed_pairs(rules: list[LimitRule]) -> list[tuple[LimitRule, LimitRule]]:
    """Pairs of rules that say the opposite about the limit value itself.

    "Under 2 megabytes" and "larger than 2 megabytes is rejected" cannot both
    be right about a photo of exactly 2 MB, and every test written from
    either of them inherits the argument. A value already reported as a gap
    is not reported again here.
    """
    pairs: list[tuple[LimitRule, LimitRule]] = []
    # The pair already reported as a gap is not reported again, but another
    # rule about the same value still has something of its own to say. One
    # note per value is enough, and the context gets one of its own, because
    # "the context says otherwise" is a different thing to go and fix.
    gapped = {
        (one.value, frozenset({one.source, two.source}))
        for one, two in gap_pairs(rules)
    }
    settled: set[tuple[str, bool]] = set()
    for refused in [one for one in rules if one.verdict == "refused"]:
        for accepted in rules:
            if accepted.verdict != "accepted" or accepted.value != refused.value:
                continue
            if accepted.source == refused.source:
                continue
            sources = frozenset({accepted.source, refused.source})
            if (refused.value, sources) in gapped:
                continue
            from_context = CONTEXT_ID in sources
            if (refused.value, from_context) in settled:
                continue
            settled.add((refused.value, from_context))
            pairs.append((refused, accepted))
            break
    return pairs


def undecided_values(rules: list[LimitRule]) -> set[str]:
    """Every limit value nobody has settled: a gap or an argument."""
    found = {one.value for one, _ in gap_pairs(rules)}
    found.update(one.value for one, _ in disputed_pairs(rules))
    return found


def _gap_notes(rules: list[LimitRule]) -> list[str]:
    notes = []
    for over, under in gap_pairs(rules):
        notes.append(
            f'{over.source} covers "{over.phrase}" and {under.source} covers '
            f'"{under.phrase}". Nobody says what happens at exactly '
            f"{over.plain}. Decide, then add it to a criterion."
        )
    return notes


def _criteria_conflicts(rules: list[LimitRule]) -> list[str]:
    """What each of those disagreements reads as on the page."""
    notes: list[str] = []
    for refused, accepted in disputed_pairs(rules):
        # The context is quoted as the context, and it leads: it is the rule
        # everything else was supposed to be written from.
        if accepted.source == CONTEXT_ID or refused.source == CONTEXT_ID:
            context = accepted if accepted.source == CONTEXT_ID else refused
            other = refused if context is accepted else accepted
            works = "works" if context.allowed else "doesn't"
            then = "doesn't" if context.allowed else "works"
            notes.append(
                f'The context says "{context.phrase}" (so exactly '
                f'{context.plain} {works}) but {other.source} says '
                f'"{other.phrase}" (so exactly {context.plain} {then}). '
                f"Decide which is right."
            )
            continue
        if accepted.rejects_over:
            thing = f"{_plural(accepted.thing)} " if accepted.thing else ""
            middle = f'{accepted.source} only refuses {thing}"{accepted.phrase}"'
        else:
            middle = f'{accepted.source} allows "{accepted.phrase}"'
        notes.append(
            f'{refused.source} says "{refused.phrase}" (so exactly {refused.plain} '
            f"is refused) but {middle} (so exactly {refused.plain} is accepted). "
            f"Decide which is right."
        )
    return notes


def _ordinal(number: float) -> str:
    """6.0 -> "6th", the way a tester narrates the try that locks them out."""
    whole = int(number)
    if 10 <= whole % 100 <= 20:
        return f"{whole}th"
    return f"{whole}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(whole % 10, 'th') }"


def _trigger_count(case: TestCase) -> float | None:
    """The count at which a case expects the rule to bite, if it says one.

    Read from the steps, the data and the expected result -- never from the
    title, which names the rule rather than the run.
    """
    text = " \n ".join(
        [*(case.steps or []), str(case.test_data or ""), str(case.expected_result or "")]
    )
    counted = [
        amount
        for unit, amount in scan(text)
        if unit in COUNT_UNIT_NAMES or unit == LOOSE_COUNT
    ]
    # The run ends on the try that trips the rule, so the highest count a
    # case names is the one it expects to be refused on.
    return max(counted) if counted else None


def trigger_disagreements(cases: list[TestCase]) -> list[str]:
    """Two cases for one criterion that fire the same rule at different counts.

    A real run had TC-001 locking the account on the 6th wrong password and
    TC-007 locking it on the 5th. Both passed review on their own; together
    they say the suite does not know what the rule is.
    """
    by_criterion: dict[str, list[tuple[TestCase, float]]] = {}
    for case in cases or []:
        if _expects_in(str(case.expected_result or "")) != "refused":
            continue
        count = _trigger_count(case)
        if count is None:
            continue
        key = str(case.traceability or "").strip()
        if not key:
            continue
        by_criterion.setdefault(key, []).append((case, count))

    notes: list[str] = []
    for source, found in by_criterion.items():
        counts = {count for _, count in found}
        if len(counts) < 2:
            continue
        first, second = found[0], next(
            pair for pair in found if pair[1] != found[0][1]
        )
        notes.append(
            f"{first[0].id} expects {source} to apply on the "
            f"{_ordinal(first[1])} try, {second[0].id} on the "
            f"{_ordinal(second[1])}. Decide which is right."
        )
    return notes


# A money amount written to the cent, with or without a currency in front.
_CENTS = re.compile(r"(?<![\w.])([$\u20ac\u00a3]?)(\d+\.\d\d)(?![\d])")
# The two halves of a percentage sum: "20% of $150".
_RATE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent)", re.IGNORECASE)


def _money_in(text: str) -> list[Decimal]:
    """Every amount written to the cent in this text."""
    return [Decimal(found.group(2)) for found in _CENTS.finditer(str(text or ""))]


def _rate_in(text: str) -> Decimal | None:
    found = _RATE.search(str(text or ""))
    return Decimal(found.group(1)) if found else None


def rounding_notes(cases: list[TestCase]) -> list[str]:
    """Two cases that take the same percentage of the same amount and differ.

    A run had one case expect $8.99 off a $59.99 cart and another expect
    $9.00 off the same cart from the same 15% coupon. Both read fine on
    their own; together they say nobody has decided how the shop rounds.
    """
    # (rate, the amount it is taken from) -> the cases and what each expects
    seen: dict[tuple[str, str], list[tuple[str, Decimal]]] = {}
    for case in cases or []:
        text = " ".join(
            [str(case.test_data or ""), str(case.pre_conditions or ""), str(case.title or "")]
        )
        rate = _rate_in(text) or _rate_in(str(case.expected_result or ""))
        if rate is None:
            continue
        totals = _money_in(text)
        if not totals:
            continue
        base = max(totals)
        raw = (rate / 100) * base
        for expected in _money_in(case.expected_result):
            # Only an amount this sum could really have produced counts: the
            # cart total itself is in the sentence too.
            if abs(expected - raw) > CENT:
                continue
            key = (f"{rate:f}", f"{base:f}")
            seen.setdefault(key, []).append((case.id, expected))

    notes: list[str] = []
    for (rate, base), found in seen.items():
        amounts = {amount for _, amount in found}
        if len(amounts) < 2:
            continue
        first, second = found[0], next(one for one in found if one[1] != found[0][1])
        notes.append(
            f"{first[0]} expects {first[1]:.2f} off and {second[0]} expects "
            f"{second[1]:.2f} off the same {_plain(float(Decimal(rate)))}% of "
            f"{Decimal(base):.2f}. Decide how the shop rounds the cent, then "
            f"fix the one that is wrong."
        )
    return notes


def precondition_notes(
    criteria: list[Criterion], cases: list[TestCase]
) -> list[str]:
    """A success test whose own data breaks the rule it is testing.

    A run wrote TC-008 with a $19.99 cart for a coupon that needs at least
    $50, and expected the discount to apply. The test cannot pass as
    written, whatever the code does.
    """
    rules = [one for one in limit_rules(criteria) if one.outcome == "accepted"]
    if not rules:
        return []
    notes: list[str] = []
    for case in cases or []:
        if _expects_in(str(case.expected_result or "")) != "accepted":
            continue
        said = scan(
            " ".join([str(case.test_data or ""), str(case.pre_conditions or "")])
        )
        for rule in rules:
            wanted = value_quantity(rule.value)
            if wanted is None:
                continue
            unit, limit = wanted
            used = [number for other, number in said if other in _matching_units(unit)]
            if not used:
                continue
            # The rule's own side says which way its precondition runs.
            short = min(used) < limit if rule.counts_up else max(used) > limit
            if not short:
                continue
            value = min(used) if rule.counts_up else max(used)
            notes.append(
                f"{case.id} uses {_said_as(unit, value)}, but {rule.source} needs "
                f'"{rule.phrase}" — this test can\'t pass as written.'
            )
            break
    return notes


def _matching_units(unit: str) -> set[str]:
    """The units an amount of this kind could have been written in."""
    if unit in CURRENCIES:
        return {unit, MONEY_ANY}
    return {unit}


def _said_as(unit: str, amount: float) -> str:
    """"$19.99", or "19.99 minutes" when the unit is not a currency."""
    if unit in CURRENCIES:
        return f"{unit}{amount:.2f}"
    if unit == MONEY_ANY:
        return f"{amount:.2f}"
    return f"{_plain(amount)} {unit}"


def limit_conflicts(criteria: list[Criterion], cases: list[TestCase]) -> list[str]:
    """Where the limit value itself is argued about: by a test, or by the criteria.

    The run this came from: AC-1 said "under 2 megabytes", so exactly 2 MB is
    too big, and the AI still wrote a case expecting a 2 MB photo to be
    accepted. Nobody can tell from the suite which of the two is wrong, which
    is exactly why it is worth saying out loud.

    A case is read one sentence at a time. "A 2.01 MB photo is refused; the
    2 MB one is saved" says two different things, and only the sentence about
    the limit itself answers the question.
    """
    rules = limit_rules(criteria)
    # Two cases that fire one rule at two counts is a disagreement the
    # criteria cannot settle, so it is reported whether or not they state
    # a limit the code could read.
    disagreements = (
        trigger_disagreements(cases)
        + precondition_notes(criteria, cases)
        + rounding_notes(cases)
    )
    if not rules:
        return disagreements[:MAX_QUALITY_NOTES]
    # A gap first: nobody deciding is worse than two people disagreeing.
    notes = _gap_notes(rules) + _criteria_conflicts(rules) + disagreements
    for case in cases or []:
        if len(notes) >= MAX_QUALITY_NOTES:
            break
        # The title is a label, not data. "Discount on an order over $50" is
        # the name of a test whose cart is $75, and reading the $50 out of it
        # is how a sound case was called wrong about a limit it never used.
        said = _sentences(
            [*(case.steps or []), str(case.test_data or ""), case.expected_result]
        )
        # Every sentence is read for its numbers once, however many limits
        # there are to compare it against.
        scanned = [(one, scan(one)) for one in said if _A_NUMBER_IN.search(one)]
        if not scanned:
            continue
        for rule in rules:
            about = [
                one
                for one, numbers in scanned
                if states(rule.value, numbers) and not over_in(rule.value, one, numbers)
            ]
            if not about:
                continue
            # A step names the value, the expected result says what happens
            # to it: the first sentence about the limit that answers wins,
            # and a sentence about a hair more is a different test.
            verdict = next((said for one in about if (said := _expects_in(one))), "")
            if not verdict:
                # The value is in "Data to use" and the answer is in the
                # expected result: two sentences, one test.
                verdict = _expects_in(str(case.expected_result or ""))
            if not verdict:
                break
            wanted = "accepted" if rule.allowed else "refused"
            if verdict != wanted:
                thing = f"a {rule.thing}" if rule.thing else "a value"
                notes.append(
                    f"{case.id} expects {thing} of exactly {rule.value} to be "
                    f'{verdict}, but {rule.source} says "{rule.phrase}", so '
                    f"exactly {rule.value} should be {wanted}. One of them is "
                    f"wrong — ask which is meant, then fix the test or the "
                    f"criterion."
                )
            break
    return notes[:MAX_QUALITY_NOTES]


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
    story: str, criteria: list[Criterion], result: TestCaseList, context: str = ""
) -> CaseReview:
    """What a principal QA would add to the AI's suite, and what is weak in it.

    The context counts as a criterion here: "orders of at least $50" is a
    limit whether it was written as AC-6 or as a line about the feature.
    """
    text = about_the_feature(story, criteria, context)
    hits = detect_hits(text, story)
    cases = list(result.test_cases)
    texts = [case_text(case) for case in cases]
    # Everything the AI wrote, read once: every check and every limit value
    # is looked for in this.
    whole_suite = "\n ".join(texts)
    suite_numbers = scan(whole_suite)
    # Where this all happens, and how every limit reads: the added cases and
    # the notes about them must say the same thing about the same value.
    ruled = with_context(criteria, context)
    rules = limit_rules(ruled)
    setting = Setting(
        page=page_in([text, *texts]),
        criteria=ruled,
        rules=tuple(rules),
        disputed=frozenset(undecided_values(rules)),
    )

    covered: list[str] = []
    gaps: list[tuple[Gap, Check]] = []
    for check in _ordered_checks(hits, text):
        if _check_covered(check, cases, whole_suite):
            covered.append(check.id)
            continue
        gaps.append(
            (Gap(check.id, check.title, check.severity, check.why), check)
        )

    boundary_gaps: list[tuple[Gap, Boundary, list[str]]] = []
    for boundary in find_boundaries(ruled):
        missing = missing_values(boundary, cases, whole_suite, suite_numbers)
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
        added.append(_case_from_boundary(boundary, case_id, missing, setting))

    return CaseReview(
        added=added,
        more=more,
        quality=_quality_notes(cases),
        covered=covered,
        conflicts=limit_conflicts(ruled, cases),
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
        # Only the values the AI really left out are claimed: the title
        # carries them, and a run that said "no case used the values" while
        # one did is the reason this names them.
        values = str(case.title or "").partition(" at ")[2].partition(" (")[0]
        if values:
            return f"The limit is where this breaks, and no case uses {values}."
        return "The limit is where this breaks, and no case uses the value either side of it."
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
# A method named for checking is checking: expectError, assertTotal,
# verifyMessage, shouldShow, checkTotal, validateForm.
_CHECKING_NAME = re.compile(r"^(?:expect|assert|verify|should|check|validate)", re.IGNORECASE)
# Something the test calls on an object: `checkout.expectErrorMessage(`.
_CALLED_METHOD = re.compile(r"\.\s*([A-Za-z_$][\w$]*)\s*\(")
# A method in any project file, with its body, so a name can be looked
# up: `async expectErrorMessage(text) { … }` or `def expect_error(self):`.
_METHOD_BODY = re.compile(
    r"(?:async\s+)?(?:def\s+)?(?P<name>[A-Za-z_$][\w$]*)\s*\([^)]*\)\s*"
    r"(?::\s*[^\n{]*)?[{:](?P<body>(?:[^{}]|\{[^{}]*\})*)"
)
_SECRET_NAME = re.compile(
    r"(?<![\w.$])([\w$]*(?:password|passwd|token|secret|apikey|api_key)[\w$]*)"
    r"\s*[:=]\s*(?:f|r|b|u)?[\"'`]([^\"'`\n]{1,200})[\"'`]",
    re.IGNORECASE,
)
_ENV_READ = re.compile(r"process\.env|os\.environ|os\.getenv|Deno\.env", re.IGNORECASE)
_BRITTLE = (
    (
        re.compile(r"nth-child", re.IGNORECASE),
        "fragile locator (`nth-child`) — it breaks when the list changes",
    ),
    (
        re.compile(r":nth-of-type", re.IGNORECASE),
        "fragile locator (`nth-of-type`) — it breaks when the page changes",
    ),
    (
        re.compile(r"/html/body", re.IGNORECASE),
        "fragile locator (full XPath) — any layout change breaks it",
    ),
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

PRINCIPAL_PREFIX = "Senior tester: "


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


def _checking_methods(files: list[ProjectFile]) -> set[str]:
    """Methods anywhere in the project that do the checking themselves.

    A page object is the normal way to write this: the test calls
    `checkout.expectErrorMessage(...)` and the `expect(` lives in
    `pages/checkout_page.ts`. Calling that an unasserted test is a false
    alarm, and a false alarm is worse than no check at all.
    """
    found: set[str] = set()
    for file in files or []:
        for match in _METHOD_BODY.finditer(file.code):
            if _ASSERTION.search(match.group("body")):
                found.add(match.group("name"))
    return found


def _asserts(body: str, checking: set[str]) -> bool:
    """Does this test check anything, itself or through something it calls?"""
    if _ASSERTION.search(body):
        return True
    for match in _CALLED_METHOD.finditer(body):
        name = match.group(1)
        if _CHECKING_NAME.match(name) or name in checking:
            return True
    return False


def _assertion_findings(file: ProjectFile, checking: set[str]) -> list[Finding]:
    findings = []
    for start, body in _test_chunks(file.code):
        if not _asserts(body, checking):
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
                    f"fragile locator `{selector[:60]}` goes {len(parts)} levels "
                    "deep — it breaks when the page changes. Use a role, a label "
                    "or a test id instead.",
                    "warning",
                )
            )
    return findings


def review_automation(script: AutomationScript, files: list[ProjectFile]) -> list[Finding]:
    """What a senior tester would send back on this project. Only ever adds."""
    findings: list[Finding] = []
    # Read every file first: the check a test calls may live in another one.
    checking = _checking_methods(files)
    for file in files or []:
        findings.extend(_only_findings(file))
        findings.extend(_assertion_findings(file, checking))
        findings.extend(_secret_findings(file))
        findings.extend(_selector_findings(file))
    findings.sort(key=lambda one: (one.file, one.line, one.message))
    return findings


# ──────────────────────────────────────────────────────────────────────────────
# After the AI call: the risks
# ──────────────────────────────────────────────────────────────────────────────

PRINCIPAL_SOURCE = "principal-qa"
# Three different sentences said one thing between them: these numbers are
# the usual ones for this kind of problem. One line says it once.
PACK_SCORE_REASON = "Typical scores for this kind of problem."


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


def _risk_words(risk: FailureMode) -> str:
    """Everything an already-named risk says: its name, and what it does."""
    return " ".join(
        [str(risk.title or ""), str(risk.effect or ""), str(risk.cause or "")]
    )


def _twin(risk: PackRisk, others: list[FailureMode]) -> FailureMode | None:
    """The risk already in the list that is this one, under whatever name.

    The AI called one of these "Timing side-channel attack distinguishes valid
    vs invalid email addresses" and the pack calls it "Response time differs
    between a known and an unknown email". Two names, one risk, so a title is
    not the only evidence: what the risk says it does counts too.

    But one shared word is a coincidence, not a match. "…enumerate emails by
    response times" is about timing and says "enumerate" in passing, which is
    enough to swallow the quite separate risk that the error message names a
    registered email. So the words in the effect and the cause have to agree
    at least twice before a risk is dropped as a repeat.

    Two titles that say the same two words are the same risk as well: "A
    provider account takes over an existing account with the same email" and
    "OAuth account linking email collision takeover" are one problem written
    twice, and the overlap score alone was too blunt to see it.

    The words are compared in one plain form, so "checks" and "checked" are
    the same word, and the covered_if words are looked for in the name too:
    an AI risk often puts the whole problem in its title and leaves the
    effect and the cause saying something more general.
    """
    for other in others:
        if title_score(risk.title, other.title) >= RISK_TITLE_MATCH:
            return other
        shared_names = normalised_words(risk.title) & normalised_words(other.title)
        if len(shared_names) >= MIN_SHARED_RISK_WORDS:
            return other
        text = _risk_words(other)
        shared = sum(1 for word in risk.covered_if if mentions(text, word))
        if shared >= MIN_SHARED_RISK_WORDS:
            return other
    return None


def _lend_words(twin: FailureMode, risk: PackRisk) -> None:
    """Give the risk that stayed the words that mean a test reaches it.

    The AI's sentences are never touched: `covered_if` is QA-Genius's own
    field, and without it the risk that survived the de-duplication would be
    the only one on the page that no test could ever be matched to.
    """
    known = {word.lower() for word in twin.covered_if}
    twin.covered_if = list(twin.covered_if) + [
        word for word in risk.covered_if if word.lower() not in known
    ]


def review_risks(
    story: str, criteria: list[str], analysis: RiskAnalysis
) -> list[FailureMode]:
    """The classic failure modes this analysis is missing. Never edits the AI's."""
    existing = list(analysis.failure_modes)
    # `covered_if` is QA-Genius's own field. A model that fills it in would be
    # claiming its own coverage, so whatever it put there goes before the
    # packs lend their words to the risks that turn out to be theirs.
    for risk in existing:
        if str(risk.source or "") != PRINCIPAL_SOURCE:
            risk.covered_if = []
    added: list[FailureMode] = []
    for risk in pack_risks(story_text(story, criteria), story):
        if len(added) >= MAX_ADDED_RISKS:
            break
        twin = _twin(risk, existing + added)
        if twin is not None:
            _lend_words(twin, risk)
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
                severity_reason=PACK_SCORE_REASON,
                likelihood_reason=PACK_SCORE_REASON,
                detectability_reason=PACK_SCORE_REASON,
                source=PRINCIPAL_SOURCE,
                # Carried through so the risk page can see for itself whether
                # a test already reaches this one.
                covered_if=list(risk.covered_if),
            )
        )
    return added
