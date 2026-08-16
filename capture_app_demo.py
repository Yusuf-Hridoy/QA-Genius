"""
Capture real QA-Genius app interactions via Playwright for the showcase video.
Outputs raw screen recordings to assets/recordings/.
"""

from pathlib import Path
import time

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8501"
RECORD_DIR = Path("assets/recordings")
RECORD_DIR.mkdir(parents=True, exist_ok=True)

VIEWPORT = {"width": 1920, "height": 1080}


def wait_for_app_ready(page):
    # Wait for the top bar / logo to appear
    page.wait_for_selector("text=QA-Genius", timeout=30000)
    page.wait_for_timeout(3000)


def click_tab(page, tab_name: str):
    page.get_by_text(tab_name).first.click()
    page.wait_for_timeout(1500)


def fill_textarea_by_placeholder(page, placeholder_text: str, value: str):
    locator = page.locator(f'textarea[placeholder*="{placeholder_text}"]')
    locator.scroll_into_view_if_needed()
    locator.fill(value)
    page.wait_for_timeout(500)


def fill_textarea_by_label(page, label: str, value: str):
    # aria-label is uppercase in the app
    locator = page.locator(f'textarea[aria-label="{label}"]')
    if locator.count() == 0:
        # Try case-insensitive partial match via JS
        locator = page.locator("textarea").filter(has_text=value[:0])  # dummy fallback
        # Fallback: find visible textarea near the label text
        locator = page.locator("textarea").locator("visible=true").last
    locator.scroll_into_view_if_needed()
    locator.fill(value)
    page.wait_for_timeout(500)


def fill_visible_textarea(page, value: str):
    """Fill the last visible textarea (main input field)."""
    locators = page.locator("textarea").all()
    for ta in reversed(locators):
        if ta.is_visible():
            ta.scroll_into_view_if_needed()
            ta.fill(value)
            page.wait_for_timeout(500)
            return
    raise RuntimeError("No visible textarea found")


def click_button_by_text(page, text: str):
    page.get_by_text(text).first.click()


def wait_for_generation(page):
    """Wait for Streamlit spinner to appear then disappear."""
    try:
        page.locator(".stSpinner").wait_for(state="visible", timeout=10000)
        print("  spinner visible")
    except Exception:
        pass
    try:
        page.locator(".stSpinner").wait_for(state="hidden", timeout=120000)
        print("  spinner hidden")
    except Exception:
        pass
    page.wait_for_timeout(2500)


def capture_story_analyzer(page, record_path: Path):
    print("Recording Story Analyzer...")
    page.goto(BASE_URL)
    wait_for_app_ready(page)
    # Already on Story Analyzer by default
    page.wait_for_timeout(2000)
    fill_visible_textarea(page, "As a user, I want to login quickly so that I can access my account.")
    page.wait_for_timeout(1000)
    click_button_by_text(page, "Analyze Story")
    wait_for_generation(page)


def capture_test_cases(page, record_path: Path):
    print("Recording Test Cases...")
    click_tab(page, "Test Cases")
    fill_visible_textarea(page, "As a user, I want to log in with email and password. The system should lock the account after 5 failed attempts.")
    page.wait_for_timeout(1000)
    click_button_by_text(page, "Generate Test Cases")
    wait_for_generation(page)


def capture_bug_report(page, record_path: Path):
    print("Recording Bug Report...")
    click_tab(page, "Bug Report")
    fill_visible_textarea(page, "500 error on checkout after applying coupon code. Happens only for logged-in users.")
    page.wait_for_timeout(1000)
    click_button_by_text(page, "Format Bug Report")
    wait_for_generation(page)


def capture_quick_tabs(page, record_path: Path):
    print("Recording quick tab montage...")
    for tab in ["Quality Analytics", "Automation Script", "Schema Validator", "Security Tests", "Performance Tests"]:
        click_tab(page, tab)
        page.wait_for_timeout(1000)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport=VIEWPORT,
            color_scheme="dark",
            record_video_dir=str(RECORD_DIR),
            record_video_size=VIEWPORT,
        )
        page = context.new_page()

        # Record Story Analyzer
        capture_story_analyzer(page, RECORD_DIR / "story_analyzer.webm")

        # Record Test Cases
        capture_test_cases(page, RECORD_DIR / "test_cases.webm")

        # Record Bug Report
        capture_bug_report(page, RECORD_DIR / "bug_report.webm")

        # Quick montage of remaining tabs
        capture_quick_tabs(page, RECORD_DIR / "quick_tabs.webm")

        context.close()
        browser.close()

        # Print video paths
        print("\nRecorded videos:")
        for v in RECORD_DIR.glob("*.webm"):
            print(f"  {v}")


if __name__ == "__main__":
    main()
