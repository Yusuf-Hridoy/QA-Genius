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


def test_the_api_key_is_a_password_field() -> None:
    # A key on screen is a key in a screen share or over a shoulder.
    drawer = (ROOT / "qagenius" / "templates" / "_keys_drawer.html").read_text(
        encoding="utf-8"
    )
    match = re.search(r"<input[^>]*id=\"drawer-key\"[^>]*>", drawer)
    assert match, "the drawer has no #drawer-key input"
    assert 'type="password"' in match.group(0)
