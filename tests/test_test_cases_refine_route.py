"""Refine/strengthen route tests. The LLM is faked; no network."""

import json

from fastapi.testclient import TestClient

import main
from qagenius import llm
from tests.factories import REAL_RUN_CRITERIA, case, real_run, suite

client = TestClient(main.app)

KEYS_HEADER = {"X-QAG-Keys": json.dumps([{"provider": "gemini", "key": "first"}])}

STORY = "As a shopper, I want my account to lock after too many wrong passwords."


def _form(**overrides) -> dict:
    current, _ = real_run()
    form = {
        "user_story": STORY,
        "criteria_json": json.dumps(REAL_RUN_CRITERIA),
        "current_json": current.model_dump_json(),
        "mode": "strengthen",
        "instruction": "",
        "coverage_focus": ["Functional", "Negative"],
    }
    form.update(overrides)
    return form


def _fake(result, captured: list | None = None):
    def _generate(keys, system, user, schema):
        if captured is not None:
            captured.append(user)
        return result, 0, ["Used Key 1 (Gemini)"]

    return _generate


def _never(keys, system, user, schema):
    raise AssertionError("the AI must not be called")


def test_render_redraws_the_result_card() -> None:
    with open("qagenius/samples/test_cases.json", encoding="utf-8") as f:
        sample = json.load(f)
    response = client.post(
        "/requirements/test-cases/render",
        json={"result": sample["result"], "criteria": sample["criteria"]},
    )
    assert response.status_code == 200
    assert "Coverage 80%" in response.text
    assert "Depth by criterion" in response.text


def test_render_rejects_a_bad_body() -> None:
    response = client.post(
        "/requirements/test-cases/render",
        json={"result": {"test_cases": "not a list"}, "criteria": []},
    )
    assert response.status_code == 422


def test_render_rejects_too_many_cases() -> None:
    big = suite(*[case(f"TC-{i:03d}") for i in range(61)])
    response = client.post(
        "/requirements/test-cases/render",
        json={"result": big.model_dump(), "criteria": ["one"]},
    )
    assert response.status_code == 422


def test_refine_without_keys_opens_drawer() -> None:
    response = client.post("/requirements/test-cases/refine", data=_form())
    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "open-keys"


def test_strengthen_sends_the_current_cases_and_an_additive_instruction(monkeypatch) -> None:
    current, _ = real_run()
    captured: list = []
    monkeypatch.setattr(llm, "generate_json", _fake(current, captured))
    client.post("/requirements/test-cases/refine", data=_form(), headers=KEYS_HEADER)
    assert len(captured) == 1
    assert "CURRENT TEST CASES" in captured[0]
    assert "Add new test cases only" in captured[0]
    assert "TC-001 | Functional | High | AC-1 |" in captured[0]
    # The focus the user chose rides along.
    assert "Test Coverage Focus: Functional, Negative" in captured[0]


def test_strengthen_ignores_ai_edits_to_existing_cases(monkeypatch) -> None:
    current, _ = real_run()
    tampered = suite(
        case("TC-001", title="The AI rewrote this title", expected_result="rewritten"),
        case("TC-009", "Negative", "AC-1", title="Unknown email is refused politely"),
    )
    monkeypatch.setattr(llm, "generate_json", _fake(tampered))
    body = client.post(
        "/requirements/test-cases/refine", data=_form(), headers=KEYS_HEADER
    ).text
    assert "+1 added" in body
    assert "~0 changed" in body
    assert "−0 removed" in body
    assert "The AI rewrote this title" not in body
    assert "Strengthen only adds cases." in body


