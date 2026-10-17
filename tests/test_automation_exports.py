"""The ZIP: one safe top folder, exact file contents, and a README carrying the checks."""

import io
import zipfile

from qagenius.automation_checks import check_project, project_files
from qagenius.automation_exports import ACTIVATE, TOP_FOLDER, build_zip, run_steps
from tests.factories import script


def _archive(data: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(data))


def _build(selected_ids: list[str], **overrides) -> tuple[bytes, zipfile.ZipFile]:
    project = script(**overrides)
    report = check_project(project, selected_ids)
    data = build_zip(project, report)
    return data, _archive(data)


def test_every_entry_sits_under_one_top_folder() -> None:
    _, archive = _build(["TC-001"])
    names = archive.namelist()
    assert names
    assert all(name.startswith(f"{TOP_FOLDER}/") for name in names)


def test_no_entry_can_escape_the_folder() -> None:
    _, archive = _build(["TC-001"], test_file_name="../evil.ts")
    for name in archive.namelist():
        assert ".." not in name
        assert not name.startswith("/")
        assert ":" not in name
    assert f"{TOP_FOLDER}/test_cases.ts" in archive.namelist()


def test_file_contents_round_trip_exactly() -> None:
    code = "test('TC-001: the account locks', async () => {\n  // nothing\n});\n"
    _, archive = _build(["TC-001"], test_code=code)
    assert archive.read(f"{TOP_FOLDER}/tests/login.spec.ts").decode("utf-8") == code


def test_the_readme_carries_the_run_command_and_setup_steps() -> None:
    _, archive = _build(["TC-001"])
    readme = archive.read(f"{TOP_FOLDER}/README.md").decode("utf-8")
    assert "npx playwright test" in readme
    assert "1. npm install" in readme
    assert "Playwright (JavaScript) with TypeScript" in readme


def test_the_readme_carries_the_checks() -> None:
    code = "test('TC-001: locks', async ({ page }) => {\n  await page.waitForTimeout(500);\n});\n"
    _, archive = _build(["TC-001", "TC-004"], test_code=code, page_object_code=None)
    readme = archive.read(f"{TOP_FOLDER}/README.md").decode("utf-8")

    assert "## Checks" in readme
    assert "1 of 2 selected test cases have a matching test." in readme
    assert "No test mentions TC-004" in readme
    assert "tests/login.spec.ts — basic check passed" in readme
    assert "Fixed wait" in readme
    assert "not a full compile" in readme


def test_a_clean_project_says_there_are_no_findings() -> None:
    _, archive = _build(["TC-001"])
    readme = archive.read(f"{TOP_FOLDER}/README.md").decode("utf-8")
    assert "### Warnings and errors\n\nNone." in readme


def test_design_notes_are_left_out_when_there_are_none() -> None:
    _, archive = _build(["TC-001"], design_notes=None)
    readme = archive.read(f"{TOP_FOLDER}/README.md").decode("utf-8")
    assert "## Design notes" not in readme


def test_the_zip_opens_and_reports_no_bad_entries() -> None:
    data, archive = _build(["TC-001"], requirements_txt='{"name": "suite"}\n')
    assert data[:2] == b"PK"
    assert archive.testzip() is None
    # A TypeScript project keeps npm's name for its dependency file, in the
    # ZIP as well as in the file list.
    assert f"{TOP_FOLDER}/package.json" in archive.namelist()


# ---------------------------------------------------------------- run steps
# A real run told the user to "mkdir aurora-automation && npm init -y", which
# builds an empty project beside the one they just downloaded. These steps are
# computed from the files in the ZIP instead.

PACKAGE_JSON = '{"devDependencies": {"@playwright/test": "^1.40.0"}}\n'

