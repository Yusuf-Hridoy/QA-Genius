# QA-Genius v2 rules
- Python 3.12, FastAPI, Jinja2, HTMX. No React, Node, npm, LangChain, database or accounts.
- Users bring their own keys. Keys live in the browser. The server never stores or logs a key.
- Prompt text in qagenius/prompts.py is reused from v1. Change it only when a brief says so.
- Field names in qagenius/models.py never change.
- Never use the names of any real employer or client in code, samples or tests. Sample product: "Aurora Storefront".
- Every change: pytest -q and ruff check . must pass. Commit message: "phase-N: what".
