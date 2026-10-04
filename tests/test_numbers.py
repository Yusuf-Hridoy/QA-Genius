from qagenius.numbers import parse_quantity


def test_attempts_are_count() -> None:
    quantity = parse_quantity("5 attempts")
    assert quantity is not None
    assert quantity.family == "count"
    assert quantity.amount == 5


def test_single_second() -> None:
    quantity = parse_quantity("1 second")
    assert quantity is not None
    assert quantity.family == "time"
    assert quantity.amount == 1


def test_plural_seconds() -> None:
    quantity = parse_quantity("3 seconds")
    assert quantity is not None
    assert quantity.family == "time"
    assert quantity.amount == 3


def test_minutes_to_seconds() -> None:
    quantity = parse_quantity("30 minutes")
    assert quantity is not None
    assert quantity.family == "time"
    assert quantity.amount == 1800


def test_milliseconds_to_seconds() -> None:
    quantity = parse_quantity("1000 milliseconds")
    assert quantity is not None
    assert quantity.family == "time"
    assert quantity.amount == 1.0


def test_abbreviated_seconds() -> None:
    quantity = parse_quantity("within 60 sec")
    assert quantity is not None
    assert quantity.family == "time"
    assert quantity.amount == 60


def test_fractional_hours() -> None:
    quantity = parse_quantity("2.5 hours")
    assert quantity is not None
    assert quantity.family == "time"
    assert quantity.amount == 9000


def test_percent() -> None:
    quantity = parse_quantity("99.9%")
    assert quantity is not None
    assert quantity.family == "percent"
    assert quantity.amount == 99.9


def test_no_number_returns_none() -> None:
    assert parse_quantity("no limit") is None


def test_bare_number_is_other() -> None:
    quantity = parse_quantity("3")
    assert quantity is not None
    assert quantity.family == "other"
    assert quantity.amount == 3
