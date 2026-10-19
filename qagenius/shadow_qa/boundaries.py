"""Every number in the acceptance criteria, and the three values worth testing.

A criterion that says "5 failed attempts within a 15-minute window" has three
numbers and nine values a principal QA would insist on. The AI writes a test
for the 5 and forgets the 4 and the 6 every time, so they are found here in
plain Python and checked against whatever the AI came back with.
"""

import re
from dataclasses import dataclass

from qagenius.models import TestCase
from qagenius.test_cases import Criterion

# More than this and the checklist stops being a glance.
MAX_BOUNDARIES = 12

KINDS = ("count", "size", "duration", "length", "digits")

# Things that look like numbers but are not quantities: ids, years, versions.
_ID = re.compile(r"\b[A-Za-z]{1,6}[-_]\d+\b")
_VERSION = re.compile(r"\bv?\d+\.\d+(?:\.\d+)*\b")
_YEAR = re.compile(r"(?<![\d.])(?:19|20)\d{2}(?![\d.])")

_NUMBER = r"(\d+(?:\.\d+)?)"
_GAP = r"\s*-?\s*"

# unit word as written -> how the boundary values spell it
_DURATION_UNITS = {
    "ms": "ms", "millisecond": "ms", "milliseconds": "ms",
    "s": "seconds", "sec": "seconds", "secs": "seconds",
    "second": "seconds", "seconds": "seconds",
    "min": "minutes", "mins": "minutes", "minute": "minutes", "minutes": "minutes",
    "h": "hours", "hr": "hours", "hrs": "hours", "hour": "hours", "hours": "hours",
    "day": "days", "days": "days", "week": "weeks", "weeks": "weeks",
}
_SIZE_UNITS = {
    "kb": "KB", "kilobyte": "KB", "kilobytes": "KB",
    "mb": "MB", "megabyte": "MB", "megabytes": "MB",
    "gb": "GB", "gigabyte": "GB", "gigabytes": "GB",
}
_LENGTH_UNITS = {
    "character": "characters", "characters": "characters",
    "char": "characters", "chars": "characters",
    "letter": "characters", "letters": "characters",
    "word": "words", "words": "words",
}
# The nouns a count is counted in. Anything else is just a number.
_COUNT_UNITS = {
    "attempt": "attempts", "attempts": "attempts",
    "try": "attempts", "tries": "attempts",
    "time": "times", "times": "times",
    "item": "items", "items": "items",
    "device": "devices", "devices": "devices",
    "session": "sessions", "sessions": "sessions",
    "user": "users", "users": "users",
    "file": "files", "files": "files",
    "request": "requests", "requests": "requests",
    "code": "codes", "codes": "codes",
    "result": "results", "results": "results",
    "record": "records", "records": "records",
    "entry": "entries", "entries": "entries",
    "message": "messages", "messages": "messages",
    "login": "logins", "logins": "logins",
    "retry": "retries", "retries": "retries",
}

