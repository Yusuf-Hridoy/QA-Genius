"""Parse and compare the numeric values duel readers commit to."""

import re
from dataclasses import dataclass

_NUMBER_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*([a-zA-Z%]+)?")

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


def parse_quantity(value: str) -> Quantity | None:
    """Parse the first number + unit in `value`. None if there is no number."""
    match = _NUMBER_RE.search(value)
    if match is None:
        return None
    number_text = match.group(1).replace(",", ".")
    try:
        number = float(number_text)
    except ValueError:
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
