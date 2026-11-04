"""The door: real JSON-RPC over HTTP, every error path, the limits and the flag.

We hand-wrote this transport rather than mounting the SDK's own app
(docs/decisions/001-mcp-transport.md), which means protocol correctness is
ours to keep. These tests are how we keep it: the first block drives the
server with the SDK's *own client*, so a shape we got wrong fails here
rather than in somebody's Claude Code session.
"""

import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from qagenius.mcp_server import transport
from qagenius.mcp_server.schemas import MAX_CRITERIA, MAX_RISKS, MAX_TESTS
from qagenius.mcp_server.transport import RateLimit, field_path, spoken_version
from qagenius.web import app

HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}
STORY = "As a shopper I want the cart to update quickly so that I can check out"



@pytest.fixture(autouse=True)
def door_open(monkeypatch):
    """Every test here wants the door open and the rate limit fresh."""
    monkeypatch.setenv("QAG_MCP_ENABLED", "1")
    monkeypatch.setattr(transport, "limiter", RateLimit())


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def rpc(client, method, params=None, request_id=1):
    body = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        body["id"] = request_id
    if params is not None:
        body["params"] = params
    return client.post("/mcp", headers=HEADERS, json=body)


def tool_call(client, name, arguments, request_id=1):
    return rpc(client, "tools/call", {"name": name, "arguments": arguments}, request_id)


def said(response) -> str:
    """The text of a tool error, which is where a tool says no."""
    return response.json()["result"]["content"][0]["text"]


# ──────────────────────────────────────────────────────────────────────────────
# Raw JSON-RPC over HTTP
# ──────────────────────────────────────────────────────────────────────────────


