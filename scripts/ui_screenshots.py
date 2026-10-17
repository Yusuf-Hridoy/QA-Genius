"""Save a PNG of every desk at desktop and phone width.

This script starts nothing. Run the app yourself first:

    uvicorn main:app --reload
    python scripts/ui_screenshots.py                  # 127.0.0.1:8000
    python scripts/ui_screenshots.py http://localhost:9000

Playwright is a development dependency only, so it is not in
requirements.txt and the deployed app never imports it:

    pip install playwright
    playwright install chromium

The PNGs land in ui-screens/, which git ignores. Nothing here needs an API
key: every page is shot empty or with its own Load example button, so no
request ever reaches a provider.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "ui-screens"

DEFAULT_BASE = "http://127.0.0.1:8000"

SIZES = {"desktop": (1366, 900), "phone": (390, 844)}

# name, path, what to press first (None = shoot the page as it loads).
# Most Load example buttons are built by JS and carry no id, so they are
# found by their words rather than by a selector this pass must not invent.
EXAMPLE = 'button:has-text("Load example")'

# Ship check comes first: its Load example button is part of the empty
# state, and every later example writes a run into sessionStorage.
SHOTS: list[tuple[str, str, str | None]] = [
    ("ship-check-example", "/ship", EXAMPLE),
    ("story-empty", "/requirements/story", None),
    ("story-example", "/requirements/story", "#load-example"),
    ("test-cases-example", "/requirements/test-cases", EXAMPLE),
    ("automation-example", "/requirements/automation", EXAMPLE),
    ("risk-radar-example", "/risks", EXAMPLE),
    ("bug-desk-empty", "/bugs", None),
    ("bug-desk-example", "/bugs", "#bug-example"),
    ("insights-example", "/insights", "#insights-example"),
    ("keys-drawer", "/requirements/story", "#key-chip"),
]


def _settle(page) -> None:
    """Wait for the answer to arrive and the fade-up to finish."""
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(700)


def main(argv: list[str]) -> int:
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
    OUT.mkdir(exist_ok=True)
    written: list[Path] = []

    with sync_playwright() as play:
        browser = play.chromium.launch()
        try:
            for label, (width, height) in SIZES.items():
                context = browser.new_context(
                    viewport={"width": width, "height": height},
                    device_scale_factor=2,
                )
                page = context.new_page()
                for name, path, click in SHOTS:
                    page.goto(base + path, wait_until="domcontentloaded")
                    _settle(page)
                    if click:
                        target = page.locator(click)
                        if target.count() == 0:
                            # Worth a PNG of the page as it stands anyway.
                            print(f"note: no {click} on {path}, shooting as-is")
                        else:
                            target.first.click()
                            _settle(page)
                    shot = OUT / f"{name}-{label}.png"
                    page.screenshot(path=str(shot), full_page=True)
                    written.append(shot)
                    print(f"wrote {shot.relative_to(ROOT)}")
                context.close()
        finally:
            browser.close()

    print(f"\n{len(written)} PNGs in {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
