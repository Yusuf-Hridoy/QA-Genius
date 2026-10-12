"""Quality insights routes. The LLM is faked; no network, nothing stored."""

import json
import pathlib

import pytest
from fastapi.testclient import TestClient

import main
from qagenius import llm
from qagenius.models import GroupInsight, QualityInsightSummary
from qagenius.test_run_metrics import insights_from_dict
from qagenius.web import ANALYZE_AGAIN_ERROR, REPORT_LIMIT_ERROR

client = TestClient(main.app)

KEYS_HEADER = {"X-QAG-Keys": json.dumps([{"provider": "gemini", "key": "first"}])}
SAMPLES = pathlib.Path("qagenius/samples/reports")
FIXTURES = pathlib.Path("tests/fixtures/reports")


def _sample_files() -> list:
    return [
        ("reports", ("nightly-chromium.xml", (SAMPLES / "nightly-chromium.xml").read_bytes())),
        ("reports", ("nightly-firefox.json", (SAMPLES / "nightly-firefox.json").read_bytes())),
    ]


def _never_called(*args, **kwargs):
    raise AssertionError("the AI must not be called here")


class _Spy:
    """Stands in for llm.generate_json and remembers what the route sent."""

    def __init__(self, **overrides) -> None:
        self.system = ""
        self.user = ""
        self.called = False
        values = {
            "headline": "Checkout is timing out.",
            "assessment": "One group looks like a product bug.",
            "groups": [
                GroupInsight(
                    group_id="G1",
                    kind="product bug",
                    likely_cause="The pay button never becomes ready.",
                    suggested_action="Place one order by hand.",
                )
            ],
            "flaky_advice": "Watch the login test for a week.",
            "next_steps": ["Re-run the checkout suite"],
        }
        values.update(overrides)
        self.summary = QualityInsightSummary(**values)

    def __call__(self, keys, system, user, schema):
        self.called = True
        self.system = system
        self.user = user
        assert schema is QualityInsightSummary
        return self.summary, 0, ["Used Key 1 (Gemini, test-model)"]


# ---------- the page ----------


def test_the_insights_page_opens() -> None:
    response = client.get("/insights")

    assert response.status_code == 200
    assert "Your report files" in response.text
    assert "Coming soon" not in response.text
    assert "/insights.js" in response.text


# ---------- analyze ----------


def test_analyze_reads_both_sample_runs_without_an_ai_call(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never_called)

    response = client.post("/insights/analyze", files=_sample_files())

    assert response.status_code == 200
    assert "85%" in response.text
    assert "G1" in response.text
    assert "Timeout 30000ms exceeded waiting for locator" in response.text
    assert "retried and passed" in response.text
    assert "passed in one run, failed in another" in response.text
    assert "nightly-chromium" in response.text
    # The promise that no AI touched these numbers is still on the page.
    assert "computed from your files" in response.text
    assert "nothing was sent to an AI" in response.text


def test_analyze_needs_no_key() -> None:
    response = client.post("/insights/analyze", files=_sample_files())

    assert response.status_code == 200
    assert "Add an API key" not in response.text


def test_the_pass_rate_pill_follows_the_number() -> None:
    green = client.post(
        "/insights/analyze",
        files=[("reports", ("green.xml", b'<testsuite name="s"><testcase name="a" time="1"/></testsuite>'))],
    )
    assert 'class="pill ok"' in green.text

    red = client.post(
        "/insights/analyze",
        files=[
            (
                "reports",
                (
                    "red.xml",
                    b'<testsuite name="s"><testcase name="a"><failure message="boom"/>'
                    b"</testcase></testsuite>",
                ),
            )
        ],
    )
    assert 'class="pill bad"' in red.text


def test_one_run_has_no_runs_table() -> None:
    one = client.post(
        "/insights/analyze",
        files=[("reports", ("one.xml", (SAMPLES / "nightly-chromium.xml").read_bytes()))],
    )
    assert 'id="insights-runs"' not in one.text

    both = client.post("/insights/analyze", files=_sample_files())
    assert 'id="insights-runs"' in both.text


