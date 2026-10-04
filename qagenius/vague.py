"""Shared list of vague words used by duel prompts and the rewrite check."""

import re

VAGUE_WORDS: tuple[str, ...] = (
    "quickly", "slowly", "fast", "soon", "immediately", "promptly", "timely",
    "too many", "too few", "several", "some", "few", "many", "multiple", "various",
    "safe", "secure", "securely", "appropriate", "appropriately", "properly",
    "user-friendly", "easy", "simple", "intuitive", "reasonable", "adequate",
    "may", "might", "could", "should be able", "etc", "and so on",
    "large", "small", "high", "low", "frequently", "rarely", "often",
)


def find_vague_words(text: str) -> list[str]:
    """Vague words/phrases in `text`, whole-word, case-insensitive, no duplicates.

    Longer phrases are checked first; once a span matches (e.g. "too many"),
    shorter entries inside that same span (e.g. "many") are not reported.
    Result order: the order of first appearance in `text`.
    """
    working = list(text)
    found: list[tuple[int, str]] = []
    for word in sorted(VAGUE_WORDS, key=len, reverse=True):
        pattern = re.compile(
            r"(?<![\w-])" + re.escape(word) + r"(?![\w-])", re.IGNORECASE
        )
        for match in pattern.finditer("".join(working)):
            start, end = match.start(), match.end()
            found.append((start, word))
            for i in range(start, end):
                working[i] = " "
    found.sort(key=lambda item: item[0])
    seen: set[str] = set()
    result: list[str] = []
    for _, word in found:
        if word not in seen:
            seen.add(word)
            result.append(word)
    return result
