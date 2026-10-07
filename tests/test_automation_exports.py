"""The ZIP: one safe top folder, exact file contents, and a README carrying the checks."""

import io
import zipfile

from qagenius.automation_checks import check_project
from qagenius.automation_exports import TOP_FOLDER, build_zip
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
    data, archive = _build(["TC-001"], requirements_txt="pytest\n")
    assert data[:2] == b"PK"
    assert archive.testzip() is None
    assert f"{TOP_FOLDER}/requirements.txt" in archive.namelist()
