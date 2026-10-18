"""Tidying the words a model puts in a story analysis.

Two jobs, both asked of the story page and of Ship check:
strip the confidence tag models append to a line and hand back the level on
its own, and drop "no acceptance criteria" from a Missing list once the
criteria exist.
"""

import re
from typing import NamedTuple

# Models end a line with "[HIGH CONFIDENCE]" (any case, sometimes before the
# full stop). The words belong to the sentence; the tag does not.
_CONFIDENCE = re.compile(
    r"\s*\[\s*(high|medium|low)\s+confidence\s*\]\s*[.;,]?\s*$",
    re.IGNORECASE,
)

LEVELS: tuple[str, ...] = ("High", "Medium", "Low")


class Said(NamedTuple):
    """A line of model text with its confidence tag taken off the end."""

    text: str
    level: str  # "High", "Medium", "Low", or "" when nothing was tagged


def split_confidence(value: object) -> Said:
    """The line without its trailing confidence tag, plus the level."""
    text = "" if value is None else str(value)
    match = _CONFIDENCE.search(text)
    if match is None:
        return Said(text.strip(), "")
    return Said(text[: match.start()].strip(), match.group(1).capitalize())


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