PYTHON_PROJECT = dict(
    framework="Playwright (Python)",
    page_object_file_name="pages/login_page.py",
    page_object_code="class LoginPage:\n    pass\n",
    test_file_name="tests/test_login.py",
    test_code="def test_tc_001_locks():\n    pass\n",
    config_file_name=None,
    config_code=None,
)
SELENIUM_PROJECT = dict(PYTHON_PROJECT, framework="Selenium (Python)")
JS_NAMES = dict(
    page_object_file_name="pages/LoginPage.js",
    test_file_name="tests/login.spec.js",
    config_file_name="playwright.config.js",
)


def _steps(**overrides) -> list[str]:
    project = script(**overrides)
    return run_steps(project, project_files(project))


def test_playwright_node_installs_from_the_package_json_it_shipped() -> None:
    assert _steps(requirements_txt=PACKAGE_JSON) == [
        "cd qa-genius-automation",
        "npm install",
        "npx playwright install",
        "npx playwright test",
    ]


def test_playwright_typescript_without_dependencies_also_installs_typescript() -> None:
    assert _steps() == [
        "cd qa-genius-automation",
        "npm init -y && npm install -D @playwright/test typescript",
        "npx playwright install",
        "npx playwright test",
    ]


def test_playwright_javascript_without_dependencies_leaves_typescript_out() -> None:
    assert _steps(**JS_NAMES) == [
        "cd qa-genius-automation",
        "npm init -y && npm install -D @playwright/test",
        "npx playwright install",
        "npx playwright test",
    ]


def test_cypress_runs_cypress() -> None:
    assert _steps(framework="Cypress (JavaScript)", **JS_NAMES) == [
        "cd qa-genius-automation",
        "npm init -y && npm install -D cypress",
        "npx cypress run",
    ]


def test_cypress_with_a_package_json_installs_from_it() -> None:
    options = dict(JS_NAMES, framework="Cypress (JavaScript)")
    assert _steps(requirements_txt=PACKAGE_JSON, **options) == [
        "cd qa-genius-automation",
        "npm install",
        "npx cypress run",
    ]


def test_playwright_python_makes_a_venv_and_installs_the_browsers() -> None:
    deps = "pytest\npytest-playwright\n"
    assert _steps(requirements_txt=deps, **PYTHON_PROJECT) == [
        "cd qa-genius-automation",
        "python -m venv .venv",
        ACTIVATE,
        "pip install -r requirements.txt",
        "playwright install",
        "pytest",
    ]


def test_playwright_python_without_a_requirements_file_names_the_packages() -> None:
    assert _steps(**PYTHON_PROJECT) == [
        "cd qa-genius-automation",
        "python -m venv .venv",
        ACTIVATE,
        "pip install pytest pytest-playwright",
        "playwright install",
        "pytest",
    ]


def test_selenium_python_skips_the_browser_install() -> None:
    assert _steps(**SELENIUM_PROJECT) == [
        "cd qa-genius-automation",
        "python -m venv .venv",
        ACTIVATE,
        "pip install pytest selenium",
        "pytest",
    ]


def test_selenium_python_installs_from_requirements_when_there_is_one() -> None:
    assert _steps(requirements_txt="pytest\nselenium\n", **SELENIUM_PROJECT) == [
        "cd qa-genius-automation",
        "python -m venv .venv",
        ACTIVATE,
        "pip install -r requirements.txt",
        "pytest",
    ]


def test_the_activate_line_covers_windows_too() -> None:
    assert "source .venv/bin/activate" in ACTIVATE
    assert r".venv\Scripts\activate" in ACTIVATE


def test_the_readme_runs_the_project_you_downloaded() -> None:
    _, archive = _build(["TC-001"], requirements_txt=PACKAGE_JSON)
    readme = archive.read(f"{TOP_FOLDER}/README.md").decode("utf-8")
    assert "cd qa-genius-automation" in readme
    assert "npm install" in readme
    assert "mkdir" not in readme


def test_the_readme_keeps_the_ai_instructions_as_notes() -> None:
    _, archive = _build(["TC-001"])
    readme = archive.read(f"{TOP_FOLDER}/README.md").decode("utf-8")
    assert "### Notes from the AI" in readme
    assert "1. npm install" in readme
    assert readme.index("## Run it") < readme.index("### Notes from the AI")
