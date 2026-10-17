"""Every desk carries the same freshness card, and the scripts that fill it."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)
ROOT = Path(__file__).resolve().parent.parent

# desk key -> the page that shows it
CARD_PAGES = {
    "risks": "/risks",
    "matrix": "/requirements/matrix",
    "ship": "/ship",
    "test_cases": "/requirements/test-cases",
    "automation": "/requirements/automation",
}
ALL_PAGES = [
    "/",
    "/requirements/story",
    "/requirements/criteria",
    "/requirements/test-cases",
    "/requirements/automation",
    "/risks",
    "/requirements/matrix",
    "/ship",
    "/bugs",
    "/insights",
]


@pytest.mark.parametrize("desk,path", sorted(CARD_PAGES.items()))
def test_each_desk_has_exactly_one_source_card(desk, path) -> None:
    body = client.get(path).text
    assert body.count('id="source-card"') == 1, path
    assert f'data-desk="{desk}"' in body


@pytest.mark.parametrize("desk,path", sorted(CARD_PAGES.items()))
def test_the_card_sits_at_the_top_of_the_page(desk, path) -> None:
    """It answers "is this current?" before the page says anything else."""
    body = client.get(path).text
    main_at = body.index("<main")
    card_at = body.index('id="source-card"')
    assert card_at > main_at
    # Nothing but the page heading may come between the two.
    between = body[main_at:card_at]
    assert "<div class=\"card" not in between, between[-300:]


@pytest.mark.parametrize("path", ALL_PAGES)
def test_run_state_loads_on_every_page(path) -> None:
    body = client.get(path).text
    assert "/run_state.js" in body, path
    assert "/source_card.js" in body, path


def test_run_state_loads_before_the_desk_scripts() -> None:
    """Every other script reads window.QAGRun, so it has to exist first."""
    body = client.get("/risks").text
    assert body.index("/run_state.js") < body.index("/app.js")
    assert body.index("/run_state.js") < body.index("/risk_radar.js")


def test_the_card_is_a_live_region_so_changes_are_announced() -> None:
    body = client.get("/risks").text
    card = re.search(r'<div id="source-card"[^>]*>', body).group(0)
    assert 'role="status"' in card
    assert 'aria-live="polite"' in card


def test_no_desk_script_writes_the_run_behind_run_states_back() -> None:
    """All writes go through QAGRun.write, or the cards fall out of sync."""
    stray = []
    for name in ("requirements_flow", "risk_radar", "ship_check", "test_matrix"):
        source = (ROOT / "public" / f"{name}.js").read_text(encoding="utf-8")
        writes = source.count('sessionStorage.setItem(RUN_KEY')
        # One fallback each, for a browser that somehow lacks the module.
        assert writes <= 1, name
        if "window.QAGRun.write(run)" not in source:
            stray.append(name)
    assert stray == [], stray


def test_the_three_states_never_rest_on_colour_alone() -> None:
    """Each state ships an icon and words, not just a background."""
    card = (ROOT / "public" / "source_card.js").read_text(encoding="utf-8")
    for state in ("none", "stale", "fresh"):
        assert f"{state}:" in card or f'"{state}"' in card
    assert "Out of date." in card
    assert "Up to date with your latest story" in card
    assert "Your latest work" in card


# ---------- the sidebar says the state before you click ----------


@pytest.mark.parametrize("desk", ["test_cases", "risks", "matrix", "ship"])
def test_every_desk_link_has_a_status_slot(desk) -> None:
    body = client.get("/risks").text
    assert f'<span class="nav-status" data-desk="{desk}"></span>' in body


def test_the_slots_sit_inside_the_desk_links() -> None:
    body = client.get("/").text
    nav = body[body.index('<nav class="nav"') : body.index("</nav>")]
    assert nav.count("nav-status") == 4


def test_the_phone_nav_is_the_same_markup() -> None:
    """The rail becomes a scrolling strip on a phone; nothing is duplicated."""
    body = client.get("/ship").text
    assert body.count('class="nav-status"') == 4


# ---------- the next-steps strip ----------


@pytest.mark.parametrize(
    "path",
    ["/requirements/test-cases/example", "/requirements/automation/example"],
)
def test_each_result_offers_the_three_next_desks(path) -> None:
    body = client.get(path).text
    assert body.count('id="next-strip"') == 1
    for href in ("/risks", "/requirements/matrix", "/ship"):
        assert f'class="next-chip" href="{href}"' in body, href


@pytest.mark.parametrize(
    "path",
    ["/requirements/test-cases/example", "/requirements/automation/example"],
)
def test_the_old_standalone_ship_link_is_gone(path) -> None:
    """The strip replaced it; two links to the same desk is one too many."""
    body = client.get(path).text
    assert "ship-link" not in body


def test_the_strip_says_what_it_is_for() -> None:
    body = client.get("/requirements/test-cases/example").text
    assert 'aria-label="Next steps"' in body
    assert "Next:" in body
