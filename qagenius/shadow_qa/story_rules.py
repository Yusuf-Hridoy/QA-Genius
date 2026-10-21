"""What a principal QA says about the story itself, before anyone writes a test.

The important one is the epic warning. A story that is really seven features
gets seven shallow test cases, and nobody notices until the sprint is over.
"""

import re
from dataclasses import dataclass, field

from qagenius.shadow_qa.detect import detect_hits, mentions, phrase_pattern, story_text

# Either of these makes the story an epic. Both are counted from what the
# person wrote -- the story and the context they gave with it -- and never
# from criteria the AI drafted: a run warned that a one-line story was
# really eight features, every one of them read off the AI's own draft.
EPIC_FEATURES = 5
EPIC_CAPABILITIES = 6
# More features than this in the sentence and the pill row stops being
# readable. Past it the row keeps this many and counts the rest, so the
# number in the title and the names under it always come from one list.
MAX_FEATURE_PILLS = 12

NEGATIVE_WORDS = (
    "invalid", "error", "errors", "reject", "rejects", "rejected", "fail",
    "fails", "failed", "failure", "denied", "deny", "wrong", "incorrect",
    "refuse", "refused", "blocked", "not allowed", "cannot", "unable",
)

_WANT_TO = re.compile(r"\bwant(?:s)?\s+to\b", re.IGNORECASE)
_SO_THAT = re.compile(r"\bso\s+that\b", re.IGNORECASE)
_AS_A = re.compile(r"\bas\s+an?\b", re.IGNORECASE)
_SPLIT = re.compile(r",|\band\b", re.IGNORECASE)


@dataclass(frozen=True)
class StoryNote:
    level: str  # "warn" | "info"
    title: str
    detail: str
    # True on the one warning that says the story is several features.
    epic: bool = False
    # The detail without the feature list, for anywhere that draws the pills.
    advice: str = ""
    # The epic warning shows these as pills; every other note leaves it empty.
    features: tuple[str, ...] = field(default=())
    # Features past the pill row, counted so the row can say "and 3 more".
    more: int = 0


def count_capabilities(story: str) -> int:
    """Comma- or "and"-separated things the story says the user wants to do."""
    match = _WANT_TO.search(story or "")
    if match is None:
        return 0
    rest = story[match.end():]
    end = _SO_THAT.search(rest)
    if end is not None:
        rest = rest[: end.start()]
    parts = [part.strip(" ,.;:") for part in _SPLIT.split(rest)]
    # A capability is a phrase, not a stray conjunction or a single article.
    return sum(1 for part in parts if len(part.split()) >= 2)


_SHALLOW = (
    "This is too much for one story. Each part will get only a few tests. "
    "Split it first, or carry on knowing that."
)


def _epic_note(features: list[str], capabilities: int) -> StoryNote:
    """The warning, worded by whichever rule caught the story."""
    shown = features[:MAX_FEATURE_PILLS]
    if features:
        # The count and the names are one list: the title says how many were
        # found, the row shows every one of them, and only a row too long to
        # read keeps the first twelve and counts the rest.
        more = len(features) - len(shown)
        listed = ", ".join(shown)
        if more:
            listed += f", and {more} more"
        return StoryNote(
            level="warn",
            title=f"This story is really {len(features)} features",
            detail=f"{listed}. {_SHALLOW}",
            advice=_SHALLOW,
            epic=True,
            features=tuple(shown),
            more=more,
        )
    return StoryNote(
        level="warn",
        title=f"This story asks for {capabilities} things at once",
        detail=(
            f"The sentence after \"want to\" lists {capabilities} separate "
            f"capabilities. {_SHALLOW}"
        ),
        epic=True,
    )


def _said_at(text: str, words: tuple[str, ...] | list[str]) -> int:
    """Where in the text the first of these words turns up."""
    spots = [
        found.start()
        for word in words
        if (found := phrase_pattern(word).search(text)) is not None
    ]
    return min(spots) if spots else len(text)


def review_story(
    story: str, criteria: list[str], context: str = ""
) -> list[StoryNote]:
    """What a principal QA would say about this story. No AI, no key.

    The features counted belong to the story and to the context the person
    typed beside it. Criteria are read for everything else here, but never
    for the size of the story: a story is not an epic because the AI was
    thorough about it.
    """
    story = str(story or "")
    texts = [str(one or "") for one in (criteria or []) if str(one or "").strip()]
    said = str(context or "").strip()
    own = story_text(story, [said] if said else [])
    # Reading order, not pack order: the pills then follow the sentence, so a
    # reader can check them off against the story as they go. The story comes
    # first in `own`, so what it named out loud leads anyway.
    hits = sorted(detect_hits(own, story), key=lambda hit: _said_at(own, hit.triggers))
    features = [hit.pack.short for hit in hits]

    notes: list[StoryNote] = []
    capabilities = count_capabilities(story)
    if len(features) >= EPIC_FEATURES or capabilities >= EPIC_CAPABILITIES:
        notes.append(_epic_note(features, capabilities))

    if not _AS_A.search(story):
        notes.append(
            StoryNote(
                level="info",
                title="No actor",
                detail=(
                    "The story never says who this is for. Start it with "
                    '"As a <role>" so the tests know whose account to use.'
                ),
            )
        )
    if not _SO_THAT.search(story):
        notes.append(
            StoryNote(
                level="info",
                title="No benefit",
                detail=(
                    "The story never says why. Without a "
                    '"so that <benefit>" there is nothing to judge a '
                    "disagreement about scope against."
                ),
            )
        )
    if texts and not any(
        mentions(text, word) for text in texts for word in NEGATIVE_WORDS
    ):
        notes.append(
            StoryNote(
                level="warn",
                title="No criterion describes what happens when something goes wrong",
                detail=(
                    "Every criterion is a happy path, so the AI has nothing to "
                    "write a negative test from. Add what the user sees when the "
                    "input is invalid, the limit is reached or the save fails."
                ),
            )
        )
    return notes


def epic_note(notes: list[StoryNote]) -> StoryNote | None:
    """The epic warning, when there is one. It is always first."""
    for note in notes:
        if note.epic:
            return note
    return None
