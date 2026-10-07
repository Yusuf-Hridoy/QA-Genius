"""Automation route tests. The LLM is faked; no network, no key ever stored."""

import io
import json
import zipfile

from fastapi.testclient import TestClient

import main
from qagenius import llm
from qagenius.automation_exports import TOP_FOLDER
from qagenius.prompts import automation_prompt
from tests.factories import case, script

client = TestClient(main.app)

KEYS_HEADER = {"X-QAG-Keys": json.dumps([{"provider": "gemini", "key": "first"}])}

SELECTED = [
    case(case_id="TC-001", title="Account locks on the fifth wrong password"),
    case(case_id="TC-003", title="Lockout message names the 30 minute duration"),
]


def _form(**overrides) -> dict:
    form = {
        "selected_json": json.dumps([one.model_dump() for one in SELECTED]),
        "framework_choice": "Playwright · TypeScript",
        "structure_choice": "Page Object Model",
        "browsers": ["chromium"],
        "base_url": "https://staging.aurora-shop.dev",
    }
    form.update(overrides)
    return form


class _Spy:
    """Stands in for llm.generate_json and remembers what the route sent."""

    def __init__(self, **script_overrides) -> None:
        self.system = ""
        self.user = ""
        self.called = False
        self.script = script(**script_overrides)

    def __call__(self, keys, system, user, schema):
        self.called = True
        self.system = system
        self.user = user
        return self.script, 0, []


# ---------------------------------------------------------------- the page


def test_the_page_shows_the_step_bar() -> None:
    response = client.get("/requirements/automation")
    assert response.status_code == 200
    assert "4 · Automation" in response.text
    assert "3 · Test cases" in response.text


def test_every_requirements_page_links_to_step_four() -> None:
    for path in (
        "/requirements/story",
        "/requirements/criteria",
        "/requirements/test-cases",
    ):
        body = client.get(path).text
        assert '/requirements/automation"' in body
        assert "soon" not in body


# ---------------------------------------------------------------- step 3 selection


def test_each_case_card_has_a_labelled_checkbox() -> None:
    body = client.get("/requirements/test-cases/example").text
    assert 'aria-label="Select TC-001"' in body
    assert 'data-case-id="TC-001"' in body
    assert body.count('class="tc-select"') == 11


def test_the_select_bar_starts_empty_and_disabled() -> None:
    body = client.get("/requirements/test-cases/example").text
    assert 'id="select-all-cases"' in body
    assert 'id="clear-selected-cases"' in body
    assert 'aria-live="polite">0 selected<' in body
    assert 'id="automate-selected" disabled' in body
    assert "Automate selected" in body


def test_the_diff_view_has_no_checkboxes() -> None:
    body = client.get("/requirements/test-cases/example-strengthen").text
    assert "tc-select" not in body
    assert "aria-label=\"Select " not in body


# ---------------------------------------------------------------- /run guards


def test_no_keys_opens_the_keys_drawer() -> None:
    response = client.post("/requirements/automation/run", data=_form())
    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "open-keys"


def test_an_unknown_framework_is_refused_without_an_ai_call(monkeypatch) -> None:
    spy = _Spy()
    monkeypatch.setattr(llm, "generate_json", spy)
    response = client.post(
        "/requirements/automation/run",
        data=_form(framework_choice="Playwright · Rust"),
        headers=KEYS_HEADER,
    )
    assert "Please check the selected test cases and settings." in response.text
    assert spy.called is False


def test_an_unknown_structure_is_refused_without_an_ai_call(monkeypatch) -> None:
    spy = _Spy()
    monkeypatch.setattr(llm, "generate_json", spy)
    response = client.post(
        "/requirements/automation/run",
        data=_form(structure_choice="Whatever"),
        headers=KEYS_HEADER,
    )
    assert "Please check the selected test cases and settings." in response.text
    assert spy.called is False


def test_thirteen_cases_are_refused_without_an_ai_call(monkeypatch) -> None:
    spy = _Spy()
    monkeypatch.setattr(llm, "generate_json", spy)
    too_many = [case(case_id=f"TC-{index:03d}").model_dump() for index in range(1, 14)]
    response = client.post(
        "/requirements/automation/run",
        data=_form(selected_json=json.dumps(too_many)),
        headers=KEYS_HEADER,
    )
    assert "Please check the selected test cases and settings." in response.text
    assert spy.called is False


