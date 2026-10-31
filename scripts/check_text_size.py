"""Open every desk in a real browser and find text under 12px.

tests/test_text_size.py reads the stylesheet, which catches a size written
down somewhere. This opens the pages and asks the browser what each piece
of text actually came out at, which catches the ones that are inherited,
clamped or computed.

Start the app yourself first:

    uvicorn main:app --reload
    python scripts/check_text_size.py                  # 127.0.0.1:8000
    python scripts/check_text_size.py http://localhost:9000

Playwright is a development dependency only, so it is not in
requirements.txt and the deployed app never imports it:

    pip install playwright
    playwright install chromium

Exit code 1 when anything visible is under the floor.
"""

from __future__ import annotations

import sys

DEFAULT_BASE = "http://127.0.0.1:8000"
FLOOR = 12.0

# The one exception the design allows: "/125" under a risk's score, where
# the number beside it is three times the size and carries the meaning.
ALLOWED_CLASSES = ("risk-score-of",)

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

# Every visible element that holds words of its own, and the size the
# browser really drew them at.
MEASURE = """
(allowed) => {
  const out = [];
  document.querySelectorAll("body *").forEach((node) => {
    if (node.children.length && !hasOwnWords(node)) return;
    const text = (node.textContent || "").trim();
    if (!text) return;
    const style = getComputedStyle(node);
    if (style.display === "none" || style.visibility === "hidden") return;
    if (parseFloat(style.fontSize) === 0) return;
    if (!node.getClientRects().length) return;
    if (allowed.some((one) => node.classList.contains(one))) return;
    const size = parseFloat(style.fontSize);
    out.push({ size: size, tag: node.tagName.toLowerCase(),
               cls: node.className && node.className.toString
                      ? node.className.toString() : "",
               text: text.slice(0, 50) });
  });
  return out;
  function hasOwnWords(node) {
    return Array.prototype.some.call(node.childNodes, (child) =>
      child.nodeType === 3 && child.textContent.trim() !== "");
  }
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
    small: list[str] = []
    checked = 0

    with sync_playwright() as play:
        browser = play.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 900})
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
            found = page.evaluate(MEASURE, list(ALLOWED_CLASSES))
            checked += len(found)
            for one in found:
                if one["size"] < FLOOR:
                    small.append(
                        f"{name}: {one['size']}px  "
                        f"<{one['tag']} class=\"{one['cls']}\">  {one['text']!r}"
                    )
        browser.close()

    print(f"measured {checked} pieces of text across {len(PAGES)} pages")
    if small:
        print(f"\n{len(small)} under {FLOOR}px:")
        for line in sorted(set(small)):
            print("  " + line)
        return 1
    print(f"nothing under {FLOOR}px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
