"""The budget is read out of the team's own words, or it is a labelled default."""

import pytest

from qagenius.models import FailureMode, RiskAnalysis
from qagenius.performance_budget import (
    DEFAULT_SOURCE,
    METRICS,
    WEIGHT_SOURCE,
    build_budget,
    extract_targets,
)
from tests.factories import case

# The owner's nav-bar run, with no real company in it.
NAV_CRITERIA = [
    "Given a signed-in user, When they open any module, "
    "Then the active module shows a highlight and bold text",
    "Then the application routes to the reports view within 200ms "
    "without a full page reload",
    "Then keyboard focus rings are visible and Enter navigates to the module",
    "Given a mobile screen width below 768 pixels, "
    "Then the bar is collapsed by default into a hamburger menu",
]


def risk(risk_id: str, title: str, category: str = "performance", **extra) -> FailureMode:
    values = {
        "id": risk_id,
        "title": title,
        "category": category,
        "effect": "",
        "cause": "",
        "severity": 3,
        "likelihood": 3,
        "detectability": 3,
        "related_criteria": [],
        "covered_by": [],
        "test_idea": "Measure it",
    }
    values.update(extra)
    return FailureMode(**values)


def line_of(budget, line_id: str):
    return {item.id: item for item in budget.lines}[line_id]


# ---------------------------------------------------------------- extraction


def test_an_interaction_target_reads_as_inp():
    found = extract_targets(
        "Then the application routes to the reports view within 200ms "
        "without a full page reload"
    )
    assert found == [("inp", 200.0, "ms", "within 200ms")]


def test_a_route_that_mentions_reload_is_still_an_interaction():
    """"reload" contains "load"; whole words keep it out of LCP."""
    metric, value, _, _ = extract_targets("routes within 200ms without a page reload")[0]
    assert (metric, value) == ("inp", 200.0)


def test_a_load_target_reads_as_lcp_in_milliseconds():
    metric, value, _, _ = extract_targets("the page loads in under 2 seconds")[0]
    assert (metric, value) == ("lcp", 2000.0)


def test_a_bare_layout_shift_number_reads_as_cls():
    assert extract_targets("layout shift stays below 0.05") == [
        ("cls", 0.05, "", "0.05")
    ]


def test_cls_written_by_its_acronym_is_read_too():
    metric, value, _, _ = extract_targets("CLS below 0.1")[0]
    assert (metric, value) == ("cls", 0.1)


def test_a_server_target_reads_as_ttfb():
    metric, value, _, _ = extract_targets("API responds within 300 ms")[0]
    assert (metric, value) == ("ttfb", 300.0)


def test_megabytes_become_kilobytes():
    metric, value, _, _ = extract_targets("bundle smaller than 1.2 MB")[0]
    assert metric == "weight"
    assert value == pytest.approx(1228.8)


@pytest.mark.parametrize("text", ["below 768 pixels", "768px"])
def test_a_pixel_width_is_custom_not_a_speed_budget(text):
    metric, value, _, _ = extract_targets(text)[0]
    assert (metric, value) == ("custom", 768.0)


def test_counts_and_durations_without_units_are_not_targets():
    assert extract_targets("after 5 failed attempts within 10 minutes") == []
    assert extract_targets("the list shows 20 items for 100 users") == []


def test_a_decimal_is_one_number_not_two_sentences():
    """The sentence split must not treat the dot in 1.2 as a full stop."""
    assert extract_targets("bundle under 1.5 MB")[0][1] == pytest.approx(1536.0)


def test_each_sentence_is_judged_on_its_own_words():
    found = extract_targets(
        "The page loads in 2 seconds.\nThe API responds within 300 ms"
    )
    assert [(metric, value) for metric, value, _, _ in found] == [
        ("lcp", 2000.0),
        ("ttfb", 300.0),
    ]


# ------------------------------------------------------------------- budget


def test_no_criteria_and_no_risks_gives_six_labelled_defaults():
    budget = build_budget([], None, [])
    assert [line.id for line in budget.lines] == list(METRICS)
    assert [line.limit for line in budget.lines] == [
        default for _, _, default, _ in METRICS.values()
    ]
    assert line_of(budget, "lcp").source == DEFAULT_SOURCE
    assert line_of(budget, "weight").source == WEIGHT_SOURCE
    assert all(line.source_text == "" for line in budget.lines)
    assert budget.gaps == []


