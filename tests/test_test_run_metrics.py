"""Pass rates, failure groups, flaky tests and the slowest list. All computed by code."""

import pytest

from qagenius.report_parsers import RunReport, TestResult
from qagenius.test_run_metrics import (
    CROSS_RUN,
    RETRIED,
    compute_insights,
    insights_from_dict,
    insights_to_dict,
    normalise_signature,
)


def result(
    name: str,
    status: str = "passed",
    message: str = "",
    duration_s: float = 1.0,
    suite: str = "checkout.spec",
    details: str = "",
) -> TestResult:
    return TestResult(
        test_id=f"{suite}::{name}",
        name=name,
        suite=suite,
        status=status,
        duration_s=duration_s,
        message=message,
        details=details,
    )


def run(label: str, *tests: TestResult) -> RunReport:
    return RunReport(label=label, format="junit", tests=list(tests))


# ---------- signatures ----------


def test_the_same_timeout_with_different_numbers_shares_a_signature() -> None:
    first = normalise_signature("Timeout 30000ms exceeded waiting for locator('#submit')")
    second = normalise_signature("Timeout 5000ms exceeded waiting for locator('#login')")

    assert first == second
    assert "30000" not in first


def test_urls_paths_hex_and_numbers_are_normalised() -> None:
    assert "<url>" in normalise_signature("GET https://shop.example.com/cart failed")
    assert "<file>" in normalise_signature("AssertionError at checkout.spec.ts:12:5")
    assert "<hex>" in normalise_signature("Order 0xdeadbeef was not found")
    assert "<hex>" in normalise_signature("Order a1b2c3d4e5 was not found")
    assert normalise_signature("Expected 3 items") == "Expected N items"


def test_a_signature_uses_the_first_line_without_colour_codes() -> None:
    signature = normalise_signature("\x1b[31mExpected true\x1b[39m\nsecond line")

    assert signature == "Expected true"


def test_an_empty_message_has_a_signature_of_its_own() -> None:
    assert normalise_signature("") == "(no message)"
    assert normalise_signature("   \n  ") == "(no message)"


def test_a_very_long_message_is_cut_to_160_characters() -> None:
    assert len(normalise_signature("word " * 200)) == 160


# ---------- pass rate ----------


def test_pass_rate_leaves_skipped_tests_out() -> None:
    insights = compute_insights(
        [
            run(
                "nightly",
                result("a"),
                result("b"),
                result("c", "failed", "boom"),
                result("d", "skipped"),
            )
        ]
    )

    assert insights.overall.total == 4
    assert insights.overall.pass_rate == 67
    assert insights.overall.skipped == 1


def test_a_run_of_only_skipped_tests_is_a_hundred_percent() -> None:
    insights = compute_insights([run("nightly", result("a", "skipped"))])

    assert insights.overall.pass_rate == 100


def test_a_flaky_test_counts_as_a_pass_for_the_rate() -> None:
    insights = compute_insights([run("nightly", result("a", "flaky", "retried"))])

    assert insights.overall.pass_rate == 100
    assert insights.overall.flaky == 1


# ---------- groups ----------


def test_timeouts_with_different_numbers_make_one_group() -> None:
    insights = compute_insights(
        [
            run(
                "nightly",
                result("pay", "failed", "Timeout 30000ms exceeded waiting for locator('#pay')"),
                result("ship", "failed", "Timeout 9000ms exceeded waiting for locator('#ship')"),
                result("gift", "failed", "Timeout 1000ms exceeded waiting for locator('#gift')"),
            )
        ]
    )

    assert len(insights.groups) == 1
    group = insights.groups[0]
    assert group.id == "G1"
    assert group.count == 3
    assert group.tests == ["pay", "ship", "gift"]
    assert group.runs == ["nightly"]
    assert group.example_message.startswith("Timeout 30000ms")