def test_strengthen_with_nothing_thin_makes_no_ai_call(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    solid = suite(
        case("TC-001", "Functional", "AC-1"),
        case("TC-002", "Negative", "AC-1"),
        case("TC-003", "Boundary", "AC-1"),
    )
    body = client.post(
        "/requirements/test-cases/refine",
        data=_form(
            criteria_json=json.dumps(["one"]), current_json=solid.model_dump_json()
        ),
        headers=KEYS_HEADER,
    ).text
    assert "Every criterion already has enough cases." in body


def test_instruction_mode_needs_an_instruction(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    body = client.post(
        "/requirements/test-cases/refine",
        data=_form(mode="instruction", instruction="   "),
        headers=KEYS_HEADER,
    ).text
    assert "Type what you want changed" in body


def test_instruction_mode_shows_added_changed_and_removed(monkeypatch) -> None:
    current, _ = real_run()
    proposed = suite(
        # TC-001 keeps its id but gains a new expected result -> changed.
        case(
            "TC-001",
            title="Account locks after 5 incorrect password attempts",
            expected_result="The account locks for 15 minutes",
        ),
        # A brand new case -> added. Every other current case is gone -> removed.
        case("TC-009", "Boundary", "AC-2", title="Fifteen minutes exactly still refuses"),
    )
    monkeypatch.setattr(llm, "generate_json", _fake(proposed))
    body = client.post(
        "/requirements/test-cases/refine",
        data=_form(mode="instruction", instruction="Use exact times."),
        headers=KEYS_HEADER,
    ).text
    assert "+1 added" in body
    assert "~1 changed" in body
    assert "−7 removed" in body
    assert "This removes 7 test cases." in body
    assert "Strengthen only adds cases." not in body


def test_refine_rejects_too_many_current_cases(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    big = suite(*[case(f"TC-{i:03d}") for i in range(61)])
    body = client.post(
        "/requirements/test-cases/refine",
        data=_form(current_json=big.model_dump_json()),
        headers=KEYS_HEADER,
    ).text
    assert "Please check the test cases and instruction." in body


def test_refine_rejects_a_broken_current_list(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    body = client.post(
        "/requirements/test-cases/refine",
        data=_form(current_json='{"test_cases": "nope"}'),
        headers=KEYS_HEADER,
    ).text
    assert "Please check the test cases and instruction." in body


def test_refine_rejects_an_unknown_mode(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    body = client.post(
        "/requirements/test-cases/refine",
        data=_form(mode="rewrite-everything"),
        headers=KEYS_HEADER,
    ).text
    assert "Please check the test cases and instruction." in body


def test_refine_rejects_an_overlong_instruction(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    body = client.post(
        "/requirements/test-cases/refine",
        data=_form(mode="instruction", instruction="x" * 1001),
        headers=KEYS_HEADER,
    ).text
    assert "Please check the test cases and instruction." in body


def test_refine_never_logs_a_key(monkeypatch, caplog) -> None:
    current, _ = real_run()
    monkeypatch.setattr(llm, "generate_json", _fake(current))
    with caplog.at_level("DEBUG"):
        client.post("/requirements/test-cases/refine", data=_form(), headers=KEYS_HEADER)
    assert "first" not in caplog.text


def test_proposal_json_round_trips_through_render(monkeypatch) -> None:
    current, _ = real_run()
    added = suite(case("TC-009", "Negative", "AC-1", title="Unknown email is refused"))
    monkeypatch.setattr(llm, "generate_json", _fake(added))
    body = client.post(
        "/requirements/test-cases/refine", data=_form(), headers=KEYS_HEADER
    ).text
    raw = body.split('<script type="application/json" id="tc-proposed">')[1]
    raw = raw.split("</script>")[0]
    payload = json.loads(raw)
    assert len(payload["result"]["test_cases"]) == 9
    response = client.post("/requirements/test-cases/render", json=payload)
    assert response.status_code == 200
    assert "TC-009" in response.text


def test_example_strengthen_only_adds_cases() -> None:
    response = client.get("/requirements/test-cases/example-strengthen")
    assert response.status_code == 200
    body = response.text
    assert "+5 added" in body
    assert "~0 changed" in body
    assert "−0 removed" in body
    assert "Thin criteria" in body
    assert "3 → 0" in body
    assert "Strengthen only adds cases." in body


def test_example_offers_the_strengthen_link() -> None:
    body = client.get("/requirements/test-cases/example").text
    assert "Try Strengthen on the example" in body


def test_generated_result_has_no_strengthen_link(monkeypatch) -> None:
    """The example-only link must not show on a real run."""
    current, _ = real_run()
    monkeypatch.setattr(llm, "generate_json", _fake(current))
    body = client.post(
        "/requirements/test-cases/run",
        data={
            "user_story": STORY,
            "criteria_json": json.dumps(REAL_RUN_CRITERIA),
            "coverage_focus": ["Functional"],
        },
        headers=KEYS_HEADER,
    ).text
    assert "Try Strengthen on the example" not in body


def test_sample_files_validate_as_test_case_lists() -> None:
    from qagenius.models import TestCaseList

    for name in ("test_cases.json", "test_cases_strengthened.json"):
        with open(f"qagenius/samples/{name}", encoding="utf-8") as f:
            sample = json.load(f)
        result = TestCaseList.model_validate(sample["result"])
        assert result.test_cases
        assert len(sample["criteria"]) == 5
