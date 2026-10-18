"""Which rule packs this story is about, found by matching their trigger words.

The matching is the one `vague.py` uses: whole word or phrase, case-insensitive.
A phrase that starts or ends with something other than a letter or digit — the
`USER@` in a covered_if list — drops the boundary on that side, so it can be
found inside `USER@EXAMPLE.COM`.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

from qagenius.shadow_qa.packs import Pack, load_packs

# One weak trigger is a coincidence; two different ones are a feature.
MIN_WEAK = 2


@lru_cache(maxsize=4096)
def phrase_pattern(phrase: str) -> re.Pattern[str]:
    """A whole-word matcher for one word or phrase. Cached: packs reuse them."""
    cleaned = phrase.strip()
    head = r"(?<![\w-])" if _is_word_edge(cleaned[:1]) else ""
    tail = r"(?![\w-])" if _is_word_edge(cleaned[-1:]) else ""
    return re.compile(head + re.escape(cleaned) + tail, re.IGNORECASE)


def _is_word_edge(char: str) -> bool:
    return bool(char) and (char.isalnum() or char == "_")


def mentions(text: str, phrase: str) -> bool:
    """Is this word or phrase in the text, as a whole word?"""
    if not phrase.strip():
        return False
    return phrase_pattern(phrase).search(text or "") is not None


def matching(text: str, phrases) -> list[str]:
    """The phrases that appear in the text, in the order they were given."""
    return [phrase for phrase in phrases if mentions(text, phrase)]


def story_text(story: str, criteria) -> str:
    """The one body of text a pack is matched against: the story and its criteria."""
    parts = [str(story or "")]
    for item in criteria or []:
        parts.append(str(getattr(item, "text", item) or ""))
    return "\n".join(parts)


@dataclass(frozen=True)
class PackHit:
    pack: Pack
    triggers: list[str]  # the words that matched, strong ones first
    in_story: bool  # at least one of them is in the story, not only a criterion


def detect_hits(text: str, story: str | None = None) -> list[PackHit]:
    """The active packs, in pack order, with the words that activated each.

    A pack activates on one strong trigger or on two different weak triggers,
    said anywhere. A word like "email" or "list" turns up in almost every
    story ever written, so one of them on its own says nothing about what the
    feature is; two different ones do.

    Where a trigger was said still matters, but only for order: `in_story`
    says the story named this pack rather than a criterion mentioning it in
    passing, and the reviewers offer those packs first.
    """
    whole = text or ""
    # A bare call has no criteria to tell apart, so all of it counts as story.
    spoken = whole if story is None else (story or "")
    found: list[PackHit] = []
    for pack in load_packs():
        if any(mentions(whole, word) for word in pack.exclude):
            continue
        strong = matching(whole, pack.triggers)
        weak = matching(whole, pack.weak_triggers)
        if not strong and not weak:
            continue
        if not strong and len(weak) < MIN_WEAK:
            continue
        hits = strong + weak
        found.append(
            PackHit(
                pack=pack,
                triggers=hits,
                in_story=any(mentions(spoken, word) for word in hits),
            )
        )
    return found


def detect_packs(text: str, story: str | None = None) -> list[tuple[Pack, list[str]]]:
    """The active packs and the trigger words that activated each, in pack order."""
    return [(hit.pack, hit.triggers) for hit in detect_hits(text, story)]


def active_packs(text: str, story: str | None = None) -> list[Pack]:
    return [hit.pack for hit in detect_hits(text, story)]
