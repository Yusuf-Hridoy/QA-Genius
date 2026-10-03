"""Every page carries the key chip + drawer; /keys redirects."""

from fastapi.testclient import TestClient

import main

client = TestClient(main.app, raise_server_exceptions=False)

PAGES = ["/", "/requirements/story", "/bugs", "/insights", "/performance"]


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


def test_keys_redirects_to_story_with_flag() -> None:
    response = client.get("/keys", follow_redirects=False)
    assert response.status_code in (301, 302, 303, 307, 308)
    assert response.headers["location"] == "/requirements/story?keys=open"