def test_a_group_card_counts_the_tests_it_did_not_list() -> None:
    cases = "".join(
        f'<testcase classname="c" name="case {n}" time="1">'
        f'<failure message="Timeout {n}000ms exceeded waiting for \'#x\'"/></testcase>'
        for n in range(1, 8)
    )
    response = client.post(
        "/insights/analyze",
        files=[("reports", ("many.xml", f'<testsuite name="s">{cases}</testsuite>'.encode()))],
    )

    assert "+2 more" in response.text


def test_html_in_a_failure_message_is_shown_as_text() -> None:
    body = (
        b'<testsuite name="s"><testcase classname="c" name="xss" time="1">'
        b'<failure message="&lt;script&gt;alert(1)&lt;/script&gt; broke it">'
        b"&lt;img src=x onerror=alert(2)&gt;</failure></testcase></testsuite>"
    )
    response = client.post("/insights/analyze", files=[("reports", ("x.xml", body))])

    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "<img src=x onerror=alert(2)>" not in response.text


def test_too_many_files_are_refused() -> None:
    one = (SAMPLES / "nightly-chromium.xml").read_bytes()
    files = [("reports", (f"run-{number}.xml", one)) for number in range(6)]

    response = client.post("/insights/analyze", files=files)

    assert REPORT_LIMIT_ERROR in response.text


def test_a_file_over_two_megabytes_is_refused() -> None:
    big = b'<testsuite name="s">' + b"<!-- " + b"x" * (3 * 1024 * 1024) + b" -->"

    response = client.post("/insights/analyze", files=[("reports", ("big.xml", big))])

    assert REPORT_LIMIT_ERROR in response.text


def test_five_megabytes_in_total_is_refused() -> None:
    chunk = b'<testsuite name="s"><!-- ' + b"x" * (1024 * 1024) + b" --></testsuite>"
    files = [("reports", (f"run-{number}.xml", chunk)) for number in range(5)]

    response = client.post("/insights/analyze", files=files)

    assert REPORT_LIMIT_ERROR in response.text


def test_an_unsupported_file_names_the_file() -> None:
    response = client.post(
        "/insights/analyze",
        files=[("reports", ("notes.txt", (FIXTURES / "notes.txt").read_bytes()))],
    )

    assert "Unsupported file: notes.txt" in response.text


def test_an_xml_bomb_is_refused_quickly() -> None:
    response = client.post(
        "/insights/analyze",
        files=[("reports", ("bomb.xml", (FIXTURES / "junit_bomb.xml").read_bytes()))],
    )

    assert "bomb.xml" in response.text
    assert "lollol" not in response.text


def test_no_file_at_all_asks_for_one() -> None:
    response = client.post("/insights/analyze", data={"nothing": "here"})

    assert "Choose a JUnit XML or Playwright JSON file first." in response.text


def test_two_files_with_the_same_name_get_numbered() -> None:
    one = (SAMPLES / "nightly-chromium.xml").read_bytes()
    response = client.post(
        "/insights/analyze",
        files=[("reports", ("run.xml", one)), ("reports", ("run.xml", one))],
    )

    assert "run (2)" in response.text


# ---------- the facts that travel back ----------


def _facts_from(html: str) -> str:
    start = html.index('<script type="application/json" id="insights-facts">')
    start = html.index(">", start) + 1
    return html[start : html.index("</script>", start)]


def test_the_page_carries_facts_that_rebuild_the_insights() -> None:
    html = client.post("/insights/analyze", files=_sample_files()).text

    insights = insights_from_dict(json.loads(_facts_from(html)))

    assert insights.overall.total == 80
    assert [group.id for group in insights.groups] == ["G1", "G2", "G3"]
    assert "<testcase" not in _facts_from(html)


def test_the_page_carries_the_markdown_summary() -> None:
    html = client.post("/insights/analyze", files=_sample_files()).text

    assert '<script type="application/json" id="insights-md">' in html
    assert "Test run summary" in html


# ---------- explain ----------


def test_explain_without_keys_opens_the_keys_drawer(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never_called)
    facts = _facts_from(client.post("/insights/analyze", files=_sample_files()).text)

    response = client.post("/insights/explain", data={"facts_json": facts})

    assert response.headers["HX-Trigger"] == "open-keys"
    assert "Add an API key" in response.text


