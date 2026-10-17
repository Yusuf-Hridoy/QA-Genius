"""Measured against budgeted, and the two exports CI can run."""

import json

import pytest

from qagenius.pagespeed import Measurement
from qagenius.performance_budget import build_budget
from qagenius.performance_check import (
    FIELD_FROM,
    LAB_FROM,
    TBT_FROM,
    compare,
    k6_thresholds,
    lighthouse_budget_json,
)

PAGE = "https://aurora-storefront.example/"


def measurement(**overrides) -> Measurement:
    values = {
        "url": PAGE,
        "strategy": "mobile",
        "lab": {"lcp": 3612.5, "cls": 0.064, "fcp": 1540, "ttfb": 410, "tbt": 340,
                "weight": 2048.0},
        "field": {},
        "performance_score": 62,
        "fetched_at": "2026-01-14T09:21:44+00:00",
    }
    values.update(overrides)
    return Measurement(**values)


def result_of(results, line_id: str):
    return {item.line.id: item for item in results}[line_id]


# ------------------------------------------------------------------ compare


def test_a_line_under_its_limit_is_within():
    budget = build_budget([], None, [])
    found = result_of(compare(budget, measurement()), "fcp")
    assert found.status == "within"
    assert (found.measured, found.measured_from) == (1540, LAB_FROM)


def test_a_line_over_its_limit_is_over():
    budget = build_budget([], None, [])
    found = result_of(compare(budget, measurement()), "lcp")
    assert found.status == "over"
    assert found.measured == 3612.5


def test_a_line_with_no_measurement_is_not_measured():
    budget = build_budget([], None, [])
    found = result_of(compare(budget, measurement(lab={}, field={})), "lcp")
    assert found.status == "not_measured"
    assert (found.measured, found.measured_from) == (None, "")


def test_every_line_is_not_measured_before_a_run():
    budget = build_budget([], None, [])
    statuses = {item.status for item in compare(budget, None)}
    assert statuses == {"not_measured"}


def test_a_custom_line_is_never_measured():
    budget = build_budget(["The bar collapses below 768 pixels"], None, [])
    found = result_of(compare(budget, measurement()), "custom-1")
    assert found.status == "not_measurable"
    assert found.measured is None


def test_real_user_data_beats_the_lab():
    budget = build_budget([], None, [])
    found = result_of(
        compare(budget, measurement(field={"lcp": 2100, "cls": 0.02})), "lcp"
    )
    assert (found.measured, found.measured_from) == (2100, FIELD_FROM)
    assert found.status == "within"


def test_blocking_time_stands_in_for_inp_and_says_so():
    """Lighthouse has no INP, so the proxy is labelled rather than hidden."""
    budget = build_budget([], None, [])
    found = result_of(compare(budget, measurement()), "inp")
    assert (found.measured, found.measured_from) == (340, TBT_FROM)
    assert found.status == "over"  # 340 ms against the 200 ms INP budget


def test_a_real_inp_from_users_beats_the_proxy():
    budget = build_budget([], None, [])
    found = result_of(compare(budget, measurement(field={"inp": 184})), "inp")
    assert (found.measured, found.measured_from) == (184, FIELD_FROM)
    assert found.status == "within"


def test_inp_with_neither_field_nor_blocking_time_is_not_measured():
    budget = build_budget([], None, [])
    thin = measurement(lab={"lcp": 1000}, field={})
    assert result_of(compare(budget, thin), "inp").status == "not_measured"


def test_a_requirement_limit_is_what_the_line_is_judged_against():
    budget = build_budget(["The view routes within 400ms"], None, [])
    found = result_of(compare(budget, measurement()), "inp")
    assert found.line.limit == 400.0
    assert found.status == "within"  # TBT 340 against the agreed 400 ms


def test_the_results_follow_the_budget_order():
    budget = build_budget(["The bar collapses below 768 pixels"], None, [])
    results = compare(budget, measurement())
    assert [item.line.id for item in results] == [line.id for line in budget.lines]


# ------------------------------------------------------------------ exports


def test_the_lighthouse_budget_parses_and_names_the_metrics():
    document = json.loads(lighthouse_budget_json(build_budget([], None, [])))
    assert isinstance(document, list) and len(document) == 1
    entry = document[0]
    assert entry["path"] == "/*"
    found = {row["metric"]: row["budget"] for row in entry["timings"]}
    assert found == {
        "largest-contentful-paint": 2500,
        "cumulative-layout-shift": 0.1,
        "first-contentful-paint": 1800,
        "total-blocking-time": 200,
    }
    assert entry["resourceSizes"] == [{"resourceType": "total", "budget": 1600}]


def test_the_lighthouse_budget_uses_the_agreed_numbers():
    budget = build_budget(
        ["The page loads in under 2 seconds", "The view routes within 150ms"], None, []
    )
    entry = json.loads(lighthouse_budget_json(budget))[0]
    found = {row["metric"]: row["budget"] for row in entry["timings"]}
    assert found["largest-contentful-paint"] == 2000.0
    assert found["total-blocking-time"] == 150.0


def test_a_custom_line_never_reaches_the_lighthouse_budget():
    """768 px is not a timing, and Lighthouse would reject it."""
    budget = build_budget(["The bar collapses below 768 pixels"], None, [])
    entry = json.loads(lighthouse_budget_json(budget))[0]
    assert all(row["budget"] != 768.0 for row in entry["timings"])
    assert len(entry["timings"]) == 4


def test_the_k6_snippet_carries_the_server_budget():
    snippet = k6_thresholds(build_budget(["The API responds within 300 ms"], None, []))
    assert "http_req_duration: ['p(95)<300']" in snippet
    assert "http_req_failed: ['rate<0.01']" in snippet
    assert "export const options" in snippet


def test_the_k6_snippet_says_what_k6_cannot_measure():
    snippet = k6_thresholds(build_budget([], None, []))
    assert "Lighthouse budget.json" in snippet
    assert "p(95)<800" in snippet


@pytest.mark.parametrize("export", [lighthouse_budget_json, k6_thresholds])
def test_an_empty_budget_still_exports(export):
    assert export(build_budget([], None, [])).strip()
