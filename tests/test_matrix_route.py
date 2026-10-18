"""Matrix routes. The AI is faked and never decides a row count."""

import json
import logging

import pytest
from fastapi.testclient import TestClient

import main
from qagenius import llm
from qagenius.models import MatrixProposal, ProposedFactor, ProposedRule
from tests.factories import case

client = TestClient(main.app)

KEY = "sk-matrix-key-never-logged"
KEYS_HEADER = {"X-QAG-Keys": json.dumps([{"provider": "gemini", "key": KEY}])}

STORY = "As a shopper, I want to sign in on any device so that I can reach my orders."
CRITERIA = ["Signing in works on a phone", "Arabic flips the layout right to left"]
CASES = [case(case_id="TC-001"), case(case_id="TC-002", category="Negative")]
FORM = {
    "user_story": STORY,
    "criteria_json": json.dumps(CRITERIA),
    "cases_json": json.dumps([one.model_dump() for one in CASES]),
}

SUGGESTED = MatrixProposal(
    factors=[
        ProposedFactor(name="Browser", values=["Chrome", "Safari"], reason="Web page."),
        ProposedFactor(name="Device", values=["Desktop", "Phone"], reason="Any device."),
        ProposedFactor(name="Language", values=["EN", "AR"], reason="Right to left."),
    ],
    rules=[
        ProposedRule(
            if_factor="Browser", if_value="Safari", then_factor="Device",
            then_value="Desktop", reason="Pretend rule.",
        )
    ],
)


def _never(*args, **kwargs):
    raise AssertionError("The matrix must not call the AI here")


def _fake(result=SUGGESTED):
    def _generate(keys, system, user, schema):
        return result, 0, ["Used Key 1 (Gemini)"]

    return _generate


def body(factors, rules=None, pinned=None) -> dict:
    return {
        "factors": [{"name": name, "values": values} for name, values in factors],
        "rules": rules or [],
        "pinned": pinned or [],
    }


STANDARD_BODY = body(
    [("Browser", ["Chrome", "Safari"]), ("Device", ["Desktop", "Phone"])]
)


# ----------------------------------------------------------------- the page


def test_the_page_renders() -> None:
    response = client.get("/requirements/matrix")
    assert response.status_code == 200
    assert 'id="matrix-root"' in response.text
    assert "/test_matrix.js" in response.text


def test_the_page_leaves_the_footer_to_the_editor() -> None:
    """Said once, where the source is known - not twice on the shell."""
    body_text = client.get("/requirements/matrix").text
    assert "computed by code" not in body_text


def test_the_footer_appears_once_and_says_who_chose_the_factors(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _fake())
    text = client.post(
        "/requirements/matrix/suggest", data=FORM, headers=KEYS_HEADER
    ).text
    assert text.count("computed by code") == 1
    assert "Factors suggested by AI from your story" in text
    assert "Standard factors" not in text


