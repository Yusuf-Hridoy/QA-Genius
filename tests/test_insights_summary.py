"""The facts the AI sees, the prompt, and the guard on what it answers."""

from qagenius.insights_summary import clean_summary, facts_text, insights_prompt
from qagenius.models import GroupInsight, QualityInsightSummary
from qagenius.report_parsers import RunReport, TestResult
from qagenius.test_run_metrics import compute_insights


def result(
    name: str,
    status: str = "passed",
    message: str = "",
    duration_s: float = 1.0,
    details: str = "",
) -> TestResult:
    return TestResult(
        test_id=f"checkout.spec::{name}",
        name=name,
        suite="checkout.spec",
        status=status,
        duration_s=duration_s,
        message=message,
        details=details,
    )


def _small():
    chromium = RunReport(
        label="nightly-chromium",
        format="junit",
        tests=[
            result("pay with card", "failed", "Timeout 30000ms exceeded waiting for '#pay'",
                   duration_s=30.0, details="TimeoutError\n  at checkout.spec.ts:42:5"),
            result("pay with paypal", "failed", "Timeout 9000ms exceeded waiting for '#pal'",
                   duration_s=9.0),
            result("remember me", "flaky", "retried once", duration_s=6.0),
            result("show the cart", duration_s=2.0),
            result("print the receipt", "skipped", duration_s=0.0),
        ],
    )
    firefox = RunReport(
        label="nightly-firefox",
        format="playwright",
        tests=[result("show the cart", "failed", "Cart total was 0", duration_s=3.0)],
    )
    return compute_insights([chromium, firefox])


EXPECTED_FACTS = """Runs: 2
Run "nightly-chromium": 5 tests, 1 passed, 2 failed, 1 skipped, 1 flaky, pass rate 50%, 47.0 s
Run "nightly-firefox": 1 tests, 0 passed, 1 failed, 0 skipped, 0 flaky, pass rate 0%, 3.0 s
All runs: 6 results, pass rate 40%

Failure groups (largest first):
G1 — 2 failures in 1 run — signature: Timeout Nms exceeded waiting for "…"
  Example message: Timeout 30000ms exceeded waiting for '#pay'
  Tests: pay with card; pay with paypal
  Example details (trimmed): TimeoutError
  at checkout.spec.ts:42:5
G2 — 1 failure in 1 run — signature: Cart total was N
  Example message: Cart total was 0
  Tests: show the cart

Flaky tests:
- remember me (retried and passed) in nightly-chromium
- show the cart (passed in one run, failed in another) in nightly-chromium, nightly-firefox

Slowest tests: pay with card 30.0 s; pay with paypal 9.0 s; remember me 6.0 s; \
show the cart 3.0 s; print the receipt 0.0 s"""


def test_facts_text_has_the_exact_shape() -> None:
    assert facts_text(_small()) == EXPECTED_FACTS


def test_facts_text_never_contains_raw_report_markup() -> None:
    facts = facts_text(_small())

    assert "<testcase" not in facts
    assert "<testsuite" not in facts


def test_facts_text_says_none_when_everything_passed() -> None:
    insights = compute_insights(
        [RunReport(label="green", format="junit", tests=[result("a")])]
    )
    facts = facts_text(insights)

    assert "Failure groups: none" in facts
    assert "Flaky tests: none" in facts


def test_facts_text_trims_long_lists() -> None:
    tests = [
        result(f"case {number}", "failed", f"Error kind {chr(65 + number)} happened")
        for number in range(18)
    ]
    insights = compute_insights([RunReport(label="big", format="junit", tests=tests)])
    facts = facts_text(insights)

    assert "G15 —" in facts
    assert "G16 —" not in facts
    assert "(+3 more groups not shown)" in facts


def test_facts_text_counts_the_tests_it_did_not_list() -> None:
    tests = [
        result(f"case {number}", "failed", f"Timeout {number}ms exceeded")
        for number in range(8)
    ]
    insights = compute_insights([RunReport(label="big", format="junit", tests=tests)])

    assert "(+3 more)" in facts_text(insights)


def test_the_system_text_forbids_inventing_numbers() -> None:
    system, user = insights_prompt("Runs: 1")

    assert "do not invent numbers" in system
    assert "Only use group ids that appear in the facts" in system
    assert user == "Test run facts:\n\nRuns: 1"


def test_the_kind_field_is_tolerant() -> None:
    def kind(raw: str) -> str:
        return GroupInsight(
            group_id="G1", kind=raw, likely_cause="c", suggested_action="a"
        ).kind

    assert kind("Product Bug") == "product bug"
    assert kind("bug") == "product bug"
    assert kind("flaky test") == "test issue"
    assert kind("Test") == "test issue"
    assert kind("infra") == "environment"
    assert kind("weird") == "unknown"
    assert kind("") == "unknown"


def _insight(group_id: str, kind: str = "test issue") -> GroupInsight:
    return GroupInsight(
        group_id=group_id,
        kind=kind,
        likely_cause="The locator waits for an element that never appears.",
        suggested_action="Re-record the locator.",
    )


def test_clean_summary_drops_unknown_groups_and_repeats() -> None:
    insights = _small()
    summary = QualityInsightSummary(
        headline="Checkout is timing out.",
        assessment="Two groups, one of them a real bug.",
        groups=[_insight("G1"), _insight("G9"), _insight("G1", "product bug")],
        next_steps=["Re-run the checkout suite"],
    )

    cleaned, notes = clean_summary(summary, insights)

    assert [group.group_id for group in cleaned.groups] == ["G1"]
    assert cleaned.groups[0].kind == "test issue"
    assert notes == [
        "Removed an explanation for unknown group G9.",
        "Removed a second explanation for group G1.",
    ]
    assert cleaned.headline == summary.headline


def test_clean_summary_keeps_a_good_answer_as_it_is() -> None:
    insights = _small()
    summary = QualityInsightSummary(
        headline="Checkout is timing out.",
        assessment="Both groups look like waits.",
        groups=[_insight("G1"), _insight("G2", "product bug")],
    )

    cleaned, notes = clean_summary(summary, insights)

    assert notes == []
    assert [group.group_id for group in cleaned.groups] == ["G1", "G2"]
