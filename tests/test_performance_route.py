"""Performance routes: one outbound call, to Google, and never for a private URL."""

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import main
from qagenius import llm, pagespeed
from qagenius.pagespeed import PSI_URL

client = TestClient(main.app)

SAMPLE = json.loads(
    (Path(__file__).parent / "fixtures" / "psi_sample.json").read_text(encoding="utf-8")
)
NAV_CRITERIA = [
    "Given a signed-in user, When they open any module, "
    "Then the active module shows a highlight and bold text",
    "Then the application routes to the reports view within 200ms "
    "without a full page reload",
    "Then keyboard focus rings are visible and Enter navigates to the module",
    "Given a mobile screen width below 768 pixels, "
    "Then the bar is collapsed by default into a hamburger menu",
]
PAGE = "https://aurora-storefront.example/dashboard"


@pytest.fixture(autouse=True)
def no_ai(monkeypatch):
    """This desk must never reach a model, whatever the body holds."""

    def _never(*args, **kwargs):
        raise AssertionError("The performance desk must not call the AI")

    monkeypatch.setattr(llm, "generate_json", _never)


class FakeHttp:
    """Replaces httpx.Client inside the pagespeed module for one test."""

    calls: list = []

    def __init__(self, *args, **kwargs):
        pass

    def get(self, url, params=None):
        FakeHttp.calls.append((url, dict(params or {})))
        return httpx.Response(
            200, json=SAMPLE, request=httpx.Request("GET", url)
        )

    def close(self):
        pass


@pytest.fixture
def fake_psi(monkeypatch):
    FakeHttp.calls = []
    monkeypatch.setattr(pagespeed.httpx, "Client", FakeHttp)
    return FakeHttp


# ---------------------------------------------------------------- the page


def test_the_page_renders() -> None:
    response = client.get("/performance")
    assert response.status_code == 200
    assert 'id="performance-root"' in response.text
    assert "/performance.js" in response.text


def test_the_page_says_there_is_no_ai_in_it() -> None:
    body = client.get("/performance").text
    assert "No AI" in body


# ---------------------------------------------------------------- the budget


def test_the_budget_route_reads_the_number_out_of_the_criterion() -> None:
    response = client.post("/performance/budget", json={"criteria": NAV_CRITERIA})
    assert response.status_code == 200
    body = response.text
    assert "Interaction to next paint (INP)" in body
    assert "200 ms" in body
    assert "AC-2" in body
    assert "within 200ms" in body


def test_the_budget_route_shows_the_custom_line_and_who_covers_it() -> None:
    cases = [
        {
            "id": "TC-004",
            "title": "The bar collapses below 768 px",
            "category": "Boundary",
            "pre_conditions": "A signed-in user",
            "steps": ["Resize to 767 px"],
            "expected_result": "The bar collapses",
            "priority": "High",
            "automation_feasibility": "High",
            "automation_effort": "Low",
            "tags": [],
            "traceability": "AC-4",
        }
    ]
    body = client.post(
        "/performance/budget", json={"criteria": NAV_CRITERIA, "cases": cases}
    ).text
    assert "Layout at 768 px" in body
    assert "not measurable" in body
    assert "use TC-004" in body


def test_a_run_with_no_criteria_still_gets_the_default_budget() -> None:
    body = client.post("/performance/budget", json={"criteria": []}).text
    assert "Largest contentful paint (LCP)" in body
    assert "Core Web Vitals" in body
    assert "not measured" in body


def test_the_budget_route_lists_a_performance_risk_with_no_number_as_a_gap() -> None:
    risk = {
        "failure_modes": [
            {
                "id": "R1",
                "title": "Race condition on rapid double-clicking",
                "category": "performance",
                "effect": "Two modules render at once",
                "cause": "The updates are not ordered",
                "severity": 3,
                "likelihood": 4,
                "detectability": 4,
                "related_criteria": [],
                "covered_by": [],
                "test_idea": "Click twice quickly",
            }
        ]
    }
    body = client.post(
        "/performance/budget", json={"criteria": NAV_CRITERIA, "risk_analysis": risk}
    ).text
    assert "is a performance risk with no target" in body


# --------------------------------------------------------------- measuring