def test_explain_sends_the_facts_and_never_the_file(monkeypatch) -> None:
    spy = _Spy()
    monkeypatch.setattr(llm, "generate_json", spy)
    facts = _facts_from(client.post("/insights/analyze", files=_sample_files()).text)

    response = client.post(
        "/insights/explain", data={"facts_json": facts}, headers=KEYS_HEADER
    )

    assert spy.called is True
    assert "Failure groups" in spy.user
    assert "<testcase" not in spy.user
    assert "<testsuite" not in spy.user
    assert "do not invent numbers" in spy.system
    assert "Checkout is timing out." in response.text
    assert "product bug" in response.text


def test_explain_shows_a_pill_per_kind(monkeypatch) -> None:
    spy = _Spy(
        groups=[
            GroupInsight(group_id="G1", kind="product bug", likely_cause="c", suggested_action="a"),
            GroupInsight(group_id="G2", kind="environment", likely_cause="c", suggested_action="a"),
            GroupInsight(group_id="G3", kind="test issue", likely_cause="c", suggested_action="a"),
        ]
    )
    monkeypatch.setattr(llm, "generate_json", spy)
    facts = _facts_from(client.post("/insights/analyze", files=_sample_files()).text)

    html = client.post(
        "/insights/explain", data={"facts_json": facts}, headers=KEYS_HEADER
    ).text

    assert 'class="pill bad">product bug' in html
    assert 'class="pill info">environment' in html
    assert 'class="pill warn">test issue' in html


def test_explain_drops_a_group_the_code_never_found(monkeypatch) -> None:
    spy = _Spy(
        groups=[
            GroupInsight(group_id="G9", kind="unknown", likely_cause="c", suggested_action="a")
        ]
    )
    monkeypatch.setattr(llm, "generate_json", spy)
    facts = _facts_from(client.post("/insights/analyze", files=_sample_files()).text)

    html = client.post(
        "/insights/explain", data={"facts_json": facts}, headers=KEYS_HEADER
    ).text

    assert "Removed an explanation for unknown group G9." in html
    assert "G9</span>" not in html


@pytest.mark.parametrize(
    "facts_json",
    ["", "not json", "{}", '{"runs": [], "overall": {}, "groups": []}', '{"runs": 3}'],
)
def test_explain_refuses_facts_it_cannot_rebuild(monkeypatch, facts_json) -> None:
    monkeypatch.setattr(llm, "generate_json", _never_called)

    response = client.post(
        "/insights/explain", data={"facts_json": facts_json}, headers=KEYS_HEADER
    )

    assert ANALYZE_AGAIN_ERROR in response.text


def test_explain_refuses_an_oversized_field(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never_called)

    response = client.post(
        "/insights/explain",
        data={"facts_json": "x" * 300_001},
        headers=KEYS_HEADER,
    )

    assert ANALYZE_AGAIN_ERROR in response.text


def test_a_busy_key_shows_an_error_card(monkeypatch) -> None:
    def busy(keys, system, user, schema):
        raise llm.AllKeysBusyError(["Key 1 (Gemini) was busy, trying the next key"])

    monkeypatch.setattr(llm, "generate_json", busy)
    facts = _facts_from(client.post("/insights/analyze", files=_sample_files()).text)

    response = client.post(
        "/insights/explain", data={"facts_json": facts}, headers=KEYS_HEADER
    )

    assert "All your keys are busy" in response.text


# ---------- the saved example ----------


def test_the_example_works_without_a_key(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never_called)

    response = client.get("/insights/example")

    assert response.status_code == 200
    assert "85%" in response.text
    assert "nightly-chromium" in response.text
    assert "/insights/example-explained" in response.text


def test_the_example_explanation_works_without_a_key(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _never_called)

    response = client.get("/insights/example-explained")

    assert response.status_code == 200
    assert "Answered by saved example." in response.text
    assert 'class="pill bad">product bug' in response.text
    assert "Removed" not in response.text


def test_the_key_is_never_echoed_by_explain(monkeypatch) -> None:
    secret = "sk-INSIGHTSSECRET123"

    def busy(keys, system, user, schema):
        raise llm.AllKeysBusyError(["Key 1 (Gemini) was busy, trying the next key"])

    monkeypatch.setattr(llm, "generate_json", busy)
    facts = _facts_from(client.post("/insights/analyze", files=_sample_files()).text)

    response = client.post(
        "/insights/explain",
        data={"facts_json": facts},
        headers={"X-QAG-Keys": json.dumps([{"provider": "gemini", "key": secret}])},
    )

    assert secret not in response.text
