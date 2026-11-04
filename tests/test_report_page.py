"""The /report page: served empty, filled in the browser, never stored.

The whole point of this page is what it does *not* do. The data lives
after the `#`, which a browser does not send, so these tests guard that
the server neither needs it nor could keep it if it wanted to.
"""

import pytest
from fastapi.testclient import TestClient

from qagenius.mcp_server import report_link, tools
from qagenius.mcp_server.schemas import TestsIn
from qagenius.web import app

HOST = "testserver"

SUITE = {
    "story": "As a shopper I want to apply a coupon so that I pay less.",
    "context": "Coupons need an order of at least $50.",
    "criteria": [{"text": "A coupon on a cart over $50 applies the discount"}],
    "test_cases": [
        {
            "id": "TC-1",
            "title": "A valid coupon on a cart over the minimum",
            "steps": ["Put $60.00 in the cart", "Enter a valid coupon"],
            "expected": "The total drops by the discount",
            "test_data": "cart_total=$60.00",
            "covers": ["AC-1"],
        }
    ],
}


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_the_page_is_served(client):
    response = client.get("/report")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_the_page_arrives_empty_and_says_so(client):
    body = client.get("/report").text
    assert 'id="report-root"' in body
    assert "Reading the report from the link" in body
    # Nothing of any report is in what the server sent.
    assert "TC-1" not in body


def test_the_page_loads_the_script_that_fills_it(client):
    assert '/report.js' in client.get("/report").text


def test_a_report_link_opens_the_page(client):
    answer = tools.review_tests(TestsIn.model_validate(SUITE), HOST)
    assert answer.report_link.startswith(f"https://{HOST}/report#")
    # The browser keeps the fragment; only the path reaches us.
    path = answer.report_link.partition(f"https://{HOST}")[2].partition("#")[0]
    assert path == "/report"
    assert client.get(path).status_code == 200


def test_the_fragment_is_never_sent_to_the_server(client):
    # httpx strips it the way a browser does. If this ever changed, the
    # promise this whole page is built on would be broken.
    answer = tools.review_tests(TestsIn.model_validate(SUITE), HOST)
    response = client.get(answer.report_link.partition(f"https://{HOST}")[2])
    assert response.status_code == 200
    assert "TC-1" not in response.text


def test_what_the_link_holds_is_what_the_page_will_draw():
    answer = tools.review_tests(TestsIn.model_validate(SUITE), HOST)
    found = report_link.unpack(answer.report_link)
    assert found["story"] == SUITE["story"]
    assert found["tool"] == "review_tests"
    assert [one["id"] for one in found["problems"]] == [
        one.id for one in answer.problems
    ]
    assert len(found["test_cases"]) == 1


def test_the_page_is_in_the_sites_own_style(client):
    body = client.get("/report").text
    assert "/style.css" in body
    assert 'class="layout"' in body


def test_the_report_page_gets_the_page_policy_not_the_api_one(client):
    # It is a document a person opens, so it needs the page's own script
    # policy — the /mcp lockdown would stop report.js running at all.
    policy = client.get("/report").headers["content-security-policy"]
    assert "script-src 'self' 'nonce-" in policy
