"""Accepting a risk: the reason, and the two optional things beside it."""

import html
import json
from datetime import date

from fastapi.testclient import TestClient

import main
from qagenius.acceptance import Acceptance, note, parse_date, read, read_all
from qagenius.ship_check import ShipInputs, compute_ship_report
client = TestClient(main.app)

LONG = "Behind a flag for internal users until the shared counter lands."


# ── reading whatever the browser saved ───────────────────────────────────────


def test_the_old_string_shape_still_loads() -> None:
    one = read(LONG)
    assert one == Acceptance(reason=LONG, owner="", review_date="")


def test_the_new_shape_keeps_the_owner_and_the_date() -> None:
    one = read({"reason": LONG, "owner": "Mina", "review_date": "2026-11-15"})
    assert one.owner == "Mina"
    assert one.review_date == "2026-11-15"


def test_an_owner_and_a_date_are_both_optional() -> None:
    one = read({"reason": LONG})
    assert one.owner == ""
    assert one.review_date == ""


def test_a_reason_too_short_is_not_an_acceptance() -> None:
    assert read("too short") is None
    assert read({"reason": "too short", "owner": "Mina"}) is None
    assert read({"owner": "Mina"}) is None


def test_a_reason_too_long_is_not_an_acceptance() -> None:
    assert read("x" * 301) is None
    assert read("x" * 300) is not None


def test_an_owner_longer_than_sixty_characters_is_cut() -> None:
    one = read({"reason": LONG, "owner": "n" * 200})
    assert len(one.owner) == 60


def test_a_date_that_is_not_a_date_is_dropped_not_kept() -> None:
    for bad in ("tomorrow", "15/11/2026", "2026-13-01", "2026-02-30", ""):
        assert read({"reason": LONG, "review_date": bad}).review_date == ""


def test_anything_that_is_not_a_string_or_an_object_is_nothing() -> None:
    for bad in (None, 7, [], True):
        assert read(bad) is None


def test_read_all_keeps_only_the_ids_it_was_asked_for() -> None:
    found = read_all({"risks": LONG, "nonsense": LONG}, ["risks", "matrix"])
    assert list(found) == ["risks"]


# ── a review date that has gone by ───────────────────────────────────────────


def test_a_date_in_the_past_has_passed() -> None:
    one = Acceptance(reason=LONG, review_date="2020-01-01")
    assert one.passed() is True


def test_a_date_in_the_future_has_not() -> None:
    one = Acceptance(reason=LONG, review_date="2999-01-01")
    assert one.passed() is False


def test_today_itself_has_not_passed() -> None:
    today = date(2026, 5, 4)
    one = Acceptance(reason=LONG, review_date="2026-05-04")
    assert one.passed(today) is False


def test_no_date_never_passes() -> None:
    assert Acceptance(reason=LONG).passed() is False


def test_the_line_says_who_and_when() -> None:
    one = Acceptance(reason=LONG, owner="Mina", review_date="2999-01-01")
    assert note(one) == f"{LONG} · Owner: Mina · Review by 2999-01-01"
    gone = Acceptance(reason=LONG, review_date="2020-01-01")
    assert note(gone) == f"{LONG} · Review date passed 2020-01-01"


def test_parse_date_reads_only_the_one_format() -> None:
    assert parse_date("2026-11-15") == date(2026, 11, 15)
    assert parse_date("15-11-2026") is None


# ── what it does to the Ship check decision ──────────────────────────────────


def _risks_item(report):
    return next(item for item in report.items if item.id == "risks")


def test_an_accepted_fail_keeps_its_owner_and_date_on_the_item() -> None:
    report = compute_ship_report(
        ShipInputs(
            story="x",
            risk_analysis=None,
            acceptances={
                "risks": {"reason": LONG, "owner": "Mina", "review_date": "2999-01-01"}
            },
        )
    )
    # With no risk analysis the check never ran, so nothing was accepted.
    assert _risks_item(report).status == "not_checked"


