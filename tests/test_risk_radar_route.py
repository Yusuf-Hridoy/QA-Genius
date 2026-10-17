"""Risk radar route tests. The LLM is faked; no network."""

import io
import json

import openpyxl
from fastapi.testclient import TestClient

import main
from qagenius import llm
from qagenius.models import RiskAnalysis
from tests.factories import case
from tests.test_risk_radar import mode

client = TestClient(main.app)

KEYS_HEADER = {"X-QAG-Keys": json.dumps([{"provider": "gemini", "key": "first"}])}

STORY = "As a shopper, I want my account to lock after too many wrong passwords."
CRITERIA = [
    "The account locks after 5 failed attempts",
    "The lock lasts 30 minutes",
]
CASES = [case(case_id="TC-001"), case(case_id="TC-002", category="Negative")]

FORM = {
    "user_story": STORY,
    "criteria_json": json.dumps(CRITERIA),
    "cases_json": json.dumps([one.model_dump() for one in CASES]),
}


def _analysis(*modes) -> RiskAnalysis:
    return RiskAnalysis(failure_modes=list(modes or [mode()]))


def _fake_generate(captured: list | None = None, result: RiskAnalysis | None = None):
    answer = result if result is not None else _analysis()

    def _generate(keys, system, user, schema):
        if captured is not None:
            captured.append((system, user))
        return answer, 0, ["Used Key 1 (Gemini)"]

    return _generate


def _never(keys, system, user, schema):
    raise AssertionError("the AI must not be called")


def _body(analysis: RiskAnalysis, cases=None) -> dict:
    return {
        "analysis": analysis.model_dump(),
        "cases": [one.model_dump() for one in (CASES if cases is None else cases)],
        "criteria": CRITERIA,
    }


# ---------- the page ----------


def test_the_page_renders() -> None:
    response = client.get("/risks")
    assert response.status_code == 200
    assert 'id="risk-root"' in response.text
    assert "/risk_radar.js" in response.text


# ---------- /risks/run ----------


def test_run_without_keys_opens_the_drawer() -> None:
    response = client.post("/risks/run", data=FORM)
    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "open-keys"


def test_run_works_with_a_story_alone(monkeypatch) -> None:
    """The standalone input on Risk radar sends no criteria and no cases."""
    captured: list = []
    monkeypatch.setattr(llm, "generate_json", _fake_generate(captured))
    response = client.post(
        "/risks/run",
        data={"user_story": STORY, "criteria_json": "[]", "cases_json": "[]"},
        headers=KEYS_HEADER,
    )

    assert response.status_code == 200
    _system, user = captured[0]
    assert "Acceptance criteria:\n(none yet)" in user
    assert "Existing test cases:\n(none yet)" in user
    # The page still renders; clean_analysis drops the ids the AI invented.
    assert 'class="risk-split"' in response.text
    assert "error-card" not in response.text


