"""Save a PNG of every Shadow QA surface, light and dark, 1366 and 390.

Three of the four surfaces need an AI answer to exist at all, so this script
does not drive the running app: it renders the result fragments through the
test client with the AI faked, writes them to standalone HTML files that link
public/style.css from disk, and shoots those with Playwright. No key is used
and no request leaves the machine.

    pip install playwright
    playwright install chromium
    python scripts/shadow_qa_screens.py

The PNGs and the HTML land in ui-screens/shadow-qa/, which git ignores.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "ui-screens" / "shadow-qa"
STYLE = (ROOT / "public" / "style.css").resolve()

SIZES = {"desktop": (1366, 900), "phone": (390, 844)}
THEMES = ("light", "dark")

PAGE = """<!doctype html>
<html lang="en"{theme}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="{style}">
</head>
<body>
<div class="layout">
  <main class="content">
    <p class="eyebrow">{title}</p>
    {body}
  </main>
</div>
</body>
</html>
"""


def _fragments() -> dict[str, str]:
    """The four result cards, rendered with a faked AI."""
    from fastapi.testclient import TestClient

    import main
    from qagenius import llm
    from qagenius.models import AmbiguityAnalysis, FailureMode, RiskAnalysis
    from tests.factories import (
        LOCKOUT_CRITERIA,
        LOCKOUT_STORY,
        PROFILE_CRITERIA,
        PROFILE_STORY,
        case,
        script,
        suite,
    )

    client = TestClient(main.app)
    keys = {"X-QAG-Keys": json.dumps([{"provider": "gemini", "key": "demo"}])}
    samples = ROOT / "qagenius" / "samples"
    story_result = AmbiguityAnalysis.model_validate(
        json.loads((samples / "story_check.json").read_text(encoding="utf-8"))["result"]
    )
    real = llm.generate_json
    shots: dict[str, str] = {}

    def fake(answer):
        def _call(keys_, system, user, schema):
            return answer, 0, []

        return _call

    try:
        llm.generate_json = fake(story_result)
        shots["story-epic-banner"] = client.post(
            "/requirements/story/run",
            data={"user_story": PROFILE_STORY},
            headers=keys,
        ).text

        llm.generate_json = fake(suite(case(case_id="TC-001")))
        shots["test-cases-principal"] = client.post(
            "/requirements/test-cases/run",
            data={
                "user_story": PROFILE_STORY,
                "criteria_json": json.dumps(PROFILE_CRITERIA),
                "coverage_focus": ["Functional", "Negative"],
            },
            headers=keys,
        ).text

        llm.generate_json = fake(
            RiskAnalysis(
                failure_modes=[
                    FailureMode(
                        id="R1",
                        title="The lock never lifts",
                        category="reliability",
                        effect="Shoppers cannot sign in again.",
                        cause="The unlock job never runs.",
                        severity=4,
                        likelihood=3,
                        detectability=3,
                    )
                ]
            )
        )
        shots["risk-radar-principal"] = client.post(
            "/risks/run",
            data={
                "user_story": LOCKOUT_STORY,
                "criteria_json": json.dumps(LOCKOUT_CRITERIA),
                "cases_json": json.dumps([case(case_id="TC-001").model_dump()]),
            },
            headers=keys,
        ).text

        bad = (
            "test.only('TC-001: it signs in', async ({ page }) => {\n"
            "  const password = 'Harbour-Lantern-42';\n"
            "  await page.goto('/');\n"
            "});\n"
        )
        llm.generate_json = fake(
            script(test_file_name="tests/login.spec.ts", test_code=bad)
        )
        shots["automation-principal"] = client.post(
            "/requirements/automation/run",
            data={
                "selected_json": json.dumps([case(case_id="TC-001").model_dump()]),
                "framework_choice": "Playwright · TypeScript",
                "structure_choice": "Page Object Model",
                "browsers": ["chromium"],
                "base_url": "https://example.com",
            },
            headers=keys,
        ).text
    finally:
        llm.generate_json = real
    return shots


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

    OUT.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    pages: dict[str, Path] = {}
    for name, body in _fragments().items():
        path = OUT / f"{name}.html"
        path.write_text(
            PAGE.format(
                theme="",
                title=name.replace("-", " "),
                style=STYLE.as_uri(),
                body=body,
            ),
            encoding="utf-8",
        )
        pages[name] = path

    with sync_playwright() as play:
        browser = play.chromium.launch()
        try:
            for theme in THEMES:
                for size, (width, height) in SIZES.items():
                    context = browser.new_context(
                        viewport={"width": width, "height": height},
                        device_scale_factor=2,
                        color_scheme=theme,
                    )
                    page = context.new_page()
                    for name, path in pages.items():
                        page.goto(path.as_uri(), wait_until="load")
                        page.evaluate(
                            "theme => document.documentElement.setAttribute("
                            "'data-theme', theme)",
                            theme,
                        )
                        page.wait_for_timeout(120)
                        shot = OUT / f"{name}-{theme}-{size}.png"
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
