"""Bug desk route tests. The LLM is faked; no network, no key or screenshot stored."""

import base64
import json

from fastapi.testclient import TestClient

import main
from qagenius import llm
from qagenius.bug_report import (
    DEVICE_ERROR,
    FIELD_ERROR,
    HAPPENED_ERROR,
    NOTES_ERROR,
    TOTAL_ERROR,
    URL_ERROR,
)
from qagenius.prompts import bug_report_prompt
from qagenius.web import SCREENSHOT_ERROR
from tests.factories import bug_report

client = TestClient(main.app)

KEYS_HEADER = {"X-QAG-Keys": json.dumps([{"provider": "gemini", "key": "first"}])}

NOTES = (
    "Checkout button does nothing on the second click in Safari, cart total shows 0. "
    "Works fine in Chrome."
)

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 64).decode("ascii")


def _form(**overrides) -> dict:
    form = {
        "notes": NOTES,
        "device": "Desktop",
        "os": "macOS 14",
        "browser": "Safari 17",
        "build": "2.8.1",
        "url": "https://staging.aurora-shop.dev/checkout",
        "total_attempts": "5",
        "successful_attempts": "3",
    }
    form.update(overrides)
    return form


class _Spy:
    """Stands in for llm.generate_json and remembers what the route sent."""

    def __init__(self, **report_overrides) -> None:
        self.system = ""
        self.user = ""
        self.image = "not called"
        self.called = False
        self.report = bug_report(**report_overrides)

    def __call__(self, keys, system, user, schema, image=None):
        self.called = True
        self.system = system
        self.user = user
        self.image = image
        return self.report, 0, []


# ---------------------------------------------------------------- the page


def test_the_page_shows_the_form() -> None:
    response = client.get("/bugs")
    assert response.status_code == 200
    assert 'id="bug-form"' in response.text
    assert 'name="notes"' in response.text
    assert 'name="total_attempts"' in response.text
    assert 'name="screenshot_data"' in response.text
    assert "Coming soon" not in response.text


def test_the_page_offers_every_device() -> None:
    body = client.get("/bugs").text
    for device in ("Not specified", "Desktop", "Mobile", "Tablet"):
        assert f'<option value="{device}">' in body


def test_the_page_loads_its_own_script_only() -> None:
    body = client.get("/bugs").text
    assert "/bug_desk.js" in body
    assert "requirements_flow.js" not in body


# ---------------------------------------------------------------- guards


def test_no_keys_opens_the_keys_drawer() -> None:
    response = client.post("/bugs/run", data=_form())
    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "open-keys"


def _refused(monkeypatch, message: str, **overrides) -> None:
    spy = _Spy()
    monkeypatch.setattr(llm, "generate_json", spy)
    response = client.post("/bugs/run", data=_form(**overrides), headers=KEYS_HEADER)
    assert message in response.text
    assert spy.called is False


def test_short_notes_are_refused_without_an_ai_call(monkeypatch) -> None:
    _refused(monkeypatch, NOTES_ERROR, notes="too short")


def test_an_unknown_device_is_refused_without_an_ai_call(monkeypatch) -> None:
    _refused(monkeypatch, DEVICE_ERROR, device="Fridge")


def test_a_long_environment_field_is_refused_without_an_ai_call(monkeypatch) -> None:
    _refused(monkeypatch, FIELD_ERROR, browser="x" * 101)


def test_a_javascript_url_is_refused_without_an_ai_call(monkeypatch) -> None:
    _refused(monkeypatch, URL_ERROR, url="javascript:alert(1)")


def test_bad_attempt_counts_are_refused_without_an_ai_call(monkeypatch) -> None:
    _refused(monkeypatch, TOTAL_ERROR, total_attempts="0")
    _refused(monkeypatch, TOTAL_ERROR, total_attempts="not a number")
    # The card escapes the apostrophe, so match the tail of the message.
    _refused(
        monkeypatch,
        HAPPENED_ERROR.split("can't ")[1],
        total_attempts="3",
        successful_attempts="4",
    )


# ---------------------------------------------------------------- screenshots


def test_a_wrong_image_type_is_refused_without_an_ai_call(monkeypatch) -> None:
    _refused(
        monkeypatch, SCREENSHOT_ERROR,
        screenshot_mime="image/gif", screenshot_data=PNG,
    )


