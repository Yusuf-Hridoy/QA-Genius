"""Open every desk in a real browser and run the polish-pass checks.

tests/test_ui_guards.py reads the templates, which catches a button written
down wrongly. This opens the pages at phone and desktop width and asks the
browser what really happened, which catches the things only a layout knows:

  * the page scrolls sideways on a phone,
  * a screen state offers more than one main (yellow) button,
  * a control can be tabbed to but shows no focus ring.

scripts/check_text_size.py covers the fourth check in the list, text under
12px, and stays its own script so each can be run on its own.

Start the app yourself first:

    uvicorn main:app --reload
    python scripts/check_polish.py                  # 127.0.0.1:8000
    python scripts/check_polish.py http://localhost:9000

Playwright is a development dependency only, so it is not in
requirements.txt and the deployed app never imports it:

    pip install playwright
    playwright install chromium

Exit code 1 when any check fails.
"""

from __future__ import annotations

import sys

DEFAULT_BASE = "http://127.0.0.1:8000"

# A phone narrow enough to catch a card that will not fold, and the desktop
# width the design is drawn at.
SIZES = {"phone": (390, 844), "desktop": (1440, 900)}

# A couple of pixels of rounding is not a sideways scroll.
SCROLL_SLACK = 2

# How many controls to tab through before moving on. Every page here has
# fewer than this; the cap only stops a focus trap from hanging the run.
TAB_LIMIT = 60

# name, path, what to press first (None = the page as it loads).
EXAMPLE = 'button:has-text("Load example")'
PAGES: list[tuple[str, str, str | None]] = [
    ("overview", "/", None),
    ("ship-check", "/ship", EXAMPLE),
    # Load example lives behind More on the Story step.
    ("story", "/requirements/story", "#story-more,#load-example"),
    ("criteria", "/requirements/criteria", None),
    ("test-cases", "/requirements/test-cases", EXAMPLE),
    ("automation", "/requirements/automation", EXAMPLE),
    ("risk-radar", "/risks", EXAMPLE),
    ("matrix", "/requirements/matrix", None),
    ("stories", "/stories", None),
    ("bugs", "/bugs", "#bug-example"),
    ("insights", "/insights", "#insights-example"),
]

# Does the document reach wider than the window it is drawn in, and which
# element is the one sticking out?
SIDEWAYS = """
() => {
  const doc = document.documentElement;
  const over = [];
  const room = doc.clientWidth;
  document.querySelectorAll("body *").forEach((node) => {
    const box = node.getBoundingClientRect();
    if (box.width === 0 && box.height === 0) return;
    if (box.right <= room + 2 && box.left >= -2) return;
    const style = getComputedStyle(node);
    if (style.display === "none" || style.visibility === "hidden") return;
    over.push({ tag: node.tagName.toLowerCase(),
                cls: node.className && node.className.toString
                       ? node.className.toString() : "",
                right: Math.round(box.right), left: Math.round(box.left) });
  });
  return { width: doc.scrollWidth, room: room, over: over.slice(0, 6) };
}
"""

# Every main button a person can actually see and press right now.
#
# The yellow is what makes a button the main one, and the class is not the
# same thing: a card that offers the page's action already takes the yellow
# off the desk's own button from the stylesheet, leaving the class behind.
# Counting ".btn-primary" called that a clash when the screen showed one
# yellow button, so this asks the browser for the colour it really drew.
MAIN_BUTTONS = """
() => {
  const probe = document.createElement("span");
  probe.style.color =
    getComputedStyle(document.documentElement).getPropertyValue("--cta").trim();
  document.body.appendChild(probe);
  const cta = getComputedStyle(probe).color;
  probe.remove();

  const out = [];
  document.querySelectorAll(".btn, button, a").forEach((node) => {
    const style = getComputedStyle(node);
    if (style.display === "none" || style.visibility === "hidden") return;
    if (!node.getClientRects().length) return;
    if (node.disabled) return;
    if (node.closest("[hidden],[aria-hidden='true']")) return;
    if (style.backgroundColor !== cta) return;
    out.push((node.textContent || "").trim().slice(0, 40));
  });
  return out;
}
"""

