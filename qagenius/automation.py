"""Turn selected test cases into an automation request, and check the generated project in code."""

from qagenius.models import TestCase

FRAMEWORK_OPTIONS = {          # label -> (framework, language)
    "Playwright · TypeScript": ("Playwright (JavaScript)", "TypeScript"),
    "Playwright · JavaScript": ("Playwright (JavaScript)", "JavaScript"),
    "Playwright · Python": ("Playwright (Python)", "Python"),
    "Cypress · JavaScript": ("Cypress (JavaScript)", "JavaScript"),
    "Selenium · Python": ("Selenium (Python)", "Python"),
}
STRUCTURE_OPTIONS = {
    "Page Object Model": "Page Object Model",
    "Flat scripts": "Flat scripts (no POM)",
}
BROWSER_OPTIONS = ("chromium", "firefox", "webkit")
DEFAULT_BASE_URL = "https://staging.aurora-shop.dev"
MAX_SELECTED = 12
SCENARIO_LIMIT = 12000

# Added when the selection does not fit in SCENARIO_LIMIT.
TRUNCATION_NOTE = "(Further selected cases were left out to keep the request short.)"

# Appended after the v1 prompt text, which is never edited.
INSTRUCTION = (
    "Write exactly one automated test per test case above. Each test's title must start "
    'with its test case id, for example "TC-001: Account locks after 5 failed attempts". '
    "Do not use fixed waits (no waitForTimeout, time.sleep or cy.wait with a number); "
    "wait for elements or network instead."
)


def effective_base_url(base_url: str) -> str:
    """The URL to test against: what the user typed, or the sample staging site."""
    return (base_url or "").strip() or DEFAULT_BASE_URL


def _case_block(case: TestCase) -> str:
    """One test case as prompt text. The Test data line appears only when there is some."""
    lines = [
        f"{case.id}: {case.title}",
        f"Pre-conditions: {case.pre_conditions}",
        "Steps:",
    ]
    lines.extend(f"{number}. {step}" for number, step in enumerate(case.steps, start=1))
    lines.append(f"Expected result: {case.expected_result}")
    test_data = (case.test_data or "").strip()
    if test_data:
        lines.append(f"Test data: {test_data}")
    return "\n".join(lines)


def build_scenario(cases: list[TestCase]) -> str:
    """The selected cases as one scenario. A long selection keeps whole cases only."""
    blocks = [_case_block(case) for case in cases]
    scenario = "\n\n".join(blocks)
    if len(scenario) <= SCENARIO_LIMIT:
        return scenario
    kept: list[str] = []
    for block in blocks:
        if len("\n\n".join([*kept, block])) > SCENARIO_LIMIT:
            break
        kept.append(block)
    return "\n\n".join([*kept, TRUNCATION_NOTE])


def build_user_text(base_user_text: str, cases: list[TestCase], base_url: str) -> str:
    """The v1 user text plus the base URL and the one-test-per-case rule."""
    return f"{base_user_text}\n\nBase URL: {effective_base_url(base_url)}\n{INSTRUCTION}"