def test_the_strictest_requirement_wins():
    budget = build_budget(
        ["The page loads in under 3 seconds", "The page renders within 2 seconds"],
        None,
        [],
    )
    lcp = line_of(budget, "lcp")
    assert lcp.limit == 2000.0
    assert lcp.source == "AC-2"
    assert budget.gaps == []


def test_a_looser_requirement_is_kept_but_called_out():
    budget = build_budget(["The page loads in under 4 seconds"], None, [])
    lcp = line_of(budget, "lcp")
    assert lcp.limit == 4000.0
    assert lcp.source == "AC-1"
    assert budget.gaps == [
        'AC-1 allows LCP 4 s — looser than the 2.5 s "good" threshold.'
    ]


def test_a_performance_risk_with_no_number_is_a_gap():
    risks = RiskAnalysis(
        failure_modes=[risk("R1", "Race condition on rapid double-clicking")]
    )
    budget = build_budget([], risks, [])
    assert budget.gaps == [
        'Risk R1 "Race condition on rapid double-clicking" is a performance risk '
        "with no target."
    ]


def test_a_risk_that_names_a_number_sets_the_line_and_is_not_a_gap():
    risks = RiskAnalysis(
        failure_modes=[
            risk("R4", "Slow first paint", effect="First paint must stay under 1 second")
        ]
    )
    budget = build_budget([], risks, [])
    fcp = line_of(budget, "fcp")
    assert (fcp.limit, fcp.source) == (1000.0, "Risk R4")
    assert budget.gaps == []


def test_a_risk_in_another_category_is_never_a_gap():
    risks = RiskAnalysis(failure_modes=[risk("R2", "Session fixation", "security")])
    assert build_budget([], risks, []).gaps == []


def test_the_real_nav_bar_run():
    risks = RiskAnalysis(
        failure_modes=[
            risk("R1", "Race condition on rapid double-clicking"),
            risk(
                "R4",
                "Layout thrashing and CLS on slow networks",
                effect="The bar jumps as the fonts load",
            ),
        ]
    )
    cases = [
        case(case_id="TC-001", traceability="AC-1"),
        case(case_id="TC-004", traceability="AC-4"),
        case(case_id="TC-007", traceability="Covers AC-4"),
    ]
    budget = build_budget(NAV_CRITERIA, risks, cases)

    inp = line_of(budget, "inp")
    assert (inp.limit, inp.source, inp.source_text) == (200.0, "AC-2", "within 200ms")

    custom = line_of(budget, "custom-1")
    assert custom.label == "Layout at 768 px"
    assert custom.measurable is False
    assert (custom.unit, custom.source) == ("px", "AC-4")
    assert custom.covered_by == ["TC-004", "TC-007"]

    # Everything the team did not pin down keeps the published threshold.
    for metric_id in ("lcp", "cls", "fcp", "ttfb", "weight"):
        assert line_of(budget, metric_id).source_text == ""

    # Both performance risks named a problem without naming a number.
    assert budget.gaps == [
        'Risk R1 "Race condition on rapid double-clicking" is a performance risk '
        "with no target.",
        'Risk R4 "Layout thrashing and CLS on slow networks" is a performance risk '
        "with no target.",
    ]


def test_measurable_lines_come_first_and_custom_lines_last():
    budget = build_budget(["The bar collapses below 768 pixels"], None, [])
    assert [line.measurable for line in budget.lines] == [True] * 6 + [False]


def test_a_custom_line_with_no_matching_case_is_simply_uncovered():
    budget = build_budget(["The bar collapses below 768 pixels"], None, [])
    assert line_of(budget, "custom-1").covered_by == []


def test_the_same_custom_target_twice_makes_one_line():
    budget = build_budget(
        ["The bar collapses below 768 pixels", "The bar collapses below 768 pixels"],
        None,
        [],
    )
    assert [line.id for line in budget.lines if not line.measurable] == ["custom-1"]
