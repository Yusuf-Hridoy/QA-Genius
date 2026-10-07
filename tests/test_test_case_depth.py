"""Depth tests: how thoroughly each criterion is tested."""

from qagenius.test_case_depth import compute_depth
from qagenius.test_cases import number_criteria
from tests.factories import case, real_run, suite


def _depth(cases, criteria_texts):
    return compute_depth(suite(*cases), number_criteria(criteria_texts))


def test_uncovered_only_reason() -> None:
    report = _depth([case("TC-001", "Functional", "AC-1")], ["one", "two"])
    row = report.rows[1]
    assert row.id == "AC-2"
    assert row.reasons == ["not covered"]
    assert row.thin is True
    assert row.case_ids == []


def test_single_happy_case() -> None:
    report = _depth([case("TC-001", "Functional", "AC-1")], ["one"])
    assert report.rows[0].reasons == [
        "only 1 case",
        "no negative case",
        "no boundary case",
    ]


def test_solid_criterion() -> None:
    report = _depth(
        [
            case("TC-001", "Functional", "AC-1"),
            case("TC-002", "Negative", "AC-1"),
            case("TC-003", "Boundary", "AC-1"),
        ],
        ["one"],
    )
    row = report.rows[0]
    assert row.reasons == []
    assert row.thin is False
    assert report.thin_ids == []


def test_case_counts_for_multiple_ids() -> None:
    report = _depth(
        [
            case("TC-001", "Functional", "AC-1"),
            case("TC-007", "Negative", "AC-1, AC-3"),
        ],
        ["one", "two", "three"],
    )
    assert report.rows[0].case_ids == ["TC-001", "TC-007"]
    assert report.rows[2].case_ids == ["TC-007"]
    assert report.rows[1].case_ids == []


def test_kinds_normalised() -> None:
    report = _depth(
        [
            case("TC-001", "negative", "AC-1"),
            case("TC-002", "Boundary ", "AC-1"),
        ],
        ["one"],
    )
    assert report.rows[0].kinds == ["Negative", "Boundary"]


def test_kinds_put_unknown_categories_last() -> None:
    report = _depth(
        [
            case("TC-001", "Security", "AC-1"),
            case("TC-002", "Functional", "AC-1"),
            case("TC-003", "Accessibility", "AC-1"),
        ],
        ["one"],
    )
    assert report.rows[0].kinds == ["Functional", "Accessibility", "Security"]


def test_real_run_shape() -> None:
    result, criteria = real_run()
    report = compute_depth(result, criteria)
    assert report.thin_ids == ["AC-1", "AC-2", "AC-3", "AC-4", "AC-5", "AC-6"]
    rows = {row.id: row for row in report.rows}
    assert rows["AC-1"].reasons == ["no negative case", "no boundary case"]
    assert rows["AC-1"].case_ids == ["TC-001", "TC-007", "TC-008"]
    assert rows["AC-2"].reasons == ["only 1 case", "no negative case", "no boundary case"]
    assert rows["AC-3"].reasons == ["no boundary case"]
    assert rows["AC-4"].reasons == ["only 1 case", "no negative case"]
