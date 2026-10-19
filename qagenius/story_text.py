"""Tidying the words a model puts in a story analysis.

Two jobs, both asked of the story page and of Ship check:
strip the confidence tag models append to a line and hand back the level on
its own, and drop "no acceptance criteria" from a Missing list once the
criteria exist.
"""

import re
from typing import NamedTuple

# Models label their own confidence in every shape they can think of:
# "[HIGH CONFIDENCE]", "[Confidence: HIGH]", "(confidence: high)" and a bare
# "Confidence: High." They do it at the end of a line and in the middle of
# one. The words belong to the sentence; the tag never does.
_LEVEL = r"high|medium|low"
_CONFIDENCE = re.compile(
    r"\s*(?:"
    rf"\[\s*(?:confidence\s*[:=-]?\s*(?:{_LEVEL})|(?:{_LEVEL})\s+confidence)\s*\]"
    rf"|\(\s*(?:confidence\s*[:=-]?\s*(?:{_LEVEL})|(?:{_LEVEL})\s+confidence)\s*\)"
    rf"|(?<![\w-])confidence\s*[:=-]\s*(?:{_LEVEL})(?![\w-])"
    r")",
    re.IGNORECASE,
)
_FOUND_LEVEL = re.compile(_LEVEL, re.IGNORECASE)
# What is left after a tag comes out: a space in front of the full stop, the
# sentence's own full stop followed by the tag's, two spaces mid-sentence.
_SPACE_BEFORE_STOP = re.compile(r"\s+([.,;:!?])")
_DOUBLED_STOP = re.compile(r"([.!?])\s*[.,;:]+")
_RUN_OF_SPACES = re.compile(r"\s{2,}")

LEVELS: tuple[str, ...] = ("High", "Medium", "Low")


class Said(NamedTuple):
    """A line of model text with its confidence tag taken off the end."""

    text: str
    level: str  # "High", "Medium", "Low", or "" when nothing was tagged


def _tidy(text: str) -> str:
    """The sentence after a tag was cut out of it, with its own stop kept."""
    text = _RUN_OF_SPACES.sub(" ", text)
    text = _SPACE_BEFORE_STOP.sub("\\1", text)
    text = _DOUBLED_STOP.sub("\\1", text)
    return text.strip()


def split_confidence(value: object) -> Said:
    """The line with every confidence tag cut out of it, plus the level.

    A tag at the end and a tag mid-sentence both go. The level comes from the
    last one, which is the one a model means when it writes two.
    """
    text = "" if value is None else str(value)
    found = list(_CONFIDENCE.finditer(text))
    if not found:
        return Said(text.strip(), "")
    level = _FOUND_LEVEL.search(found[-1].group(0))
    return Said(
        _tidy(_CONFIDENCE.sub(" ", text)),
        level.group(0).capitalize() if level else "",
    )


def strip_confidence(value: object) -> str:
    """Just the words, for places with nowhere to put a pill."""
    return split_confidence(value).text


def without_criteria_lines(missing: list, has_criteria: bool) -> list:
    """Written criteria answer "no acceptance criteria", so that line goes.

    Ship check and the story page have to agree about this, or a story reads
    as missing its criteria on one page and not on the other.
    """
    if not has_criteria:
        return list(missing)
    return [item for item in missing if "acceptance criteria" not in str(item).lower()]


def strip_confidence_deep(value: object) -> object:
    """Every string in a nested structure, with its confidence tag removed.

    What the story page stores for Ship check and Risk radar goes through
    here: those desks quote the same sentences and have nowhere to show a
    level, so they should never inherit the tag.
    """
    if isinstance(value, str):
        return strip_confidence(value)
    if isinstance(value, list):
        return [strip_confidence_deep(item) for item in value]
    if isinstance(value, dict):
        return {key: strip_confidence_deep(item) for key, item in value.items()}
    return value