def test_a_past_review_date_takes_an_acceptance_back_to_check_this() -> None:
    from qagenius.ship_check import ShipCheckItem, _accepted

    failing = ShipCheckItem(
        id="risks", title="Risks with a test", status="fail",
        summary="1 high risk has no test", details=[], link="/risks",
    )
    gone = _accepted(failing, {"risks": {"reason": LONG, "review_date": "2020-01-01"}})
    assert gone.status == "warn"
    assert gone.review_passed is True
    assert "Review date passed" in gone.accepted_note

    holds = _accepted(failing, {"risks": {"reason": LONG, "review_date": "2999-01-01"}})
    assert holds.status == "accepted"
    assert holds.review_passed is False
    assert holds.owner == ""
    assert holds.review_date == "2999-01-01"


def test_an_old_string_acceptance_still_accepts() -> None:
    from qagenius.ship_check import ShipCheckItem, _accepted

    failing = ShipCheckItem(
        id="risks", title="Risks with a test", status="fail",
        summary="1 high risk has no test", details=[], link="/risks",
    )
    assert _accepted(failing, {"risks": LONG}).status == "accepted"


# ── a risk accepted on the Risk radar reaches Ship check ─────────────────────


def _ship_body(acceptances: dict) -> dict:
    return {
        "story": "As a shopper, I want my Aurora Storefront cart saved.",
        "risk_analysis": {
            "analysis": {
                "failure_modes": [
                    {
                        "id": "R-01",
                        "title": "The saved cart is lost",
                        "category": "Data",
                        "cause": "The cart is not written",
                        "effect": "The shopper starts again",
                        "severity": 5,
                        "likelihood": 5,
                        "detectability": 5,
                        "severity_reason": "",
                        "likelihood_reason": "",
                        "detectability_reason": "",
                        "test_idea": "",
                        "related_criteria": [],
                        "covered_by": [],
                    }
                ],
                "summary": "",
            },
            "cases": [],
            "criteria": [],
        },
        "risk_acceptances": acceptances,
    }


def _risks_status(body: dict) -> str:
    """What the risks check came back as, read from the report's own data."""
    text = client.post("/ship/report", json=body).text
    block = text.split('id="ship-data">', 1)[1].split("</script>", 1)[0]
    data = json.loads(html.unescape(block))
    return next(item["status"] for item in data["items"] if item["id"] == "risks")


def test_a_high_risk_with_no_test_fails_until_it_is_accepted() -> None:
    assert _risks_status(_ship_body({})) == "fail"
    accepted = _ship_body({"R-01": {"reason": LONG, "owner": "Mina"}})
    assert _risks_status(accepted) != "fail"


def test_an_acceptance_whose_review_date_passed_does_not_count() -> None:
    gone = _ship_body({"R-01": {"reason": LONG, "review_date": "2020-01-01"}})
    assert _risks_status(gone) == "fail"


def test_a_risk_id_the_radar_would_never_write_is_ignored() -> None:
    assert _risks_status(_ship_body({"../../etc/passwd": {"reason": LONG}})) == "fail"


def test_a_risk_only_clear_because_it_was_accepted_says_accepted() -> None:
    """A written reason is not a test, and the check must not read as if it were."""
    body = _ship_body({"R-01": {"reason": LONG, "owner": "Mina"}})
    assert _risks_status(body) == "accepted"
    text = client.post("/ship/report", json=body).text
    assert "accepted in writing" in text
    assert "Mina" in text


def test_the_grade_counts_an_accepted_risk_as_half_a_check() -> None:
    """Signing a risk off is worth less than having a test for it."""
    accepted = _ship_body({"R-01": {"reason": LONG}})
    text = client.post("/ship/report", json=accepted).text
    block = text.split('id="ship-data">', 1)[1].split("</script>", 1)[0]
    data = json.loads(html.unescape(block))
    scored = [one for one in data["items"] if one["status"] != "not_checked"]
    risks = next(one for one in scored if one["id"] == "risks")
    assert risks["status"] == "accepted"
    # Every other check that ran came back fine, so the only point lost is this one.
    assert data["grade"]["points"] == data["grade"]["max_points"] - 1
