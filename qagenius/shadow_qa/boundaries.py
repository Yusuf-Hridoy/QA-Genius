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
# How far apart a number and its unit may sit and still be one mention.
_NEAR = 28

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
_OVER_SIZE = ("1 byte over", "one byte over", "byte over the limit", "byte above")


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


def _value_in(value: str, text: str) -> bool:
    """The number and its unit, close enough together to be one statement."""
    number, _, unit = value.partition(" ")
    if not unit:
        return False
    number_re = re.compile(r"(?<![\d.])" + re.escape(number) + r"(?![\d])")
    unit_re = re.compile(r"(?<![\w-])" + re.escape(unit.rstrip("s")), re.IGNORECASE)
    spots = [match.start() for match in number_re.finditer(text)]
    if not spots:
        return False
    units = [match.start() for match in unit_re.finditer(text)]
    return any(abs(spot - other) <= _NEAR for spot in spots for other in units)


def boundary_covered(b: Boundary, cases: list[TestCase]) -> list[str]:
    """Which of the boundary's values appear in at least one of the cases."""
    text = " \n ".join(case_text(case) for case in cases or [])
    lowered = text.lower()
    covered = []
    for index, value in enumerate(b.values):
        if _value_in(value, text):
            covered.append(value)
        elif b.kind == "size" and index == 2 and any(one in lowered for one in _OVER_SIZE):
            covered.append(value)
    return covered


def missing_values(b: Boundary, cases: list[TestCase]) -> list[str]:
    covered = set(boundary_covered(b, cases))
    return [value for value in b.values if value not in covered]
