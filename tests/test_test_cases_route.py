"""Test-case route tests. The LLM is faked; no network."""

import io
import json
import re

import openpyxl
from fastapi.testclient import TestClient

import main
from qagenius import llm

# Aliased: pytest tries to collect any module-level name starting with 'Test'.
from qagenius.models import TestCase as Case
from qagenius.models import TestCaseList as CaseList
from qagenius.models import TestSuiteSummary as Summary

client = TestClient(main.app)

KEYS_HEADER = {"X-QAG-Keys": json.dumps([{"provider": "gemini", "key": "first"}])}

STORY = "As a shopper, I want my account to lock after too many wrong passwords."

CRITERIA = [
    "The account locks after 5 failed attempts",
    "The lock lasts 30 minutes",
]

FORM = {
    "user_story": STORY,
    "criteria_json": json.dumps(CRITERIA),
    "coverage_focus": ["Functional", "Negative"],
}


def _case(case_id: str = "TC-001", category: str = "Functional", traceability: str = "AC-1") -> Case:
    return Case(
        id=case_id,
        title="Lock after five wrong passwords",
        category=category,
        pre_conditions="The shopper has an active account",
        steps=["Open the login page", "Enter a wrong password five times"],
        expected_result="The account locks for 30 minutes",
        priority="High",
        test_data="email=shopper@example.com",
        bdd_scenario="Given a shopper\nWhen they fail\nThen it locks",
        automation_feasibility="High",
        automation_effort="Low",
        tags=["login"],
        traceability=traceability,
    )


def _suite(*cases: Case) -> CaseList:
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


def _fake_generate(captured: list | None = None, suite: CaseList | None = None):
    result = suite if suite is not None else _suite(
        _case("TC-001", "Functional", "AC-1"),
        _case("TC-002", "Negative", "AC-2"),
    )

    def _generate(keys, system, user, schema):
        if captured is not None:
            captured.append(user)
        return result, 0, ["Used Key 1 (Gemini)"]

    return _generate


def test_criteria_page_renders() -> None:
    response = client.get("/requirements/criteria")
    assert response.status_code == 200
    assert "2 · Acceptance criteria" in response.text
    assert "1 · Story" in response.text


def test_test_cases_page_renders() -> None:
    response = client.get("/requirements/test-cases")
    assert response.status_code == 200
    assert "3 · Test cases" in response.text


def test_run_without_keys_opens_drawer() -> None:
    response = client.post("/requirements/test-cases/run", data=FORM)
    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "open-keys"


def test_run_sends_criteria_and_focus_to_the_ai(monkeypatch) -> None:
    captured: list = []
    monkeypatch.setattr(llm, "generate_json", _fake_generate(captured))
    response = client.post("/requirements/test-cases/run", data=FORM, headers=KEYS_HEADER)
    assert response.status_code == 200
    assert len(captured) == 1
    assert "AC-1:" in captured[0]
    assert "AC-2:" in captured[0]
    assert "Test Coverage Focus: Functional, Negative" in captured[0]


def test_run_renders_chips_and_coverage(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _fake_generate())
    body = client.post("/requirements/test-cases/run", data=FORM, headers=KEYS_HEADER).text
    assert '<span class="pill accent"' in body
    assert "AC-1" in body and "AC-2" in body
    assert "Coverage 100%" in body
    assert "meter-fill" in body


def test_run_reports_uncovered_criteria(monkeypatch) -> None:
    # Only AC-1 is traced, so AC-2 must be reported as uncovered.
    monkeypatch.setattr(
        llm, "generate_json", _fake_generate(suite=_suite(_case("TC-001", "Functional", "AC-1")))
    )
    body = client.post("/requirements/test-cases/run", data=FORM, headers=KEYS_HEADER).text
    assert "Coverage 50%" in body
    assert "Not covered:" in body


def test_run_rejects_unknown_coverage_focus(monkeypatch) -> None:
    calls: list = []

    def _never(keys, system, user, schema):
        calls.append(user)
        raise AssertionError("the AI must not be called")

    monkeypatch.setattr(llm, "generate_json", _never)
    data = dict(FORM)
    data["coverage_focus"] = ["Hacking"]
    body = client.post("/requirements/test-cases/run", data=data, headers=KEYS_HEADER).text
    assert "Please check the story and criteria." in body
    assert calls == []


def test_run_rejects_too_many_criteria(monkeypatch) -> None:
    def _never(keys, system, user, schema):
        raise AssertionError("the AI must not be called")

    monkeypatch.setattr(llm, "generate_json", _never)
    data = dict(FORM)
    data["criteria_json"] = json.dumps([f"criterion {i}" for i in range(41)])
    body = client.post("/requirements/test-cases/run", data=data, headers=KEYS_HEADER).text
    assert "Please check the story and criteria." in body


