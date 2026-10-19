"""Depth tests: how thoroughly each criterion is tested."""

from qagenius.test_case_depth import (
    compute_depth,
    needs_limit_test,
    reason_counts,
    summary_line,
)
from qagenius.test_cases import number_criteria
from tests.factories import case, navbar_run, real_run, suite


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
    """A criterion with something to type into and a limit to type past."""
    report = _depth(
        [case("TC-001", "Functional", "AC-1")],
        ["The password field takes at most 64 characters"],
    )
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
    assert report.thin_ids == ["AC-1", "AC-2", "AC-4", "AC-5", "AC-6"]
    rows = {row.id: row for row in report.rows}
    # AC-1 counts attempts and takes a password: it needs both kinds.
    assert rows["AC-1"].reasons == ["no test for wrong input", "no test at the limits"]
    assert rows["AC-1"].case_ids == ["TC-001", "TC-007", "TC-008"]
    # AC-2 states 15 minutes but nothing is typed into it.
    assert rows["AC-2"].reasons == ["only one test", "no test at the limits"]
    # "The shopper is told why sign-in failed" has three cases and neither a
    # limit nor an input, so it asks for nothing more.
    assert rows["AC-3"].reasons == []
    assert rows["AC-4"].reasons == ["only one test"]


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
        [
            "The name field is saved",
            "The email field is saved",
            "The phone field is saved",
            "The bio field is saved",
            "The role field is saved",
        ],
    )
    assert summary_line(report) == (
        "5 of 5 criteria need more tests — 4 have no test for wrong input, "
        "1 has only one test."
    )


def test_a_single_criterion_reads_as_one() -> None:
    report = _depth(
        [case("TC-001", "Functional", "AC-1")],
        ["The password field takes at most 64 characters"],
    )
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
    assert summary_line(report) == "Every criterion has the tests it needs."


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
        ["The name field is saved", "The email field is saved"],
    )
    assert reason_counts(report) == [("no test for wrong input", 1)]


def test_only_two_reasons_reach_the_sentence() -> None:
    """A criterion with nothing at all needs three things; the line says two."""
    report = _depth(
        [case("TC-001", "Functional", "AC-1")],
        ["The password field takes at most 64 characters", "The name is shown"],
    )
    line = summary_line(report)
    assert line.count(" have ") + line.count(" has ") == 2
    assert "no test at the limits" not in line


# ── a criterion is only asked for the tests it can really have ───────────────


def test_the_navbar_run_is_well_tested_the_whole_way_down() -> None:
    """The nav-bar run, where every criterion asked for something different.

    AC-1 and AC-4 are about the way it looks, so one test answers each.
    AC-2 and AC-3 are plain behaviour with two tests each. Only AC-5 can
    turn a reader away, and it has the test that does.
    """
    result, criteria = navbar_run()
    report = compute_depth(result, criteria)
    assert report.thin_ids == []
    rows = {row.id: row for row in report.rows}
    assert rows["AC-1"].case_ids == ["TC-001"] and rows["AC-1"].reasons == []
    assert rows["AC-2"].case_ids == ["TC-002", "TC-003"]
    assert rows["AC-4"].case_ids == ["TC-004"] and rows["AC-4"].reasons == []
    assert rows["AC-5"].needs_wrong_input is True
    assert "Negative" in rows["AC-5"].kinds
    assert summary_line(report) == "Every criterion has the tests it needs."


def test_only_a_criterion_with_a_limit_is_asked_for_a_limit_test() -> None:
    stated = [
        "The bio takes at most 160 characters",  # a limit word
        "The account locks after 5 failed attempts",  # a number with a unit
        "Breadcrumbs show the path to the current page",  # neither
    ]
    report = _depth([case(f"TC-00{n}", "Functional", f"AC-{n}") for n in (1, 2, 3)], stated)
    assert [row.needs_limit for row in report.rows] == [True, True, False]
    assert "no test at the limits" in report.rows[0].reasons
    assert "no test at the limits" not in report.rows[2].reasons


def test_only_a_criterion_someone_can_put_something_into_asks_for_wrong_input() -> None:
    stated = [
        "The reader types a search term into the field",  # an input
        "A reader without the admin role is refused",  # a rule can refuse them
        "The sidebar shows one item per section",  # neither
    ]
    report = _depth([case(f"TC-00{n}", "Functional", f"AC-{n}") for n in (1, 2, 3)], stated)
    assert [row.needs_wrong_input for row in report.rows] == [True, True, False]
    assert "no test for wrong input" not in report.rows[2].reasons


def test_a_criterion_about_the_way_it_looks_is_answered_by_one_test() -> None:
    report = _depth(
        [case("TC-001", "Functional", "AC-1"), case("TC-002", "Functional", "AC-2")],
        ["The current item is shown in bold", "The menu closes on the second press"],
    )
    assert report.rows[0].reasons == []
    # The one that is not about looks still wants a second test.
    assert report.rows[1].reasons == ["only one test"]


def test_a_limit_word_counts_only_when_it_says_how_much() -> None:
    """The nav-bar run: a cursor moves "over" a link, which is no limit at all."""
    assert needs_limit_test("The reader moves their mouse cursor over an unselected link") is False
    assert needs_limit_test("Files over 5 MB are refused") is True
    assert needs_limit_test("The menu collapses below 768 pixels") is True
    assert needs_limit_test("The code expires within 10 minutes") is True
    # A number with its unit still says "limit" on its own.
    assert needs_limit_test("The account locks after 5 failed attempts") is True
    # And a number too far behind the word is about something else.
    assert needs_limit_test("The banner sits above the bar that holds the 5 sections") is False


def test_the_navbar_breadcrumb_criterion_is_not_asked_for_a_limit_test() -> None:
    """AC-2 says "cursor over a step" and has two tests: it is well tested."""
    result, criteria = navbar_run()
    row = {one.id: one for one in compute_depth(result, criteria).rows}["AC-2"]
    assert "over" in row.text
    assert row.needs_limit is False
    assert row.reasons == []
