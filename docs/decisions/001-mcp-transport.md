# 001 — How QA-Genius speaks MCP

**Date:** 2026-11-04
**Status:** accepted
**Applies to:** the `/mcp` door on the same Vercel app

## The choice

Two ways to put an MCP server on the FastAPI app we already deploy:

- **Plan A** — mount the SDK's own Starlette app:
  `app.mount("/mcp", server.streamable_http_app(...))`, with the SDK's
  session manager started in the FastAPI lifespan.
- **Plan B** — one hand-written route, `POST /mcp`, that reads JSON-RPC and
  answers it, while still using the SDK's types and schemas
  (`Tool`, `CallToolResult`, `InitializeResult`, the error codes)
  for every shape that goes on the wire.

**We chose plan B.**

## What was tried

The spike was `mcp==2.3.0`. In 2.x the class the brief calls `FastMCP` is
named `MCPServer`; everything else in the brief's sketch held:

```python
from mcp.server.mcpserver import MCPServer

spike = MCPServer("QA-Genius", version="2.0.0")

@spike.tool()
def ping() -> dict:
    return {"ok": True}

sub = spike.streamable_http_app(
    streamable_http_path="/", json_response=True, stateless_http=True
)

@contextlib.asynccontextmanager
async def lifespan(app):
    async with spike.session_manager.run():
        yield

app = FastAPI(lifespan=lifespan)
app.mount("/mcp", sub)
```

Driven over real HTTP (`httpx.ASGITransport`), plan A works:

| call | result |
| --- | --- |
| `initialize` | `200`, `application/json`, protocol `2025-06-18` |
| `notifications/initialized` | `202` |
| `tools/list` | `200`, one tool |
| `tools/call ping` | `200`, `{"ok": true}` |

## What went wrong

Three things, all of them about running this on Vercel rather than about
the SDK being wrong.

1. **No lifespan, no server.** Taking the lifespan away and leaving
   everything else alone turns *every* call into `500 Internal Server
   Error`. The session manager holds the task group each request is
   answered in; without `run()` there is nothing to answer in. Vercel's
   changelog says FastAPI lifespan events are supported, and its own
   community threads report startup code that did not run on deployments
   and previews. We could not settle that either way: see "What we could
   not test".

2. **The Host check refuses the deployed domain.** `streamable_http_app`
   defaults to `host="127.0.0.1"`, and that default silently switches on
   DNS-rebinding protection with `allowed_hosts=["127.0.0.1:*",
   "localhost:*", "[::1]:*"]`. The first spike run answered
   `421 Misdirected Request — Invalid Host header` to every call, because
   the client sent a host that was not one of those three. On Vercel the
   Host header is the deployment domain, so plan A needs
   `transport_security` configured by hand or it answers 421 to everyone.

3. **The address a client is given redirects.** Mounted at `/mcp` with the
   sub-app's path at `/`, a `POST /mcp` — the exact URL a user types into
   `claude mcp add` — answers `307` to `/mcp/`. A 307 keeps the method and
   the body, so a client that follows redirects recovers; a client that
   does not, or one that will not re-send a body, does not.

## What we could not test

The brief asks for a Vercel preview URL, an MCP Inspector run against it,
and `claude mcp add` against the preview. None of that happened: this work
was done under a standing instruction not to commit, so there is no branch
to push and no preview to point an Inspector at. Point 1 above is therefore
**the thing we could not settle** — and it is the one that decides plan A.

## Why plan B

Plan B cannot hit any of the three.

- It is a plain route in the app we already deploy, so there is no session
  manager, no task group and nothing for a lifespan to start. A cold
  serverless instance answers the first request correctly.
- It is a route, not a mount, so `POST /mcp` is the address — no redirect.
- It has no Host allow-list, and never needed one: an MCP client calls this
  server from a server, and the browser rules that DNS-rebinding protection
  exists for do not apply.

