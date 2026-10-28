"""An accepted risk: the reason, and optionally who owns it and when to look again.

A team that accepts a risk and writes nothing down has not accepted it, so
the reason stays required. An owner and a review date are the two things a
reader asks for next, and both are optional -- a date nobody agreed is worse
than no date at all.

The browser used to store a plain string, and runs saved then must still
open, so `read` takes either shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

MIN_REASON = 10
MAX_REASON = 300
MAX_OWNER = 60

_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


@dataclass(frozen=True)
class Acceptance:
    """Why a risk was accepted, and who is watching it."""

    reason: str
    owner: str = ""
    review_date: str = ""  # YYYY-MM-DD, or "" when nobody set one

    def passed(self, today: date | None = None) -> bool:
        """True when a review date was set and it is behind us."""
        when = parse_date(self.review_date)
        if when is None:
            return False
        return when < (today or date.today())

    def as_dict(self) -> dict[str, str]:
        return {
            "reason": self.reason,
            "owner": self.owner,
            "review_date": self.review_date,
        }


def parse_date(text: str) -> date | None:
    """A YYYY-MM-DD string as a date, or None for anything else."""
    match = _DATE.match(str(text or "").strip())
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def read(value: object) -> Acceptance | None:
    """One acceptance out of whatever the browser saved.

    A string is the old shape and is all reason. A dict may carry an owner
    and a review date as well. Anything whose reason is the wrong length is
    not an acceptance at all, which is the same rule as before.
    """
    if isinstance(value, Acceptance):
        return value
    if isinstance(value, str):
        reason = value.strip()
        owner, review = "", ""
    elif isinstance(value, dict):
        reason = str(value.get("reason") or "").strip()
        owner = str(value.get("owner") or "").strip()[:MAX_OWNER]
        review = str(value.get("review_date") or "").strip()
        if parse_date(review) is None:
            review = ""
    else:
        return None
    if not MIN_REASON <= len(reason) <= MAX_REASON:
        return None
    return Acceptance(reason=reason, owner=owner, review_date=review)


def read_all(value: object, keys: list[str] | tuple[str, ...]) -> dict[str, Acceptance]:
    """The acceptances for the ids we know about, in whatever shape they came."""
    if not isinstance(value, dict):
        return {}
    found: dict[str, Acceptance] = {}
    for key in keys:
        one = read(value.get(key))
        if one is not None:
            found[key] = one
    return found


def note(one: Acceptance, today: date | None = None) -> str:
    """The acceptance as one line: the reason, then who and when."""
    parts = [one.reason]
    if one.owner:
        parts.append(f"Owner: {one.owner}")
    if one.review_date:
        word = "Review by" if not one.passed(today) else "Review date passed"
        parts.append(f"{word} {one.review_date}")
    return " · ".join(parts)
