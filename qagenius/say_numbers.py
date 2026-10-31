"""Amounts written the way a person writes them.

A senior-tester note read "TC-001 uses 1.57286e+06 bytes". Nobody reads
that and thinks "a 1.5 MB photo", which is what it is. Everything on the
page compares in base units -- bytes, seconds -- because that is the only
way to compare at all; nothing on the page is allowed to *say* them that
way. One formatter, used by every note.

There is no AI and no network here: it is arithmetic and words.
"""

_BYTE_UNITS = (("GB", 1024.0**3), ("MB", 1024.0**2), ("KB", 1024.0))
_TIME_UNITS = (("day", 86400.0), ("hour", 3600.0), ("minute", 60.0))

# The base units every family is compared in, and the names a scan gives
# them. Anything else is a count of something, said as it was written.
BYTES = "bytes"
SECONDS = "seconds"
DIGITS = "digits"
MONEY_ANY = "money"
CURRENCY_SYMBOLS = ("$", "€", "£")
LOOSE_COUNT = "loose-count"

# Which family a unit belongs to. Two amounts are only ever compared, or
# weighed against a rule, when they answer the same name here.
FAMILIES = {BYTES: "size", SECONDS: "time", DIGITS: "length", MONEY_ANY: "money"}


def family_of(unit: str) -> str:
    """"size", "time", "money", "length" or "count"."""
    name = str(unit or "")
    if name in FAMILIES:
        return FAMILIES[name]
    if name in CURRENCY_SYMBOLS:
        return "money"
    return "count"


def plain(amount: float) -> str:
    """20.0 -> "20", 12.5 -> "12.5", and never 1.57286e+06."""
    rounded = round(float(amount), 4)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.4f}".rstrip("0").rstrip(".")


def _with_unit(amount: float, unit: str) -> str:
    """"1 minute", "11 minutes", "6 digits"."""
    return f"{plain(amount)} {unit}" if amount == 1 else f"{plain(amount)} {unit}s"


def say_size(amount: float) -> str:
    """1572864 -> "1.5 MB"; 2097153 -> "2 MB + 1 byte"."""
    for name, size in _BYTE_UNITS:
        if amount < size:
            continue
        whole = int(amount // size)
        rest = amount - whole * size
        if rest == 0:
            return f"{plain(amount / size)} {name}"
        # A hair past a round figure is the whole point of a limit test, so
        # it is said as what it is rather than as a long decimal.
        if rest <= 4:
            return f"{whole} {name} + {_with_unit(rest, 'byte')}"
        if size - rest <= 4:
            return f"{whole + 1} {name} − {_with_unit(size - rest, 'byte')}"
        return f"{plain(round(amount / size, 2))} {name}"
    return _with_unit(amount, "byte")


def say_time(amount: float) -> str:
    """660 -> "11 minutes"; 90 -> "1.5 minutes"; 30 -> "30 seconds"."""
    for name, size in _TIME_UNITS:
        if amount < size:
            continue
        if amount % size == 0:
            return _with_unit(amount / size, name)
        return _with_unit(round(amount / size, 2), name)
    return _with_unit(amount, "second")


def say_money(amount: float, symbol: str = "") -> str:
    """49.99 -> "$49.99". Money is always written to the cent."""
    head = symbol if symbol in CURRENCY_SYMBOLS else ""
    return f"{head}{amount:.2f}"


def say_amount(unit: str, amount: float) -> str:
    """One amount, in the words a reader would use for it.

    `unit` is whatever the scanner called it: a base unit ("bytes",
    "seconds"), a currency symbol, "digits", a counted noun ("attempts"),
    or the loose count it files a number of unknown things under.
    """
    name = str(unit or "")
    value = float(amount)
    if name == BYTES:
        return say_size(value)
    if name == SECONDS:
        return say_time(value)
    if name in CURRENCY_SYMBOLS:
        return say_money(value, name)
    if name == MONEY_ANY:
        return say_money(value)
    if name == DIGITS:
        return _with_unit(value, "digit")
    if not name or name == LOOSE_COUNT:
        return plain(value)
    return _with_unit(value, name.rstrip("s"))
