"""Risk scoring: the AI proposes, code computes. No network."""

from qagenius.models import FailureMode, RiskAnalysis
from qagenius.prompts import risk_radar_prompt
from qagenius.risk_radar import (
    case_lines,
    clean_analysis,
    criteria_lines,
    match_score,
    risk_level,
    score_risks,
)
from qagenius.test_cases import number_criteria
from tests.factories import case


def mode(
    risk_id: str = "R1",
    severity: int = 5,
    likelihood: int = 4,
    detectability: int = 4,
    **overrides,
) -> FailureMode:
    values = {
        "id": risk_id,
        "title": "Lockout counter not shared across servers",
        "category": "security",
        "effect": "An attacker keeps guessing passwords past the limit",
        "cause": "Each server keeps its own counter in memory",
        "severity": severity,
        "likelihood": likelihood,
        "detectability": detectability,
        "severity_reason": "Account takeover",
        "likelihood_reason": "Two servers are already running",
        "detectability_reason": "Only shows under a load balancer",
        "related_criteria": ["AC-1"],
        "covered_by": [],
        "test_idea": "Send failed sign-ins through both servers",
    }
    values.update(overrides)
    return FailureMode(**values)


def analysis(*modes: FailureMode) -> RiskAnalysis:
    return RiskAnalysis(failure_modes=list(modes))


# ---------- validators ----------


def test_scores_are_read_from_whatever_the_ai_wrote() -> None:
    risk = mode(severity="4/5", likelihood=7, detectability="high")
    assert (risk.severity, risk.likelihood, risk.detectability) == (4, 5, 3)


def test_a_zero_score_is_clamped_to_one() -> None:
    assert mode(severity=0).severity == 1


def test_a_float_score_is_rounded() -> None:
    assert mode(severity=3.6).severity == 4


def test_categories_are_normalised() -> None:
    assert mode(category="a11y").category == "accessibility"
    assert mode(category=" PERF ").category == "performance"
    assert mode(category="data integrity").category == "data"
    assert mode(category="weird").category == "functional"


# ---------- risk_level ----------


def test_risk_level_counts_the_rpn() -> None:
    assert risk_level(5, 4, 4) == "high"  # 80
    assert risk_level(4, 4, 4) == "high"  # 64
    assert risk_level(4, 3, 3) == "medium"  # 36
    assert risk_level(2, 2, 2) == "low"  # 8


def test_a_severe_likely_failure_is_high_however_easy_it_is_to_spot() -> None:
    assert risk_level(5, 3, 1) == "high"  # rpn 15


# ---------- coverage ----------


def test_a_tagged_case_verifies_the_risk() -> None:
    tagged = case(case_id="TC-012", tags=["login", "RISK:r1"])
    report = score_risks(analysis(mode()), [tagged])
    item = report.risks[0]
    assert item.coverage == "verified"
    assert item.covered_tests == [("TC-012", "Case TC-012", 1.0)]


def test_a_claimed_case_about_the_same_thing_covers_the_risk() -> None:
    matching = case(
        case_id="TC-005",
        title="Lockout counter shared across every server",
        expected_result="The counter is shared, so the fifth attempt locks",
    )
    report = score_risks(analysis(mode(covered_by=["TC-005"])), [matching])
    assert report.risks[0].coverage == "covered"
    assert report.risks[0].covered_tests[0][2] > 0


def test_a_claimed_case_about_something_else_is_a_weak_link() -> None:
    unrelated = case(
        case_id="TC-003",
        title="Newsletter footer shows the current year",
        expected_result="The footer prints 2026",
        steps=["Scroll down"],
    )
    report = score_risks(analysis(mode(covered_by=["TC-003"])), [unrelated])
    assert report.risks[0].coverage == "weak"
    assert report.risks[0].covered_tests[0][0] == "TC-003"


def test_a_claimed_id_that_does_not_exist_is_ignored() -> None:
    report = score_risks(analysis(mode(covered_by=["TC-999"])), [case()])
    assert report.risks[0].coverage == "none"
    assert report.risks[0].covered_tests == []


def test_match_score_is_zero_for_unrelated_text() -> None:
    unrelated = case(
        title="Newsletter footer shows the current year",
        expected_result="The footer prints 2026",
        steps=["Scroll down"],
    )
    assert match_score(mode(), unrelated) == 0.0


# ---------- the report ----------


def test_risks_are_sorted_by_rpn_then_severity_then_id() -> None:
    report = score_risks(
        analysis(
            mode("R1", severity=2, likelihood=2, detectability=2),  # 8
            mode("R2", severity=5, likelihood=4, detectability=4),  # 80
            mode("R3", severity=4, likelihood=4, detectability=5),  # 80
            mode("R4", severity=4, likelihood=2, detectability=1),  # 8
        ),
        [],
    )
    assert [item.risk.id for item in report.risks] == ["R2", "R3", "R4", "R1"]


