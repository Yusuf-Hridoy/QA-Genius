"""Depth tests: how thoroughly each criterion is tested."""

from qagenius.test_case_depth import compute_depth, reason_counts, summary_line
from qagenius.test_cases import number_criteria
from tests.factories import case, real_run, suite


def _depth(cases, criteria_texts):
    return compute_depth(suite(*cases), number_criteria(criteria_texts))


def test_uncovered_only_reason() -> None:
    report = _depth([case("TC-001", "Functional", "AC-1")], ["one", "two"])
    row = report.rows[1]
    assert row.id == "AC-2"
    assert row.reasons == ["no tests yet"]
    assert row.thin is True
    assert row.case_ids == []


def test_single_happy_case() -> None:
    report = _depth([case("TC-001", "Functional", "AC-1")], ["one"])
    assert report.rows[0].reasons == [
        "only one test",
        "no test for wrong input",
        "no test at the limits",
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
    assert rows["AC-1"].reasons == ["no test for wrong input", "no test at the limits"]
    assert rows["AC-1"].case_ids == ["TC-001", "TC-007", "TC-008"]
    assert rows["AC-2"].reasons == [
        "only one test",
        "no test for wrong input",
        "no test at the limits",
    ]
    assert rows["AC-3"].reasons == ["no test at the limits"]
    assert rows["AC-4"].reasons == ["only one test", "no test for wrong input"]


# ── the one-line summary says what is really missing ──────────────────────────


def test_the_summary_names_the_real_reasons_not_a_generic_one() -> None:
    """The real run: 12 boundary cases, yet the sentence claimed there were none."""
    report = _depth(
        [
            case("TC-001", "Functional", "AC-1"),
            case("TC-002", "Boundary", "AC-1"),
            case("TC-003", "Functional", "AC-2"),
            case("TC-004", "Boundary", "AC-2"),
            case("TC-005", "Functional", "AC-3"),
            case("TC-006", "Boundary", "AC-3"),
            case("TC-007", "Functional", "AC-4"),
            case("TC-008", "Boundary", "AC-4"),
            case("TC-009", "Negative", "AC-5"),
        ],
        ["one", "two", "three", "four", "five"],
    )
    assert summary_line(report) == (
        "5 of 5 criteria need more tests — 4 have no test for wrong input, "
        "1 has only one test."
    )


def test_a_single_criterion_reads_as_one() -> None:
    report = _depth([case("TC-001", "Functional", "AC-1")], ["one"])
    # The table under the line carries the third reason.
    assert summary_line(report) == (
        "1 of 1 criterion needs more tests — 1 has only one test, "
        "1 has no test for wrong input."
    )


def test_a_solid_suite_says_so() -> None:
    report = _depth(
        [
            case("TC-001", "Functional", "AC-1"),
            case("TC-002", "Negative", "AC-1"),
            case("TC-003", "Boundary", "AC-1"),
        ],
        ["one"],
    )
    assert summary_line(report) == (
        "Every criterion has a test for wrong input and one at the limits."
    )


def test_no_criteria_says_nothing() -> None:
    assert summary_line(_depth([], [])) == ""


def test_reasons_are_counted_commonest_first() -> None:
    report = _depth(
        [
            case("TC-001", "Functional", "AC-1"),
            case("TC-002", "Boundary", "AC-1"),
            case("TC-003", "Negative", "AC-2"),
            case("TC-004", "Boundary", "AC-2"),
        ],
        ["one", "two"],
    )
    assert reason_counts(report) == [("no test for wrong input", 1)]


def test_only_two_reasons_reach_the_sentence() -> None:
    """A criterion with nothing at all needs three things; the line says two."""
    report = _depth([case("TC-001", "Functional", "AC-1")], ["one", "two"])
    line = summary_line(report)
    assert line.count(" have ") + line.count(" has ") == 2
    assert "no test at the limits" not in line
