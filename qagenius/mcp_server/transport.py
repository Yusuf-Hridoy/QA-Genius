"""The door itself: one route that reads JSON-RPC and answers it.

Why this is hand-written and not the SDK's own app is in
docs/decisions/001-mcp-transport.md. The short version: this runs on
serverless, where nothing starts a background task group for us, and every
limit and every error sentence in here is one the brief asks for by name.

Nothing in this module ever logs, stores or forwards the text somebody
sent. One line per call, with counts and no content.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
from collections import deque
from dataclasses import dataclass

import anyio
import anyio.to_thread
from mcp_types import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    JSONRPC_VERSION,
    LATEST_PROTOCOL_VERSION,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    CallToolResult,
    Implementation,
    InitializeResult,
    ListToolsResult,
    ServerCapabilities,
    TextContent,
    ToolsCapability,
)
from mcp_types.version import SUPPORTED_PROTOCOL_VERSIONS
from pydantic import BaseModel, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from qagenius.mcp_server import server
from qagenius.mcp_server.schemas import MAX_CRITERIA, MAX_TESTS

log = logging.getLogger("qagenius.mcp")

# ──────────────────────────────────────────────────────────────────────────────
# The flag
# ──────────────────────────────────────────────────────────────────────────────

FLAG = "QAG_MCP_ENABLED"
# Vercel sets this on every deployment. "production" is the live site; a
# preview is anything else. The door is on in previews so it can be tried,
# and off in production until the owner turns it on by setting the flag.
VERCEL_ENV = "VERCEL_ENV"
TRUE_WORDS = {"1", "true", "yes", "on"}
FALSE_WORDS = {"0", "false", "no", "off"}


def enabled() -> bool:
    """Is the MCP door open on this deployment?

    Read on every request, not once at import: a serverless instance is
    long-lived, and turning the flag off should not need a redeploy to
    take effect on the next cold start only.
    """
    said = os.environ.get(FLAG, "").strip().lower()
    if said in TRUE_WORDS:
        return True
    if said in FALSE_WORDS:
        return False
    # Nothing said: on everywhere except the live site.
    return os.environ.get(VERCEL_ENV, "").strip().lower() != "production"


# ──────────────────────────────────────────────────────────────────────────────
# The limits
# ──────────────────────────────────────────────────────────────────────────────

MAX_BODY_BYTES = 1024 * 1024          # 1 MB
TIME_BUDGET_SECONDS = 5.0
RATE_LIMIT_CALLS = 60                 # per IP
RATE_LIMIT_WINDOW = 60.0              # seconds
# One client's worth of timestamps is 60 floats. This caps how many clients
# are remembered at once, so a spray of addresses cannot grow the dict for
# ever on a warm instance.
MAX_TRACKED_CLIENTS = 2048

TOO_MANY_TESTS = f"Too many tests (412). Send {MAX_TESTS} or fewer."
TOO_MANY_CRITERIA = f"Too many criteria (412). Send {MAX_CRITERIA} or fewer."
BODY_TOO_BIG = "That request is too big (413). Send 1 MB or less."
TOO_FAST = (
    f"Too many calls (429). This server takes {RATE_LIMIT_CALLS} calls a "
    "minute from one address."
)
TOO_SLOW = (
    f"That took longer than {TIME_BUDGET_SECONDS:.0f} seconds and was "
    "stopped. Send fewer tests or fewer criteria."
)
OUR_FAULT = "Something went wrong on our side (ref {ref})."


class ToolTrouble(Exception):
    """Something the caller can fix, said in one sentence."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# ──────────────────────────────────────────────────────────────────────────────