def test_no_cases_are_refused_without_an_ai_call(monkeypatch) -> None:
    spy = _Spy()
    monkeypatch.setattr(llm, "generate_json", spy)
    response = client.post(
        "/requirements/automation/run",
        data=_form(selected_json="[]"),
        headers=KEYS_HEADER,
    )
    assert "Please check the selected test cases and settings." in response.text
    assert spy.called is False


def test_a_javascript_base_url_is_refused_without_an_ai_call(monkeypatch) -> None:
    spy = _Spy()
    monkeypatch.setattr(llm, "generate_json", spy)
    response = client.post(
        "/requirements/automation/run",
        data=_form(base_url="javascript:alert(1)"),
        headers=KEYS_HEADER,
    )
    assert "Please check the selected test cases and settings." in response.text
    assert spy.called is False


def test_an_unknown_browser_is_refused_without_an_ai_call(monkeypatch) -> None:
    spy = _Spy()
    monkeypatch.setattr(llm, "generate_json", spy)
    response = client.post(
        "/requirements/automation/run",
        data=_form(browsers=["chromium", "netscape"]),
        headers=KEYS_HEADER,
    )
    assert "Please check the selected test cases and settings." in response.text
    assert spy.called is False


# ---------------------------------------------------------------- what we send


def test_the_prompt_keeps_the_v1_system_text_and_adds_our_rules(monkeypatch) -> None:
    spy = _Spy()
    monkeypatch.setattr(llm, "generate_json", spy)
    client.post("/requirements/automation/run", data=_form(), headers=KEYS_HEADER)

    expected_system, _ = automation_prompt(
        "",
        "Playwright (JavaScript)",
        "TypeScript",
        "Page Object Model",
        "chromium",
        "Custom web app at https://staging.aurora-shop.dev",
    )
    assert spy.system == expected_system

    assert "TC-001:" in spy.user
    assert "TC-003:" in spy.user
    assert "Write exactly one automated test" in spy.user
    assert "Base URL: https://staging.aurora-shop.dev" in spy.user
    assert "Framework: Playwright (JavaScript)" in spy.user
    assert "Language: TypeScript" in spy.user


def test_an_empty_base_url_falls_back_to_the_sample_site(monkeypatch) -> None:
    spy = _Spy()
    monkeypatch.setattr(llm, "generate_json", spy)
    client.post(
        "/requirements/automation/run", data=_form(base_url=""), headers=KEYS_HEADER
    )
    assert "Base URL: https://staging.aurora-shop.dev" in spy.user


def test_a_non_playwright_framework_sends_chromium(monkeypatch) -> None:
    spy = _Spy()
    monkeypatch.setattr(llm, "generate_json", spy)
    client.post(
        "/requirements/automation/run",
        data=_form(framework_choice="Selenium · Python", browsers=["firefox"]),
        headers=KEYS_HEADER,
    )
    assert "Browsers: chromium" in spy.user


def test_playwright_sends_the_chosen_browsers(monkeypatch) -> None:
    spy = _Spy()
    monkeypatch.setattr(llm, "generate_json", spy)
    client.post(
        "/requirements/automation/run",
        data=_form(browsers=["webkit", "chromium"]),
        headers=KEYS_HEADER,
    )
    assert "Browsers: chromium, webkit" in spy.user


# ---------------------------------------------------------------- the result


def test_the_result_shows_traced_missing_and_syntax(monkeypatch) -> None:
    spy = _Spy(
        test_code="test('TC-001: locks', async () => {});\n",
        page_object_code=None,
        config_code=None,
    )
    monkeypatch.setattr(llm, "generate_json", spy)
    response = client.post(
        "/requirements/automation/run", data=_form(), headers=KEYS_HEADER
    )
    assert response.status_code == 200
    assert "1 of 2 selected test cases have a matching test" in response.text
    assert "No test mentions TC-003" in response.text
    assert "basic check passed" in response.text
    assert "not a full compile" in response.text


def test_a_syntax_error_is_shown(monkeypatch) -> None:
    spy = _Spy(
        test_code="test('TC-001: locks', async () => {\n",
        page_object_code=None,
        config_code=None,
    )
    monkeypatch.setattr(llm, "generate_json", spy)
    response = client.post(
        "/requirements/automation/run", data=_form(), headers=KEYS_HEADER
    )
    assert "Unclosed" in response.text


def test_a_busy_key_shows_the_friendly_card(monkeypatch) -> None:
    def busy(keys, system, user, schema):
        raise llm.AllKeysBusyError(["Key 1 (Gemini) was busy, trying the next key"])

    monkeypatch.setattr(llm, "generate_json", busy)
    response = client.post(
        "/requirements/automation/run", data=_form(), headers=KEYS_HEADER
    )
    assert "All your keys are busy." in response.text