def test_run_rejects_criteria_that_are_not_strings(monkeypatch) -> None:
    def _never(keys, system, user, schema):
        raise AssertionError("the AI must not be called")

    monkeypatch.setattr(llm, "generate_json", _never)
    data = dict(FORM)
    data["criteria_json"] = json.dumps([{"text": "sneaky"}])
    body = client.post("/requirements/test-cases/run", data=data, headers=KEYS_HEADER).text
    assert "Please check the story and criteria." in body


def test_run_rejects_empty_story(monkeypatch) -> None:
    data = dict(FORM)
    data["user_story"] = "   "
    body = client.post("/requirements/test-cases/run", data=data, headers=KEYS_HEADER).text
    assert "Please paste a user story first." in body


def test_example_needs_no_key() -> None:
    response = client.get("/requirements/test-cases/example")
    assert response.status_code == 200
    body = response.text
    assert "Coverage 80%" in body
    assert "Not covered:" in body
    assert "AC-5" in body
    assert "saved example" in body


def test_export_csv_route() -> None:
    payload = {"result": _suite(_case()).model_dump(), "criteria": CRITERIA}
    response = client.post("/requirements/test-cases/export.csv", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "qa-genius-test-cases.csv" in response.headers["content-disposition"]
    assert response.content.startswith(b"\xef\xbb\xbf")


def test_export_xlsx_route() -> None:
    payload = {"result": _suite(_case()).model_dump(), "criteria": CRITERIA}
    response = client.post("/requirements/test-cases/export.xlsx", json=payload)
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]
    book = openpyxl.load_workbook(io.BytesIO(response.content))
    assert book.sheetnames == ["Test Cases", "Coverage"]


def test_export_rejects_too_many_criteria() -> None:
    payload = {
        "result": _suite(_case()).model_dump(),
        "criteria": [f"criterion {i}" for i in range(41)],
    }
    response = client.post("/requirements/test-cases/export.csv", json=payload)
    assert response.status_code == 422


def test_export_rejects_a_broken_result() -> None:
    response = client.post(
        "/requirements/test-cases/export.csv",
        json={"result": {"test_cases": "not a list"}, "criteria": []},
    )
    assert response.status_code == 422


def test_result_has_one_card_per_case(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _fake_generate())
    body = client.post("/requirements/test-cases/run", data=FORM, headers=KEYS_HEADER).text
    assert body.count('class="card tc-card"') == 2


def test_coverage_bar_width_matches_percent() -> None:
    body = client.get("/requirements/test-cases/example").text
    assert 'style="width:80%"' in body


def test_filter_chips_list_only_present_categories() -> None:
    body = client.get("/requirements/test-cases/example").text
    chips = re.findall(r'<button type="button" class="chip[^"]*" data-filter="([^"]+)"', body)
    assert chips == ["all", "Functional", "Negative", "Boundary", "Edge Case"]


def test_tc_data_round_trips_through_the_export_route() -> None:
    body = client.get("/requirements/test-cases/example").text
    raw = body.split('<script type="application/json" id="tc-data">')[1].split("</script>")[0]
    payload = json.loads(raw)
    assert len(payload["criteria"]) == 5
    response = client.post("/requirements/test-cases/export.csv", json=payload)
    assert response.status_code == 200
    assert b"TC-001" in response.content


def test_keys_are_never_logged(monkeypatch, caplog) -> None:
    monkeypatch.setattr(llm, "generate_json", _fake_generate())
    with caplog.at_level("DEBUG"):
        client.post("/requirements/test-cases/run", data=FORM, headers=KEYS_HEADER)
    assert "first" not in caplog.text


def test_requirements_pages_load_the_flow_script() -> None:
    for path in ("/requirements/story", "/requirements/criteria", "/requirements/test-cases"):
        body = client.get(path).text
        assert '<script src="/requirements_flow.js" defer></script>' in body


def test_other_pages_do_not_load_the_flow_script() -> None:
    assert "requirements_flow.js" not in client.get("/bugs").text


def test_step_bar_links_between_steps() -> None:
    body = client.get("/requirements/criteria").text
    assert '<a href="/requirements/story">1 \u00b7 Story</a>' in body
    assert '<a href="/requirements/test-cases">3 \u00b7 Test cases</a>' in body
    # The current step is marked, and step 4 is not a link yet.
    assert '<li class="now">2 \u00b7 Acceptance criteria</li>' in body
    assert "4 \u00b7 Automation" in body
    assert '<a href="/requirements/automation"' not in body
