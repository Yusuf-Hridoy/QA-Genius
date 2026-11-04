"""The official MCP client, pointed at our hand-written route.

We serve the protocol ourselves rather than mounting the SDK's own app
(docs/decisions/001-mcp-transport.md), which means protocol correctness is
ours to keep. This is how we keep it: a real `ClientSession` over the
SDK's streamable-HTTP transport, driving this app through an ASGI
transport, doing exactly what Claude Code does — initialize, list, call.

If we get a shape wrong, it fails here rather than in somebody's session.

The whole `mcp` package is a dev dependency; the server itself runs on
`mcp_types` alone. An install from requirements.txt skips this module
rather than failing on it.
"""

import anyio
import pytest

from qagenius.web import app

HOST = "qa.test"
STORY = "As a shopper I want the cart to update quickly so that I can check out"

CRITERIA = [{"text": "The cart total updates within 2 seconds of a change"}]
TESTS = [
    {
        "id": "TC-1",
        "title": "The total updates after an item is added",
        "steps": ["Open the cart", "Add an item", "Read the total"],
        "expected": "The total shows the new amount within 2 seconds",
        "test_data": "items=1",
        "covers": ["AC-1"],
    }
]

try:  # pragma: no cover - whether this imports is the point
    import httpx2
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    HAS_SDK = True
except ImportError:  # pragma: no cover
    HAS_SDK = False

pytestmark = pytest.mark.skipif(
    not HAS_SDK, reason="the mcp SDK is a dev dependency (pip install -e '.[dev]')"
)


@pytest.fixture(autouse=True)
def door_open(monkeypatch):
    monkeypatch.setenv("QAG_MCP_ENABLED", "1")


def with_client(work):
    """Run `work(session)` against this app through the real MCP client."""

    async def main():
        http = httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url=f"http://{HOST}"
        )
        async with http:
            async with streamable_http_client(
                f"http://{HOST}/mcp", http_client=http
            ) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    return await work(session)

    return anyio.run(main)


EXPECTED = (
    "check_story",
    "review_tests",
    "score_risks",
    "plan_matrix",
    "check_code",
    "ship_check",
)


def test_a_real_client_shakes_hands():
    start = with_client(lambda session: session.initialize())
    assert start.server_info.name == "QA-Genius"
    assert start.server_info.version
    assert start.protocol_version
    assert "never tell the user a check passed" in (start.instructions or "").lower()


def test_a_real_client_lists_six_read_only_tools():
    async def work(session):
        await session.initialize()
        return (await session.list_tools()).tools

    tools = with_client(work)
    assert [tool.name for tool in tools] == list(EXPECTED)
    for tool in tools:
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.idempotent_hint is True
        assert tool.annotations.open_world_hint is False
        assert tool.description
        assert tool.input_schema and tool.output_schema


def test_a_real_client_can_call_every_tool():
    calls = {
        "check_story": {"story": STORY},
        "review_tests": {"story": STORY, "criteria": CRITERIA, "test_cases": TESTS},
        "score_risks": {
            "story": STORY,
            "criteria": CRITERIA,
            "test_cases": TESTS,
            "risks": [
                {
                    "id": "R1",
                    "title": "The total is stale after a slow response",
                    "effect": "The shopper pays the wrong amount",
                    "cause": "The page shows the old total while the new one loads",
                    "category": "data",
                    "how_bad": 4,
                    "how_likely": 3,
                    "how_hard_to_notice": 4,
                }
            ],
        },
        "plan_matrix": {
            "factors": [
                {"name": "Browser", "options": ["Chrome", "Safari"]},
                {"name": "Device", "options": ["Desktop", "Phone"]},
            ]
        },
        "check_code": {
            "framework": "playwright-ts",
            "files": [
                {
                    "path": "tests/cart.spec.ts",
                    "content": (
                        "import { test, expect } from '@playwright/test';\n"
                        "test('TC-1 the total updates', async ({ page }) => {\n"
                        "  await page.goto('/cart');\n"
                        "  await expect(page.getByText('Total')).toBeVisible();\n"
                        "});\n"
                    ),
                }
            ],
        },
        "ship_check": {"story": STORY, "criteria": CRITERIA, "test_cases": TESTS},
    }

    async def work(session):
        await session.initialize()
        found = {}
        for name, arguments in calls.items():
            found[name] = await session.call_tool(name, arguments)
        return found

    answers = with_client(work)
    assert set(answers) == set(EXPECTED)
    for name, answer in answers.items():
        assert answer.is_error is False, name
        assert answer.structured_content["tool"] == name, name
        assert answer.structured_content["summary"], name
        assert answer.content[0].text, name


def test_a_real_client_sees_the_tool_error_not_an_exception():
    # A wrong shape is a tool error the client reads, never a transport
    # failure that kills the session.
    async def work(session):
        await session.initialize()
        bad = await session.call_tool(
            "review_tests",
            {
                "story": STORY,
                "criteria": CRITERIA,
                "test_cases": [{"id": "TC-1", "title": "x", "steps": [], "expected": "y"}],
            },
        )
        # ... and the session still works afterwards.
        good = await session.call_tool("check_story", {"story": STORY})
        return bad, good

    bad, good = with_client(work)
    assert bad.is_error is True
    assert "steps: needs at least one step" in bad.content[0].text
    assert good.is_error is False


def test_a_real_client_gets_a_report_link_it_can_hand_over():
    async def work(session):
        await session.initialize()
        return await session.call_tool("check_story", {"story": STORY})

    answer = with_client(work)
    link = answer.structured_content["report_link"]
    # https, because qa.test is not a machine somebody is sitting at. Only
    # localhost gets a plain http link, and for the obvious reason.
    assert link.startswith(f"https://{HOST}/report#v1.")