def test_the_heat_map_has_every_cell_and_puts_the_risk_in_its_own() -> None:
    report = score_risks(analysis(mode(severity=5, likelihood=4)), [])
    assert len(report.heatmap) == 25
    assert report.heatmap[(5, 4)] == ["R1"]
    assert report.heatmap[(1, 1)] == []


def test_counts_only_call_a_high_risk_untested_when_no_test_matches() -> None:
    covered = case(
        case_id="TC-005",
        title="Lockout counter shared across every server",
        expected_result="The counter is shared, so the fifth attempt locks",
    )
    report = score_risks(
        analysis(
            mode("R1", covered_by=["TC-005"]),  # high, covered
            mode("R2", title="Lock email arrives late"),  # high, none
            mode("R3", severity=2, likelihood=2, detectability=2),  # low, none
        ),
        [covered],
    )
    assert report.counts == {
        "total": 3,
        "high": 2,
        "medium": 0,
        "low": 1,
        "untested_high": 1,
    }


def test_by_category_keeps_the_fixed_order_and_drops_empty_ones() -> None:
    report = score_risks(
        analysis(
            mode("R1", category="functional"),
            mode("R2", category="security"),
            mode("R3", category="security"),
        ),
        [],
    )
    assert list(report.by_category.items()) == [("security", 2), ("functional", 1)]


# ---------- the prompt ----------


def test_the_prompt_asks_for_breadth_and_forbids_guessing() -> None:
    system, _ = risk_radar_prompt("story", "AC-1: locks", "TC-001 | Functional | lock")
    assert "FMEA" in system
    assert "at least three different categories" in system
    assert "Do not guess" in system


def test_the_user_text_lists_the_criteria_and_the_cases() -> None:
    criteria = number_criteria(["The account locks\nafter 5 attempts", "It stays locked"])
    cases = [case(case_id="TC-001", title="Lock after five"), case(case_id="TC-002")]
    _, user = risk_radar_prompt(
        "As a shopper...", criteria_lines(criteria), case_lines(cases)
    )
    assert "AC-1: The account locks / after 5 attempts" in user
    assert "AC-2: It stays locked" in user
    assert "TC-001 | Functional | Lock after five" in user
    assert user.startswith("User story:\nAs a shopper...")


def test_without_test_cases_the_prompt_says_none_yet() -> None:
    _, user = risk_radar_prompt("story", criteria_lines([]), case_lines([]))
    assert "Existing test cases:\n(none yet)" in user


# ---------- clean_analysis ----------


def test_clean_analysis_renumbers_in_order() -> None:
    cleaned, notes = clean_analysis(
        analysis(mode("R7", title="Second"), mode("", title="First")),
        {"AC-1"},
        set(),
    )
    assert [risk.id for risk in cleaned.failure_modes] == ["R1", "R2"]
    assert [risk.title for risk in cleaned.failure_modes] == ["Second", "First"]
    assert notes == []


def test_clean_analysis_caps_the_list_at_fifteen() -> None:
    many = analysis(*[mode(f"R{n}", title=f"Failure {n}") for n in range(1, 21)])
    cleaned, notes = clean_analysis(many, set(), set())
    assert len(cleaned.failure_modes) == 15
    assert "Kept the first 15 failure modes." in notes


def test_clean_analysis_drops_failure_modes_without_a_title() -> None:
    cleaned, notes = clean_analysis(
        analysis(mode("R1", title="Real"), mode("R2", title="  ")), set(), set()
    )
    assert len(cleaned.failure_modes) == 1
    assert "Dropped 1 failure modes without a title." in notes


def test_clean_analysis_keeps_the_first_of_two_identical_titles() -> None:
    cleaned, notes = clean_analysis(
        analysis(
            mode("R1", title="Counter not shared", effect="first"),
            mode("R2", title="counter NOT shared", effect="second"),
        ),
        set(),
        set(),
    )
    assert len(cleaned.failure_modes) == 1
    assert cleaned.failure_modes[0].effect == "first"
    assert "Removed 1 repeated failure modes." in notes


def test_clean_analysis_removes_ids_the_ai_invented() -> None:
    cleaned, notes = clean_analysis(
        analysis(
            mode(
                "R1",
                related_criteria=["AC-1", "AC-9"],
                covered_by=["tc-001", "TC-404", "TC-405"],
            )
        ),
        {"AC-1", "AC-2"},
        {"TC-001"},
    )
    risk = cleaned.failure_modes[0]
    assert risk.related_criteria == ["AC-1"]
    assert risk.covered_by == ["TC-001"]
    assert "Removed 1 unknown acceptance criteria ids from the AI's list." in notes
    assert "Removed 2 unknown test case ids from the AI's coverage claims." in notes


def test_clean_analysis_does_not_touch_what_it_was_given() -> None:
    original = analysis(mode("R9", covered_by=["TC-404"]))
    clean_analysis(original, set(), set())
    assert original.failure_modes[0].id == "R9"
    assert original.failure_modes[0].covered_by == ["TC-404"]
