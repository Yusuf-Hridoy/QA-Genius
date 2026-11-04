"""What code alone can say about a story, before anyone writes a test.

No AI. The three things a reader gets are the words nobody can test, the
warning that this is really several stories, and the fact that nothing here
says what happens when it goes wrong.
"""

from dataclasses import dataclass, field

from qagenius.shadow_qa.detect import mentions
from qagenius.shadow_qa.review import limit_conflicts, with_context
from qagenius.shadow_qa.story_rules import NEGATIVE_WORDS, StoryNote, review_story
from qagenius.test_cases import Criterion, number_criteria
from qagenius.vague import find_vague_words

# A plain replacement for each word the vague rules catch. The rule says a
# word cannot be tested; this says what to write instead, which is the only
# half of that a reader can act on.
SAY_INSTEAD: dict[str, str] = {
    "quickly": "a time: “within 2 seconds”",
    "slowly": "a time: “takes longer than 5 seconds”",
    "fast": "a time: “within 2 seconds”",
    "soon": "a time: “within 1 minute”",
    "immediately": "a time: “within 1 second”",
    "promptly": "a time: “within 2 seconds”",
    "timely": "a time: “within 2 seconds”",
    "too many": "a count: “more than 5”",
    "too few": "a count: “fewer than 3”",
    "several": "a count: “3”",
    "some": "a count: “at least 1”",
    "few": "a count: “fewer than 3”",
    "many": "a count: “more than 10”",
    "multiple": "a count: “2 or more”",
    "various": "the list itself: “card, bank transfer, wallet”",
    "safe": "the rule: “only the account owner can open it”",
    "secure": "the rule: “sent over HTTPS, never written to a log”",
    "securely": "the rule: “sent over HTTPS, never written to a log”",
    "appropriate": "the exact value, or the rule that picks it",
    "appropriately": "the exact value, or the rule that picks it",
    "properly": "what “properly” looks like on the screen",
    "user-friendly": "the behaviour: “the error names the field that is wrong”",
    "easy": "the behaviour: “done in 2 clicks from the home page”",
    "simple": "the behaviour: “one field, no extra screen”",
    "intuitive": "the behaviour: “the button says what it does”",
    "reasonable": "the number you mean",
    "adequate": "the number you mean",
    "may": "“does” or “does not”",
    "might": "“does” or “does not”",
    "could": "“does” or “does not”",
    "should be able": "“can”",
    "etc": "the rest of the list, written out",
    "and so on": "the rest of the list, written out",
    "large": "a size: “over 2 MB”",
    "small": "a size: “under 100 KB”",
    "high": "the number you mean",
    "low": "the number you mean",
    "frequently": "how often: “more than once an hour”",
    "rarely": "how often: “less than once a week”",
    "often": "how often: “more than once a day”",
}

# What a reader is told about a word with no replacement written for it.
# Better than inventing one on the spot: the suggestion stays honest.
SAY_INSTEAD_FALLBACK = "a number, a time or the rule you mean"

NO_FAILURE_TITLE = "Nothing says what happens when it fails"
NO_FAILURE_DETAIL = (
    "The story only describes the path where everything works. Say what the "
    "user sees when the input is invalid, the limit is reached or the save "
    "fails — that is the half the tests come from."
)


@dataclass(frozen=True)
class UnclearWord:
    """A word nobody can test, and what to write in its place."""

    word: str
    say_instead: str


@dataclass(frozen=True)
class StoryReview:
    """Everything code can say about one story."""

    unclear: list[UnclearWord] = field(default_factory=list)
    # The warning that this story is really several features, when there is one.
    epic: StoryNote | None = None
    # Every other note: no actor, no benefit, no failure behaviour.
    notes: list[StoryNote] = field(default_factory=list)
    # Limits two criteria disagree about, or that nobody has decided.
    limit_notes: list[str] = field(default_factory=list)
    # The criteria as they were read, numbered AC-1..n.
    criteria: list[Criterion] = field(default_factory=list)


def says_what_fails(texts: list[str]) -> bool:
    """Does any of this text say what happens when something goes wrong?"""
    return any(
        mentions(text, word)
        for text in texts
        if str(text or "").strip()
        for word in NEGATIVE_WORDS
    )


def _no_failure_note() -> StoryNote:
    return StoryNote(level="warn", title=NO_FAILURE_TITLE, detail=NO_FAILURE_DETAIL)


def review_story_text(
    story: str,
    context: str = "",
    story_type: str = "user story",
    criteria: list[str] | None = None,
) -> StoryReview:
    """The code-only read of a story. No AI, no key, no network.

    `story_type` is carried for the caller's own wording; nothing here reads
    it, because a bug and a feature are equally untestable when they are
    written in words nobody can measure.
    """
    story = str(story or "")
    context = str(context or "")
    texts = [str(one or "") for one in (criteria or []) if str(one or "").strip()]

    found = review_story(story, texts, context)
    epic = next((note for note in found if note.epic), None)
    notes = [note for note in found if not note.epic]

    # review_story judges failure behaviour from the criteria, and is silent
    # when there are none. A story checked on its own still deserves the
    # answer, so its own words are read instead.
    if not texts and not says_what_fails([story, context]):
        notes.append(_no_failure_note())

    numbered = number_criteria(texts)
    return StoryReview(
        unclear=[
            UnclearWord(word, SAY_INSTEAD.get(word, SAY_INSTEAD_FALLBACK))
            for word in find_vague_words("\n".join([story, context]))
        ],
        epic=epic,
        notes=notes,
        limit_notes=limit_conflicts(with_context(numbered, context), []),
        criteria=numbered,
    )
