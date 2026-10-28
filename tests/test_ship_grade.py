"""The grade: every band edge, the safety cap, and what it does not count."""

import pytest

from qagenius.ship_check import ShipCheckItem, ShipReport
from qagenius.ship_grade import grade_for, letter_for


def item(check_id: str, status: str, title: str = "") -> ShipCheckItem:
    return ShipCheckItem(
        id=check_id,
        title=title or check_id.title(),
        status=status,
        summary="",
        details=[],
        link="/",
    )


def report(statuses: list[str], verdict: str = "ship") -> ShipReport:
    items = [item(f"check-{at}", status) for at, status in enumerate(statuses)]
    counts = {
        name: sum(1 for one in items if one.status == name)
        for name in ("pass", "warn", "fail", "accepted", "not_checked")
    }
    return ShipReport(
        verdict=verdict,
        verdict_reason="",
        items=items,
        counts=counts,
        checked=sum(1 for one in items if one.status != "not_checked"),
    )


# ── the bands, edge by edge ──────────────────────────────────────────────────

BAND_EDGES = [
    (100, "A+"), (97, "A+"), (96, "A"), (93, "A"), (92, "A-"), (90, "A-"),
    (89, "B+"), (87, "B+"), (86, "B"), (83, "B"), (82, "B-"), (80, "B-"),
    (79, "C+"), (77, "C+"), (76, "C"), (73, "C"), (72, "C-"), (70, "C-"),
    (69, "D+"), (67, "D+"), (66, "D"), (63, "D"), (62, "D-"), (60, "D-"),
    (59, "F"), (30, "F"), (0, "F"),
]


@pytest.mark.parametrize("percent,letter", BAND_EDGES)
def test_every_band_edge_lands_on_the_right_letter(percent: int, letter: str) -> None:
    assert letter_for(percent) == letter


def test_f_never_carries_a_plus_or_a_minus() -> None:
    for percent in range(0, 60):
        assert letter_for(percent) == "F"


# ── the points ───────────────────────────────────────────────────────────────


def test_a_clean_report_scores_full_marks() -> None:
    grade = grade_for(report(["pass", "pass", "pass"]))
    assert grade is not None
    assert (grade.points, grade.max_points, grade.percent) == (6, 6, 100)
    assert grade.letter == "A+"
    assert grade.capped is False


def test_check_this_is_worth_half_and_needs_fixing_nothing() -> None:
    grade = grade_for(report(["pass", "warn", "fail"], verdict="ship_with_risks"))
    assert (grade.points, grade.max_points) == (3, 6)
    assert grade.percent == 50
    assert grade.letter == "F"


def test_an_accepted_risk_scores_the_same_as_check_this() -> None:
    accepted = grade_for(report(["pass", "accepted"]))
    checked = grade_for(report(["pass", "warn"]))
    assert accepted.points == checked.points == 3
    assert accepted.letter == checked.letter


def test_a_check_that_never_ran_is_not_counted_either_way() -> None:
    """Two checks fine out of two is full marks, however many never ran."""
    grade = grade_for(report(["pass", "pass", "not_checked", "not_checked"]))
    assert (grade.points, grade.max_points, grade.percent) == (4, 4, 100)
    assert len(grade.lines) == 2


def test_no_check_ran_means_no_grade() -> None:
    assert grade_for(report(["not_checked", "not_checked"])) is None
    assert grade_for(report([])) is None


def test_the_percent_is_rounded_not_truncated() -> None:
    # 5 of 8 is 62.5, which rounds to 62 under banker's rounding.
    grade = grade_for(report(["pass", "pass", "warn", "fail"]))
    assert grade.points == 5
    assert grade.max_points == 8
    assert grade.percent == 62
    assert grade.letter == "D-"


# ── the safety rule ──────────────────────────────────────────────────────────


def test_not_ready_is_never_graded_above_d() -> None:
    grade = grade_for(report(["pass", "pass", "pass", "fail"], verdict="dont_ship"))
    # 6 of 8 is 75, a C-, and the decision says otherwise.
    assert grade.percent == 75
    assert grade.letter == "D"
    assert grade.capped is True
    assert grade.lines[-1] == "Capped at D because the decision is Not ready."


def test_a_not_ready_report_already_under_d_is_left_alone() -> None:
    grade = grade_for(report(["warn", "fail", "fail"], verdict="dont_ship"))
    assert grade.percent == 17
    assert grade.letter == "F"
    assert grade.capped is False
    assert "Capped" not in " ".join(grade.lines)


def test_a_not_ready_report_inside_the_d_band_keeps_its_sign() -> None:
    # 5 of 8 is 62: a D-, which is already at most D.
    grade = grade_for(report(["pass", "pass", "warn", "fail"], verdict="dont_ship"))
    assert grade.letter == "D-"
    assert grade.capped is False


def test_release_with_known_risks_is_not_capped() -> None:
    grade = grade_for(
        report(["pass", "pass", "pass", "accepted"], verdict="ship_with_risks")
    )
    assert grade.percent == 88
    assert grade.letter == "B+"
    assert grade.capped is False


# ── the explanation ──────────────────────────────────────────────────────────


def test_each_line_names_its_check_and_what_it_scored() -> None:
    made = report(["pass", "fail"])
    named = ShipReport(
        verdict=made.verdict,
        verdict_reason="",
        items=[
            item("clarity", "pass", "How clear the story is"),
            item("risks", "fail", "Risks with a test"),
        ],
        counts=made.counts,
        checked=2,
    )
    grade = grade_for(named)
    assert grade.lines == [
        "How clear the story is: fine (2 of 2)",
        "Risks with a test: needs fixing (0 of 2)",
    ]
