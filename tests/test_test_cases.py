"""Test-case logic tests. Pure functions, no network, no AI."""

# Aliased: pytest tries to collect any module-level name starting with 'Test'.
from qagenius.models import TestCase as Case
from qagenius.models import TestCaseList as CaseList
from qagenius.models import TestSuiteSummary as Summary
from qagenius.test_cases import (
    build_user_text,
    compute_counts,
    compute_coverage,
    criteria_block,
    number_criteria,
    traced_ids,
)


def _case(
    case_id: str = "TC-001",
    category: str = "Functional",
    priority: str = "High",
    traceability: str = "AC-1",
) -> Case:
    return Case(
        id=case_id,
        title="Lock the account",
        category=category,
        pre_conditions="The shopper has an active account",
        steps=["Open the login page", "Enter a wrong password"],
        expected_result="The account locks",
        priority=priority,
        automation_feasibility="High",
        automation_effort="Low",
        tags=["login"],
        traceability=traceability,
    )


def _suite(*cases: Case) -> CaseList:
    """The summary carries deliberately wrong numbers: nothing may read it."""
    return CaseList(
        test_cases=list(cases),
        summary=Summary(
            total_generated=999,
            category_breakdown=[],
            priority_breakdown=[],
            automation_coverage_potential="99%",
            coverage_gaps=[],
            recommendations=[],
        ),
    )


def test_number_criteria() -> None:
    criteria = number_criteria(["  a ", "", "b"])
    assert [(c.id, c.text) for c in criteria] == [("AC-1", "a"), ("AC-2", "b")]


def test_criteria_block_format() -> None:
    criteria = number_criteria(["Scenario: lock\n  Given a shopper", "Plain one"])
    block = criteria_block(criteria)
    assert "AC-1: " in block
    assert "AC-2: " in block
    assert "Scenario: lock / Given a shopper" in block
    # The whole criterion sits on its own line.
    ac_1_line = next(line for line in block.splitlines() if line.startswith("AC-1: "))
    assert ac_1_line == "AC-1: Scenario: lock / Given a shopper"
    assert "every criterion must be covered" in block


def test_build_user_text_no_criteria() -> None:
    text = build_user_text("User Story / Requirement:\nAs a shopper", ["Negative"], [])
    assert text.endswith("\n\nTest Coverage Focus: Negative")
    assert "Acceptance criteria" not in text


def test_build_user_text_empty_focus_uses_all_options() -> None:
    text = build_user_text("base", [], number_criteria(["a"]))
    assert "Test Coverage Focus: Functional, Negative, Boundary, Edge Case" in text
    assert "AC-1: a" in text


def test_traced_ids_variants() -> None:
    case = _case(traceability="Covers ac-2 and AC-1, AC-2; story")
    assert traced_ids(case, {"AC-1", "AC-2"}) == ["AC-2", "AC-1"]


def test_traced_ids_ignores_unknown() -> None:
    assert traced_ids(_case(traceability="AC-9"), {"AC-1"}) == []


def test_coverage() -> None:
    criteria = number_criteria(["one", "two", "three"])
    result = _suite(
        _case("TC-001", traceability="AC-1"),
        _case("TC-002", traceability="AC-1"),
        _case("TC-003", traceability="AC-3"),
    )
    coverage = compute_coverage(result, criteria)
    assert coverage.covered == ["AC-1", "AC-3"]
    assert coverage.uncovered == ["AC-2"]
    assert coverage.percent == 67
    assert coverage.cases_per_id == {"AC-1": 2, "AC-2": 0, "AC-3": 1}


def test_coverage_no_criteria() -> None:
    coverage = compute_coverage(_suite(_case()), [])
    assert coverage.percent == 100
    assert coverage.covered == []
    assert coverage.uncovered == []


def test_counts_normalised() -> None:
    result = _suite(
        _case("TC-001", category="functional"),
        _case("TC-002", category="Edge case "),
        _case("TC-003", category="Security"),
        _case("TC-004", category="functional"),
    )
    counts = compute_counts(result)
    assert list(counts.by_category) == ["Functional", "Edge Case", "Security"]
    assert counts.by_category == {"Functional": 2, "Edge Case": 1, "Security": 1}
    assert counts.total == 4


def test_counts_priority_order() -> None:
    result = _suite(
        _case("TC-001", priority="low"),
        _case("TC-002", priority="HIGH"),
        _case("TC-003", priority="Medium"),
    )
    counts = compute_counts(result)
    assert list(counts.by_priority) == ["High", "Medium", "Low"]
