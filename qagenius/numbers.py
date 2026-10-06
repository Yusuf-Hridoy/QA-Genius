"""Parse and compare the numeric values duel readers commit to."""

import re
from collections import Counter
from dataclasses import dataclass

from qagenius.models import Interpretation

NUMBER_PATTERN = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?)"
_NUMBER_RE = re.compile(NUMBER_PATTERN + r"\s*([a-zA-Z%]+)?")
_THOUSANDS_RE = re.compile(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$")
# A comma between a digit and exactly three more is a thousands separator.
_THOUSANDS_COMMA_RE = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")

# unit -> (family, factor to base unit, normalised singular name)
_UNITS: dict[str, tuple[str, float, str]] = {
    "ms": ("time", 1 / 1000, "millisecond"),
    "millisecond": ("time", 1 / 1000, "millisecond"),
    "milliseconds": ("time", 1 / 1000, "millisecond"),
    "s": ("time", 1, "second"),
    "sec": ("time", 1, "second"),
    "secs": ("time", 1, "second"),
    "second": ("time", 1, "second"),
    "seconds": ("time", 1, "second"),
    "min": ("time", 60, "minute"),
    "mins": ("time", 60, "minute"),
    "minute": ("time", 60, "minute"),
    "minutes": ("time", 60, "minute"),
    "h": ("time", 3600, "hour"),
    "hr": ("time", 3600, "hour"),
    "hrs": ("time", 3600, "hour"),
    "hour": ("time", 3600, "hour"),
    "hours": ("time", 3600, "hour"),
    "day": ("time", 86400, "day"),
    "days": ("time", 86400, "day"),
    "attempt": ("count", 1, "attempt"),
    "attempts": ("count", 1, "attempt"),
    "try": ("count", 1, "try"),
    "tries": ("count", 1, "try"),
    "time": ("count", 1, "time"),
    "times": ("count", 1, "time"),
    "login": ("count", 1, "login"),
    "logins": ("count", 1, "login"),
    "click": ("count", 1, "click"),
    "clicks": ("count", 1, "click"),
    "request": ("count", 1, "request"),
    "requests": ("count", 1, "request"),
    "%": ("percent", 1, "percent"),
    "percent": ("percent", 1, "percent"),
    "kb": ("size", 1, "kilobyte"),
    "mb": ("size", 1024, "megabyte"),
    "gb": ("size", 1024 * 1024, "gigabyte"),
    "usd": ("money", 1, "dollar"),
    "$": ("money", 1, "dollar"),
    "eur": ("money", 1, "euro"),
}


@dataclass(frozen=True)
class Quantity:
    amount: float  # in the base unit of its family
    family: str  # "time" | "count" | "money" | "size" | "percent" | "other"
    unit: str  # normalised unit name as written, e.g. "minute", "attempt"
    text: str  # original value text


def drop_thousands_commas(text: str) -> str:
    """Remove thousands separators, so "1,000" reads as "1000"."""
    return _THOUSANDS_COMMA_RE.sub("", text)


def _to_float(number_text: str) -> float | None:
    """A comma is a thousands separator when it groups three digits, else a point."""
    if _THOUSANDS_RE.match(number_text):
        cleaned = number_text.replace(",", "")
    elif number_text.count(",") == 1 and "." not in number_text:
        cleaned = number_text.replace(",", ".")
    else:
        cleaned = number_text
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_quantity(value: str) -> Quantity | None:
    """Parse the first number + unit in `value`. None if there is no number."""
    match = _NUMBER_RE.search(value)
    if match is None:
        return None
    number = _to_float(match.group(1))
    if number is None:
        return None
    raw_unit = (match.group(2) or "").lower()
    if raw_unit in _UNITS:
        family, factor, unit = _UNITS[raw_unit]
        return Quantity(
            amount=number * factor, family=family, unit=unit, text=value
        )
    if "$" in value or "€" in value:
        unit = "euro" if "€" in value else "dollar"
        return Quantity(amount=number, family="money", unit=unit, text=value)
    return Quantity(amount=number, family="other", unit="other", text=value)


# Words that say nothing about which value a name refers to.
_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "of",
        "for",
        "to",
        "before",
        "after",
        "per",
        "account",
        "limit",
        "time",
    }
)

_PAIR_THRESHOLD = 0.25
_ONLY_ONE_BONUS = 0.5


@dataclass(frozen=True)
class NumberMatch:
    name: str  # Reader A's name if paired, else the one that exists
    value_a: str | None  # original text or None
    value_b: str | None
    status: str  # "same" | "different" | "only_a" | "only_b"


def name_score(a: str, b: str) -> float:
    """Jaccard overlap of the meaningful words in two value names."""
    tokens_a = _name_tokens(a)
    tokens_b = _name_tokens(b)
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def _name_tokens(name: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z]+", name.lower())
        if token and token not in _STOPWORDS
    }


def _as_quantity(value: str) -> Quantity:
    """Every value gets a Quantity; unparseable ones land in family "other"."""
    parsed = parse_quantity(value)
    if parsed is not None:
        return parsed
    return Quantity(amount=0.0, family="other", unit="other", text=value)


def _is_same(a: Quantity, b: Quantity) -> bool:
    if a.family == "other":
        return a.text.strip().lower() == b.text.strip().lower()
    return abs(a.amount - b.amount) <= 1e-9 * max(1, abs(a.amount))


def match_numbers(
    reading_a: Interpretation, reading_b: Interpretation
) -> list[NumberMatch]:
    """Pair the two readers' numbers by unit family and name, then compare them.

    Pairing is greedy: the best-scoring candidate wins, then the scores are
    worked out again over what is left. The "only item of its family" bonus is
    judged on the unpaired items, so the last two numbers of a family pair up
    even when the readers named them differently.
    """
    items_a = [(n.name, n.value, _as_quantity(n.value)) for n in reading_a.numbers]
    items_b = [(n.name, n.value, _as_quantity(n.value)) for n in reading_b.numbers]

    paired: dict[int, int] = {}
    used_b: set[int] = set()
    while True:
        free_a = [i for i in range(len(items_a)) if i not in paired]
        free_b = [j for j in range(len(items_b)) if j not in used_b]
        left_a = Counter(items_a[i][2].family for i in free_a)
        left_b = Counter(items_b[j][2].family for j in free_b)
        best: tuple[float, int, int] | None = None
        for i in free_a:
            family = items_a[i][2].family
            for j in free_b:
                if items_b[j][2].family != family:
                    continue
                score = name_score(items_a[i][0], items_b[j][0])
                if left_a[family] == 1 and left_b[family] == 1:
                    score += _ONLY_ONE_BONUS
                if score < _PAIR_THRESHOLD:
                    continue
                if best is None or score > best[0]:
                    best = (score, i, j)
        if best is None:
            break
        paired[best[1]] = best[2]
        used_b.add(best[2])

    matches: list[NumberMatch] = []
    for i, (name_a, value_a, quantity_a) in enumerate(items_a):
        j = paired.get(i)
        if j is None:
            matches.append(
                NumberMatch(
                    name=name_a, value_a=value_a, value_b=None, status="only_a"
                )
            )
            continue
        _, value_b, quantity_b = items_b[j]
        matches.append(
            NumberMatch(
                name=name_a,
                value_a=value_a,
                value_b=value_b,
                status="same" if _is_same(quantity_a, quantity_b) else "different",
            )
        )
    for j, (name_b, value_b, _) in enumerate(items_b):
        if j not in used_b:
            matches.append(
                NumberMatch(
                    name=name_b, value_a=None, value_b=value_b, status="only_b"
                )
            )
    return matches
