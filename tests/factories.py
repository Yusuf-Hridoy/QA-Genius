"""Shared builders for test-case fixtures. Not a test module; pytest does not collect it."""

from qagenius.models import (
    AutomationScript,
    BugReport,
    TestCase,
    TestCaseList,
    TestSuiteSummary,
)
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


def bug_report(**overrides) -> BugReport:
    """A complete, valid bug report. Any field can be overridden by keyword."""
    values = {
        "title": "Checkout button does nothing on the second click in Safari",
        "severity": "High",
        "reproducibility_rate": "Often",
        "environment_details": "Device: Desktop; OS: macOS 14; Browser/App: Safari 17",
        "steps_to_reproduce": [
            "Open the Aurora Storefront cart with two items",
            "Click Checkout once and wait for the page",
            "Click Checkout a second time",
        ],
        "actual_result": "Nothing happens and the cart total shows 0",
        "expected_result": "The payment page opens with the correct total",
        "suggested_fix": "Disable the button until the first request resolves",
        "root_cause_category": "Race Condition",
        "business_impact": "Shoppers cannot pay, so the order is lost",
        "affected_users": "Desktop shoppers on Safari",
        "regression_risk": "Medium",
        "workaround": "Reload the cart page and click Checkout once",
        "related_areas": ["Cart totals", "Payment page"],
        "screenshot_annotations": ["Cart header showing a total of 0"],
        "jira_labels": ["checkout", "safari", "race-condition"],
        "suspected_pattern": "Race Condition",
        "related_issues": ["Cart badge keeps the old count"],
        "investigation_steps": [
            "Check the console for a duplicate POST",
            "Inspect the network tab for a second checkout call",
        ],
    }
    values.update(overrides)
    return BugReport(**values)


# ── the two stories the Shadow QA tests use (fictional) ───────────────────────

PROFILE_STORY = (
    "As a registered user, I want to seamlessly view and manage my personal "
    "information, security credentials, notification preferences, and privacy "
    "settings on a central User Profile page, so that I stay in control of my "
    "account. I can edit basic details (full name, email, phone number, bio, "
    "language, and timezone), upload, crop, or remove an avatar (JPEG/PNG/WebP "
    "up to 5MB), update my password with enforced strength criteria, configure "
    "two-factor authentication (2FA) via authenticator apps with recovery codes, "
    "review and revoke active login sessions across devices, link or unlink OAuth "
    "providers like Google or GitHub, toggle granular email, push, and theme "
    "preferences (Light/Dark mode) with instant auto-saving, and initiate "
    "multi-step permanent account deletion."
)

PROFILE_CRITERIA = [
    "The profile page shows the full name, email, phone number, bio, language and timezone",
    "The full name accepts at most 80 characters",
    "The bio accepts at most 160 characters",
    "An avatar must be a JPEG, PNG or WebP image under 5MB",
    "Changing the password requires the current password",
    "Enabling 2FA shows a 6-digit verification code step and ten recovery codes",
    "The account locks when a user exceeds 5 failed verification attempts "
    "within a 15-minute window",
    "A locked account stays locked for 30 minutes",
    "Active sessions list each device and its last active time, and can be revoked",
    "Preference toggles auto-save and persist across devices",
    "Account deletion requires the password and offers a 30-day grace period",
]

# The settings story from the real run that these fixes came out of. It says
# "password" without ever signing anybody in, and it names eight features.
BIG_STORY = (
    "As a registered user, I want to manage my profile, change my password, "
    "set up two-factor authentication with an authenticator app, see and "
    "revoke my active sessions, link my Google or GitHub account, choose "
    "light or dark theme with auto-saving, upload an avatar up to 5 MB, and "
    "permanently delete my account, so that my account is accurate and secure."
)

BIG_CRITERIA = [
    "The profile page shows the full name, email, phone number and bio",
    "Changing the password requires the current password",
    "Enabling two-factor shows a 6-digit verification code step",
    "An avatar must be a JPEG, PNG or WebP image under 5MB",
    "Active sessions list each device and can be revoked",
    "Deleting the account asks for the password again",
]

LOCKOUT_STORY = (
    "As a shopper, I want my Aurora Storefront account to lock quickly after "
    "too many wrong passwords so that my account stays safe."
)

LOCKOUT_CRITERIA = [
    "The account locks after 5 failed sign-in attempts",
    "A locked account stays locked for 30 minutes",
]


# Test B: the photo-upload run. Short, and every criterion states the same
# limit from a different side.
PHOTO_STORY = (
    "As a registered user, I want to upload a profile photo so that other "
    "users can recognise me."
)

PHOTO_CONTEXT = (
    "Profile page. Accepted formats: JPEG and PNG. Maximum size 2 MB. "
    "The photo is cropped to a square."
)

PHOTO_CRITERIA = [
    "The user can select a JPEG photo under 2 megabytes and upload it",
    "The user can select a PNG photo under 2 megabytes and upload it",
    "A photo larger than 2 megabytes is rejected with a message",
    "A file in a format other than JPEG or PNG is rejected with a message",
]


NAVBAR_STORY = (
    "As a reader, I want a navigation bar with a sidebar menu and breadcrumbs "
    "so that I can move around the site."
)

# The criteria from the nav-bar run, one of each shape the depth rule knows:
# AC-1 and AC-4 are about how it looks, AC-2 and AC-3 are plain behaviour,
# and only AC-5 can turn a reader away.
NAVBAR_CRITERIA = [
    "The sidebar highlights the item for the page the reader is on",
    "Breadcrumbs show the path to the current page, with a hint when the "
    "reader moves their mouse cursor over a step",
    "The menu opens and closes with the menu button on a phone",
    "The current item is shown in bold",
    "A reader without the admin role is not shown the admin link "
    "and cannot open it by URL",
]

_NAVBAR_CASES = (
    ("TC-001", "Functional", "AC-1", "The item for the open page is highlighted"),
    ("TC-002", "Functional", "AC-2", "Breadcrumbs show the path to the current page"),
    ("TC-003", "Functional", "AC-2", "Breadcrumbs follow a move to another section"),
    ("TC-004", "Functional", "AC-4", "The current item is bold"),
    ("TC-005", "Functional", "AC-3", "The menu button opens the menu on a phone"),
    ("TC-006", "Functional", "AC-3", "The menu closes again on the second press"),
    ("TC-007", "Negative", "AC-5", "A reader without the admin role is refused the admin URL"),
    ("TC-008", "Functional", "AC-5", "An admin sees the admin link in the sidebar"),
)


def navbar_run() -> tuple[TestCaseList, list[Criterion]]:
    """The 8 cases and 5 criteria from the nav-bar run, every criterion sound."""
    cases = [
        case(case_id=cid, category=category, traceability=trace, title=title)
        for cid, category, trace, title in _NAVBAR_CASES
    ]
    return suite(*cases), number_criteria(NAVBAR_CRITERIA)