_DURATION_RE = re.compile(
    _NUMBER + _GAP + r"(" + "|".join(sorted(_DURATION_UNITS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_SIZE_RE = re.compile(
    _NUMBER + _GAP + r"(" + "|".join(sorted(_SIZE_UNITS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_LENGTH_RE = re.compile(
    _NUMBER + _GAP + r"(" + "|".join(sorted(_LENGTH_UNITS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_DIGITS_RE = re.compile(_NUMBER + _GAP + r"(digits?)\b", re.IGNORECASE)
# "5 failed verification attempts": the number, up to three words, then the noun.
_COUNT_RE = re.compile(
    _NUMBER
    + r"\s+((?:[A-Za-z][A-Za-z-]*\s+){0,3}?)("
    + "|".join(sorted(_COUNT_UNITS, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Boundary:
    source: str  # "AC-11"
    phrase: str  # "5 failed verification attempts"
    values: list[str]  # ["4 attempts", "5 attempts", "6 attempts"]
    kind: str  # "count" | "size" | "duration" | "length" | "digits"

    @property
    def label(self) -> str:
        """How the checklist writes it: "4 / 5 / 6 failed verification attempts".

        The words the criterion itself used come first, because "4 / 5 / 6
        failed attempts" tells a reader which limit this is and "4 / 5 / 6
        attempts" does not. A phrase with nothing but the number and its unit
        falls back to the unit.
        """
        numbers = " / ".join(value.split(" ", 1)[0] for value in self.values)
        unit = self.values[-1].split(" ", 1)[1] if " " in self.values[-1] else ""
        tail = re.sub(r"^\s*\d+(?:\.\d+)?\s*-?\s*", "", self.phrase).strip()
        words = tail.split()
        return f"{numbers} {tail if len(words) >= 2 else unit}".strip()

    @property
    def id(self) -> str:
        return f"boundary:{self.source}:{self.values[0]}"


def _mask(text: str) -> str:
    """Blank out ids, versions and years, keeping every other character in place."""
    masked = text
    for pattern in (_ID, _VERSION, _YEAR):
        masked = pattern.sub(lambda match: " " * len(match.group(0)), masked)
    return masked


def _number_text(value: float) -> str:
    """2.0 -> "2", 4.99 -> "4.99"."""
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _step_values(amount: float, unit: str) -> list[str]:
    return [f"{_number_text(amount + step)} {unit}" for step in (-1, 0, 1)]


def _size_values(amount: float, unit: str) -> list[str]:
    """Just under, exactly, and one byte over — written the way a tester writes it."""
    return [
        f"{_number_text(round(amount - 0.01, 2))} {unit}",
        f"{_number_text(amount)} {unit}",
        f"{_number_text(round(amount + 0.01, 2))} {unit}",
    ]


def _duration_values(amount: float, unit: str) -> list[str]:
    # One millisecond either side of 500 ms is not a boundary anybody can feel.
    if unit == "ms":
        return [
            f"{_number_text(round(amount * 0.9, 2))} ms",
            f"{_number_text(amount)} ms",
            f"{_number_text(round(amount * 1.1, 2))} ms",
        ]
    return _step_values(amount, unit)


def _found(text: str, source: str) -> list[Boundary]:
    masked = _mask(text)
    found: list[tuple[int, Boundary]] = []
    taken: list[tuple[int, int]] = []

    def claim(start: int, end: int) -> bool:
        if any(start < other_end and other_start < end for other_start, other_end in taken):
            return False
        taken.append((start, end))
        return True

    # Most specific first: "6-digit" is digits, never a count of sixes.
    for pattern, kind, units in (
        (_DIGITS_RE, "digits", None),
        (_SIZE_RE, "size", _SIZE_UNITS),
        (_DURATION_RE, "duration", _DURATION_UNITS),
        (_LENGTH_RE, "length", _LENGTH_UNITS),
    ):
        for match in pattern.finditer(masked):
            if not claim(match.start(), match.end()):
                continue
            amount = float(match.group(1))
            if kind == "digits":
                values = _step_values(amount, "digits")
            elif kind == "size":
                values = _size_values(amount, units[match.group(2).lower()])
            elif kind == "duration":
                values = _duration_values(amount, units[match.group(2).lower()])
            else:
                values = _step_values(amount, units[match.group(2).lower()])
            found.append(
                (match.start(), Boundary(source, match.group(0).strip(), values, kind))
            )

    for match in _COUNT_RE.finditer(masked):
        if not claim(match.start(), match.end()):
            continue
        amount = float(match.group(1))
        unit = _COUNT_UNITS[match.group(3).lower()]
        found.append(
            (match.start(), Boundary(source, match.group(0).strip(), _step_values(amount, unit), "count"))
        )

    found.sort(key=lambda item: item[0])
    return [boundary for _, boundary in found]


def find_boundaries(criteria: list[Criterion]) -> list[Boundary]:
    """Every testable number in the criteria, in criterion order, at most 12."""
    boundaries: list[Boundary] = []
    seen: set[tuple[str, str]] = set()
    for criterion in criteria or []:
        for boundary in _found(criterion.text, criterion.id):
            key = (boundary.kind, boundary.values[1])
            if key in seen:
                continue
            seen.add(key)
            boundaries.append(boundary)
            if len(boundaries) >= MAX_BOUNDARIES:
                return boundaries
    return boundaries


# ──────────────────────────────────────────────────────────────────────────────
# Is this value anywhere in the cases the AI wrote?
# ──────────────────────────────────────────────────────────────────────────────

# What a tester writes instead of "5.01 MB".
_OVER_SIZE = (
    "1 byte over", "one byte over", "byte over the limit", "byte above",
    "+1 byte", "and 1 byte", "and one byte", "1 byte more", "one byte more",
    "byte past the limit", "byte too many", "1 byte larger", "one byte larger",
)

# "four attempts" is "4 attempts" said out loud.
_WORD_NUMBERS = {
    "zero": 0.0, "one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0,
    "five": 5.0, "six": 6.0, "seven": 7.0, "eight": 8.0, "nine": 9.0,
    "ten": 10.0, "eleven": 11.0, "twelve": 12.0, "thirteen": 13.0,
    "fourteen": 14.0, "fifteen": 15.0, "sixteen": 16.0, "seventeen": 17.0,
    "eighteen": 18.0, "nineteen": 19.0, "twenty": 20.0, "thirty": 30.0,
    "forty": 40.0, "fifty": 50.0, "sixty": 60.0, "ninety": 90.0,
    "hundred": 100.0,
}

# One spelling per quantity, so "5 MB", "5.00 megabytes" and "5120 KB" are
# one number and "14 min", "14 minutes" and "14:00" are another.
_BYTES = {"B": 1.0, "KB": 1024.0, "MB": 1024.0**2, "GB": 1024.0**3}
_SECONDS = {
    "ms": 0.001, "seconds": 1.0, "minutes": 60.0, "hours": 3600.0,
    "days": 86400.0, "weeks": 604800.0,
}
# The unit a value is counted in -> the family it is measured in.
_FAMILY = {name: "bytes" for name in _BYTES}
_FAMILY.update({name: "seconds" for name in _SECONDS})

# Written as a word or as digits, with or without a space or hyphen before
# the unit: "5MB", "5 MB", "5-digit", "four attempts".
_AMOUNT = r"(?<![\w.])(\d+(?:\.\d+)?|" + "|".join(sorted(_WORD_NUMBERS, key=len, reverse=True)) + r")"
_JOIN = r"[\s-]*"


def _unit_group(units) -> str:
    return r"(" + "|".join(sorted(units, key=len, reverse=True)) + r")\b"


_SAID_SIZE = re.compile(
    _AMOUNT + _JOIN + _unit_group(list(_SIZE_UNITS) + ["byte", "bytes"]),
    re.IGNORECASE,
)
_SAID_DURATION = re.compile(_AMOUNT + _JOIN + _unit_group(_DURATION_UNITS), re.IGNORECASE)
_SAID_LENGTH = re.compile(_AMOUNT + _JOIN + _unit_group(_LENGTH_UNITS), re.IGNORECASE)
_SAID_DIGITS = re.compile(_AMOUNT + _JOIN + r"(digits?)\b", re.IGNORECASE)
_SAID_COUNT = re.compile(
    _AMOUNT
    + r"\s+((?:[A-Za-z][A-Za-z-]*\s+){0,3}?)"
    + _unit_group(_COUNT_UNITS),
    re.IGNORECASE,
)
# A quoted code says its own length: '12345' is five digits.
_QUOTED_CODE = re.compile(r"[\"'‘’“”](\d{2,})[\"'‘’“”]")
# "locked for 14:00" is fourteen minutes.
_CLOCK = re.compile(r"(?<![\w:.])(\d{1,3}):([0-5]\d)(?![\d:])")


def _amount_of(written: str) -> float | None:
    word = written.strip().lower()
    if word in _WORD_NUMBERS:
        return _WORD_NUMBERS[word]
    try:
        return float(word)
    except ValueError:
        return None


def _one_quantity(amount: float, unit: str) -> tuple[str, float]:
    """The quantity in the one spelling everything is compared in."""
    family = _FAMILY.get(unit)
    if family == "bytes":
        return ("bytes", amount * _BYTES[unit])
    if family == "seconds":
        return ("seconds", amount * _SECONDS[unit])
    return (unit, amount)


def quantities(text: str) -> list[tuple[str, float]]:
    """Every quantity this text states, however it chose to write it."""
    said: list[tuple[str, float]] = []

    def take(pattern, units, unit_group: int) -> None:
        for match in pattern.finditer(text):
            amount = _amount_of(match.group(1))
            if amount is None:
                continue
            written = match.group(unit_group).lower()
            said.append(_one_quantity(amount, units.get(written, written)))

    take(_SAID_SIZE, {**_SIZE_UNITS, "byte": "B", "bytes": "B"}, 2)
    take(_SAID_DURATION, _DURATION_UNITS, 2)
    take(_SAID_LENGTH, _LENGTH_UNITS, 2)
    take(_SAID_DIGITS, {"digit": "digits", "digits": "digits"}, 2)
    take(_SAID_COUNT, _COUNT_UNITS, 3)
    for match in _QUOTED_CODE.finditer(text):
        said.append(("digits", float(len(match.group(1)))))
    for match in _CLOCK.finditer(text):
        said.append(
            _one_quantity(float(match.group(1)) + float(match.group(2)) / 60.0, "minutes")
        )
    return said


def case_text(case: TestCase) -> str:
    """Everything of a case a boundary value could be written in."""
    return " ".join(
        [
            str(case.title or ""),
            str(case.pre_conditions or ""),
            " ".join(case.steps or []),
            str(case.expected_result or ""),
            str(case.test_data or ""),
            " ".join(case.tags or []),
        ]
    )


def _as_quantity(value: str) -> tuple[str, float] | None:
    """One of a boundary's own values -- "4.99 MB" -- in the same spelling."""
    number, _, unit = value.partition(" ")
    amount = _amount_of(number)
    if amount is None or not unit:
        return None
    return _one_quantity(amount, unit)


def _same(left: float, right: float) -> bool:
    return abs(left - right) <= max(abs(right), 1.0) * 1e-9


def _value_in(value: str, said: list[tuple[str, float]]) -> bool:
    """Did the cases state this quantity, in any of the ways people write it?"""
    wanted = _as_quantity(value)
    if wanted is None:
        return False
    unit, amount = wanted
    return any(other == unit and _same(number, amount) for other, number in said)


def states_value(text: str, value: str) -> bool:
    """Does this sentence state this quantity, however it spells it?

    "2 MB", "2.00 megabytes" and "2,097,152 bytes" are one number, so the
    criterion that refuses a photo at the limit can be found from the
    criterion that allows one under it.
    """
    return _value_in(value, quantities(str(text or "").replace(",", "")))


def boundary_covered(b: Boundary, cases: list[TestCase]) -> list[str]:
    """Which of the boundary's values the cases state, however they spell it.

    A tester writes "a 5-digit code '12345'", "5.00 megabytes" or "four
    attempts" and means the value this boundary asks for. Reading the number
    only as it was written here is how a limit test gets added twice.
    """
    text = " \n ".join(case_text(case) for case in cases or [])
    said = quantities(text)
    lowered = text.lower()
    covered = []
    for index, value in enumerate(b.values):
        if _value_in(value, said):
            covered.append(value)
        elif b.kind == "size" and index == 2 and any(one in lowered for one in _OVER_SIZE):
            covered.append(value)
    return covered


def missing_values(b: Boundary, cases: list[TestCase]) -> list[str]:
    covered = set(boundary_covered(b, cases))
    return [value for value in b.values if value not in covered]
