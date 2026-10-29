"""One yellow button per screen, and the yellow is only ever that button.

The main button is the thing the page wants you to press next. Two of them is
two answers to the same question, so every page is counted here -- empty, and
with its own saved example on screen.
"""

import re

from fastapi.testclient import TestClient

import main

client = TestClient(main.app, raise_server_exceptions=False)

# Pages whose markup the server writes, and the examples they can show.
PAGES = (
    "/",
    "/stories",
    "/requirements/story",
    "/requirements/criteria",
    "/requirements/test-cases",
    "/requirements/automation",
    "/requirements/matrix",
    "/risks",
    "/ship",
    "/bugs",
    "/insights",
)

EXAMPLES = (
    "/requirements/story/example",
    "/requirements/test-cases/example",
    "/requirements/automation/example",
    "/requirements/matrix/example",
    "/risks/example",
    "/ship/example",
)


def _page(path: str) -> str:
    """The page itself, without the key drawer that sits behind every one."""
    body = client.get(path).text
    start = body.index('<main class="content">')
    return body[start : body.index("</main>", start)]


def _fragment(path: str) -> str:
    return client.post(path).text


def _primaries(markup: str) -> list[str]:
    """Every main button in the markup, with enough around it to name it."""
    return [
        " ".join(one.split())[:90]
        for one in re.findall(r"<(?:button|a)[^>]*btn-primary[^>]*>.*?</(?:button|a)>",
                              markup, re.DOTALL)
    ]


def test_every_page_has_at_most_one_main_button() -> None:
    for path in PAGES:
        found = _primaries(_page(path))
        assert len(found) <= 1, f"{path}: {found}"


def test_every_saved_example_adds_at_most_one_main_button() -> None:
    """A result swapped into a page must not bring a second yellow button."""
    for path in EXAMPLES:
        found = _primaries(_fragment(path))
        assert len(found) <= 1, f"{path}: {found}"


def test_the_story_result_steps_its_own_check_button_down() -> None:
    """With an answer on screen the next move is the criteria, not Check again."""
    body = _fragment("/requirements/story/example")
    assert 'id="check-btn" type="submit" class="btn"' in body
    assert "Check again" in body
    assert 'id="use-criteria"' in body


def test_the_yellow_is_only_ever_the_main_button() -> None:
    """Nothing else on a screen may paint itself in the call-to-action colour."""
    css = (
        __import__("pathlib").Path(__file__).resolve().parent.parent
        / "public"
        / "style.css"
    ).read_text(encoding="utf-8")
    users = re.findall(r"([^{}]*)\{[^{}]*var\(--cta\)[^{}]*\}", css)
    allowed = (
        ".btn-primary",
        # Save inside an open pop-up. The pop-up is its own screen state:
        # while it is shut this button is not on the screen at all.
        ".btn.btn-pop-save",
        ".logo-mark",
        ".nav a.active::before",
        ".steps li.now .step-n",
        ".bench-strip",
        ".bench-bar-fill",
        ".clarity-bar-fill",
        ":root",
    )
    for selector in users:
        name = selector.strip().split("\n")[-1].strip()
        assert any(one in selector for one in allowed), name