def test_broken_base64_is_refused_without_an_ai_call(monkeypatch) -> None:
    _refused(
        monkeypatch, SCREENSHOT_ERROR,
        screenshot_mime="image/png", screenshot_data="not base64 !!!",
    )


def test_an_image_over_two_megabytes_is_refused_without_an_ai_call(monkeypatch) -> None:
    over_cap = base64.b64encode(b"x" * (2 * 1024 * 1024 + 1)).decode("ascii")
    _refused(
        monkeypatch,
        SCREENSHOT_ERROR,
        screenshot_mime="image/png",
        screenshot_data=over_cap,
    )

    bigger = base64.b64encode(b"x" * (2 * 1024 * 1024 + 500_000)).decode("ascii")
    _refused(
        monkeypatch, SCREENSHOT_ERROR, screenshot_mime="image/png", screenshot_data=bigger
    )


def test_an_image_too_big_even_to_parse_never_reaches_the_ai(monkeypatch) -> None:
    """A 3 MB image is ~4 MB of base64, which the form parser refuses outright."""
    spy = _Spy()
    monkeypatch.setattr(llm, "generate_json", spy)
    huge = base64.b64encode(b"x" * (3 * 1024 * 1024)).decode("ascii")
    response = client.post(
        "/bugs/run",
        data=_form(screenshot_mime="image/png", screenshot_data=huge),
        headers=KEYS_HEADER,
    )
    assert response.status_code == 400
    assert spy.called is False


def test_a_good_screenshot_is_passed_to_the_model(monkeypatch) -> None:
    spy = _Spy()
    monkeypatch.setattr(llm, "generate_json", spy)
    client.post(
        "/bugs/run",
        data=_form(screenshot_mime="image/png", screenshot_data=PNG),
        headers=KEYS_HEADER,
    )
    assert spy.image == ("image/png", PNG)
    assert "A screenshot is attached." in spy.user


def test_no_screenshot_sends_no_image(monkeypatch) -> None:
    spy = _Spy()
    monkeypatch.setattr(llm, "generate_json", spy)
    client.post("/bugs/run", data=_form(), headers=KEYS_HEADER)
    assert spy.image is None
    assert "A screenshot is attached." not in spy.user


# ---------------------------------------------------------------- what we send


def test_the_prompt_keeps_the_v1_system_text_and_adds_the_facts(monkeypatch) -> None:
    spy = _Spy()
    monkeypatch.setattr(llm, "generate_json", spy)
    client.post("/bugs/run", data=_form(), headers=KEYS_HEADER)

    expected_system, _ = bug_report_prompt("")
    assert spy.system == expected_system

    assert spy.user.startswith("Raw bug notes:\n" + NOTES)
    assert "Reproducibility: Intermittent (3 of 5)" in spy.user
    assert "Total Attempts: 5" in spy.user
    assert "Times It Happened: 3" in spy.user
    assert "Environment Details: Device: Desktop; OS: macOS 14" in spy.user


# ---------------------------------------------------------------- the result


def test_the_result_shows_the_checks(monkeypatch) -> None:
    spy = _Spy()
    monkeypatch.setattr(llm, "generate_json", spy)
    response = client.post("/bugs/run", data=_form(), headers=KEYS_HEADER)

    assert response.status_code == 200
    assert "Report checks" in response.text
    assert "Checked by code." in response.text
    assert "Steps to reproduce" in response.text
    # No screenshot was sent, so that one check is missing.
    assert "Ask for a screenshot or screen recording." in response.text


def test_a_busy_key_shows_the_friendly_card(monkeypatch) -> None:
    def busy(keys, system, user, schema, image=None):
        raise llm.AllKeysBusyError(["Key 1 (Gemini) was busy, trying the next key"])

    monkeypatch.setattr(llm, "generate_json", busy)
    response = client.post("/bugs/run", data=_form(), headers=KEYS_HEADER)
    assert "All your keys are busy." in response.text


# ---------------------------------------------------------------- the example


def test_the_example_needs_no_key() -> None:
    response = client.get("/bugs/example")
    assert response.status_code == 200
    assert "saved example" in response.text


