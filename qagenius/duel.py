"""Ambiguity duel: two readers interpret the story, then a comparison."""

import concurrent.futures
import re
from dataclasses import dataclass, field

from qagenius import llm
from qagenius.models import DuelComparison, Interpretation
from qagenius.numbers import NumberMatch, match_numbers, name_score
from qagenius.prompts import duel_compare_prompt, duel_reader_prompt
from qagenius.providers import get_provider
from qagenius.vague import find_vague_words

NOT_STATED_A = "not stated by Reader A"
NOT_STATED_B = "not stated by Reader B"


@dataclass
class DuelResult:
    reading_a: Interpretation
    reading_b: Interpretation
    comparison: DuelComparison
    agreement_pct: int
    highlights: list[tuple[int, int, int]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    provider_name: str = "unknown provider"
    used_index: int = 0
    vague_rewrites: dict[int, list[str]] = field(default_factory=dict)
    removed_claims: int = 0
    number_matches: list[NumberMatch] = field(default_factory=list)


def reader_text(reading: Interpretation) -> str:
    """Everything a reader wrote, lowercased, joined by ' | '."""
    parts: list[str] = []
    parts.extend(reading.actors)
    for rule in reading.rules:
        parts.append(rule.topic)
        parts.append(rule.reading)
    for number in reading.numbers:
        parts.append(number.name)
        parts.append(number.value)
    parts.extend(reading.outcomes)
    parts.extend(reading.assumptions)
    return " | ".join(parts).lower()


def ground_forks(
    comparison: DuelComparison, reading_a: Interpretation, reading_b: Interpretation
) -> tuple[DuelComparison, int, list[str]]:
    """Return (cleaned comparison, removed_claims, notes). Never mutates the input."""
    removed = 0
    notes: list[str] = []
    new_forks = []
    for fork in comparison.forks:
        sides = [
            ("A", fork.reading_a, reading_a, NOT_STATED_A),
            ("B", fork.reading_b, reading_b, NOT_STATED_B),
        ]
        updated = {}
        for letter, side, reader, not_stated in sides:
            text_side = side or ""
            lowered = text_side.strip().lower()
            if lowered == "not stated" or lowered in (NOT_STATED_A.lower(), NOT_STATED_B.lower()):
                updated[letter] = not_stated
                continue
            numbers = re.findall(r"\d+(?:\.\d+)?", text_side)
            if not numbers:
                updated[letter] = text_side
                continue
            text = reader_text(reader)
            missing = any(
                re.search(r"(?<![\d.])" + re.escape(n) + r"(?![\d.])", text) is None
                for n in numbers
            )
            if missing:
                updated[letter] = not_stated
                removed += 1
                notes.append(
                    f'Removed an unsupported claim about Reader {letter} in fork "{fork.topic}".'
                )
            else:
                updated[letter] = text_side
        if updated["A"] == NOT_STATED_A and updated["B"] == NOT_STATED_B:
            continue
        new_forks.append(
            fork.model_copy(
                update={"reading_a": updated["A"], "reading_b": updated["B"]}
            )
        )
    cleaned = comparison.model_copy(update={"forks": new_forks})
    return cleaned, removed, notes


_FACT_LABELS = {
    "same": "SAME",
    "different": "DIFFERENT",
    "only_a": "ONLY A",
    "only_b": "ONLY B",
}

# A fork topic this close to an agreed value's name is talking about that value.
FALSE_FORK_SCORE = 0.25


def format_number_facts(matches: list[NumberMatch]) -> str:
    """One line per match, for the comparison prompt."""
    lines = []
    for match in matches:
        value_a = match.value_a or "not given"
        value_b = match.value_b or "not given"
        label = _FACT_LABELS[match.status]
        lines.append(f"- {match.name}: A = {value_a}, B = {value_b} -> {label}")
    return "\n".join(lines)


def drop_false_forks(
    comparison: DuelComparison, matches: list[NumberMatch]
) -> tuple[DuelComparison, list[str]]:
    """Drop forks claiming a reader said nothing about a value both readers gave.

    Returns (cleaned comparison, notes). Never mutates the input.
    """
    agreed = [m for m in matches if m.status == "same"]
    notes: list[str] = []
    kept = []
    for fork in comparison.forks:
        if fork.reading_a == NOT_STATED_A or fork.reading_b == NOT_STATED_B:
            found = next(
                (
                    m
                    for m in agreed
                    if name_score(fork.topic, m.name) >= FALSE_FORK_SCORE
                ),
                None,
            )
            if found is not None:
                notes.append(
                    f'Dropped fork "{fork.topic}": both readers gave {found.value_a}.'
                )
                continue
        kept.append(fork)
    return comparison.model_copy(update={"forks": kept}), notes


def _find_first(story_lower: str, phrase: str) -> tuple[int, int] | None:
    needle = phrase.lower()
    if not needle.strip():
        return None
    start = story_lower.find(needle)
    if start == -1:
        return None
    return (start, start + len(phrase))


def build_highlights(
    story: str, forks: list
) -> list[tuple[int, int, int]]:
    """Map each fork's source_phrase to (start, end, fork_index).

    Case-insensitive first match only. Phrases not found are skipped.
    Overlapping ranges keep the longer one. Sorted by start.
    """
    story_lower = story.lower()
    candidates: list[tuple[int, int, int]] = []
    for idx, fork in enumerate(forks):
        phrase = getattr(fork, "source_phrase", "") or ""
        if not phrase.strip():
            continue
        found = _find_first(story_lower, phrase)
        if found is None:
            continue
        candidates.append((found[0], found[1], idx))
    # Longer first so it wins overlaps; earliest start breaks ties.
    candidates.sort(key=lambda item: (-(item[1] - item[0]), item[0]))
    kept: list[tuple[int, int, int]] = []
    for start, end, idx in candidates:
        overlaps = any(not (end <= ks or start >= ke) for ks, ke, _ in kept)
        if not overlaps:
            kept.append((start, end, idx))
    kept.sort(key=lambda item: item[0])
    return kept


def agreed_values(
    comparison: DuelComparison, matches: list[NumberMatch]
) -> list[NumberMatch]:
    """Matched values both readers gave that the AI did not already mention."""
    said = [text.lower() for text in comparison.agreements]
    return [
        m
        for m in matches
        if m.status == "same"
        and m.value_a
        and not any(m.value_a.lower() in text for text in said)
    ]


def run_duel(
    keys: list[dict[str, str]],
    user_story: str,
    story_type: str,
    context: str,
    generate=llm.generate_json,
) -> DuelResult:
    """Run Reader A + Reader B concurrently, then compare.

    Each call gets the full key list so rotation still works. Any reader
    failure aborts the duel (the caller maps it to a friendly error).
    """
    system_a, user_a = duel_reader_prompt(
        user_story, story_type=story_type, context=context, persona="A"
    )
    system_b, user_b = duel_reader_prompt(
        user_story, story_type=story_type, context=context, persona="B"
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        future_a = pool.submit(generate, keys, system_a, user_a, Interpretation)
        future_b = pool.submit(generate, keys, system_b, user_b, Interpretation)
        reading_a, used_a, notes_a = future_a.result()
        reading_b, used_b, notes_b = future_b.result()

    matches = match_numbers(reading_a, reading_b)
    system_c, user_c = duel_compare_prompt(
        user_story,
        reading_a.model_dump_json(),
        reading_b.model_dump_json(),
        number_facts=format_number_facts(matches),
    )
    comparison, used_c, notes_c = generate(
        keys, system_c, user_c, DuelComparison
    )

    comparison, removed, guard_notes = ground_forks(comparison, reading_a, reading_b)
    comparison, drop_notes = drop_false_forks(comparison, matches)
    notes = (
        list(notes_a) + list(notes_b) + list(notes_c) + guard_notes + drop_notes
    )
    n_forks = len(comparison.forks)
    n_agree = len(comparison.agreements) + len(
        agreed_values(comparison, matches)
    )
    if n_forks + n_agree == 0:
        agreement_pct = 100
    else:
        agreement_pct = round(100 * n_agree / (n_forks + n_agree))

    highlights = build_highlights(user_story, comparison.forks)
    vague_rewrites = {
        i: words
        for i, fork in enumerate(comparison.forks)
        if (words := find_vague_words(fork.suggested_rewrite))
    }

    provider = get_provider(keys[used_c]["provider"]) if keys else None
    provider_name = provider["name"] if provider else "unknown provider"
    _ = used_a, used_b
    return DuelResult(
        reading_a=reading_a,
        reading_b=reading_b,
        comparison=comparison,
        agreement_pct=agreement_pct,
        highlights=highlights,
        notes=notes,
        provider_name=provider_name,
        used_index=used_c,
        vague_rewrites=vague_rewrites,
        removed_claims=removed,
        number_matches=matches,
    )