def test_initialize_answers_json_with_the_server_and_its_instructions(client):
    response = rpc(
        client,
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "t", "version": "0"},
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    result = response.json()["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert result["serverInfo"]["name"] == "QA-Genius"
    assert result["capabilities"]["tools"] == {"listChanged": False}
    assert result["instructions"]


def test_an_unknown_protocol_version_gets_the_newest_one_we_speak():
    assert spoken_version("2025-06-18") == "2025-06-18"
    assert spoken_version("tomorrow") != "tomorrow"
    assert spoken_version("") != ""


def test_the_initialized_notification_is_accepted_and_answers_nothing(client):
    response = client.post(
        "/mcp", headers=HEADERS, json={"jsonrpc": "2.0", "method": "notifications/initialized"}
    )
    assert response.status_code == 202
    assert response.content == b""


def test_ping_answers_an_empty_result(client):
    assert rpc(client, "ping").json() == {"jsonrpc": "2.0", "id": 1, "result": {}}


def test_tools_list_names_six_read_only_tools(client):
    tools = rpc(client, "tools/list", {}).json()["result"]["tools"]
    assert [tool["name"] for tool in tools] == [
        "check_story",
        "review_tests",
        "score_risks",
        "plan_matrix",
        "check_code",
        "ship_check",
    ]
    for tool in tools:
        assert tool["annotations"] == {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }
        # The description is the only instruction an agent gets about when
        # to reach for this tool, so it has to say when and show one.
        assert "Use it" in tool["description"]
        assert "Example" in tool["description"]


def test_a_tool_call_answers_both_structured_and_text(client):
    result = tool_call(client, "check_story", {"story": STORY}).json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["tool"] == "check_story"
    assert result["content"][0]["type"] == "text"
    assert "structuredContent" in result["content"][0]["text"]


def test_the_answer_is_never_cached(client):
    assert rpc(client, "ping").headers["cache-control"] == "no-store"


def test_the_door_sends_no_cors_header(client):
    # An MCP client calls this from its own server. A header inviting a web
    # page to call it would be a wider door than anybody asked for.
    response = rpc(client, "ping")
    assert "access-control-allow-origin" not in response.headers


def test_the_door_gets_an_api_policy_not_the_page_policy(client):
    policy = rpc(client, "ping").headers["content-security-policy"]
    assert policy == "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


def test_the_page_policy_is_untouched(client):
    policy = client.get("/").headers["content-security-policy"]
    assert "script-src 'self' 'nonce-" in policy


def test_a_get_is_told_to_post_instead(client):
    response = client.get("/mcp")
    assert response.status_code == 405
    assert response.headers["allow"] == "POST"


# ──────────────────────────────────────────────────────────────────────────────
# Errors
# ──────────────────────────────────────────────────────────────────────────────


def test_a_wrong_shape_names_the_field_path(client):
    response = tool_call(
        client,
        "review_tests",
        {
            "story": "s",
            "criteria": [{"text": "a"}],
            "test_cases": [
                {"id": "TC-1", "title": "t", "steps": ["a"], "expected": "b"},
                {"id": "TC-2", "title": "t", "steps": ["a"], "expected": "b"},
                {"id": "TC-3", "title": "t", "steps": [], "expected": "b"},
            ],
        },
    )
    assert said(response) == "test_cases[2].steps: needs at least one step"
    assert response.json()["result"]["isError"] is True


def test_a_missing_field_says_it_is_required(client):
    assert "story: is required" in said(tool_call(client, "check_story", {}))


def test_a_field_this_tool_does_not_take_says_so(client):
    response = tool_call(client, "check_story", {"story": STORY, "stroy": "x"})
    assert "stroy: is not a field this tool takes" in said(response)


def test_field_path_reads_the_way_an_agent_writes_it():
    assert field_path({"loc": ("test_cases", 2, "steps")}) == "test_cases[2].steps"
    assert field_path({"loc": ("story",)}) == "story"
    assert field_path({"loc": ()}) == "(the request)"


def test_too_many_tests_is_refused_with_the_number_to_send(client):
    response = tool_call(
        client,
        "review_tests",
        {
            "story": "s",
            "criteria": [{"text": "a"}],
            "test_cases": [
                {"id": f"TC-{n}", "title": "t", "steps": ["a"], "expected": "b"}
                for n in range(MAX_TESTS + 1)
            ],
        },
    )
    assert said(response) == f"Too many tests (412). Send {MAX_TESTS} or fewer."


def test_too_many_criteria_is_refused_the_same_way(client):
    response = tool_call(
        client,
        "review_tests",
        {
            "story": "s",
            "criteria": [{"text": f"c{n}"} for n in range(MAX_CRITERIA + 1)],
            "test_cases": [],
        },
    )
    assert said(response) == f"Too many criteria (412). Send {MAX_CRITERIA} or fewer."


def test_an_oversized_body_is_refused_before_anything_is_parsed(client):
    body = b"x" * (transport.MAX_BODY_BYTES + 1)
    started = time.monotonic()
    response = client.post("/mcp", headers=HEADERS, content=body)
    spent = time.monotonic() - started
    assert response.status_code == 413
    assert response.json()["error"]["message"] == transport.BODY_TOO_BIG
    assert spent < 0.05, f"took {spent * 1000:.0f} ms to refuse 1 MB"


def test_a_body_that_claims_to_be_enormous_is_refused_unread(client):
    # The header is checked first, so a caller announcing a gigabyte never
    # gets a gigabyte read into this process.
    response = client.post(
        "/mcp",
        headers={**HEADERS, "Content-Length": str(10**9)},
        content=b'{"jsonrpc":"2.0","id":1,"method":"ping"}',
    )
    assert response.status_code == 413
    assert response.json()["error"]["message"] == transport.BODY_TOO_BIG


def test_a_body_that_is_not_json_says_so(client):
    response = client.post("/mcp", headers=HEADERS, content=b"{not json")
    assert response.json()["error"]["message"] == "That is not JSON."


def test_a_batch_is_refused_in_one_sentence(client):
    response = client.post("/mcp", headers=HEADERS, json=[{"jsonrpc": "2.0"}])
    assert "one call at a time" in response.json()["error"]["message"]


def test_an_unknown_method_names_what_was_asked_for(client):
    assert "'wat'" in rpc(client, "wat").json()["error"]["message"]


def test_an_unknown_tool_lists_the_ones_there_are(client):
    message = said(tool_call(client, "nope", {}))
    assert "check_story" in message and "review_tests" in message


def test_a_call_with_no_tool_name_says_name_is_required(client):
    response = rpc(client, "tools/call", {"arguments": {}})
    assert response.json()["error"]["message"] == "name: is required"


def test_our_own_bug_answers_a_reference_and_never_a_stack_trace(
    client, monkeypatch, caplog
):
    def explode(_payload, _host=""):
        raise RuntimeError("the story was: a secret the log must never hold")

    monkeypatch.setattr(transport.server.BY_NAME["check_story"], "run", explode)
    with caplog.at_level("ERROR"):
        response = tool_call(client, "check_story", {"story": STORY})

    message = said(response)
    assert message.startswith("Something went wrong on our side (ref ")
    assert "Traceback" not in message and "RuntimeError" not in message
    # The reference in the answer is the one in the log.
    ref = message.split("ref ")[1].rstrip(").")
    assert any(ref in record.getMessage() for record in caplog.records)


def test_a_call_that_runs_over_the_budget_is_cut_off(client, monkeypatch):
    def forever(_payload, _host=""):
        time.sleep(transport.TIME_BUDGET_SECONDS + 1)

    monkeypatch.setattr(transport, "TIME_BUDGET_SECONDS", 0.05)
    monkeypatch.setattr(transport.server.BY_NAME["check_story"], "run", forever)
    started = time.monotonic()
    response = tool_call(client, "check_story", {"story": STORY})
    spent = time.monotonic() - started
    assert said(response) == transport.TOO_SLOW
    assert spent < 1.0, "the caller waited for the whole of the work"


# ──────────────────────────────────────────────────────────────────────────────
# The rate limit
# ──────────────────────────────────────────────────────────────────────────────


def test_one_address_is_held_to_the_limit():
    limiter = RateLimit(calls=3, window=60)
    assert [limiter.allows("1.2.3.4", now=0.0) for _ in range(4)] == [
        True,
        True,
        True,
        False,
    ]


def test_another_address_is_counted_on_its_own():
    limiter = RateLimit(calls=1, window=60)
    assert limiter.allows("1.2.3.4", now=0.0)
    assert limiter.allows("5.6.7.8", now=0.0)
    assert not limiter.allows("1.2.3.4", now=0.0)


def test_the_window_moves_on():
    limiter = RateLimit(calls=1, window=60)
    assert limiter.allows("1.2.3.4", now=0.0)
    assert not limiter.allows("1.2.3.4", now=59.0)
    assert limiter.allows("1.2.3.4", now=60.0)


def test_a_client_that_goes_quiet_is_forgotten():
    limiter = RateLimit(calls=5, window=60)
    limiter.allows("1.2.3.4", now=0.0)
    limiter.allows("1.2.3.4", now=100.0)
    assert len(limiter._seen["1.2.3.4"]) == 1


def test_the_route_answers_429_once_the_limit_is_reached(client, monkeypatch):
    monkeypatch.setattr(transport, "limiter", RateLimit(calls=2, window=60))
    assert rpc(client, "ping").status_code == 200
    assert rpc(client, "ping").status_code == 200
    response = rpc(client, "ping")
    assert response.status_code == 429
    assert "60 calls a minute" in response.json()["error"]["message"]


def test_a_forwarded_address_is_the_one_counted():
    class FakeRequest:
        headers = {"x-forwarded-for": "9.9.9.9, 10.0.0.1"}
        client = None

    assert transport.caller(FakeRequest()) == "9.9.9.9"


# ──────────────────────────────────────────────────────────────────────────────
# The flag
# ──────────────────────────────────────────────────────────────────────────────


def test_the_flag_off_makes_the_door_a_404(client, monkeypatch):
    monkeypatch.setenv("QAG_MCP_ENABLED", "0")
    assert rpc(client, "ping").status_code == 404
    assert client.get("/mcp").status_code == 404


def test_production_is_off_until_the_owner_says_otherwise(monkeypatch):
    monkeypatch.delenv("QAG_MCP_ENABLED", raising=False)
    monkeypatch.setenv("VERCEL_ENV", "production")
    assert transport.enabled() is False


def test_a_preview_is_on(monkeypatch):
    monkeypatch.delenv("QAG_MCP_ENABLED", raising=False)
    monkeypatch.setenv("VERCEL_ENV", "preview")
    assert transport.enabled() is True


def test_the_flag_beats_the_environment(monkeypatch):
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("QAG_MCP_ENABLED", "true")
    assert transport.enabled() is True


def test_the_flag_is_read_on_every_call_not_once_at_import(monkeypatch):
    monkeypatch.setenv("QAG_MCP_ENABLED", "1")
    assert transport.enabled() is True
    monkeypatch.setenv("QAG_MCP_ENABLED", "0")
    assert transport.enabled() is False


def test_the_rest_of_the_site_does_not_care_about_the_flag(client, monkeypatch):
    monkeypatch.setenv("QAG_MCP_ENABLED", "0")
    assert client.get("/").status_code == 200
    assert client.get("/health").status_code == 200


# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────


def test_one_line_per_call_with_counts_and_no_content(client, caplog):
    secret = "the shopper's name is a thing no log may hold"
    with caplog.at_level("INFO", logger="qagenius.mcp"):
        tool_call(
            client,
            "review_tests",
            {
                "story": secret,
                "criteria": [{"text": "a"}, {"text": "b"}],
                "test_cases": [
                    {"id": "TC-1", "title": "t", "steps": ["a"], "expected": "b"}
                ],
            },
        )
    lines = [r.getMessage() for r in caplog.records if r.name == "qagenius.mcp"]
    assert len(lines) == 1
    line = lines[0]
    assert line.startswith("mcp tool=review_tests ms=")
    assert "criteria=2" in line and "tests=1" in line and "problems=" in line
    assert line.endswith("status=ok")
    assert secret not in line


def test_a_refused_call_is_logged_without_what_was_sent(client, caplog):
    secret = "a sentence that must not reach a log file"
    with caplog.at_level("INFO", logger="qagenius.mcp"):
        tool_call(client, "check_story", {"story": secret, "nope": 1})
    lines = [r.getMessage() for r in caplog.records if r.name == "qagenius.mcp"]
    assert lines and lines[0].endswith("status=bad_input")
    assert all(secret not in line for line in lines)


def test_no_input_text_reaches_any_log_anywhere(client, caplog):
    secret = "Aurora Storefront coupons expire on a Tuesday"
    with caplog.at_level("DEBUG"):
        tool_call(client, "check_story", {"story": secret})
    assert all(secret not in record.getMessage() for record in caplog.records)


# ──────────────────────────────────────────────────────────────────────────────
# Determinism and speed
# ──────────────────────────────────────────────────────────────────────────────


def _big_call() -> dict:
    """A call at the published limits: 60 criteria, 300 tests."""
    return {
        "story": "As a shopper I want to check out so that I can pay. " * 20,
        "context": "Aurora Storefront checkout. Orders of at least $50 ship free.",
        "criteria": [
            {"text": f"The checkout step {n} finishes within 2 seconds"}
            for n in range(MAX_CRITERIA)
        ],
        "test_cases": [
            {
                "id": f"TC-{n:03d}",
                "title": f"Checkout step {n % MAX_CRITERIA} finishes in time",
                "steps": ["Open the cart", "Press Continue", "Read the next page"],
                "expected": f"Step {n % MAX_CRITERIA} is shown within 2 seconds",
                "test_data": "cart_total=$60.00",
                "covers": [f"AC-{(n % MAX_CRITERIA) + 1}"],
                "kind": "normal",
            }
            for n in range(MAX_TESTS)
        ],
    }


def test_the_same_call_twice_gives_byte_identical_output(client):
    arguments = {"story": STORY}
    first = tool_call(client, "check_story", arguments).json()["result"]
    second = tool_call(client, "check_story", arguments).json()["result"]
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_review_tests_is_byte_identical_twice_at_the_limits(client):
    arguments = _big_call()
    first = tool_call(client, "review_tests", arguments).json()["result"]
    second = tool_call(client, "review_tests", arguments).json()["result"]
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_ship_check_is_byte_identical_twice(client):
    arguments = _big_call()
    first = tool_call(client, "ship_check", arguments).json()["result"]
    second = tool_call(client, "ship_check", arguments).json()["result"]
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


# Every tool, in the order tools/list gives them.
TOOL_NAMES = (
    "check_story",
    "review_tests",
    "score_risks",
    "plan_matrix",
    "check_code",
    "ship_check",
)

# A file big enough to be a real one: 30 files is the published limit.
_SPEC = """import { test, expect } from '@playwright/test';

test('TC-%03d something worth checking', async ({ page }) => {
  await page.goto('/cart');
  await expect(page.getByText('Total')).toBeVisible();
});
"""


def _at_the_limits(name: str) -> dict:
    """One call at whatever this tool's published limits are."""
    big = _big_call()
    if name == "check_story":
        return {"story": big["story"], "context": big["context"]}
    if name == "score_risks":
        return {
            **big,
            "risks": [
                {
                    "id": f"R{n}",
                    "title": f"Failure number {n} in the checkout path",
                    "effect": "The shopper is charged the wrong amount",
                    "cause": "Two requests race before either is recorded",
                    "category": "data",
                    "how_bad": 4,
                    "how_likely": 3,
                    "how_hard_to_notice": 4,
                }
                for n in range(1, MAX_RISKS + 1)
            ],
        }
    if name == "plan_matrix":
        return {
            "factors": [
                {"name": f"Factor {n}", "options": [f"Option {m}" for m in range(8)]}
                for n in range(8)
            ]
        }
    if name == "check_code":
        return {
            "framework": "playwright-ts",
            "files": [
                {"path": f"tests/spec-{n:02d}.spec.ts", "content": _SPEC % n}
                for n in range(30)
            ],
            "test_cases": big["test_cases"],
        }
    return big


@pytest.mark.parametrize("name", list(TOOL_NAMES))
def test_every_tool_answers_inside_300ms_at_the_published_limits(name):
    from qagenius.mcp_server.transport import call_tool

    arguments = _at_the_limits(name)
    call_tool(name, arguments)  # warm the rule packs, which are cached
    started = time.monotonic()
    call_tool(name, arguments)
    spent = (time.monotonic() - started) * 1000
    assert spent < 300, f"{name} took {spent:.0f} ms at the limits"


def test_the_environment_the_suite_runs_in_leaves_the_door_open():
    # Nothing above is proving anything if the flag defaults to off here.
    assert "VERCEL_ENV" not in os.environ or transport.enabled()
