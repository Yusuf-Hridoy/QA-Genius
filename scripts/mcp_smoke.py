"""Act like a real MCP client and walk a whole story through the door.

This is the test that cannot be faked by a unit test: it speaks JSON-RPC
over HTTP, in order, the way Claude Code does, and checks the answers are
the ones a person would want.

    python scripts/mcp_smoke.py                       # starts the app itself
    python scripts/mcp_smoke.py --url http://127.0.0.1:8000
    python scripts/mcp_smoke.py --url https://qa-genius-ashy.vercel.app

Exits non-zero on any failure, so CI can run it as it stands.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# The table has "·" and "→" in it, and a Windows console is cp1252 by
# default. Say so rather than dying halfway through printing the results.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL = "2025-06-18"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}
TOOLS = (
    "check_story",
    "review_tests",
    "score_risks",
    "plan_matrix",
    "check_code",
    "ship_check",
)
START_TIMEOUT = 30.0


# ──────────────────────────────────────────────────────────────────────────────
# The story this walks through
# ──────────────────────────────────────────────────────────────────────────────

STORY = (
    "As a shopper, I want to apply a discount coupon at checkout so that I "
    "pay less for my order."
)
CONTEXT = (
    "Aurora Storefront checkout. Coupons give a percentage off the order "
    "total, up to a maximum discount of $30. A coupon works only on orders "
    "of at least $50. One coupon per order."
)
CRITERIA = [
    {
        "text": "Given a cart of more than $50.00, when a valid coupon is "
        "entered, then the discount is applied"
    },
    {
        "text": "Given a cart of less than $50.00, when a valid coupon is "
        "entered, then the coupon is refused"
    },
    {
        "text": "Given a coupon gives 20% off, when the order total is $200, "
        "then the discount is $30, not $40"
    },
]
TESTS = [
    {
        "id": "TC-01",
        "title": "A valid coupon on a cart over the minimum",
        "steps": ["Put $60.00 of items in the cart", "Enter a valid coupon code"],
        "expected": "The order total drops by the discount and the new total is shown",
        "test_data": "cart_total=$60.00",
        "covers": ["AC-1"],
    },
    {
        "id": "TC-02",
        "title": "A valid coupon on a cart under the minimum",
        "steps": ["Put $40.00 of items in the cart", "Enter a valid coupon code"],
        "expected": "The page shows: This coupon needs an order of at least $50.",
        "test_data": "cart_total=$40.00",
        "covers": ["AC-2"],
        "kind": "wrong input",
    },
    {
        "id": "TC-03",
        "title": "The discount stops at the cap",
        "steps": ["Put $200.00 of items in the cart", "Enter a coupon for 20% off"],
        "expected": "The discount is $30.00, not $40.00",
        "test_data": "cart_total=$200.00; coupon=20%",
        "covers": ["AC-3"],
        "kind": "at the limit",
    },
]
# The criteria, with the $50 argument settled the way the product owner
# would settle it, plus the test nobody had written.
FIXED_CRITERIA = [
    {
        "text": "Given a cart of at least $50.00, when a valid coupon is "
        "entered, then the discount is applied"
    },
    {
        "text": "Given a cart of under $50.00, when a valid coupon is "
        "entered, then the coupon is refused"
    },
    CRITERIA[2],
]
RISKS = [
    {
        "id": "R1",
        "title": "The same coupon is applied twice at the same moment",
        "effect": "The shop gives double the discount and loses the money",
        "cause": "Two checkout requests race before either is recorded",
        "category": "data",
        "how_bad": 5,
        "how_likely": 3,
        "how_hard_to_notice": 4,
        "linked_criteria": ["AC-1"],
    },
    {
        "id": "R2",
        "title": "The discount is rounded the wrong way",
        "effect": "Order totals are a cent out",
        "cause": "Floating point arithmetic on money",
        "category": "data",
        "how_bad": 2,
        "how_likely": 2,
        "how_hard_to_notice": 3,
    },
]
SPEC = """import { test, expect } from '@playwright/test';

