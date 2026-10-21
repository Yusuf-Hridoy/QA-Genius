from qagenius.models import Interpretation, NumberReading
from qagenius.numbers import match_numbers, parse_quantity, read_scope, scopes_clash


def _reading(*pairs: tuple[str, str]) -> Interpretation:
    return Interpretation(
        numbers=[
            NumberReading(name=name, value=value, source_phrase="")
            for name, value in pairs
        ]
    )


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


def test_real_run_numbers() -> None:
    reading_a = _reading(
        ("Failed Password Attempt Limit", "5 attempts"),
        ("Lockout Response Time", "1 second"),
        ("Account Lockout Duration", "30 minutes"),
    )
    reading_b = _reading(
        ("Failed password threshold", "5 attempts"),
        ("Lock execution time limit", "3 seconds"),
        ("Account lockout duration", "30 minutes"),
    )
    matches = match_numbers(reading_a, reading_b)
    assert [(m.name, m.value_a, m.value_b, m.status) for m in matches] == [
        ("Failed Password Attempt Limit", "5 attempts", "5 attempts", "same"),
        ("Lockout Response Time", "1 second", "3 seconds", "different"),
        ("Account Lockout Duration", "30 minutes", "30 minutes", "same"),
    ]


def test_units_converted() -> None:
    matches = match_numbers(
        _reading(("Lockout duration", "1 minute")),
        _reading(("Lockout duration", "60 seconds")),
    )
    assert len(matches) == 1
    assert matches[0].status == "same"


def test_different_families_never_pair() -> None:
    matches = match_numbers(
        _reading(("Attempt limit", "5 attempts")),
        _reading(("Attempt limit", "5 minutes")),
    )
    assert [m.status for m in matches] == ["only_a", "only_b"]


def test_unmatched_reported() -> None:
    matches = match_numbers(
        _reading(("Lockout duration", "30 minutes"), ("Session timeout", "20 minutes")),
        _reading(("Lockout duration", "30 minutes")),
    )
    assert [(m.name, m.status) for m in matches] == [
        ("Lockout duration", "same"),
        ("Session timeout", "only_a"),
    ]


def test_empty_readers() -> None:
    assert match_numbers(_reading(), _reading()) == []


def test_thousands_separator() -> None:
    quantity = parse_quantity("1,000 attempts")
    assert quantity is not None
    assert quantity.family == "count"
    assert quantity.amount == 1000


def test_thousands_separator_with_decimal() -> None:
    quantity = parse_quantity("12,500.5 seconds")
    assert quantity is not None
    assert quantity.family == "time"
    assert quantity.amount == 12500.5


def test_comma_as_decimal_point() -> None:
    quantity = parse_quantity("1,5 hours")
    assert quantity is not None
    assert quantity.family == "time"
    assert quantity.amount == 5400


# ---------- scope: what a limit counts against ----------


def test_scope_read_from_the_name() -> None:
    assert read_scope("Coupon limit per order") == "order"
    assert read_scope("Coupon usage limit per account") == "account"
    assert read_scope("Total coupons") == "total"
    assert read_scope("Attempt limit") is None


def test_scopes_clash_only_when_both_are_stated() -> None:
    assert scopes_clash("Coupon limit per order", "Coupon uses per account")
    assert not scopes_clash("Coupon limit per order", "Coupon limit")
    assert not scopes_clash("Coupon limit per order", "Coupons per order")


def test_different_scopes_never_pair() -> None:
    # The real run paired "1 coupon per order" with "1 use per account" and
    # called the readers wrong about a limit they never both named.
    matches = match_numbers(
        _reading(("Coupon limit per order", "1 coupon")),
        _reading(("Coupon usage limit per account", "1 use")),
    )
    assert [m.status for m in matches] == ["only_a", "only_b"]


def test_same_number_said_two_ways_is_not_a_difference() -> None:
    matches = match_numbers(
        _reading(("Coupon limit", "1 coupon")),
        _reading(("Coupon limit", "1 use")),
    )
    assert [m.status for m in matches] == ["same"]


def test_free_text_the_code_cannot_read_is_a_check_not_a_difference() -> None:
    matches = match_numbers(
        _reading(("Lock reason", "too many tries")),
        _reading(("Lock reason", "repeated failures")),
    )
    assert [m.status for m in matches] == ["check"]


def test_two_different_counts_of_the_same_thing_still_differ() -> None:
    matches = match_numbers(
        _reading(("Coupon limit", "1 coupon")),
        _reading(("Coupon limit", "3 coupons")),
    )
    assert [m.status for m in matches] == ["different"]
