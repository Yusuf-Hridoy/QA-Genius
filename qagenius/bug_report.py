"""Build the bug-report request from the form and check the AI's report in code."""

from dataclasses import dataclass

NOTES_MIN, NOTES_LIMIT = 20, 3000
FIELD_LIMIT = 100  # os, browser, build
URL_LIMIT = 500
DEVICE_OPTIONS = ("Not specified", "Desktop", "Mobile", "Tablet")
MAX_ATTEMPTS = 100

# Appended only when the user attached a screenshot.
SCREENSHOT_NOTE = (
    "A screenshot is attached. Describe only what is actually visible in it in "
    '"screenshot_annotations"; do not invent UI elements that are not shown.'
)

NOTES_ERROR = f"Bug notes must be {NOTES_MIN} to {NOTES_LIMIT} characters."
DEVICE_ERROR = "Please pick a device from the list."
FIELD_ERROR = f"Keep each environment field under {FIELD_LIMIT} characters."
URL_ERROR = "The URL must start with http:// or https://."
TOTAL_ERROR = f"Total attempts must be between 1 and {MAX_ATTEMPTS}."
HAPPENED_ERROR = "Times it happened can't be more than total attempts."


@dataclass(frozen=True)
class BugInput:
    notes: str
    device: str = "Not specified"
    os: str = ""
    browser: str = ""
    build: str = ""
    url: str = ""
    total_attempts: int = 1
    successful_attempts: int = 0  # times the bug happened
    has_screenshot: bool = False


def reproducibility_text(total: int, happened: int) -> str:
    """How often it happened, worked out from the counts the tester gave."""
    if happened <= 0:
        return "Not reproduced yet"
    if happened >= total:
        return "Always"
    return f"Intermittent ({happened} of {total})"


def environment_text(bug: BugInput) -> str:
    """The environment line for the prompt and the report. Only what was filled in."""
    parts = []
    if bug.device and bug.device != "Not specified":
        parts.append(f"Device: {bug.device}")
    if bug.os.strip():
        parts.append(f"OS: {bug.os.strip()}")
    if bug.browser.strip():
        parts.append(f"Browser/App: {bug.browser.strip()}")
    if bug.build.strip():
        parts.append(f"Build/Env: {bug.build.strip()}")
    if bug.url.strip():
        parts.append(f"URL: {bug.url.strip()}")
    return "; ".join(parts) or "Not provided"


def build_user_text(base_user_text: str, bug: BugInput) -> str:
    """The v1 user text plus the facts code worked out. The v1 prompt is untouched."""
    text = (
        f"{base_user_text}\n\n"
        f"Environment Details: {environment_text(bug)}\n"
        f"Reproducibility: {reproducibility_text(bug.total_attempts, bug.successful_attempts)}\n"
        f"Total Attempts: {bug.total_attempts}\n"
        f"Times It Happened: {bug.successful_attempts}"
    )
    if bug.has_screenshot:
        text += f"\n{SCREENSHOT_NOTE}"
    return text


def validate_bug_input(
    notes: str = "",
    device: str = "Not specified",
    os: str = "",
    browser: str = "",
    build: str = "",
    url: str = "",
    total_attempts: int = 1,
    successful_attempts: int = 0,
    has_screenshot: bool = False,
) -> "BugInput | str":
    """BugInput, or a short error message for the user."""
    cleaned = (notes or "").strip()
    if not NOTES_MIN <= len(cleaned) <= NOTES_LIMIT:
        return NOTES_ERROR
    if device not in DEVICE_OPTIONS:
        return DEVICE_ERROR
    if any(len(field or "") > FIELD_LIMIT for field in (os, browser, build)):
        return FIELD_ERROR
    link = (url or "").strip()
    if len(link) > URL_LIMIT:
        return URL_ERROR
    if link and not (link.startswith("http://") or link.startswith("https://")):
        return URL_ERROR
    if not 1 <= total_attempts <= MAX_ATTEMPTS:
        return TOTAL_ERROR
    if not 0 <= successful_attempts <= total_attempts:
        return HAPPENED_ERROR
    return BugInput(
        notes=cleaned,
        device=device,
        os=(os or "").strip(),
        browser=(browser or "").strip(),
        build=(build or "").strip(),
        url=link,
        total_attempts=total_attempts,
        successful_attempts=successful_attempts,
        has_screenshot=has_screenshot,
    )
