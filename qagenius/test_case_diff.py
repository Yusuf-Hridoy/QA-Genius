"""Compare a current and a proposed test case list."""

import re
from dataclasses import dataclass, field

from qagenius.models import TestCase, TestCaseList

COMPARED_FIELDS = (
    "title",
    "category",
    "priority",
    "pre_conditions",
    "steps",
    "expected_result",
    "test_data",
    "bdd_scenario",
    "traceability",
)
TITLE_MATCH = 0.6
# Compared without regard to letter case.
_CASELESS_FIELDS = ("category", "priority")
_TITLE_STOPWORDS = frozenset(
    {
        "a", "an", "the", "of", "to", "in", "on", "for", "with",
        "after", "before", "is", "are", "be",
    }
)


@dataclass(frozen=True)
class FieldChange:
    field: str
    before: str
    after: str


@dataclass(frozen=True)
class CaseChange:
    status: str  # "added" | "changed" | "removed" | "unchanged"
    before: TestCase | None
    after: TestCase | None
    changes: list[FieldChange] = field(default_factory=list)


@dataclass(frozen=True)
class Diff:
    items: list[CaseChange]
    added: int
    changed: int
    removed: int
    unchanged: int


def _flat(value: str) -> str:
    return " ".join(str(value or "").split())


def field_text(test_case: TestCase, name: str) -> str:
    """One field as text: a list of steps becomes one line per step."""
    value = getattr(test_case, name, None)
    if isinstance(value, list):
        return "\n".join(_flat(item) for item in value)
    return _flat(value)


def _title_tokens(title: str) -> set[str]:
    parts = re.split(r"[^a-z0-9]+", str(title or "").lower())
    return {part for part in parts if part and part not in _TITLE_STOPWORDS}


def title_score(left: str, right: str) -> float:
    """Jaccard overlap of the meaningful words in two titles."""
    a = _title_tokens(left)
    b = _title_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _field_changes(before: TestCase, after: TestCase) -> list[FieldChange]:
    changes = []
    for name in COMPARED_FIELDS:
        old = field_text(before, name)
        new = field_text(after, name)
        same = old.lower() == new.lower() if name in _CASELESS_FIELDS else old == new
        if not same:
            changes.append(FieldChange(field=name, before=old, after=new))
    return changes


def _key(test_case: TestCase) -> str:
    return str(test_case.id or "").strip().lower()


def _match_by_id(
    current: list[TestCase], proposed: list[TestCase]
) -> dict[int, int]:
    """Proposed index -> current index, for ids that appear on both sides."""
    by_id: dict[str, int] = {}
    for index, test_case in enumerate(current):
        by_id.setdefault(_key(test_case), index)
    pairs: dict[int, int] = {}
    used: set[int] = set()
    for index, test_case in enumerate(proposed):
        found = by_id.get(_key(test_case))
        if found is not None and found not in used:
            pairs[index] = found
            used.add(found)
    return pairs


def _match_by_title(
    current: list[TestCase],
    proposed: list[TestCase],
    pairs: dict[int, int],
) -> None:
    """Pair up what is left by title similarity, best score first."""
    used_current = set(pairs.values())
    candidates = []
    for p_index, p_case in enumerate(proposed):
        if p_index in pairs:
            continue
        for c_index, c_case in enumerate(current):
            if c_index in used_current:
                continue
            score = title_score(p_case.title, c_case.title)
            if score >= TITLE_MATCH:
                candidates.append((score, p_index, c_index))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    taken_proposed: set[int] = set()
    taken_current: set[int] = set()
    for _, p_index, c_index in candidates:
        if p_index in taken_proposed or c_index in taken_current:
            continue
        pairs[p_index] = c_index
        taken_proposed.add(p_index)
        taken_current.add(c_index)


def diff_cases(current: TestCaseList, proposed: TestCaseList) -> Diff:
    """What changed between two lists. Neither input is modified."""
    current_cases = list(current.test_cases)
    proposed_cases = list(proposed.test_cases)
    pairs = _match_by_id(current_cases, proposed_cases)
    _match_by_title(current_cases, proposed_cases, pairs)

    items: list[CaseChange] = []
    added = changed = unchanged = 0
    for index, test_case in enumerate(proposed_cases):
        partner = pairs.get(index)
        if partner is None:
            items.append(CaseChange(status="added", before=None, after=test_case))
            added += 1
            continue
        before = current_cases[partner]
        changes = _field_changes(before, test_case)
        if changes:
            items.append(
                CaseChange(
                    status="changed", before=before, after=test_case, changes=changes
                )
            )
            changed += 1
        else:
            items.append(
                CaseChange(status="unchanged", before=before, after=test_case)
            )
            unchanged += 1

    matched_current = set(pairs.values())
    removed = 0
    for index, test_case in enumerate(current_cases):
        if index not in matched_current:
            items.append(CaseChange(status="removed", before=test_case, after=None))
            removed += 1

    return Diff(
        items=items,
        added=added,
        changed=changed,
        removed=removed,
        unchanged=unchanged,
    )