# The rate limit
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class RateLimit:
    """A count of recent calls per address, held in this instance's memory.

    A backup, not the guard. A serverless app runs as many instances as it
    likes and each one counts on its own, so the real limit belongs in the
    Vercel Firewall on /mcp. This stops one loop in one client; it does not
    stop a crowd.
    """

    calls: int = RATE_LIMIT_CALLS
    window: float = RATE_LIMIT_WINDOW

    def __post_init__(self) -> None:
        self._seen: dict[str, deque[float]] = {}

    def allows(self, who: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        recent = self._seen.setdefault(who, deque())
        while recent and now - recent[0] >= self.window:
            recent.popleft()
        if len(recent) >= self.calls:
            return False
        recent.append(now)
        self._forget_old(now)
        return True

    def _forget_old(self, now: float) -> None:
        if len(self._seen) <= MAX_TRACKED_CLIENTS:
            return
        stale = [
            who
            for who, seen in self._seen.items()
            if not seen or now - seen[-1] >= self.window
        ]
        for who in stale:
            self._seen.pop(who, None)
        # Still too many, and all of them recent: drop the oldest-touched.
        if len(self._seen) > MAX_TRACKED_CLIENTS:
            ordered = sorted(self._seen.items(), key=lambda pair: pair[1][-1])
            for who, _ in ordered[: len(self._seen) - MAX_TRACKED_CLIENTS]:
                self._seen.pop(who, None)


limiter = RateLimit()


def caller(request: Request) -> str:
    """The address this call came from, as well as we can know it."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return getattr(request.client, "host", "") or "unknown"


# ──────────────────────────────────────────────────────────────────────────────
# JSON-RPC shapes
# ──────────────────────────────────────────────────────────────────────────────


def _result(request_id, payload: BaseModel | dict) -> dict:
    body = (
        payload.model_dump(by_alias=True, exclude_none=True, mode="json")
        if isinstance(payload, BaseModel)
        else payload
    )
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": body}


def _error(request_id, code: int, message: str) -> dict:
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _capabilities() -> ServerCapabilities:
    return ServerCapabilities(tools=ToolsCapability(listChanged=False))


def spoken_version(asked: str) -> str:
    """The protocol version we answer in.

    The client's own, when it is a revision the SDK knows — these tools use
    nothing that changed between them. Anything else gets the newest version
    we have, which is what the spec asks a server to do when it cannot
    speak what it was asked for.
    """
    return asked if asked in SUPPORTED_PROTOCOL_VERSIONS else LATEST_PROTOCOL_VERSION


def _initialize(params: dict) -> InitializeResult:
    """The handshake."""
    asked = str((params or {}).get("protocolVersion") or "")
    return InitializeResult(
        protocolVersion=spoken_version(asked),
        capabilities=_capabilities(),
        serverInfo=Implementation(
            name=server.SERVER_NAME,
            title=server.SERVER_TITLE,
            version=server.version(),
        ),
        instructions=server.INSTRUCTIONS,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Reading what the caller sent
# ──────────────────────────────────────────────────────────────────────────────


# More than this and the list stops being something to read and act on.
MAX_FIELD_ERRORS = 5


def field_path(error: dict) -> str:
    """Where a validation error happened, as an agent would write it.

    "test_cases[2].steps" — not "('body', 'test_cases', 2, 'steps')".
    """
    parts: list[str] = []
    for item in error.get("loc", ()):
        if isinstance(item, int):
            parts.append(f"[{item}]")
        elif parts:
            parts.append(f".{item}")
        else:
            parts.append(str(item))
    return "".join(parts) or "(the request)"


def _said(error: dict) -> str:
    """One validation error in words, without pydantic's own punctuation."""
    kind = error.get("type", "")
    message = str(error.get("msg") or "").strip()
    if kind == "missing":
        return "is required"
    if kind == "too_short":
        return "needs at least one step" if "steps" in field_path(error) else message
    if kind == "extra_forbidden":
        return "is not a field this tool takes"
    return message[0].lower() + message[1:] if message else "is not valid"


def read_arguments(model: type[BaseModel], arguments: dict) -> BaseModel:
    """The caller's arguments as the tool's input model.

    A wrong shape comes back as the field path and what is wrong with it,
    because an agent can fix "test_cases[2].steps: needs at least one step"
    and cannot fix a stack trace.
    """
    try:
        return model.model_validate(arguments or {})
    except ValidationError as bad:
        problems = bad.errors()
        said = "; ".join(
            f"{field_path(one)}: {_said(one)}" for one in problems[:MAX_FIELD_ERRORS]
        )
        if len(problems) > MAX_FIELD_ERRORS:
            said += f"; and {len(problems) - MAX_FIELD_ERRORS} more"
        raise ToolTrouble(said) from None



def check_sizes(arguments: dict) -> None:
    """The two limits worth their own sentence, refused before any work."""
    tests = arguments.get("test_cases")
    if isinstance(tests, list) and len(tests) > MAX_TESTS:
        raise ToolTrouble(TOO_MANY_TESTS)
    criteria = arguments.get("criteria")
    if isinstance(criteria, list) and len(criteria) > MAX_CRITERIA:
        raise ToolTrouble(TOO_MANY_CRITERIA)


# ──────────────────────────────────────────────────────────────────────────────
# Running one tool
# ──────────────────────────────────────────────────────────────────────────────


def _counts(arguments: dict) -> dict[str, int]:
    """What the log line says about the call. Counts only, never content."""
    found = {}
    criteria = arguments.get("criteria")
    if isinstance(criteria, list):
        found["criteria"] = len(criteria)
    tests = arguments.get("test_cases")
    if isinstance(tests, list):
        found["tests"] = len(tests)
    risks = arguments.get("risks")
    if isinstance(risks, list):
        found["risks"] = len(risks)
    return found


def _log(tool: str, started: float, counts: dict[str, int], status: str, **extra):
    """One line per call. No story, no test, no criterion, ever."""
    parts = [f"mcp tool={tool}", f"ms={int((time.monotonic() - started) * 1000)}"]
    parts.extend(f"{name}={value}" for name, value in counts.items())
    parts.extend(f"{name}={value}" for name, value in extra.items())
    parts.append(f"status={status}")
    log.info(" ".join(parts))


def _ready(name: str, arguments: dict) -> tuple[server.Spec, BaseModel]:
    """The tool and its checked arguments, or the sentence saying why not."""
    spec = server.BY_NAME.get(name)
    if spec is None:
        raise ToolTrouble(
            f"There is no tool called {name!r}. This server has: "
            + ", ".join(sorted(server.BY_NAME))
            + "."
        )
    if not isinstance(arguments, dict):
        raise ToolTrouble("arguments: must be an object.")
    check_sizes(arguments)
    return spec, read_arguments(spec.input_model, arguments)


def call_tool(name: str, arguments: dict) -> CallToolResult:
    """Run one tool, start to finish. The in-process way in, used by tests."""
    spec, payload = _ready(name, arguments if isinstance(arguments, dict) else {})
    answer = spec.run(payload)
    return CallToolResult(
        content=[TextContent(type="text", text=server.text_summary(answer))],
        structuredContent=answer.model_dump(mode="json"),
        isError=False,
    )


def _tool_error(message: str) -> CallToolResult:
    """A tool error: the call worked, the tool says no. Never a stack trace."""
    return CallToolResult(
        content=[TextContent(type="text", text=message)],
        isError=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# The route
# ──────────────────────────────────────────────────────────────────────────────

# A notification carries no id and gets no body back, only 202.
NOTIFICATIONS = {"notifications/initialized", "notifications/cancelled"}


def _answer(body: dict) -> Response:
    # No session id is minted and none is read: this door is stateless, so
    # every call carries everything it needs.
    return JSONResponse(body, headers={"Cache-Control": "no-store"})


async def handle(request: Request) -> Response:
    """One JSON-RPC call over HTTP. Always application/json, never a stream."""
    if not enabled():
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    # The header first, so an enormous body is refused before it is read
    # into this process's memory at all. The length check after it is what
    # catches a caller that lied or sent none.
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        log.info("mcp tool=? ms=0 bytes=%s status=too_big", declared)
        return JSONResponse(
            _error(None, INVALID_REQUEST, BODY_TOO_BIG), status_code=413
        )

    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        log.info("mcp tool=? ms=0 bytes=%d status=too_big", len(raw))
        return JSONResponse(
            _error(None, INVALID_REQUEST, BODY_TOO_BIG), status_code=413
        )

    try:
        message = json.loads(raw or b"")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _answer(_error(None, PARSE_ERROR, "That is not JSON."))

    if isinstance(message, list):
        # A batch is legal JSON-RPC and no MCP client needs it from us.
        return _answer(
            _error(None, INVALID_REQUEST, "Send one call at a time, not a batch.")
        )
    if not isinstance(message, dict):
        return _answer(_error(None, INVALID_REQUEST, "A call must be an object."))

    request_id = message.get("id")
    method = str(message.get("method") or "")
    params = message.get("params")
    params = params if isinstance(params, dict) else {}

    # Counted before anything is answered, notifications included: a client
    # looping on notifications is still a client looping on us.
    if not limiter.allows(caller(request)):
        log.info("mcp tool=? ms=0 status=rate_limited")
        return JSONResponse(
            _error(request_id, INVALID_REQUEST, TOO_FAST), status_code=429
        )

    if method in NOTIFICATIONS or (
        request_id is None and method.startswith("notifications/")
    ):
        return Response(status_code=202)

    if method == "initialize":
        return _answer(_result(request_id, _initialize(params)))
    if method == "ping":
        return _answer(_result(request_id, {}))
    if method == "tools/list":
        return _answer(
            _result(request_id, ListToolsResult(tools=server.definitions()))
        )
    if method == "tools/call":
        return _answer(await _call(request_id, params))
    return _answer(
        _error(request_id, METHOD_NOT_FOUND, f"This server does not do {method!r}.")
    )


async def _call(request_id, params: dict) -> dict:
    """tools/call, with every way it can go wrong already decided."""
    name = str(params.get("name") or "")
    arguments = params.get("arguments")
    arguments = arguments if isinstance(arguments, dict) else {}
    started = time.monotonic()

    if not name:
        return _error(request_id, INVALID_PARAMS, "name: is required")

    # The size checks and the shape check are cheap and happen here, on the
    # event loop, so a refusal is fast and never costs a thread.
    try:
        spec, payload = _ready(name, arguments)
    except ToolTrouble as trouble:
        _log(name or "?", started, _counts(arguments), "bad_input")
        return _result(request_id, _tool_error(trouble.message))

    try:
        # The work itself is plain CPU, so it goes to a worker thread and
        # the budget is held out here. A thread doing arithmetic cannot be
        # cancelled in Python; what this guarantees is that the *caller*
        # waits five seconds and no longer. The orphan finishes on its own
        # moments later, and the size limits above are what keep "moments"
        # true.
        with anyio.fail_after(TIME_BUDGET_SECONDS):
            answer = await anyio.to_thread.run_sync(
                spec.run, payload, abandon_on_cancel=True
            )
    except TimeoutError:
        _log(name, started, _counts(arguments), "timeout")
        return _result(request_id, _tool_error(TOO_SLOW))
    except Exception:
        # A number nobody can read back to us, in the log and in the answer,
        # so a report of "ref 7f3a" finds the one line that explains it. The
        # content that caused it is never written down.
        ref = secrets.token_hex(2)
        log.exception("mcp tool=%s ref=%s status=error", name, ref)
        _log(name, started, _counts(arguments), "error", ref=ref)
        return _result(request_id, _tool_error(OUR_FAULT.format(ref=ref)))

    structured = answer.model_dump(mode="json")
    counts = _counts(arguments)
    counts["problems"] = len(structured.get("problems") or [])
    _log(name, started, counts, "ok")
    return _result(
        request_id,
        CallToolResult(
            content=[TextContent(type="text", text=server.text_summary(answer))],
            structuredContent=structured,
            isError=False,
        ),
    )
