"""Shared builders for test-case fixtures. Not a test module; pytest does not collect it."""

from qagenius.models import AutomationScript, TestCase, TestCaseList, TestSuiteSummary
from qagenius.test_cases import Criterion, number_criteria


def case(
    case_id: str = "TC-001",
    category: str = "Functional",
    traceability: str = "AC-1",
    title: str | None = None,
    priority: str = "High",
    **overrides,
) -> TestCase:
    """A complete, valid test case. Any field can be overridden by keyword."""
    values = {
        "id": case_id,
        "title": title if title is not None else f"Case {case_id}",
        "category": category,
        "pre_conditions": "The shopper has an active Aurora Storefront account",
        "steps": ["Open the sign-in page", "Submit the form"],
        "expected_result": "The account locks for 30 minutes",
        "priority": priority,
        "test_data": "email=dana.reed@example.com",
        "bdd_scenario": "Given a shopper\nWhen they fail\nThen it locks",
        "automation_feasibility": "High",
        "automation_effort": "Low",
        "tags": ["login"],
        "traceability": traceability,
    }
    values.update(overrides)
    return TestCase(**values)


def suite(*cases: TestCase) -> TestCaseList:
    """A suite whose summary carries wrong numbers on purpose: nothing may read it."""
    return TestCaseList(
        test_cases=list(cases),
        summary=TestSuiteSummary(
            total_generated=999,
            category_breakdown=[],
            priority_breakdown=[],
            automation_coverage_potential="99%",
            coverage_gaps=[],
            recommendations=[],
        ),
    )


REAL_RUN_CRITERIA = [
    "The account locks after 5 consecutive incorrect password attempts",
    "A locked account stays locked for 15 minutes",
    "The shopper is told why sign-in failed",
    "The counter resets after a successful sign-in",
    "Support can unlock an account early",
    "The lock is recorded in the audit log",
]

_REAL_RUN_CASES = (
    ("TC-001", "Functional", "AC-1", "Account locks after 5 incorrect password attempts"),
    ("TC-002", "Functional", "AC-2", "Locked account stays locked for 15 minutes"),
    ("TC-003", "Negative", "AC-3", "Sign-in failure message does not name the field"),
    ("TC-004", "Boundary", "AC-4", "Counter resets to zero on a successful sign-in"),
    ("TC-005", "Functional", "AC-5", "Support unlocks an account from the console"),
    ("TC-006", "Edge Case", "AC-6", "Lock is written to the audit log"),
    ("TC-007", "Edge Case", "AC-1, AC-3", "Failures from two browsers share one counter"),
    ("TC-008", "Edge Case", "AC-1, AC-3", "Lock survives a browser restart"),
)


def real_run() -> tuple[TestCaseList, list[Criterion]]:
    """The 8 cases and 6 criteria from the Gemini run this phase is based on."""
    cases = [
        case(case_id=cid, category=category, traceability=trace, title=title)
        for cid, category, trace, title in _REAL_RUN_CASES
    ]
    return suite(*cases), number_criteria(REAL_RUN_CRITERIA)


def script(**overrides) -> AutomationScript:
    """A complete, valid automation project. Any field can be overridden by keyword."""
    values = {
        "framework": "Playwright (JavaScript) with TypeScript",
        "project_structure": ["pages/LoginPage.ts", "tests/login.spec.ts"],
        "page_object_file_name": "pages/LoginPage.ts",
        "page_object_code": "export class LoginPage {}\n",
        "test_file_name": "tests/login.spec.ts",
        "test_code": "test('TC-001: the account locks', async () => {});\n",
        "conftest_file_name": None,
        "conftest_code": None,
        "config_file_name": "playwright.config.ts",
        "config_code": "export default { testDir: './tests' };\n",
        "requirements_txt": None,
        "setup_instructions": ["npm install", "npx playwright install"],
        "execution_command": "npx playwright test",
        "design_notes": "Role-based locators, one test per test case.",
    }
    values.update(overrides)
    return AutomationScript(**values)