def test_a_private_url_is_refused_without_calling_google(fake_psi) -> None:
    response = client.post(
        "/performance/measure",
        json={"criteria": [], "url": "http://localhost:8000", "strategy": "mobile"},
    )
    assert response.status_code == 200
    assert "can only measure public pages" in response.text
    assert "k6 export" in response.text
    assert fake_psi.calls == []


@pytest.mark.parametrize(
    "url", ["http://192.168.1.5/", "http://10.0.0.2/", "ftp://example.com", "javascript:alert(1)"]
)
def test_every_refused_url_shape_stops_before_the_network(fake_psi, url) -> None:
    client.post("/performance/measure", json={"criteria": [], "url": url})
    assert fake_psi.calls == []


def test_a_public_url_is_measured_and_compared(fake_psi) -> None:
    response = client.post(
        "/performance/measure",
        json={"criteria": NAV_CRITERIA, "url": PAGE, "strategy": "mobile"},
    )
    assert response.status_code == 200
    body = response.text
    assert '<span class="pill bad">over</span>' in body
    assert '<span class="pill ok">within</span>' in body
    assert "PageSpeed score 62" in body
    # One call, to Google, carrying the page as a parameter.
    assert len(fake_psi.calls) == 1
    url, params = fake_psi.calls[0]
    assert url == PSI_URL
    assert params["url"] == PAGE
    assert params["strategy"] == "MOBILE"


def test_the_strategy_reaches_google(fake_psi) -> None:
    client.post(
        "/performance/measure",
        json={"criteria": [], "url": PAGE, "strategy": "desktop"},
    )
    assert fake_psi.calls[0][1]["strategy"] == "DESKTOP"


def test_the_key_is_passed_through_but_never_rendered(fake_psi) -> None:
    key = "AIzaTESTKEYmustnotappear"
    response = client.post(
        "/performance/measure",
        json={"criteria": [], "url": PAGE, "strategy": "mobile", "psi_key": key},
    )
    assert fake_psi.calls[0][1]["key"] == key
    assert key not in response.text


def test_a_pagespeed_failure_becomes_an_error_card(monkeypatch) -> None:
    class Failing(FakeHttp):
        def get(self, url, params=None):
            raise httpx.TimeoutException("too slow")

    monkeypatch.setattr(pagespeed.httpx, "Client", Failing)
    response = client.post(
        "/performance/measure", json={"criteria": [], "url": PAGE}
    )
    assert response.status_code == 200
    assert "PageSpeed took too long" in response.text


def test_a_rate_limit_without_a_key_explains_the_key(monkeypatch) -> None:
    class Limited(FakeHttp):
        def get(self, url, params=None):
            return httpx.Response(
                429, json={"error": {"code": 429}}, request=httpx.Request("GET", url)
            )

    monkeypatch.setattr(pagespeed.httpx, "Client", Limited)
    body = client.post("/performance/measure", json={"criteria": [], "url": PAGE}).text
    assert "free Google API key" in body


# ---------------------------------------------------------------- example


def test_the_example_renders_without_touching_the_network(fake_psi) -> None:
    response = client.get("/performance/example")
    assert response.status_code == 200
    assert fake_psi.calls == []
    body = response.text
    assert '<span class="pill bad">over</span>' in body
    assert "Layout at 768 px" in body
    assert "is a performance risk with no target" in body
    assert "use TC-004, TC-007" in body


def test_the_example_names_no_real_company() -> None:
    body = client.get("/performance/example").text
    assert "aurora-storefront.example" in body


# ----------------------------------------------------------------- exports


def test_the_lighthouse_export_downloads_as_json() -> None:
    response = client.post(
        "/performance/export/lighthouse", json={"criteria": NAV_CRITERIA}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "budget.json" in response.headers["content-disposition"]
    document = json.loads(response.text)
    found = {row["metric"]: row["budget"] for row in document[0]["timings"]}
    assert found["total-blocking-time"] == 200.0


def test_the_k6_export_downloads_as_javascript() -> None:
    response = client.post("/performance/export/k6", json={"criteria": NAV_CRITERIA})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert "k6-thresholds.js" in response.headers["content-disposition"]
    assert "http_req_duration" in response.text


def test_a_body_the_browser_got_wrong_is_refused_rather_than_guessed() -> None:
    response = client.post("/performance/budget", json={"criteria": "not a list"})
    assert response.status_code == 422
