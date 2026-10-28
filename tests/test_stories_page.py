"""The "My stories" page, and the promise it makes about where things live."""

from pathlib import Path

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)
ROOT = Path(__file__).resolve().parent.parent

PAGES = ("/", "/requirements/story", "/risks", "/requirements/matrix", "/ship", "/stories")


def test_the_page_loads_and_carries_its_script() -> None:
    body = client.get("/stories").text
    assert '<script src="/stories.js" defer></script>' in body
    assert 'id="stories-list"' in body


def test_the_scripts_are_served() -> None:
    for path in ("/stories.js", "/story_store.js", "/stories_ui.js"):
        assert client.get(path).status_code == 200, path


def test_the_page_says_where_the_stories_live() -> None:
    body = client.get("/stories").text
    assert "Saved in this browser until you delete them." in body
    assert "All your stories in one place." in body


def test_the_toolbar_offers_search_filter_and_sort() -> None:
    body = client.get("/stories").text
    for marker in ('id="stories-search"', 'id="stories-status"', 'id="stories-sort"'):
        assert marker in body, marker


def test_the_page_has_one_main_button() -> None:
    body = client.get("/stories").text
    page = body[body.index('<main class="content">') : body.index("</main>")]
    assert page.count("btn-primary") == 1
    assert 'id="stories-new"' in page


def test_deleting_everything_asks_for_the_word_delete() -> None:
    body = client.get("/stories").text
    assert "Type DELETE to confirm" in body
    assert 'id="delete-all-word"' in body
    assert "It cannot be" in body and "undone." in body


def test_every_page_offers_the_stories_link() -> None:
    """The rail shows it once there is something to show; the link is always there."""
    for path in PAGES:
        body = client.get(path).text
        assert body.count('id="nav-stories"') == 1, path
        assert 'href="/stories"' in body, path


def test_the_rail_says_where_the_work_lives() -> None:
    body = client.get("/").text
    assert "Your keys and your stories stay in this" in body
    assert "browser until you delete them." in body


def test_the_story_step_offers_an_id_and_a_draft() -> None:
    body = client.get("/requirements/story").text
    assert 'id="story-label"' in body
    assert 'id="save-draft"' in body
    assert 'id="draft-status"' in body
    assert "leave empty and we&#39;ll number it" in body


def test_the_store_keeps_its_promises_in_one_place() -> None:
    """The limits the brief set are in the module, not scattered in pages."""
    source = (ROOT / "public" / "story_store.js").read_text(encoding="utf-8")
    assert 'var KEY = "qag.stories.v1"' in source
    assert "var MAX_STORIES = 25" in source
    assert "var SAVE_DELAY = 600" in source
    assert "4 * 1024 * 1024" in source
    # Every storage call is wrapped: a private window must not break a page.
    assert source.count("try {") >= 5


def test_the_run_still_lives_in_the_tab_and_the_stories_in_the_browser() -> None:
    """Two stores, two promises: one goes with the tab, one stays."""
    run_state = (ROOT / "public" / "run_state.js").read_text(encoding="utf-8")
    store = (ROOT / "public" / "story_store.js").read_text(encoding="utf-8")
    assert "sessionStorage.getItem" in run_state
    assert "localStorage" not in run_state
    assert "localStorage.getItem" in store
    assert "sessionStorage.getItem" not in store