It also makes the rest of the brief straightforward rather than awkward. A
1 MB body cap, a 5-second budget, a 60-calls-a-minute limit per IP, the
`QAG_MCP_ENABLED` flag that must answer 404, one log line per call that
never contains input text, and the exact error wording the brief asks for
("Too many tests (412). Send 300 or fewer.") are all things we write in the
route. Through the SDK's app they would be middleware wrapped around code
that wants to phrase its own errors.

The cost is real and worth naming: we now own protocol correctness.
`initialize`, `notifications/initialized`, `tools/list`, `tools/call` and
`ping` are ours to keep right. We hold that cost down two ways.

**Every shape on the wire comes from the SDK.** `Tool` builds the tool
list, `InitializeResult` builds the handshake, `CallToolResult` builds
every answer, and the error codes are `INVALID_PARAMS` and friends. The
only hand-written part is the dispatch, never the vocabulary.

**The SDK's own client drives our route in the test suite.**
`tests/test_mcp_transport.py` opens a real `ClientSession` over
`streamable_http_client`, pointed at this app through an ASGI transport,
and runs `initialize` → `tools/list` → all three tools through it. If we
get a shape wrong, a genuine MCP client finds out in CI rather than in
somebody's Claude Code session.

## What we ship, and what we only test with

The server imports `mcp_types`, which is the wire types and nothing else —
pydantic and typing-extensions are its only dependencies, and the app
already has both. The full `mcp` package pulls cryptography,
opentelemetry, httpx2, sse-starlette, pyjwt and uvicorn behind it, all for
a server and a client we do not run. The SDK's own `mcp.types` docstring
says to depend on `mcp_types` directly when all you do is read and write
the shapes, which is exactly our case.

So `requirements.txt` has `mcp-types==2.3.0` and the `dev` extra has
`mcp==2.3.0`, for the one test above. CI proves the split holds: it builds
a second virtualenv from `requirements.txt` alone and imports the app in
it. The SDK-client test skips itself when the SDK is absent, so that
install is green rather than broken.

## The rate limit is a backup, not the guard

`transport.py` holds 60 calls a minute per address in the instance's own
memory. That stops one client stuck in a loop. It does not stop a crowd:
Vercel runs as many instances as it likes and each one counts on its own,
so the number is per instance, not per deployment.

The real guard is a **Vercel Firewall rate-limit rule on `/mcp`**, which
the owner has to add — it is not something this repo can set. Checked
2026-11-04: Vercel's WAF rate limiting is documented as available on all
plans including Hobby, with one free rate-limit rule per project on Hobby
and a fixed-window algorithm; the pricing page and the firewall limits
table list 3 custom firewall rules for Hobby. Worth confirming on the
pricing page before relying on it, since the sources did not agree on the
rule count.

## How to test it

Locally:

```
pytest -q tests/test_mcp_transport.py tests/test_mcp_golden.py tests/test_mcp_contracts.py
```

- `test_mcp_transport.py` — the SDK client against this app, then raw
  JSON-RPC over HTTP, every error path, the limits, the rate limit, the
  flag, the log lines and the timings at the published limits.
- `test_mcp_golden.py` — the five reference stories, frozen.
- `test_mcp_contracts.py` — the JSON Schemas an agent builds its calls
  from, frozen.

To run the door by hand:

```
QAG_MCP_ENABLED=1 uvicorn main:app --port 8000
curl -s localhost:8000/mcp -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

Against a deployment, once there is one:

```
npx @modelcontextprotocol/inspector
# transport: Streamable HTTP, URL: https://<deployment>/mcp

claude mcp add --transport http qa-genius https://<deployment>/mcp
```

## If we ever want plan A back

It is not a one-line change, but it is a small one: mount the SDK app at
`/mcp`, pass `transport_security=TransportSecuritySettings(...)` naming the
deployment's hosts (fixing 2), give the sub-app the path `""` or add a
redirect-free route for the bare `/mcp` (fixing 3), and confirm on a real
preview that the lifespan runs (settling 1). The service layer and the
tools underneath do not change — they are plain functions, and which door
calls them is the only thing this decision is about.
