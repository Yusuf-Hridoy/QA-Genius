"""Every desk carries the same freshness card, and the scripts that fill it."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def open_page(path: str):
    """An example is asked for with POST, so no reader's URL can carry one."""
    return client.post(path) if "/example" in path else client.get(path)
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
    body = open_page(path).text
    assert body.count('id="source-card"') == 1, path
    assert f'data-desk="{desk}"' in body


@pytest.mark.parametrize("desk,path", sorted(CARD_PAGES.items()))
def test_the_card_sits_at_the_top_of_the_page(desk, path) -> None:
    """It answers "is this current?" before the page says anything else."""
    body = open_page(path).text
    main_at = body.index("<main")
    card_at = body.index('id="source-card"')
    assert card_at > main_at
    # Nothing but the page heading may come between the two.
    between = body[main_at:card_at]
    assert "<div class=\"card" not in between, between[-300:]


@pytest.mark.parametrize("path", ALL_PAGES)
def test_run_state_loads_on_every_page(path) -> None:
    body = open_page(path).text
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
    assert "Old — your work changed." in card
    assert "Matches your latest story" in card
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
    body = open_page(path).text
    assert body.count('id="next-strip"') == 1
    for href in ("/risks", "/requirements/matrix", "/ship"):
        assert f'class="next-chip" href="{href}"' in body, href


@pytest.mark.parametrize(
    "path",
    ["/requirements/test-cases/example", "/requirements/automation/example"],
)
def test_the_old_standalone_ship_link_is_gone(path) -> None:
    """The strip replaced it; two links to the same desk is one too many."""
    body = open_page(path).text
    assert "ship-link" not in body


def test_the_strip_says_what_it_is_for() -> None:
    body = client.post("/requirements/test-cases/example").text
    assert 'aria-label="Next steps"' in body
    assert "Next:" in body


# ---------- the desk does not say the same thing twice ----------


def test_the_risk_page_hides_its_old_summary_when_a_story_exists() -> None:
    """The source card is the summary; the old card repeated it.

    The card is still in the page so the source card can press its buttons,
    so the rule is a CSS one keyed on the state run_state.js publishes.
    """
    css = (ROOT / "public" / "style.css").read_text(encoding="utf-8")
    assert (
        'body[data-has-story="yes"] #risk-root [data-input-card="Your run"]{display:none}'
        in css
    )


def test_the_card_publishes_whether_a_story_exists() -> None:
    card = (ROOT / "public" / "source_card.js").read_text(encoding="utf-8")
    assert 'setAttribute(\n      "data-has-story",' in card or '"data-has-story"' in card


def test_the_risk_desk_keeps_one_load_example_button() -> None:
    """The card borrows the desk's button rather than making a second one."""
    radar = (ROOT / "public" / "risk_radar.js").read_text(encoding="utf-8")
    card = (ROOT / "public" / "source_card.js").read_text(encoding="utf-8")
    assert 'example.id = "risk-example"' in radar
    assert 'risks: "#risk-example"' in card


def test_an_out_of_date_answer_stays_on_screen_and_still_readable() -> None:
    css = (ROOT / "public" / "style.css").read_text(encoding="utf-8")
    # The panel is dimmed, never the words: an opacity over the whole block
    # took the text under 4.5:1 against the page behind it.
    assert ".stale-result{background:var(--card-2)" in css
    assert ".stale-result{opacity" not in css
    assert ".stale-result button" in css  # read-only while it is out of date
    card = (ROOT / "public" / "source_card.js").read_text(encoding="utf-8")
    assert "Built from older criteria — press update" in card
    assert "Built from an older story — press update" in card


def test_a_loaded_sample_is_marked_in_the_html() -> None:
    """run_state.js needs to see that what is on screen is a sample."""
    body = client.post("/risks/example").text
    assert 'data-is-example="1"' in body


def test_the_matrix_page_is_its_own_desk_in_the_breadcrumb() -> None:
    body = client.get("/requirements/matrix").text
    assert "— TEST MATRIX" in body or ">Test matrix<" in body
    assert "Requirements · Test matrix" not in body


def test_a_result_that_lands_late_still_gets_dimmed() -> None:
    """A desk draws its answer after the card has drawn, so it says so."""
    state = (ROOT / "public" / "run_state.js").read_text(encoding="utf-8")
    radar = (ROOT / "public" / "risk_radar.js").read_text(encoding="utf-8")
    matrix = (ROOT / "public" / "test_matrix.js").read_text(encoding="utf-8")
    card = (ROOT / "public" / "source_card.js").read_text(encoding="utf-8")
    assert 'RESULT_EVENT = "qag:result-shown"' in state
    assert "announceResult: announceResult," in state
    assert "window.QAGRun.announceResult()" in radar
    assert "window.QAGRun.announceResult()" in matrix
    assert "window.addEventListener(window.QAGRun.RESULT_EVENT, drawAll)" in card
