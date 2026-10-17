"""The Ship check page and its result card: what a reader actually sees."""

import json

import pytest
from fastapi.testclient import TestClient

import main
from qagenius import llm

client = TestClient(main.app)

REASON = "Behind a feature flag for internal users until the shared counter lands."


@pytest.fixture(autouse=True)
def no_ai(monkeypatch):
    def _never(*args, **kwargs):
        raise AssertionError("Ship check must not call the AI")

    monkeypatch.setattr(llm, "generate_json", _never)


def sample() -> dict:
    with open("qagenius/samples/ship_check.json", encoding="utf-8") as f:
        return json.load(f)


def post(body: dict) -> str:
    return client.post("/ship/report", content=json.dumps(body)).text


# ---------- the shell ----------


def test_the_page_loads_its_own_script_and_nothing_else_new():
    body = client.get("/ship").text
    assert '<script src="/ship_check.js" defer></script>' in body
    assert 'id="ship-root"' in body
    assert 'id="ship-output"' in body


def test_the_script_is_served():
    assert client.get("/ship_check.js").status_code == 200


# ---------- the verdict banner ----------


@pytest.mark.parametrize(
    "tone,label",
    [("bad", "Don&#39;t ship"), ("warn", "Ship with risks"), ("ok", "Ship")],
)
def test_the_banner_tone_matches_the_verdict(tone, label):
    body = sample()
    if tone == "warn":
        body["acceptances"] = {"risks": REASON}
    if tone == "ok":
        for case in body["test_cases"]["result"]["test_cases"]:
            if case["id"] == "TC-001":
                case["tags"].append("risk:R1")
        body["duel_summary"] = {"agreement_pct": 95, "forks": []}
        body["test_cases"]["criteria"] = body["test_cases"]["criteria"][:2]
    text = post(body)
    assert f"ship-verdict ship-{tone}" in text
    assert label in text


def test_the_banner_counts_the_checks_that_ran():
    assert "5 of 7 checks ran" in client.get("/ship/example").text


# ---------- the rows ----------


def test_a_pass_row_carries_no_accept_button():
    rows = client.get("/ship/example").text.split('class="card ship-row"')
    passing = [row for row in rows if 'data-status="pass"' in row]
    assert passing
    assert all("Accept with reason" not in row for row in passing)


def test_a_warn_row_carries_no_accept_button():
    rows = client.get("/ship/example").text.split('class="card ship-row"')
    warning = [row for row in rows if 'data-status="warn"' in row]
    assert warning
    assert all("Accept with reason" not in row for row in warning)


def test_a_fail_row_carries_the_accept_form():
    rows = client.get("/ship/example").text.split('class="card ship-row"')
    failing = [row for row in rows if 'data-status="fail"' in row][0]
    assert "Accept with reason" in failing
    assert 'class="ship-accept-form"' in failing
    assert 'minlength="10"' in failing and 'maxlength="300"' in failing


def test_an_accepted_row_shows_the_note_and_a_way_back():
    body = sample()
    body["acceptances"] = {"risks": REASON}
    text = post(body)
    assert f"<em>Accepted: {REASON}</em>" in text
    assert "Remove acceptance" in text


def test_a_script_tag_in_a_reason_shows_as_text():
    body = sample()
    body["acceptances"] = {"risks": "<script>alert(1)</script> shipping anyway"}
    text = post(body)
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text


def test_details_are_a_disclosure_not_a_wall_of_text():
    body = client.get("/ship/example").text
    assert '<details class="ship-details">' in body
    assert "no test" in body


# ---------- the buttons ----------


def test_the_report_offers_copy_and_print():
    body = client.get("/ship/example").text
    assert 'id="ship-copy-md"' in body
    assert 'id="ship-print"' in body


def test_the_markdown_block_holds_the_whole_report():
    body = client.get("/ship/example").text
    markdown = json.loads(
        body.split('id="ship-md">', 1)[1].split("</script>", 1)[0]
    )
    assert "# Ship check" in markdown
    assert "## Details" in markdown


def test_the_print_stylesheet_hides_the_chrome():
    css = client.get("/style.css").text
    assert "@media print" in css
    assert ".ship-print" in css


# ---------- the promise on the page ----------


def test_the_result_repeats_that_nothing_left_the_browser():
    body = client.get("/ship/example").text
    assert "Nothing was sent to an AI" in body


# ---------- getting here from the other desks ----------


def test_the_sidebar_offers_ship_check_last():
    body = client.get("/ship").text
    assert 'href="/ship"' in body
    assert body.index('href="/risks"') < body.index('href="/ship"')


def test_the_sidebar_does_not_offer_performance():
    body = client.get("/").text
    assert 'href="/performance"' not in body
    assert "Performance" not in body


def test_the_home_page_sends_you_to_ship_check():
    body = client.get("/").text
    assert 'class="desk" href="/ship"' in body


@pytest.mark.parametrize(
    "url",
    [
        "/requirements/test-cases/example",
        "/risks/example",
        "/requirements/automation/example",
    ],
)
def test_each_result_card_links_on_to_ship_check(url):
    body = client.get(url).text
    assert 'class="btn btn-small ship-link" href="/ship"' in body