def test_without_a_key_the_footer_does_not_claim_the_ai_chose(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    text = client.post("/requirements/matrix/suggest", data=FORM).text
    assert text.count("computed by code") == 1
    assert "Standard factors" in text
    assert "suggested by AI" not in text


def test_the_keys_header_reaches_the_ai_path(monkeypatch) -> None:
    """The bug: the browser never sent the header, so the key was unused."""
    seen: dict[str, object] = {}

    def _generate(keys, system, user, schema):
        seen["keys"] = keys
        return SUGGESTED, 0, []

    monkeypatch.setattr(llm, "generate_json", _generate)
    response = client.post(
        "/requirements/matrix/suggest", data=FORM, headers=KEYS_HEADER
    )
    assert response.status_code == 200
    assert [one["provider"] for one in seen["keys"]] == ["gemini"]
    assert seen["keys"][0]["key"] == KEY
    assert "Factors suggested by AI from your story" in response.text


def test_reopening_keeps_the_footer_the_factors_were_born_with(monkeypatch) -> None:
    """Saved factors come back with their provenance, so the words hold."""
    monkeypatch.setattr(llm, "generate_json", _never)
    saved = dict(STANDARD_BODY)
    saved["from_ai"] = True
    text = client.post(
        "/requirements/matrix/suggest",
        data={**FORM, "saved_json": json.dumps(saved)},
    ).text
    assert "Factors suggested by AI from your story" in text


# ------------------------------------------------------------------ suggest


def test_without_a_key_the_standard_set_arrives_and_no_ai_is_called(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    response = client.post("/requirements/matrix/suggest", data=FORM)
    assert response.status_code == 200
    text = response.text
    assert "Using the standard set. Add an AI key" in text
    assert "Browser" in text and "Device" in text and "Signed in" in text
    assert "Runs needed" in text


def test_with_a_key_the_suggested_factors_are_used(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _fake())
    text = client.post(
        "/requirements/matrix/suggest", data=FORM, headers=KEYS_HEADER
    ).text
    assert "Language" in text
    assert "Right to left." in text  # the reason is shown with the factor
    assert "Using the standard set" not in text


def test_a_key_problem_still_leaves_a_working_matrix(monkeypatch) -> None:
    def _broken(keys, system, user, schema):
        raise llm.AllKeysBusyError([])

    monkeypatch.setattr(llm, "generate_json", _broken)
    text = client.post(
        "/requirements/matrix/suggest", data=FORM, headers=KEYS_HEADER
    ).text
    assert "Using the standard set" in text
    assert "Runs needed" in text


def test_a_story_that_is_far_too_long_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    data = dict(FORM, user_story="x" * 20000)
    text = client.post("/requirements/matrix/suggest", data=data).text
    assert "didn&#39;t arrive in one piece" in text


def test_the_key_is_never_written_to_a_log(monkeypatch, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(llm, "generate_json", _fake())
    response = client.post(
        "/requirements/matrix/suggest", data=FORM, headers=KEYS_HEADER
    )
    assert KEY not in caplog.text
    assert KEY not in response.text


# -------------------------------------------------------------------- build


def test_build_returns_the_rows_and_the_proof(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    response = client.post("/requirements/matrix/build", json=STANDARD_BODY)
    assert response.status_code == 200
    text = response.text
    assert "Runs needed" in text
    assert "4<span class=\"unit\"> / 4</span> ✓" in text
    assert "Every pair of values appears in at least one run." in text


def test_build_respects_a_rule(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    payload = body(
        [("Browser", ["Chrome", "Safari"]), ("Device", ["Desktop", "Phone"])],
        rules=[{
            "if_factor": "Safari".replace("Safari", "Browser"),
            "if_value": "Safari",
            "then_factor": "Device",
            "then_value": "Phone",
            "reason": "Pretend.",
        }],
    )
    text = client.post("/requirements/matrix/build", json=payload).text
    assert "Impossible pairs:" in text
    assert "Safari · Phone (rule)" in text


def test_build_keeps_a_pinned_run_first(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    payload = dict(STANDARD_BODY, pinned=[{"Browser": "Safari", "Device": "Phone"}])
    text = client.post("/requirements/matrix/build", json=payload).text
    first = text.index("matrix-pinned")
    assert "Safari" in text[first : first + 400]


def test_a_factor_with_one_value_gets_an_error_card(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    payload = body([("Browser", ["Chrome"]), ("Device", ["Desktop", "Phone"])])
    text = client.post("/requirements/matrix/build", json=payload).text
    assert "Factor &#39;Browser&#39; needs at least 2 values." in text


def test_a_pinned_run_that_breaks_a_rule_gets_an_error_card(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    payload = body(
        [("Browser", ["Chrome", "Safari"]), ("Device", ["Desktop", "Phone"])],
        rules=[{
            "if_factor": "Browser", "if_value": "Safari",
            "then_factor": "Device", "then_value": "Phone", "reason": "",
        }],
        pinned=[{"Browser": "Safari", "Device": "Phone"}],
    )
    assert "breaks one of your rules" in client.post(
        "/requirements/matrix/build", json=payload
    ).text


def test_too_many_factors_are_refused_by_the_body() -> None:
    payload = body([(f"F{i}", ["a", "b"]) for i in range(9)])
    assert client.post("/requirements/matrix/build", json=payload).status_code == 422


def test_a_value_with_a_script_tag_is_escaped(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    payload = body(
        [("Browser", ["<script>alert('x')</script>", "Safari"]),
         ("Device", ["Desktop", "Phone"])]
    )
    text = client.post("/requirements/matrix/build", json=payload).text
    assert "<script>alert" not in text
    assert "&lt;script&gt;alert" in text


# ------------------------------------------------------------------ exports


def test_the_playwright_config_downloads(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    response = client.post(
        "/requirements/matrix/export/playwright", json=STANDARD_BODY
    )
    assert response.status_code == 200
    assert "playwright.matrix.config.ts" in response.headers["content-disposition"]
    assert "defineConfig" in response.text


def test_the_csv_downloads(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    response = client.post("/requirements/matrix/export/csv", json=STANDARD_BODY)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "test-matrix.csv" in response.headers["content-disposition"]
    assert "Run,Browser,Device,Automated" in response.text


@pytest.mark.parametrize(
    "path", ["/requirements/matrix/export/playwright", "/requirements/matrix/export/csv"]
)
def test_an_unbuildable_matrix_is_a_422_not_a_broken_file(path) -> None:
    payload = body([("Browser", ["Chrome"]), ("Device", ["Desktop", "Phone"])])
    assert client.post(path, json=payload).status_code == 422


# ------------------------------------------------------------------ example


def test_the_example_needs_no_key_and_no_network(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    response = client.get("/requirements/matrix/example")
    assert response.status_code == 200
    text = response.text
    assert "<s>216</s>" in text
    assert "Runs needed" in text
    assert "This is a saved example" in text


def test_the_example_covers_every_valid_pair(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    text = client.get("/requirements/matrix/example").text
    assert "85<span class=\"unit\"> / 85</span> ✓" in text


def test_the_example_names_no_real_company(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never)
    text = client.get("/requirements/matrix/example").text
    assert "Aurora Storefront" in text or "Store admin" in text
