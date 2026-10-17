"""Turn the AI's suggested factors into something the engine can build from.

The model proposes *which* factors matter for this story; it never decides how
many runs there are or whether they cover anything. Everything it sends is
trimmed, deduped and checked here, and anything unusable falls back to the
standard set with a note the user can read.
"""

from qagenius.models import MatrixProposal
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


def clean_proposal(
    proposal: MatrixProposal,
) -> tuple[list[Factor], list[Rule], list[str]]:
    """(factors, rules, notes). Always returns something the engine can build."""
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
    "FALLBACK_NOTE",
    "MAX_PROPOSED_FACTORS",
    "MAX_PROPOSED_VALUES",
    "MAX_VALUES",
    "clean_proposal",
    "reasons_for",
    "standard_set",
]