def test_groups_are_ordered_by_size_then_first_appearance() -> None:
    insights = compute_insights(
        [
            run(
                "nightly",
                result("a", "failed", "Cart total was wrong"),
                result("b", "failed", "Timeout 1ms exceeded"),
                result("c", "failed", "Timeout 2ms exceeded"),
                result("d", "failed", "Timeout 3ms exceeded"),
                result("e", "failed", "Cart total was wrong"),
            )
        ]
    )

    assert [group.id for group in insights.groups] == ["G1", "G2"]
    assert [group.count for group in insights.groups] == [3, 2]
    assert insights.groups[0].signature.startswith("Timeout")


def test_a_group_records_every_run_it_appeared_in() -> None:
    insights = compute_insights(
        [
            run("chromium", result("pay", "failed", "Timeout 100ms exceeded")),
            run("firefox", result("pay", "failed", "Timeout 200ms exceeded")),
        ]
    )

    assert insights.groups[0].count == 2
    assert insights.groups[0].runs == ["chromium", "firefox"]


def test_only_failed_results_are_grouped() -> None:
    insights = compute_insights(
        [run("nightly", result("a", "flaky", "retried once"), result("b"))]
    )

    assert insights.groups == []


# ---------- flaky ----------


def test_a_retried_result_is_flaky() -> None:
    insights = compute_insights([run("nightly", result("login", "flaky", "retried"))])

    assert [(test.name, test.reason, test.runs) for test in insights.flaky] == [
        ("login", RETRIED, ["nightly"])
    ]


def test_passing_in_one_run_and_failing_in_another_is_flaky() -> None:
    insights = compute_insights(
        [
            run("chromium", result("search")),
            run("firefox", result("search", "failed", "No suggestions")),
        ]
    )

    assert len(insights.flaky) == 1
    assert insights.flaky[0].reason == CROSS_RUN
    assert insights.flaky[0].runs == ["chromium", "firefox"]


def test_a_test_that_fails_in_both_runs_is_not_flaky() -> None:
    insights = compute_insights(
        [
            run("chromium", result("pay", "failed", "boom")),
            run("firefox", result("pay", "failed", "boom")),
        ]
    )

    assert insights.flaky == []


def test_one_entry_per_test_and_the_first_reason_wins() -> None:
    insights = compute_insights(
        [
            run("chromium", result("login", "flaky", "retried")),
            run("firefox", result("login", "failed", "boom")),
        ]
    )

    assert len(insights.flaky) == 1
    assert insights.flaky[0].reason == RETRIED


# ---------- slowest and overall ----------


def test_slowest_lists_the_top_five_longest_first() -> None:
    insights = compute_insights(
        [
            run(
                "nightly",
                *[
                    result(f"case {number}", duration_s=float(number))
                    for number in range(1, 8)
                ],
            )
        ]
    )

    assert insights.slowest == [
        ("case 7", 7.0),
        ("case 6", 6.0),
        ("case 5", 5.0),
        ("case 4", 4.0),
        ("case 3", 3.0),
    ]


def test_overall_counts_every_result_across_runs() -> None:
    insights = compute_insights(
        [
            run("chromium", result("a", duration_s=2.0), result("b", "failed", "boom")),
            run("firefox", result("a", duration_s=3.0), result("b", "failed", "boom")),
        ]
    )

    assert [summary.label for summary in insights.runs] == ["chromium", "firefox"]
    assert insights.overall.label == "All runs"
    assert insights.overall.total == 4
    assert insights.overall.failed == 2
    assert insights.overall.duration_s == pytest.approx(7.0)
    # The same test in two runs takes one row in the slowest list.
    assert insights.slowest[0] == ("a", 3.0)


# ---------- round trip ----------


def test_insights_survive_a_round_trip_through_json() -> None:
    insights = compute_insights(
        [
            run("chromium", result("pay", "failed", "Timeout 100ms exceeded")),
            run("firefox", result("pay", "flaky", "retried", duration_s=4.0)),
        ]
    )

    assert insights_from_dict(insights_to_dict(insights)) == insights


def test_a_wrong_shape_is_refused() -> None:
    with pytest.raises(ValueError):
        insights_from_dict({"runs": [], "overall": {}, "groups": []})
    with pytest.raises(ValueError):
        insights_from_dict("not an object")