test.only('TC-01 a valid coupon on a cart over the minimum', async ({ page }) => {
  await page.goto('/cart');
  await page.fill('#coupon', 'SPRING20');
  await expect(page.getByText('Discount applied')).toBeVisible();
});
"""


# ──────────────────────────────────────────────────────────────────────────────
# Talking to the door
# ──────────────────────────────────────────────────────────────────────────────


class Door:
    """One MCP connection, counting its own calls."""

    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/")
        self.next_id = 0

    def call(self, method: str, params: dict | None = None, notify: bool = False):
        body = {"jsonrpc": "2.0", "method": method}
        if not notify:
            self.next_id += 1
            body["id"] = self.next_id
        if params is not None:
            body["params"] = params
        request = Request(
            self.url,
            data=json.dumps(body).encode("utf-8"),
            headers=HEADERS,
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read()
                status = response.status
        except HTTPError as bad:
            raw, status = bad.read(), bad.code
        except URLError as bad:
            raise RuntimeError(f"cannot reach {self.url}: {bad.reason}") from bad
        if notify:
            return status, None
        return status, json.loads(raw) if raw else None

    def tool(self, name: str, arguments: dict) -> dict:
        """One tools/call, unwrapped to the structured answer."""
        status, body = self.call("tools/call", {"name": name, "arguments": arguments})
        if status != 200 or not body or "result" not in body:
            raise RuntimeError(f"{name}: HTTP {status} {str(body)[:200]}")
        result = body["result"]
        if result.get("isError"):
            text = (result.get("content") or [{}])[0].get("text", "")
            raise RuntimeError(f"{name} refused: {text}")
        found = result.get("structuredContent")
        if not isinstance(found, dict):
            raise RuntimeError(f"{name}: no structuredContent")
        return found


def get(url: str) -> int:
    try:
        with urlopen(Request(url, method="GET"), timeout=30) as response:
            return response.status
    except HTTPError as bad:
        return bad.code
    except URLError:
        return 0


# ──────────────────────────────────────────────────────────────────────────────
# The run
# ──────────────────────────────────────────────────────────────────────────────


class Results:
    """A pass/fail table that prints itself."""

    def __init__(self) -> None:
        self.rows: list[tuple[bool, str, str]] = []

    def check(self, ok: bool, step: str, said: str = "") -> bool:
        self.rows.append((bool(ok), step, said))
        return bool(ok)

    def failed(self) -> int:
        return sum(1 for ok, _, _ in self.rows if not ok)

    def show(self) -> None:
        width = max((len(step) for _, step, _ in self.rows), default=10)
        print()
        print("  " + "RESULT".ljust(7) + "STEP".ljust(width + 2) + "WHAT CAME BACK")
        print("  " + "-" * (7 + width + 2 + 40))
        for ok, step, said in self.rows:
            mark = "pass" if ok else "FAIL"
            print("  " + mark.ljust(7) + step.ljust(width + 2) + said)
        print()
        bad = self.failed()
        total = len(self.rows)
        if bad:
            print(f"  {bad} of {total} checks failed.")
        else:
            print(f"  All {total} checks passed.")


def walk(url: str, results: Results) -> None:
    door = Door(url + "/mcp")

    # ── the handshake ────────────────────────────────────────────────────
    status, body = door.call(
        "initialize",
        {
            "protocolVersion": PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "mcp_smoke", "version": "1"},
        },
    )
    start = (body or {}).get("result") or {}
    results.check(
        status == 200 and start.get("serverInfo", {}).get("name") == "QA-Genius",
        "initialize",
        f"{start.get('serverInfo', {}).get('name')} "
        f"{start.get('serverInfo', {}).get('version')} · "
        f"protocol {start.get('protocolVersion')}",
    )
    results.check(
        bool(start.get("instructions")),
        "instructions",
        f"{len(start.get('instructions') or '')} characters",
    )

    status, _ = door.call("notifications/initialized", notify=True)
    results.check(status == 202, "initialized", f"HTTP {status}")

    # ── the tools ────────────────────────────────────────────────────────
    status, body = door.call("tools/list", {})
    tools = ((body or {}).get("result") or {}).get("tools") or []
    names = [tool.get("name") for tool in tools]
    results.check(
        names == list(TOOLS), "tools/list", f"{len(names)}: {', '.join(names)}"
    )
    read_only = all(
        (tool.get("annotations") or {}).get("readOnlyHint") is True for tool in tools
    )
    results.check(read_only, "read-only", "every tool is annotated read-only")

    # ── 1. the story ─────────────────────────────────────────────────────
    story = door.tool("check_story", {"story": STORY, "context": CONTEXT})
    results.check(
        story.get("tool") == "check_story" and "summary" in story,
        "check_story",
        story.get("summary", ""),
    )

    # ── 2. the tests, as first written ───────────────────────────────────
    first = door.tool(
        "review_tests",
        {
            "story": STORY,
            "context": CONTEXT,
            "criteria": CRITERIA,
            "test_cases": TESTS,
            "story_label": "AUR-14",
        },
    )
    said = " ".join(
        [first.get("summary", ""), *first.get("ask_the_po", [])]
        + [one.get("says", "") for one in first.get("problems", [])]
    )
    results.check(
        "exactly $50" in said,
        "review_tests · $50 gap",
        "nobody decided what happens at exactly $50",
    )
    results.check(
        'context says "at least $50"' in said,
        "review_tests · context vs AC-1",
        "the context and AC-1 disagree",
    )
    link = first.get("report_link", "")
    results.check(
        link.startswith(url) and "/report#v1." in link,
        "report_link",
        f"{len(link)} characters",
    )

    # ── 3. the same tests, with the argument settled ─────────────────────
    second = door.tool(
        "review_tests",
        {
            "story": STORY,
            "context": CONTEXT,
            "criteria": FIXED_CRITERIA,
            "test_cases": TESTS + first.get("add_tests", [])[:4],
            "previous_report_link": link,
            "story_label": "AUR-14",
        },
    )
    fixed = second.get("fixed_since_last_check") or []
    results.check(
        bool(fixed),
        "round tracking",
        f"{len(fixed)} fixed since the last check: {', '.join(fixed[:4])}",
    )

    # ── 4. the risks ─────────────────────────────────────────────────────
    risks = door.tool(
        "score_risks",
        {
            "story": STORY,
            "context": CONTEXT,
            "criteria": FIXED_CRITERIA,
            "test_cases": TESTS,
            "risks": RISKS,
            "previous_report_link": second.get("report_link", ""),
        },
    )
    scored = risks.get("risks") or []
    results.check(
        len(scored) == len(RISKS) and all(one.get("score") for one in scored),
        "score_risks",
        risks.get("summary", ""),
    )
    results.check(
        bool(risks.get("untested_high")),
        "score_risks · untested high",
        f"{', '.join(risks.get('untested_high') or [])} has no test",
    )

    # ── 5. the matrix ────────────────────────────────────────────────────
    matrix = door.tool(
        "plan_matrix",
        {
            "factors": [
                {"name": "Browser", "options": ["Chrome", "Firefox", "Safari", "Edge"]},
                {"name": "Device", "options": ["Desktop", "Tablet", "Phone"]},
                {"name": "Signed in", "options": ["Yes", "No"]},
            ],
            "rules": [
                {
                    "a": "Browser=Firefox",
                    "b": "Device=Phone",
                    "reason": "Playwright cannot emulate Firefox on mobile.",
                }
            ],
        },
    )
    results.check(
        matrix.get("pairs_covered") == matrix.get("pairs_possible")
        and bool(matrix.get("runs")),
        "plan_matrix",
        matrix.get("summary", ""),
    )

    # ── 6. the code ──────────────────────────────────────────────────────
    code = door.tool(
        "check_code",
        {
            "framework": "playwright-ts",
            "files": [{"path": "tests/coupon.spec.ts", "content": SPEC}],
            "test_cases": TESTS,
        },
    )
    only = [
        one for one in code.get("findings", []) if ".only" in str(one.get("says", ""))
    ]
    results.check(
        bool(only),
        "check_code · .only",
        only[0]["says"] if only else "the leftover .only was not found",
    )

    # ── 7. the decision ──────────────────────────────────────────────────
    ship = door.tool(
        "ship_check",
        {
            "story": STORY,
            "context": CONTEXT,
            "criteria": FIXED_CRITERIA,
            "test_cases": TESTS,
            "risks": RISKS,
            "previous_report_link": risks.get("report_link", ""),
            "story_label": "AUR-14",
        },
    )
    results.check(
        bool(ship.get("decision")) and bool(ship.get("checks")),
        "ship_check",
        f"{ship.get('decision')} · grade "
        f"{(ship.get('grade') or {}).get('letter', '—')} · "
        f"{len(ship.get('checks') or [])} checks",
    )
    not_checked = [
        one for one in ship.get("checks", []) if one.get("status") == "not_checked"
    ]
    results.check(
        all("fine" not in str(one.get("summary", "")).lower() for one in not_checked),
        "ship_check · honesty",
        f"{len(not_checked)} checks say not done yet, none say fine",
    )

    # ── 8. the report page opens ─────────────────────────────────────────
    report = ship.get("report_link", "")
    page = report.partition("#")[0]
    results.check(
        bool(page) and get(page) == 200,
        "/report opens",
        f"HTTP {get(page) if page else 'no link'} at {page or '—'}",
    )
    results.check(
        len(report) < 60_000,
        "report size",
        f"{len(report) / 1024:.1f} KB",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Running the app ourselves
# ──────────────────────────────────────────────────────────────────────────────


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for(url: str) -> bool:
    until = time.monotonic() + START_TIMEOUT
    while time.monotonic() < until:
        if get(url + "/health") == 200:
            return True
        time.sleep(0.3)
    return False


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default="",
        help="A running QA-Genius. Omit and this starts one on a free port.",
    )
    args = parser.parse_args(argv[1:])

    results = Results()
    server = None
    url = args.url.rstrip("/")

    if not url:
        port = free_port()
        url = f"http://127.0.0.1:{port}"
        env = {**os.environ, "QAG_MCP_ENABLED": "1"}
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "main:app",
                "--port",
                str(port),
                "--log-level",
                "warning",
            ],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"Started QA-Genius on {url}")
        if not wait_for(url):
            server.terminate()
            print(f"The app did not come up within {START_TIMEOUT:.0f}s.")
            return 2
    else:
        print(f"Using {url}")

    try:
        walk(url, results)
    except Exception as bad:  # noqa: BLE001 - the table is the report
        results.check(False, "ran to the end", f"{type(bad).__name__}: {bad}")
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()

    results.show()
    return 1 if results.failed() else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
