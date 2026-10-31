"""The UI rules a later change must not quietly undo.

These are the four mistakes this pass fixed. A regression in any of them
shows up as a broken-looking page long before anyone reads the CSS, so they
are cheaper to catch here.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = sorted((ROOT / "qagenius" / "templates").glob("*.html"))

# Controls these rules do not cover: a hidden input holds data, and
# checkboxes, radios and file pickers have their own sizing.
EXEMPT_TYPES = {"hidden", "checkbox", "radio", "file"}

_TAG = re.compile(r"<(input|select|textarea|button)\b([^>]*)>", re.IGNORECASE)
_ATTR = re.compile(r"""(\w[\w-]*)\s*=\s*"([^"]*)\"""")


def _attrs(raw: str) -> dict[str, str]:
    return {name.lower(): value for name, value in _ATTR.findall(raw)}


def _lines(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def test_the_hidden_attribute_always_wins() -> None:
    # Without this, any rule that sets display (.row, .btn, .card) shows an
    # element the JS has hidden - the bug desk preview with no screenshot.
    css = (ROOT / "public" / "style.css").read_text(encoding="utf-8")
    assert "[hidden]{display:none !important}" in css


def test_every_button_in_a_template_is_a_btn() -> None:
    stray = []
    for path in TEMPLATES:
        text = path.read_text(encoding="utf-8")
        for match in _TAG.finditer(text):
            if match.group(1).lower() != "button":
                continue
            classes = _attrs(match.group(2)).get("class", "")
            if "btn" not in classes:
                stray.append(f"{path.name}:{_lines(text, match.start())}")
    assert not stray, f"buttons with no btn class: {stray}"


_JINJA = re.compile(r"\{%.*?%\}|\{\{.*?\}\}|\{#.*?#\}", re.DOTALL)
# A {% call field(...) %} block renders the .field wrapper from
# _form_fields.html, so it counts as one here.
_CALL = re.compile(r"\{%\s*call\s+(?:field|group)\(.*?%\}", re.DOTALL)
_ENDCALL = re.compile(r"\{%\s*endcall\s*%\}")
_VOID = {"input", "img", "br", "hr", "meta", "link", "source", "path", "circle",
         "rect", "line", "polyline", "polygon", "use", "col"}


class _FieldWalker(HTMLParser):
    """Walks a template and notes controls with no .field ancestor."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool]] = []
        self.stray: list[str] = []

    def _in_field(self) -> bool:
        return any(is_field for _, is_field in self.stack)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): (value or "") for name, value in attrs}
        classes = values.get("class", "").split()
        if tag in {"input", "select", "textarea"}:
            kind = values.get("type", "text").lower()
            exempt = tag == "input" and kind in EXEMPT_TYPES
            if not exempt and "ctl" not in classes and not self._in_field():
                self.stray.append(f"line {self.getpos()[0]}: <{tag}>")
        if tag not in _VOID:
            self.stack.append((tag, any("field" in name for name in classes)))

    def handle_startendtag(self, tag, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID and self.stack:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        for at in range(len(self.stack) - 1, -1, -1):
            if self.stack[at][0] == tag:
                del self.stack[at:]
                return


def test_every_control_is_in_a_field_or_carries_ctl() -> None:
    """A control outside .field and without .ctl gets none of the sizing."""
    stray = []
    for path in TEMPLATES:
        text = path.read_text(encoding="utf-8")
        text = _ENDCALL.sub("</div>", _CALL.sub('<div class="field">', text))
        # The rest of the Jinja goes: an {% if %} around a tag is not markup.
        text = _JINJA.sub("", text)
        walker = _FieldWalker()
        walker.feed(text)
        stray += [f"{path.name} {where}" for where in walker.stray]
    assert not stray, f"controls outside a field and without .ctl: {stray}"


def _key_input() -> str:
    drawer = (ROOT / "qagenius" / "templates" / "_keys_drawer.html").read_text(
        encoding="utf-8"
    )
    match = re.search(r"<input[^>]*id=\"drawer-key\"[^>]*>", drawer)
    assert match, "the drawer has no #drawer-key input"
    return match.group(0)


def test_the_api_key_is_not_a_password_field() -> None:
    # Browsers offer to fill a password field with a saved login, and a real
    # run had one filled with an email address.
    tag = _key_input()
    assert 'type="text"' in tag
    assert "password" not in tag


def test_the_api_key_is_masked_and_left_alone_by_password_managers() -> None:
    tag = _key_input()
    assert 'autocomplete="off"' in tag
    assert 'data-lpignore="true"' in tag
    assert "data-1p-ignore" in tag
    assert 'spellcheck="false"' in tag
    assert 'autocapitalize="off"' in tag
    # A key on screen is a key in a screen share or over a shoulder.
    assert 'class="masked"' in tag
    css = (ROOT / "public" / "style.css").read_text(encoding="utf-8")
    assert ".masked{-webkit-text-security:disc" in css


def test_the_key_form_is_not_a_login_form() -> None:
    # A username and a password together is what a browser looks for; a
    # decoy password field would hand it exactly that.
    drawer = (ROOT / "qagenius" / "templates" / "_keys_drawer.html").read_text(
        encoding="utf-8"
    )
    assert 'type="password"' not in drawer
    assert 'name="qag-key-label"' in drawer


# ── the number inside the round score ────────────────────────────────────────

STYLE = (ROOT / "public" / "style.css").read_text(encoding="utf-8")


def test_the_number_in_a_ring_is_sized_from_the_ring() -> None:
    """"100%" used to run over the edge of the circle at every width."""
    assert "--ring-size:104px" in STYLE
    assert "font-size:clamp(17px,calc(var(--ring-size) * .25),26px)" in STYLE
    assert "font-variant-numeric:tabular-nums" in STYLE
    assert "white-space:nowrap" in STYLE
    # The sign is a footnote to the number, not half of it — with a floor,
    # because .55em of the small ring came out at 7px.
    assert ".score-ring .score-num .pct{font-size:max(12px,.55em)" in STYLE


def test_no_ring_sizes_its_percent_sign_by_hand() -> None:
    """A fixed 16px "%" is what broke the fit; the class owns the size now."""
    for path in TEMPLATES:
        body = path.read_text(encoding="utf-8")
        assert 'style="font-size:16px"' not in body, path.name


# Each of these draws its own button and turns the shared focus ring off to
# do it, at the same weight as ".btn:focus-visible" but later in the file,
# so the ring loses. The keyboard then lands on them with nothing to show
# where it is. A browser pass found all four; these keep them fixed.
RING_OFF = (
    ".btn.tc-row-main",
    ".btn.btn-icon-tiny",
    ".btn.grade-circle",
    ".steps li.locked a",
)


def test_a_control_that_drops_the_shared_ring_puts_its_own_back() -> None:
    for selector in RING_OFF:
        rule = f"{selector}:focus-visible{{box-shadow:var(--ring)}}"
        assert rule in STYLE, f"{selector} takes focus with no ring"


def test_the_shared_ring_is_still_there_for_everything_else() -> None:
    assert ":focus-visible{outline:none;box-shadow:var(--ring)}" in STYLE
    assert ".btn:focus-visible{outline:none;box-shadow:var(--ring)}" in STYLE


def test_the_rail_footer_label_fits_on_one_line() -> None:
    """"LOCAL-FIRST · NO ACCOUNT" broke onto a second line.

    The rail is 252px with 16px of padding each side, so the label gets
    219px. At .12em it wants 225px and "ACCOUNT" dropped underneath; at
    .06em it takes 206px. nowrap keeps it one line if the wording grows,
    and scripts/check_polish.py catches it if it grows past the rail.
    """
    assert "letter-spacing:.06em;text-transform:uppercase" in STYLE
    assert ".12em;text-transform:uppercase;color:var(--rail-ink)" not in STYLE
    label = STYLE[STYLE.index(".rail-foot-label{") :][:220]
    assert "white-space:nowrap" in label


def test_the_quiet_ship_note_never_takes_the_yellow() -> None:
    """With a report on screen the note is a note, not a second front door."""
    ship = (ROOT / "public" / "ship_check.js").read_text(encoding="utf-8")
    note = ship[ship.index("ship-story-note") :][:400]
    assert "btn-primary" not in note, "the note's button must stay secondary"
    assert "Add the story text on the Story step" in note


def test_the_sample_sentence_is_only_said_when_nothing_else_says_it() -> None:
    """Two notices saying "this is a sample" was the bug.

    The JS tests cover resultSaysSample on its own; this is the half they
    cannot see, that the card actually asks before speaking.
    """
    card = (ROOT / "public" / "source_card.js").read_text(encoding="utf-8")
    guarded = (
        'if (!resultSaysSample()) {\n'
        '      body.appendChild(el("p", "source-title", "Showing a sample."));\n'
        "    }"
    )
    assert guarded in card, "the sample sentence is said unconditionally again"
