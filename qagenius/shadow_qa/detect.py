"""Which rule packs this story is about, found by matching their trigger words.

The matching is the one `vague.py` uses: whole word or phrase, case-insensitive.
A phrase that starts or ends with something other than a letter or digit — the
`USER@` in a covered_if list — drops the boundary on that side, so it can be
found inside `USER@EXAMPLE.COM`.
"""

import re
from functools import lru_cache

from qagenius.shadow_qa.packs import Pack, load_packs


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


def detect_packs(text: str) -> list[tuple[Pack, list[str]]]:
    """The active packs and the trigger words that activated each, in pack order.

    A pack is active when any trigger matches and no excluded word does.
    """
    found: list[tuple[Pack, list[str]]] = []
    for pack in load_packs():
        if any(mentions(text, word) for word in pack.exclude):
            continue
        hits = matching(text, pack.triggers)
        if hits:
            found.append((pack, hits))
    return found


def active_packs(text: str) -> list[Pack]:
    return [pack for pack, _ in detect_packs(text)]
