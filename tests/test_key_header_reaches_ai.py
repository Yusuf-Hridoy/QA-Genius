"""No AI route may be called from the browser without the user's keys.

The matrix shipped with a plain fetch to an AI route. The server saw no key,
fell back to the standard factors, and the page looked like it had worked.
Nothing in the UI said the key had been ignored, so this is a guard, not a
test of behaviour.
"""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
WEB = ROOT / "qagenius" / "web.py"

HEADER = "X-QAG-Keys"
# Every fetch, with the chunk of the call that follows it.
_FETCH = re.compile(r'fetch\(\s*(?:"([^"]+)"|([^,)]+))', re.MULTILINE)


def ai_routes() -> set[str]:
    """Routes whose handler reads the key header, read out of web.py itself."""
    tree = ast.parse(WEB.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        reads_keys = any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "_request_keys"
            for call in ast.walk(node)
        )
        if not reads_keys:
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
            ):
                found.add(str(decorator.args[0].value))
    return found


def test_web_py_still_has_ai_routes() -> None:
    """If this ever goes empty the guard below would pass by doing nothing."""
    routes = ai_routes()
    assert "/requirements/matrix/suggest" in routes
    assert len(routes) >= 5


def test_every_browser_fetch_to_an_ai_route_sends_the_keys() -> None:
    routes = ai_routes()
    missing = []
    for script in sorted(PUBLIC.glob("*.js")):
        source = script.read_text(encoding="utf-8")
        for match in _FETCH.finditer(source):
            url = match.group(1)
            if url is None:
                continue
            path = url.split("?")[0]
            if path not in routes:
                continue
            # The options object is whatever follows, up to the call's end.
            call = source[match.start() : match.start() + 400]
            if HEADER not in call and "keyHeader" not in call:
                missing.append(f"{script.name}: {url}")
    assert not missing, f"AI routes fetched without the keys header: {missing}"


def test_the_matrix_suggest_fetch_is_the_one_being_guarded() -> None:
    """Keeps the guard honest: it really does look at the fetch that broke."""
    source = (PUBLIC / "test_matrix.js").read_text(encoding="utf-8")
    assert "/requirements/matrix/suggest" in source
    assert "keyHeader" in source
    assert HEADER in source


def test_the_header_is_built_the_same_way_htmx_builds_it() -> None:
    """One definition of what a key header holds, in app.js."""
    app = (PUBLIC / "app.js").read_text(encoding="utf-8")
    matrix = (PUBLIC / "test_matrix.js").read_text(encoding="utf-8")
    assert "headerKeys: headerKeys," in app  # exported for other desks
    assert "window.QAG.headerKeys()" in matrix