def test_run_without_a_story_points_back_to_requirements(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    data = dict(FORM, user_story="  ")
    body = client.post("/risks/run", data=data, headers=KEYS_HEADER).text
    assert "Start from a story in Requirements first." in body


def test_run_rejects_broken_criteria(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    data = dict(FORM, criteria_json="{not json")
    body = client.post("/risks/run", data=data, headers=KEYS_HEADER).text
    assert "Please check the story, criteria and test cases." in body


def test_run_rejects_broken_test_cases(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    data = dict(FORM, cases_json=json.dumps([{"id": "TC-001"}]))
    body = client.post("/risks/run", data=data, headers=KEYS_HEADER).text
    assert "Please check the story, criteria and test cases." in body


def test_run_sends_the_criteria_and_the_cases_to_the_ai(monkeypatch) -> None:
    captured: list = []
    monkeypatch.setattr(llm, "generate_json", _fake_generate(captured))
    response = client.post("/risks/run", data=FORM, headers=KEYS_HEADER)
    assert response.status_code == 200
    system, user = captured[0]
    assert "FMEA" in system
    assert "AC-1: The account locks after 5 failed attempts" in user
    assert "TC-001 | Functional |" in user


def test_run_works_before_any_test_case_exists(monkeypatch) -> None:
    captured: list = []
    monkeypatch.setattr(llm, "generate_json", _fake_generate(captured))
    data = dict(FORM, cases_json="[]")
    response = client.post("/risks/run", data=data, headers=KEYS_HEADER)
    assert response.status_code == 200
    assert "(none yet)" in captured[0][1]
    assert "No test covers this risk" in response.text


def test_run_drops_test_case_ids_the_ai_invented(monkeypatch) -> None:
    monkeypatch.setattr(
        llm,
        "generate_json",
        _fake_generate(result=_analysis(mode(covered_by=["TC-404"]))),
    )
    body = client.post("/risks/run", data=FORM, headers=KEYS_HEADER).text
    # The apostrophe in the note is escaped on the way into the page.
    assert "Removed 1 unknown test case ids from the AI" in body
    assert "No test covers this risk" in body


def test_run_escapes_whatever_the_ai_wrote(monkeypatch) -> None:
    monkeypatch.setattr(
        llm,
        "generate_json",
        _fake_generate(result=_analysis(mode(title="<script>alert(1)</script>"))),
    )
    body = client.post("/risks/run", data=FORM, headers=KEYS_HEADER).text
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


# ---------- /risks/rescore ----------


def test_rescore_recomputes_the_level_without_calling_the_ai(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    low = _analysis(mode("R1", severity=2, likelihood=2, detectability=2))
    body = client.post("/risks/rescore", json=_body(low)).text
    assert "RPN 8 · low" in body

    raised = _analysis(mode("R1", severity=5, likelihood=2, detectability=2))
    body = client.post("/risks/rescore", json=_body(raised)).text
    assert "RPN 20 · medium" in body


def test_rescore_reorders_the_list(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    before = _analysis(
        mode("R1", title="Quiet one", severity=2, likelihood=2, detectability=2),
        mode("R2", title="Loud one", severity=4, likelihood=3, detectability=3),
    )
    body = client.post("/risks/rescore", json=_body(before)).text
    assert body.index("Loud one") < body.index("Quiet one")

    after = _analysis(
        mode("R1", title="Quiet one", severity=5, likelihood=5, detectability=5),
        mode("R2", title="Loud one", severity=4, likelihood=3, detectability=3),
    )
    body = client.post("/risks/rescore", json=_body(after)).text
    assert body.index("Quiet one") < body.index("Loud one")


def test_rescore_reads_a_score_the_user_typed_as_text(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    payload = _body(_analysis(mode("R1")))
    payload["analysis"]["failure_modes"][0]["severity"] = "5"
    payload["analysis"]["failure_modes"][0]["likelihood"] = "5"
    payload["analysis"]["failure_modes"][0]["detectability"] = "5"
    body = client.post("/risks/rescore", json=payload).text
    assert "RPN 125 · high" in body


def test_rescore_refuses_a_payload_that_is_not_an_analysis() -> None:
    assert client.post("/risks/rescore", json={"analysis": "nope"}).status_code == 422


def test_rescore_refuses_too_many_risks() -> None:
    payload = _body(_analysis(*[mode(f"R{n}") for n in range(1, 17)]))
    assert client.post("/risks/rescore", json=payload).status_code == 422


def test_the_page_data_round_trips_through_rescore(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    page = client.get("/risks/example").text
    start = page.index('id="risk-data">') + len('id="risk-data">')
    raw = page[start : page.index("</script>", start)]
    data = json.loads(raw)
    again = client.post("/risks/rescore", json=data)
    assert again.status_code == 200
    assert "Verified by TC-010" in again.text


# ---------- /risks/example ----------


def test_the_example_shows_every_coverage_state() -> None:
    body = client.get("/risks/example").text
    assert "Verified by TC-010 (tagged risk:R1)" in body
    assert "Likely covered by TC-005" in body
    assert "matched on:" in body
    assert "to mark it verified" in body
    assert "but the test doesn't seem to match" in body
    assert "No test covers this risk" in body


def test_the_example_counts_two_untested_high_risks() -> None:
    body = client.get("/risks/example").text
    assert "Write tests for 2 untested high risks" in body
    assert '<div class="num">2</div><div class="lbl">High risk, untested</div>' in body
    assert "stat stat-bad" in body


def test_the_example_needs_no_key_and_says_so() -> None:
    response = client.get("/risks/example")
    assert response.status_code == 200
    assert "Answered by saved example." in response.text


# ---------- the heat map and the pills ----------


def test_the_heat_map_has_every_cell_and_the_ids_in_the_right_one() -> None:
    body = client.get("/risks/example").text
    assert body.count('class="heat-cell') == 25
    # R1 is severity 5, likelihood 4 in the saved example.
    marker = 'data-cell="5-4"'
    cell = body[body.index(marker) : body.index("</td>", body.index(marker))]
    assert ">R1<" in cell
    empty = 'data-cell="1-1"'
    cell = body[body.index(empty) : body.index("</td>", body.index(empty))]
    assert "pill" not in cell


def test_the_rpn_pill_is_coloured_by_level(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    levels = {
        "bad": mode("R1", severity=5, likelihood=4, detectability=4),
        "warn": mode("R1", severity=4, likelihood=3, detectability=3),
        "ok": mode("R1", severity=2, likelihood=2, detectability=2),
    }
    for tone, risk in levels.items():
        body = client.post("/risks/rescore", json=_body(_analysis(risk))).text
        assert f'<span class="pill {tone}">RPN' in body


def test_the_card_shows_the_reasons_and_the_test_idea() -> None:
    body = client.get("/risks/example").text
    assert "Why these scores" in body
    assert "Scores are the AI's proposal" in body
    assert "class=\"score-input\"" in body


# ---------- exports ----------


def test_export_csv_returns_a_register() -> None:
    response = client.post("/risks/export.csv", json=_body(_analysis(mode("R1"))))
    assert response.status_code == 200
    assert "qa-genius-risk-register.csv" in response.headers["content-disposition"]
    text = response.content.decode("utf-8")
    assert text.startswith("﻿")
    assert "Failure mode" in text
    assert "R1" in text


def test_export_xlsx_returns_a_workbook() -> None:
    response = client.post("/risks/export.xlsx", json=_body(_analysis(mode("R1"))))
    assert response.status_code == 200
    assert "qa-genius-risk-register.xlsx" in response.headers["content-disposition"]
    book = openpyxl.load_workbook(io.BytesIO(response.content))
    assert book.sheetnames == ["Risk register", "Heat map"]


def test_export_refuses_a_broken_payload() -> None:
    assert client.post("/risks/export.csv", json={"cases": []}).status_code == 422
    assert client.post("/risks/export.xlsx", json={"cases": []}).status_code == 422


def _cell(body: str, severity: int, likelihood: int) -> str:
    marker = f'data-cell="{severity}-{likelihood}"'
    start = body.index(marker)
    return body[start : body.index("</td>", start)]


def test_two_risks_in_one_cell_are_two_separate_pills(monkeypatch) -> None:
    """A real run rendered a cell holding R1 and R6 as "R1R6"."""
    monkeypatch.setattr(llm, "generate_json", _never)
    together = _analysis(
        mode("R1", severity=5, likelihood=4),
        mode("R6", severity=5, likelihood=4),
    )
    body = client.post("/risks/rescore", json=_body(together)).text
    cell = _cell(body, 5, 4)
    assert cell.count('class="pill plain"') == 2
    assert ">R1<" in cell and ">R6<" in cell
    assert "R1R6" not in cell
    assert 'class="heat-ids"' in cell


def test_a_crowded_cell_keeps_three_ids_and_counts_the_rest(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    crowd = _analysis(
        *[mode(f"R{n}", severity=5, likelihood=4) for n in range(1, 6)]
    )
    body = client.post("/risks/rescore", json=_body(crowd)).text
    cell = _cell(body, 5, 4)
    assert cell.count('class="pill plain"') == 4
    assert ">R3<" in cell
    assert ">R4<" not in cell
    assert ">+2<" in cell
    # Nothing is lost: the full list stays in the title and in data-ids.
    assert "R1,R2,R3,R4,R5" in cell
    assert "R4, R5" in cell