# The element the keyboard is on, and whether anything marks it out.
FOCUSED = """
() => {
  const node = document.activeElement;
  if (!node || node === document.body) return null;
  const style = getComputedStyle(node);
  const ring = style.boxShadow && style.boxShadow !== "none";
  const line = style.outlineStyle !== "none"
    && parseFloat(style.outlineWidth || "0") > 0;
  return {
    tag: node.tagName.toLowerCase(),
    cls: node.className && node.className.toString
           ? node.className.toString() : "",
    text: (node.textContent || node.value || "").trim().slice(0, 30),
    seen: Boolean(ring || line),
  };
}
"""


def say_plainly() -> None:
    """Let the report print an arrow on a console that predates Unicode.

    The words on these pages carry → and ·, and a Windows console is still
    cp1252 by default, so the run dies at the moment it has something to
    say. Nothing is lost by replacing what the console cannot draw.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str]) -> int:
    say_plainly()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright is missing. Run:\n"
            "    pip install playwright\n"
            "    playwright install chromium",
            file=sys.stderr,
        )
        return 2

    base = (argv[1] if len(argv) > 1 else DEFAULT_BASE).rstrip("/")
    sideways: list[str] = []
    crowded: list[str] = []
    unseen: list[str] = []

    with sync_playwright() as play:
        browser = play.chromium.launch()
        for size, (wide, tall) in SIZES.items():
            context = browser.new_context(viewport={"width": wide, "height": tall})
            page = context.new_page()
            for name, path, click in PAGES:
                page.goto(base + path, wait_until="domcontentloaded")
                page.wait_for_timeout(900)
                for one in (click or "").split(","):
                    if not one:
                        continue
                    target = page.locator(one)
                    if not target.count() or not target.first.is_visible():
                        continue
                    target.first.click()
                    page.wait_for_timeout(1200)
                where = f"{name} ({size})"

                # Sideways scroll is a phone problem; a desktop page that
                # reaches past 1440 is one too, so both widths are checked.
                room = page.evaluate(SIDEWAYS)
                if room["width"] > room["room"] + SCROLL_SLACK:
                    out = ", ".join(
                        f"<{one['tag']} class=\"{one['cls'][:40]}\"> to {one['right']}px"
                        for one in room["over"]
                    )
                    sideways.append(
                        f"{where}: page is {room['width']}px wide in "
                        f"{room['room']}px of room — {out or 'no single element'}"
                    )

                # One main button per screen state, counted once per page:
                # the same markup draws both widths.
                if size == "phone":
                    mains = page.evaluate(MAIN_BUTTONS)
                    if len(mains) > 1:
                        crowded.append(
                            f"{name}: {len(mains)} main buttons — "
                            + " · ".join(repr(one) for one in mains)
                        )

                    # Tab through the page and watch for a control that
                    # takes the keyboard without showing where it went.
                    page.keyboard.press("Tab")
                    seen_here: set[str] = set()
                    for _ in range(TAB_LIMIT):
                        spot = page.evaluate(FOCUSED)
                        if not spot:
                            break
                        mark = f"{spot['tag']}.{spot['cls']}|{spot['text']}"
                        if mark in seen_here:
                            break
                        seen_here.add(mark)
                        if not spot["seen"]:
                            unseen.append(
                                f"{name}: <{spot['tag']} "
                                f"class=\"{spot['cls'][:40]}\"> {spot['text']!r}"
                            )
                        page.keyboard.press("Tab")
            context.close()
        browser.close()

    print(f"checked {len(PAGES)} pages at {' and '.join(SIZES)} width")
    trouble = 0
    for title, found in (
        ("scroll sideways", sideways),
        ("offer more than one main button", crowded),
        ("take focus without showing it", unseen),
    ):
        if found:
            trouble += len(found)
            print(f"\n{len(found)} {title}:")
            for line in sorted(set(found)):
                print("  " + line)
    if trouble:
        return 1
    print("no sideways scroll, one main button per state, focus always visible")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
