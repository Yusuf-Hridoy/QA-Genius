"""Every word on a screen clears WCAG AA against the surface behind it.

The colours live in one place -- the token block at the top of style.css --
so the check can read them straight from the file. A token whose value drops
under 4.5:1 fails here long before anyone squints at a screenshot.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "public" / "style.css").read_text(encoding="utf-8")

_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _block(selector: str) -> dict[str, str]:
    """The `--name:value` pairs inside one rule, comments stripped."""
    start = CSS.index(selector + "{") + len(selector) + 1
    end = CSS.index("\n}", start)
    body = re.sub(r"/\*.*?\*/", " ", CSS[start:end], flags=re.DOTALL)
    found = {}
    for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+)", body):
        found[name] = value.strip()
    return found


LIGHT = _block(":root")
DARK = {**LIGHT, **_block(':root[data-theme="dark"]')}

# text token, background token. Everything a reader has to read.
PAIRS = [
    ("--text", "--canvas"),
    ("--text", "--card"),
    ("--text", "--card-2"),
    ("--text-2", "--card"),
    ("--text-2", "--card-2"),
    ("--muted", "--card"),
    ("--muted", "--card-2"),
    ("--muted", "--canvas"),
    ("--accent", "--card"),
    ("--accent", "--canvas"),
    ("--accent-ink", "--accent-soft"),
    ("--on-cta", "--cta"),
    ("--on-cta", "--cta-hover"),
    ("--on-accent", "--accent"),
    ("--rail-ink", "--rail"),
    ("--rail-ink", "--rail-2"),
    ("--rail-ink-2", "--rail"),
    ("--ok-fg", "--ok-bg"),
    ("--warn-fg", "--warn-bg"),
    ("--bad-fg", "--bad-bg"),
    ("--info-fg", "--info-bg"),
]

AA = 4.5

# AA is the floor the law asks for; it is not the floor a page reads well at.
# These are what the ink on a card has to clear: main text, the second level,
# and the quiet text that is left.
ON_CARD = {"--text": 12.0, "--text-2": 9.0, "--muted": 6.0}


def _rgb(value: str) -> tuple[int, int, int]:
    text = value.lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    return tuple(int(text[at : at + 2], 16) for at in (0, 2, 4))  # type: ignore[return-value]


def _luminance(value: str) -> float:
    channels = []
    for raw in _rgb(value):
        part = raw / 255
        channels.append(part / 12.92 if part <= 0.03928 else ((part + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(front: str, back: str) -> float:
    first, second = _luminance(front), _luminance(back)
    high, low = max(first, second), min(first, second)
    return (high + 0.05) / (low + 0.05)


def _check(theme: dict[str, str], label: str) -> list[str]:
    bad = []
    for ink, surface in PAIRS:
        assert ink in theme, f"{label}: {ink} is not a token"
        assert surface in theme, f"{label}: {surface} is not a token"
        assert _HEX.match(theme[ink]), f"{label}: {ink} is not a hex colour"
        ratio = contrast(theme[ink], theme[surface])
        if ratio < AA:
            bad.append(f"{label} {ink} on {surface}: {ratio:.2f}:1")
    return bad


def test_the_maths_is_right() -> None:
    """Black on white is 21:1 and white on white is 1:1, or nothing below means anything."""
    assert round(contrast("#000000", "#FFFFFF"), 2) == 21.0
    assert round(contrast("#FFFFFF", "#FFFFFF"), 2) == 1.0
    assert contrast("#777777", "#FFFFFF") < AA


def test_every_text_pair_clears_aa_in_the_light_theme() -> None:
    assert _check(LIGHT, "light") == []


def test_every_text_pair_clears_aa_in_the_dark_theme() -> None:
    assert _check(DARK, "dark") == []


def _reads_well(theme: dict[str, str], label: str) -> list[str]:
    thin = []
    for ink, want in ON_CARD.items():
        ratio = contrast(theme[ink], theme["--card"])
        if ratio < want:
            thin.append(f"{label} {ink} on a card: {ratio:.2f}:1, wanted {want}:1")
    return thin


def test_the_ink_on_a_card_is_dark_enough_to_read_in_the_light_theme() -> None:
    assert _reads_well(LIGHT, "light") == []


def test_the_ink_on_a_card_is_dark_enough_to_read_in_the_dark_theme() -> None:
    assert _reads_well(DARK, "dark") == []


def test_the_three_inks_stay_in_order() -> None:
    """Main text is always darker than the second, and that than the quiet one."""
    for label, theme in (("light", LIGHT), ("dark", DARK)):
        main = contrast(theme["--text"], theme["--card"])
        second = contrast(theme["--text-2"], theme["--card"])
        quiet = contrast(theme["--muted"], theme["--card"])
        assert main > second > quiet, label


def test_the_dark_theme_redeclares_every_colour_it_changes() -> None:
    """A token the dark block forgets keeps a light value on a dark card."""
    dark_only = _block(':root[data-theme="dark"]')
    for name in ("--canvas", "--card", "--text", "--muted", "--accent", "--border"):
        assert name in dark_only, name


def test_the_three_families_are_tokens() -> None:
    for name in ("--font-serif", "--font-sans", "--font-mono"):
        assert name in LIGHT, name
    assert "Source Serif 4" in LIGHT["--font-serif"]
    assert "Noto Sans" in LIGHT["--font-sans"]
    assert "JetBrains Mono" in LIGHT["--font-mono"]
    # The fallbacks matter on the first paint, before the web font lands.
    assert "Georgia" in LIGHT["--font-serif"]
    assert "system-ui" in LIGHT["--font-sans"]
    assert "ui-monospace" in LIGHT["--font-mono"]


def test_the_page_asks_for_those_three_families_and_no_others() -> None:
    base = (ROOT / "qagenius" / "templates" / "base.html").read_text(encoding="utf-8")
    link = re.search(r'<link href="https://fonts\.googleapis\.com[^"]*"', base)
    assert link, "no Google Fonts link in base.html"
    href = link.group(0)
    for family in ("Source+Serif+4", "Noto+Sans", "JetBrains+Mono"):
        assert family in href, family
    assert "display=swap" in href
    assert "Plus+Jakarta" not in href
    assert "Instrument+Sans" not in href
    assert 'rel="preconnect" href="https://fonts.gstatic.com"' in base
    # Nothing in the stylesheet may name a family the page never loads.
    assert "Plus Jakarta" not in CSS
    assert "Instrument Sans" not in CSS


def test_the_one_main_button_colour_is_only_the_cta() -> None:
    """Yellow is the main button. It is never a status and never the rail."""
    for name in ("--cta", "--cta-hover", "--on-cta", "--alert", "--alert-soft"):
        assert name in LIGHT, name
        assert name in DARK, name
    assert LIGHT["--cta"].upper() == "#FFD166"
    assert DARK["--cta"].upper() == "#FFD166"


# ── how heavy the text is ────────────────────────────────────────────────────


def test_body_text_carries_a_little_more_weight_than_regular() -> None:
    """450 on the variable axis: the same shapes, enough ink to hold a line."""
    assert "font-weight:450" in CSS
    # Thinning every glyph on a Mac is exactly what this used to do.
    assert "-webkit-font-smoothing:" not in CSS


def test_the_sans_is_loaded_as_a_variable_font() -> None:
    base = (ROOT / "qagenius" / "templates" / "base.html").read_text(encoding="utf-8")
    assert "family=Noto+Sans:wght@400..700" in base


def test_titles_and_big_numbers_are_medium_not_light() -> None:
    for rule, weight in (
        (".page-head h1,h1.page-title", "font-weight:500"),
        (".card-title", "font-weight:500"),
        (".stat .num,.stat-num", "font-weight:500"),
    ):
        start = CSS.index(rule + "{")
        block = CSS[start : CSS.index("}", start)]
        assert weight in block, rule


def test_a_sentence_is_never_painted_in_the_quiet_ink() -> None:
    """.muted is what the templates put on second-level sentences."""
    start = CSS.index("\n.muted{")
    assert "var(--text-2)" in CSS[start : CSS.index("}", start)]


def test_the_senior_tester_chip_is_the_same_amber_everywhere() -> None:
    """.pill.accent would otherwise win and paint it cobalt on one desk."""
    assert ".pill.pq-label" in CSS
    start = CSS.index(".pill.pq-label")
    block = CSS[start : CSS.index("}", start)]
    assert "var(--warn-bg)" in block and "var(--warn-fg)" in block
