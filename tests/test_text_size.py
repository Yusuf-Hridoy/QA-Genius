"""Nothing a reader has to read is smaller than 13px.

A browser pass counted 50 to 80 pieces of text per page under 12px: chips,
ids, step numbers, "/125", code line numbers. They are all one size now.

The rule is checked against the stylesheet, which is where every size in
this app is written: no template sets a font size of its own. The computed
check against a running browser is scripts/check_text_size.py, which needs
Playwright and a server and so is not part of this suite.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "public" / "style.css").read_text(encoding="utf-8")

SMALLEST = 13.0

# The one exception the design allows: the "/125" under a risk's score,
# where the big number beside it carries the meaning.
ALLOWED = {
    ".risk-score-of": 12.0,
}

_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.DOTALL)
_SIZE = re.compile(r"font-size\s*:\s*([0-9.]+)px")


def _rules() -> list[tuple[str, str]]:
    """Every selector and its body, with comments and at-rules stripped."""
    text = re.sub(r"/\*.*?\*/", " ", CSS, flags=re.DOTALL)
    return [
        (" ".join(selector.split()), body)
        for selector, body in _RULE.findall(text)
        if not selector.strip().startswith("@")
    ]


def _too_small() -> list[tuple[str, float]]:
    found = []
    for selector, body in _rules():
        for raw in _SIZE.findall(body):
            size = float(raw)
            # font-size:0 hides a glyph a ::before replaces; it is not text.
            if size == 0 or size >= SMALLEST:
                continue
            floor = next(
                (one for key, one in ALLOWED.items() if key in selector), None
            )
            if floor is not None and size >= floor:
                continue
            found.append((selector, size))
    return found


def test_no_text_is_smaller_than_thirteen_pixels() -> None:
    assert _too_small() == []


def test_the_one_exception_is_the_slash_one_two_five() -> None:
    """And it is 12px, beside a number three times its size."""
    assert ".risk-score-of{display:block;font-size:12px" in CSS
    smaller = [one for one in _rules() if "font-size:12px" in one[1]]
    assert [selector for selector, _ in smaller] == [".risk-score-of"]


def test_a_chip_label_is_bold_rather_than_small() -> None:
    body = next(body for selector, body in _rules() if selector == ".chip")
    assert "font-size:13px" in body
    assert "font-weight:600" in body


def test_a_mono_id_reads_at_thirteen() -> None:
    body = next(body for selector, body in _rules() if selector == ".chip-id")
    assert "font-size:13px" in body
    assert "font-weight:500" in body


def test_a_step_number_reads_at_thirteen() -> None:
    body = next(body for selector, body in _rules() if selector == ".step-n")
    assert "font-size:13px" in body
    assert "font-weight:600" in body


def test_a_unit_inside_a_ring_has_a_floor_of_its_own() -> None:
    """.55em of a 13px ring is a 7px per-cent sign."""
    assert "font-size:max(12px,.55em)" in CSS


def test_the_code_line_numbers_clear_four_and_a_half_to_one() -> None:
    from tests.test_design_tokens import contrast

    assert "color:#7C84A6" in CSS
    assert round(contrast("#7C84A6", "#0E1430"), 2) >= 4.5