# ---------------------------------------------------------------- the example


def test_the_example_needs_no_key_and_traces_every_case() -> None:
    response = client.get("/requirements/automation/example")
    assert response.status_code == 200
    assert "3 of 3 selected test cases have a matching test" in response.text
    assert "saved example" in response.text


def test_the_example_shows_exactly_one_fixed_wait_warning() -> None:
    body = client.get("/requirements/automation/example").text
    assert body.count("Fixed wait") == 1


# ---------------------------------------------------------------- the file viewer


def test_there_is_one_button_per_file() -> None:
    body = client.get("/requirements/automation/example").text
    assert body.count('class="file-tab') == 3
    assert body.count('class="code file-body"') == 3
    assert "pages/LoginPage.ts" in body
    assert "tests/login-lockout.spec.ts" in body
    assert "playwright.config.ts" in body


def test_the_stat_row_counts_files_traces_syntax_and_warnings() -> None:
    body = client.get("/requirements/automation/example").text
    assert ">3 / 3<" in body
    assert "all valid" in body
    assert ">Tests traced<" in body
    assert ">Warnings<" in body


def test_the_run_command_and_setup_steps_are_shown() -> None:
    body = client.get("/requirements/automation/example").text
    assert "npx playwright test" in body
    assert "npm init -y" in body
    assert 'id="copy-command"' in body
    assert "Design notes" in body


def test_code_is_escaped_not_run(monkeypatch) -> None:
    spy = _Spy(
        page_object_code=None,
        config_code=None,
        test_code="const bad = '<script>alert(1)</script>';\n",
    )
    monkeypatch.setattr(llm, "generate_json", spy)
    body = client.post(
        "/requirements/automation/run", data=_form(), headers=KEYS_HEADER
    ).text
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body


def test_the_download_button_and_its_payload_are_present() -> None:
    body = client.get("/requirements/automation/example").text
    assert 'id="download-zip"' in body
    assert 'id="automation-data"' in body


def test_the_rendered_payload_round_trips_through_the_export_route() -> None:
    body = client.get("/requirements/automation/example").text
    raw = body.split('id="automation-data">', 1)[1].split("</script>", 1)[0]
    payload = json.loads(raw)
    assert payload["selected_ids"] == ["TC-001", "TC-003", "TC-004"]

    response = client.post("/requirements/automation/export.zip", json=payload)
    assert response.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert f"{TOP_FOLDER}/tests/login-lockout.spec.ts" in names


# ---------------------------------------------------------------- the ZIP


def _export(project, selected_ids: list[str]):
    return client.post(
        "/requirements/automation/export.zip",
        json={"script": project.model_dump(), "selected_ids": selected_ids},
    )


def test_the_export_returns_a_zip() -> None:
    response = _export(script(), ["TC-001"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "qa-genius-automation.zip" in response.headers["content-disposition"]

    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert archive.testzip() is None
    assert f"{TOP_FOLDER}/tests/login.spec.ts" in archive.namelist()
    assert f"{TOP_FOLDER}/README.md" in archive.namelist()


def test_an_escaping_file_name_lands_inside_the_top_folder() -> None:
    response = _export(script(test_file_name="../evil.ts"), ["TC-001"])
    assert response.status_code == 200

    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert f"{TOP_FOLDER}/test_cases.ts" in names
    assert all(name.startswith(f"{TOP_FOLDER}/") and ".." not in name for name in names)


def test_a_broken_export_body_is_refused() -> None:
    response = client.post(
        "/requirements/automation/export.zip", json={"selected_ids": ["TC-001"]}
    )
    assert response.status_code == 422


def test_an_oversized_export_body_is_refused() -> None:
    project = script(test_code="x" * 600000)
    response = _export(project, ["TC-001"])
    assert response.status_code == 422


# ---------------------------------------------------------------- the key


def test_the_key_never_reaches_the_page_or_the_logs(monkeypatch, caplog) -> None:
    secret = "sk-AUTOMATIONSECRET123"

    def busy(keys, system, user, schema):
        raise llm.AllKeysBusyError(["Key 1 (Gemini) was busy, trying the next key"])

    monkeypatch.setattr(llm, "generate_json", busy)
    header = {"X-QAG-Keys": json.dumps([{"provider": "gemini", "key": secret}])}
    with caplog.at_level("DEBUG"):
        response = client.post(
            "/requirements/automation/run", data=_form(), headers=header
        )
    assert secret not in response.text
    assert secret not in caplog.text