def test_the_example_passes_six_of_seven_checks() -> None:
    body = client.get("/bugs/example").text
    assert "Report quality 86% — 6 of 7" in body
    assert "Ask for a screenshot or screen recording." in body


# ---------------------------------------------------------------- the result card


def _result(monkeypatch, **report_overrides) -> str:
    spy = _Spy(**report_overrides)
    monkeypatch.setattr(llm, "generate_json", spy)
    return client.post("/bugs/run", data=_form(), headers=KEYS_HEADER).text


def test_severity_picks_the_right_pill(monkeypatch) -> None:
    assert '<span class="pill bad">Critical</span>' in _result(
        monkeypatch, severity="Critical"
    )
    assert '<span class="pill bad">High</span>' in _result(monkeypatch, severity="High")
    assert '<span class="pill warn">Medium</span>' in _result(
        monkeypatch, severity="Medium"
    )
    assert '<span class="pill ok">Low</span>' in _result(monkeypatch, severity="Low")
    assert '<span class="pill neutral">Spicy</span>' in _result(
        monkeypatch, severity="Spicy"
    )


def test_the_reproducibility_pill_is_computed_by_code(monkeypatch) -> None:
    # The form said 3 of 5; the AI said "Often". The card shows the counted one.
    body = _result(monkeypatch, reproducibility_rate="Often")
    assert "Intermittent (3 of 5)" in body


def test_optional_sections_are_hidden_when_empty(monkeypatch) -> None:
    body = _result(
        monkeypatch,
        workaround=None,
        suggested_fix=None,
        related_areas=[],
        jira_labels=[],
        investigation_steps=[],
        screenshot_annotations=[],
        related_issues=[],
        suspected_pattern=None,
        business_impact=None,
        affected_users=None,
        regression_risk=None,
        root_cause_category=None,
    )
    for heading in (
        "<h3>Workaround</h3>",
        "<h3>Suggested fix</h3>",
        "<h3>Related areas</h3>",
        "<h3>Labels</h3>",
        "<h3>Investigation steps</h3>",
        "<h3>Screenshot notes</h3>",
    ):
        assert heading not in body
    assert "More detail" not in body


def test_optional_sections_show_when_present(monkeypatch) -> None:
    body = _result(monkeypatch)
    assert "<h3>Workaround</h3>" in body
    assert "<h3>Investigation steps</h3>" in body
    assert "<h3>Labels</h3>" in body


def test_the_export_payload_carries_both_texts(monkeypatch) -> None:
    body = _result(monkeypatch)
    raw = body.split('id="bug-export">', 1)[1].split("</script>", 1)[0]
    payload = json.loads(raw)

    assert set(payload) == {"markdown", "jira"}
    assert payload["markdown"].startswith("## ")
    assert payload["jira"].startswith("h2. ")
    assert "copy-markdown" in body
    assert "copy-jira" in body
    assert "download-md" in body


def test_ai_text_is_escaped_not_run(monkeypatch) -> None:
    body = _result(monkeypatch, title="Checkout <script>alert(1)</script> breaks")
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body


def test_a_model_that_refused_the_image_says_so(monkeypatch) -> None:
    note = "Key 1 (Gemini, m) can't read images — the screenshot was not used."

    def refused(keys, system, user, schema, image=None):
        return bug_report(), 0, [note]

    monkeypatch.setattr(llm, "generate_json", refused)
    body = client.post(
        "/bugs/run",
        data=_form(screenshot_mime="image/png", screenshot_data=PNG),
        headers=KEYS_HEADER,
    ).text
    assert "can&#39;t read images" in body
    assert "warn-line" in body


# ---------------------------------------------------------------- secrets


def test_the_key_and_the_screenshot_never_leak(monkeypatch, caplog) -> None:
    secret = "sk-BUGDESKSECRET123456"
    spy = _Spy()
    monkeypatch.setattr(llm, "generate_json", spy)
    header = {"X-QAG-Keys": json.dumps([{"provider": "gemini", "key": secret}])}
    with caplog.at_level("DEBUG"):
        response = client.post(
            "/bugs/run",
            data=_form(screenshot_mime="image/png", screenshot_data=PNG),
            headers=header,
        )
    assert secret not in response.text
    assert secret not in caplog.text
    assert PNG not in response.text
    assert PNG not in caplog.text
