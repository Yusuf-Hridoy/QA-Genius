"""Every page carries the key chip + drawer; /keys redirects."""

from fastapi.testclient import TestClient

import main

client = TestClient(main.app, raise_server_exceptions=False)

PAGES = [
    "/",
    "/requirements/story",
    "/risks",
    "/bugs",
    "/ship",
]


def test_every_page_has_chip_and_drawer_once() -> None:
    for path in PAGES:
        body = client.get(path).text
        assert body.count('id="key-chip"') == 1, path
        assert body.count('id="keys-drawer"') == 1, path
        assert body.count('id="drawer-key-list"') == 1, path


def test_sidebar_has_no_keys_link() -> None:
    for path in PAGES:
        body = client.get(path).text
        assert 'href="/keys"' not in body, path
        assert 'id="key-status"' not in body, path


def test_home_lists_every_desk_and_does_not_redirect() -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200
    body = response.text
    for href in ("/requirements/story", "/risks", "/requirements/matrix", "/ship"):
        assert f'class="desk" href="{href}"' in body, href


def test_home_cards_follow_the_sidebar_order() -> None:
    body = client.get("/").text
    order = ["/requirements/story", "/risks", "/requirements/matrix", "/ship"]
    found = [body.index(f'class="desk" href="{href}"') for href in order]
    assert found == sorted(found)


def test_home_lists_four_desks_and_hides_two() -> None:
    """Bug desk and Quality insights still work; they are just not listed."""
    body = client.get("/").text
    assert body.count('class="desk"') == 4
    assert "Bug desk" not in body
    assert "Quality insights" not in body
    assert "Performance" not in body
    assert "Four desks between a vague story" in body
    assert "Build a matrix" in body


def test_the_performance_desk_is_gone() -> None:
    """Phase 9 built it, phase 10 removed it; the route must not linger."""
    assert client.get("/performance").status_code == 404


def test_the_hidden_desks_still_answer() -> None:
    """Nothing is deleted - the pages are only unlisted."""
    for path in ("/bugs", "/insights"):
        assert client.get(path).status_code == 200, path


def test_every_page_offers_the_theme_toggle() -> None:
    for path in PAGES:
        assert client.get(path).text.count('id="theme-toggle"') == 1, path


def test_risks_page_loads_its_script() -> None:
    """Risk radar builds its own input card, so the script must be on the page."""
    body = client.get("/risks").text
    assert "/risk_radar.js" in body
    assert 'id="risk-root"' in body


def test_keys_redirects_to_story_with_flag() -> None:
    response = client.get("/keys", follow_redirects=False)
    assert response.status_code in (301, 302, 303, 307, 308)
    assert response.headers["location"] == "/requirements/story?keys=open"


def test_the_sidebar_lists_the_four_desks_in_order() -> None:
    body = client.get("/risks").text
    order = ["/requirements/story", "/risks", "/requirements/matrix", "/ship"]
    found = [body.index(f'href="{href}"') for href in order]
    assert found == sorted(found)
    assert 'href="/bugs"' not in body
    assert 'href="/insights"' not in body
    assert 'href="/performance"' not in body
    assert '<a href="/risks" class="active">' in body
    assert "<span>Risk radar</span>" in body


def test_the_matrix_page_marks_itself_active_in_the_sidebar() -> None:
    body = client.get("/requirements/matrix").text
    assert '<a href="/requirements/matrix" class="active">' in body
    assert "<b>Test matrix</b>" in body


def test_the_ring_check_page_shows_every_awkward_value() -> None:
    """0, 7, 44 and 100 percent, which is where "100%" used to overflow."""
    body = client.get("/dev/rings").text
    for value in (0, 7, 44, 100):
        assert f'<span class="score-num">{value}<span class="pct">%</span>' in body
    assert body.count("score-ring") == 4


def test_the_next_row_check_page_shows_all_three_states() -> None:
    """The marks have to be small at every width, so they are all on one page."""
    body = client.get("/dev/next-row").text
    assert body.count("next-chip") == 3
    assert 'class="next-mark dot-stale"' in body
    assert "next-mark tick-fresh" in body
    for state in ("Not built yet", "Old", "Matches your work"):
        assert state in body


def _key_name(body: str) -> str:
    import re

    match = re.search(r'<input[^>]*id="drawer-key"[^>]*>', body)
    assert match, "no key input on the page"
    name = re.search(r'name="([^"]*)"', match.group(0))
    assert name, "the key input has no name"
    return name.group(1)


def test_the_key_box_gets_a_fresh_name_every_render() -> None:
    # A password manager matches a field by name. A name it has never seen
    # gives it nothing to fill.
    first = _key_name(client.get("/").text)
    second = _key_name(client.get("/").text)
    assert first.startswith("qag-api-key-")
    assert second.startswith("qag-api-key-")
    assert first != second


def test_no_page_serves_a_password_field() -> None:
    for path in PAGES:
        assert 'type="password"' not in client.get(path).text, path
