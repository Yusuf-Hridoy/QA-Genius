"""Turn the AI's suggested factors into something the engine can build from.

The model proposes *which* factors matter for this story; it never decides how
many runs there are or whether they cover anything. Everything it sends is
trimmed, deduped and checked here, and anything unusable falls back to the
standard set with a note the user can read.
"""

from qagenius.models import MatrixProposal
from qagenius.shadow_qa.detect import mentions
from qagenius.pairwise import (
    MAX_VALUES,
    MIN_VALUES,
    Factor,
    Rule,
    validate,
)
from qagenius.test_matrix_defaults import STANDARD_FACTORS, STANDARD_RULES

MAX_PROPOSED_FACTORS = 6
MAX_PROPOSED_VALUES = 5
FALLBACK_NOTE = "The suggested factors didn't work, so the standard set is used."
# What a screen is tested on. A real run dropped both for a sign-in story and
# proposed Signed in / Role / Language, which is a matrix nobody can run.
SCREEN_FACTORS = ("Browser", "Device")
ADDED_NOTE = "Added Browser and Device — they matter for almost every screen."
ADDED_ONE_NOTE = "Added {name} — it matters for almost every screen."
# A story about an API has no browser and no screen to put it on.
BACKEND_WORDS = (
    "api",
    "apis",
    "endpoint",
    "endpoints",
    "backend",
    "back-end",
    "webhook",
    "webhooks",
    "service-to-service",
    "server-to-server",
    "cron",
    "batch job",
)


def _clean(text: str) -> str:
    return " ".join(str(text or "").split())


def _unique(values: list[str], limit: int) -> list[str]:
    """Trimmed, non-empty, first-spelling-wins, capped."""
    kept: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean(value)
        if not cleaned or cleaned.lower() in seen:
            continue
        seen.add(cleaned.lower())
        kept.append(cleaned)
        if len(kept) >= limit:
            break
    return kept


def _reasons(proposal: MatrixProposal) -> dict[str, str]:
    return {
        _clean(factor.name).lower(): _clean(factor.reason)
        for factor in proposal.factors
        if _clean(factor.name)
    }


def is_backend_only(text: str) -> bool:
    """Is this story about something with no screen to test it on?"""
    return any(mentions(text, word) for word in BACKEND_WORDS)


def _with_screen_factors(
    factors: list[Factor], text: str
) -> tuple[list[Factor], list[str]]:
    """Put Browser and Device back when the AI forgot them.

    Almost every story is a screen, and a matrix without the two things a
    screen is actually opened on is a matrix nobody would run: a real run
    proposed Signed in / Role / Language for a sign-in story. A story about an
    API has no browser and no device, so it is left as the AI wrote it.

    Nothing is added to a proposal with no usable factor in it: that one falls
    back to the standard set whole, which already has both.
    """
    if not factors or is_backend_only(text):
        return factors, []
    have = {factor.name.strip().lower() for factor in factors}
    missing = [
        standard
        for standard in STANDARD_FACTORS
        if standard.name in SCREEN_FACTORS and standard.name.lower() not in have
    ]
    if not missing:
        return factors, []
    note = ADDED_NOTE if len(missing) == 2 else ADDED_ONE_NOTE.format(name=missing[0].name)
    # The AI's own factors keep their order; the cap counts them all, so the
    # last suggestion gives way rather than the matrix growing.
    room = max(1, MAX_PROPOSED_FACTORS - len(missing))
    return factors[:room] + missing, [note]


def clean_proposal(
    proposal: MatrixProposal, text: str = ""
) -> tuple[list[Factor], list[Rule], list[str]]:
    """(factors, rules, notes). Always returns something the engine can build.

    `text` is the story and its criteria: it only decides whether a story is
    about an API, which is the one case with no browser and no device.
    """
    notes: list[str] = []

    factors: list[Factor] = []
    seen_names: set[str] = set()
    thin = 0
    for proposed in proposal.factors:
        name = _clean(proposed.name)
        if not name or name.lower() in seen_names:
            continue
        values = _unique(list(proposed.values or []), MAX_PROPOSED_VALUES)
        if len(values) < MIN_VALUES:
            thin += 1
            continue
        seen_names.add(name.lower())
        factors.append(Factor(name=name, values=tuple(values)))
        if len(factors) >= MAX_PROPOSED_FACTORS:
            break
    if thin:
        notes.append(
            f"Dropped {thin} suggested factor{'' if thin == 1 else 's'} "
            "with fewer than two values."
        )

    factors, screen_notes = _with_screen_factors(factors, text)
    notes.extend(screen_notes)

    known = {factor.name.lower(): factor for factor in factors}

    def usable(rule: Rule) -> bool:
        left = known.get(_clean(rule.if_factor).lower())
        right = known.get(_clean(rule.then_factor).lower())
        if left is None or right is None or left.name.lower() == right.name.lower():
            return False
        left_values = {_clean(one).lower() for one in left.values}
        right_values = {_clean(one).lower() for one in right.values}
        return (
            _clean(rule.if_value).lower() in left_values
            and _clean(rule.then_value).lower() in right_values
        )

    rules: list[Rule] = []
    seen_rules: set[tuple[str, str, str, str]] = set()
    dropped = 0
    proposed_rules = [
        Rule(
            if_factor=_clean(one.if_factor),
            if_value=_clean(one.if_value),
            then_factor=_clean(one.then_factor),
            then_value=_clean(one.then_value),
            reason=_clean(one.reason),
        )
        for one in proposal.rules
    ]
    # The standard rules are facts about the tools, so they apply whenever the
    # factors they talk about are present.
    for rule in proposed_rules + STANDARD_RULES:
        if not usable(rule):
            if rule in proposed_rules:
                dropped += 1
            continue
        key = (
            rule.if_factor.lower(),
            rule.if_value.lower(),
            rule.then_factor.lower(),
            rule.then_value.lower(),
        )
        mirrored = (key[2], key[3], key[0], key[1])
        if key in seen_rules or mirrored in seen_rules:
            continue
        seen_rules.add(key)
        rules.append(rule)
    if dropped:
        notes.append(
            f"Ignored {dropped} rule{'' if dropped == 1 else 's'} that referred to "
            "an unknown value."
        )

    problems = validate(factors, rules)
    if problems:
        return list(STANDARD_FACTORS), list(STANDARD_RULES), notes + [FALLBACK_NOTE]
    return factors, rules, notes


def standard_set() -> tuple[list[Factor], list[Rule]]:
    """What a user with no AI key gets: a sensible matrix, built the same way."""
    return list(STANDARD_FACTORS), list(STANDARD_RULES)


def reasons_for(proposal: MatrixProposal | None) -> dict[str, str]:
    """factor name (lower) -> the one-line reason, for the editor to show."""
    return _reasons(proposal) if proposal else {}


__all__ = [
    "ADDED_NOTE",
    "ADDED_ONE_NOTE",
    "BACKEND_WORDS",
    "FALLBACK_NOTE",
    "MAX_PROPOSED_FACTORS",
    "MAX_PROPOSED_VALUES",
    "MAX_VALUES",
    "clean_proposal",
    "is_backend_only",
    "reasons_for",
    "standard_set",
]
