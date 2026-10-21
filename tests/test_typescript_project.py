"""A generated TypeScript project must be one `npx tsc --noEmit` can read.

A real run downloaded Playwright · TypeScript with no compiler, no Node
types and no tsconfig.json, so the type-check could not even start. The
files and the dependencies are checked here always; the project is really
compiled when QAG_TS_COMPILE=1 says there is a Node to do it with.
"""

import json
import os
import shutil
import subprocess
import zipfile
from io import BytesIO

import pytest

from qagenius.automation_checks import (
    TS_DEV_DEPENDENCIES,
    TSCONFIG_NAME,
    check_project,
    project_files,
)
from qagenius.automation_exports import TOP_FOLDER, build_zip, useful_notes
from tests.factories import script


def _names(**overrides) -> list[str]:
    return [file.name for file in project_files(script(**overrides))]


def test_a_typescript_project_ships_a_tsconfig():
    assert TSCONFIG_NAME in _names()


def test_the_compiler_and_the_node_types_are_in_the_dev_dependencies():
    files = project_files(script())
    package = next(file for file in files if file.name == "package.json")
    dev = json.loads(package.code)["devDependencies"]
    for name in ("typescript", "@types/node", "@playwright/test"):
        assert name in dev, name


def test_the_tsconfig_says_what_it_has_to_say():
    files = project_files(script())
    config = next(file for file in files if file.name == TSCONFIG_NAME)
    options = json.loads(config.code)["compilerOptions"]
    assert options["types"] == ["node", "@playwright/test"]
    assert options["strict"] is True
    assert options["noEmit"] is True


def test_a_version_the_ai_already_chose_is_left_alone():
    chosen = json.dumps({"devDependencies": {"typescript": "^5.0.0"}})
    files = project_files(script(requirements_txt=chosen))
    package = next(file for file in files if file.name == "package.json")
    dev = json.loads(package.code)["devDependencies"]
    assert dev["typescript"] == "^5.0.0"
    assert dev["@types/node"] == TS_DEV_DEPENDENCIES["@types/node"]


def test_a_package_json_that_does_not_parse_is_left_for_the_syntax_check():
    broken = '{"devDependencies": }'
    files = project_files(script(requirements_txt=broken))
    package = next(file for file in files if file.name == "package.json")
    assert package.code == broken


def test_a_python_project_gets_none_of_this():
    names = _names(
        framework="Playwright (Python)",
        page_object_file_name="pages/login_page.py",
        page_object_code="class LoginPage:\n    pass\n",
        test_file_name="tests/test_login.py",
        test_code="def test_tc_001():\n    assert True\n",
        config_file_name=None,
        config_code=None,
        requirements_txt="pytest\n",
    )
    assert TSCONFIG_NAME not in names
    assert "package.json" not in names


def test_a_javascript_project_gets_none_of_this():
    names = _names(
        page_object_file_name="pages/LoginPage.js",
        test_file_name="tests/login.spec.js",
        config_file_name="playwright.config.js",
    )
    assert TSCONFIG_NAME not in names


# ── the notes that argue with the run steps ─────────────────────────────────


def test_a_note_that_builds_a_second_project_is_hidden():
    kept = useful_notes(
        [
            "mkdir aurora-automation && cd aurora-automation",
            "npm init -y",
            "npm install",
            "npx playwright install",
        ]
    )
    assert kept == ["npm install", "npx playwright install"]


def test_a_note_about_the_folder_we_actually_unzipped_is_kept():
    assert useful_notes([f"cd {TOP_FOLDER}"]) == [f"cd {TOP_FOLDER}"]


# ── the real compile, when there is a Node to do it with ────────────────────

# The compile needs the dependencies the project asks for, which means a
# real npm install over the network. That is a CI job, not a unit test.
npm = shutil.which("npm")
npx = shutil.which("npx")
COMPILE = os.environ.get("QAG_TS_COMPILE") == "1"

# A Playwright project as one is really written, so the compile is about the
# scaffolding QA-Genius adds and not about a one-line fixture.
PAGE_OBJECT = """import { Page } from '@playwright/test';

export class LoginPage {
  constructor(private readonly page: Page) {}

  async open(): Promise<void> {
    await this.page.goto('/sign-in');
  }
}
"""

TEST_CODE = """import { expect, test } from '@playwright/test';
import { LoginPage } from '../pages/LoginPage';

test('TC-001: the account locks', async ({ page }) => {
  const login = new LoginPage(page);
  await login.open();
  await expect(page).toHaveURL(/sign-in/);
});
"""

CONFIG_CODE = """import { defineConfig } from '@playwright/test';

export default defineConfig({ testDir: './tests' });
"""


def _real_script():
    return script(
        page_object_code=PAGE_OBJECT, test_code=TEST_CODE, config_code=CONFIG_CODE
    )


def _unzip(target) -> None:
    real = _real_script()
    with zipfile.ZipFile(BytesIO(build_zip(real, check_project(real, [])))) as archive:
        archive.extractall(target)


def _run(command, cwd):
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )


@pytest.mark.skipif(
    not COMPILE or npm is None or npx is None,
    reason="set QAG_TS_COMPILE=1 with node installed to really compile",
)
def test_the_generated_project_type_checks(tmp_path):
    _unzip(tmp_path)
    root = tmp_path / TOP_FOLDER
    assert (root / TSCONFIG_NAME).exists()
    installed = _run([npm, "install", "--no-audit", "--no-fund"], root)
    assert installed.returncode == 0, installed.stdout + installed.stderr
    checked = _run([npx, "--no-install", "tsc", "--noEmit", "-p", TSCONFIG_NAME], root)
    assert checked.returncode == 0, checked.stdout + checked.stderr
