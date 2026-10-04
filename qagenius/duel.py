"""Ambiguity duel: two readers interpret the story, then a comparison."""

import concurrent.futures
import html
from dataclasses import dataclass, field

from markupsafe import Markup

from qagenius import llm
from qagenius.models import DuelComparison, Interpretation
from qagenius.prompts import duel_compare_prompt, duel_reader_prompt
from qagenius.providers import get_provider


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


def highlight_story(
    story: str, highlights: list[tuple[int, int, int]], forks: list
) -> Markup:
    """Escape the story, then wrap each highlight in a <mark>.

    `forks` is accepted for context but only the index in `data-fork`
    is rendered; no AI text is inserted here, so nothing can inject HTML.
    """
    valid: list[tuple[int, int, int]] = []
    for start, end, idx in highlights:
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if start < 0 or end > len(story) or start >= end:
            continue
        if idx < 0 or idx >= len(forks):
            continue
        valid.append((start, end, idx))
    valid.sort(key=lambda item: item[0])
    # Drop any residual overlaps defensively (keep earliest).
    deduped: list[tuple[int, int, int]] = []
    for item in valid:
        if deduped and item[0] < deduped[-1][1]:
            continue
        deduped.append(item)
    parts: list[str] = []
    last = 0
    for start, end, idx in deduped:
        parts.append(html.escape(story[last:start]))
        parts.append(
            f'<mark class="fork-mark" tabindex="0" data-fork="{idx}">'
            + html.escape(story[start:end])
            + "</mark>"
        )
        last = end
    parts.append(html.escape(story[last:]))
    return Markup("".join(parts))


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

    system_c, user_c = duel_compare_prompt(
        user_story,
        reading_a.model_dump_json(),
        reading_b.model_dump_json(),
    )
    comparison, used_c, notes_c = generate(
        keys, system_c, user_c, DuelComparison
    )

    notes = list(notes_a) + list(notes_b) + list(notes_c)
    n_forks = len(comparison.forks)
    n_agree = len(comparison.agreements)
    if n_forks + n_agree == 0:
        agreement_pct = 100
    else:
        agreement_pct = round(100 * n_agree / (n_forks + n_agree))

    highlights = build_highlights(user_story, comparison.forks)

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
    )
