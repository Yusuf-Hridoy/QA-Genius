"""File-name safety, traceability, syntax checks and fixed-wait warnings. No AI, no network."""

from qagenius.automation_checks import (
    WAIT_MESSAGE,
    basic_js_check,
    check_project,
    project_files,
    safe_file_name,
)
from tests.factories import script

BACKTICK = "`"


def test_a_plain_path_is_kept() -> None:
    assert safe_file_name("tests/login.spec.ts") == "tests/login.spec.ts"


def test_parent_directory_is_rejected() -> None:
    assert safe_file_name("../../etc/passwd") is None


def test_leading_slash_is_stripped() -> None:
    assert safe_file_name("/abs/x.ts") == "abs/x.ts"


def test_leading_dot_slash_is_stripped() -> None:
    assert safe_file_name("./tests/x.ts") == "tests/x.ts"


def test_a_windows_drive_is_rejected() -> None:
    assert safe_file_name("C:\\x.ts") is None


def test_more_than_three_parts_is_rejected() -> None:
    assert safe_file_name("a/b/c/d.ts") is None


def test_a_space_in_the_name_is_rejected() -> None:
    assert safe_file_name("a b.ts") is None


def test_an_empty_name_is_rejected() -> None:
    assert safe_file_name("") is None


def test_a_duplicate_name_gets_a_number() -> None:
    files = project_files(
        script(
            page_object_file_name="tests/login.spec.ts",
            page_object_code="export class LoginPage {}\n",
            test_file_name="tests/login.spec.ts",
        )
    )
    assert [file.name for file in files] == [
        "tests/login.spec.ts",
        "tests/login.spec_2.ts",
        "playwright.config.ts",
    ]


def test_an_unsafe_name_falls_back_to_a_safe_one() -> None:
    files = project_files(script(test_file_name="../evil.ts", page_object_code=None))
    assert [file.name for file in files] == ["test_cases.ts", "playwright.config.ts"]


def test_empty_code_is_not_a_file() -> None:
    files = project_files(script(page_object_code="   ", config_code=None))
    assert [file.name for file in files] == ["tests/login.spec.ts"]


def test_requirements_txt_is_added_last() -> None:
    files = project_files(script(requirements_txt="pytest\n"))
    assert files[-1].name == "requirements.txt"
    assert files[-1].code == "pytest\n"


def test_an_id_in_the_test_code_is_traced() -> None:
    report = check_project(
        script(test_code="test('TC-001: locks', async () => {});\n"), ["TC-001"]
    )
    assert report.traced == ["TC-001"]
    assert report.missing == []


def test_a_longer_id_does_not_count_as_a_shorter_one() -> None:
    report = check_project(
        script(test_code="test('TC-0011: locks', async () => {});\n"), ["TC-001"]
    )
    assert report.traced == []
    assert report.missing == ["TC-001"]


def test_a_lowercase_id_counts() -> None:
    report = check_project(
        script(test_code="test('tc-002: locks', async () => {});\n"), ["TC-002"]
    )
    assert report.traced == ["TC-002"]


def test_a_missing_id_is_reported() -> None:
    report = check_project(
        script(test_code="test('TC-001: locks', async () => {});\n"),
        ["TC-001", "TC-004"],
    )
    assert report.traced == ["TC-001"]
    assert report.missing == ["TC-004"]


def test_valid_python_is_valid() -> None:
    report = check_project(
        script(
            framework="Playwright (Python)",
            page_object_code=None,
            config_code=None,
            test_file_name="tests/test_login.py",
            test_code="def test_tc_001():\n    assert True\n",
        ),
        ["TC-001"],
    )
    assert report.syntax["tests/test_login.py"] == "valid"
    assert report.findings == []


def test_broken_python_reports_the_line() -> None:
    report = check_project(
        script(
            framework="Playwright (Python)",
            page_object_code=None,
            config_code=None,
            test_file_name="tests/test_login.py",
            test_code="def test_one():\n    assert True\n\ndef test_two(:\n    pass\n",
        ),
        [],
    )
    assert report.syntax["tests/test_login.py"] == "error"
    error = report.findings[0]
    assert error.level == "error"
    assert error.line == 4
    assert error.message.startswith("Python syntax error:")


def test_typescript_with_braces_in_strings_and_templates_passes() -> None:
    code = "\n".join(
        [
            "// a closing } in a comment is not a brace",
            "/* neither is this one: } */",
            'const shape = "{ not a brace }";',
            "const label = " + BACKTICK + "TC-001: ${items.filter((i) => { return i.ok; }).length}"
            + BACKTICK + ";",
            "const nested = " + BACKTICK + "a${" + BACKTICK + "b${1}c" + BACKTICK + "}d"
            + BACKTICK + ";",
            "const quoted = 'it\\'s fine';",
            "export { shape, label, nested, quoted };",
        ]
    )
    assert basic_js_check(code) is None

    report = check_project(script(page_object_code=None, config_code=None, test_code=code), [])
    assert report.syntax["tests/login.spec.ts"] == "basic check passed"


def test_an_unclosed_brace_reports_the_opening_line() -> None:
    code = "const a = 1;\nfunction go() {\n  return a;\n"
    assert basic_js_check(code) == (2, "Unclosed { opened on line 2")

    report = check_project(script(page_object_code=None, config_code=None, test_code=code), [])
    assert report.syntax["tests/login.spec.ts"] == "error"
    assert report.findings[0].line == 2


def test_an_unclosed_string_is_an_error() -> None:
    line, message = basic_js_check("const a = 'open;\nconst b = 2;\n")
    assert line == 1
    assert message.startswith("Unclosed '")


def test_an_unclosed_template_string_is_an_error() -> None:
    line, message = basic_js_check("const a = " + BACKTICK + "open;\n")
    assert line == 1
    assert "Unclosed" in message


def test_an_unclosed_block_comment_is_an_error() -> None:
    assert basic_js_check("const a = 1;\n/* still going\n") == (
        2,
        "Unclosed /* opened on line 2",
    )


def test_a_bracket_closed_out_of_order_is_an_error() -> None:
    line, message = basic_js_check("const a = [1, 2;\nconst b = (3];\n")
    assert line == 2
    assert message.startswith("Unexpected ]")


def test_a_stray_closing_bracket_is_an_error() -> None:
    assert basic_js_check("const a = 1;\n}\n") == (2, "Unexpected }")


def test_fixed_waits_are_warnings_with_line_numbers() -> None:
    code = "\n".join(
        [
            "test('TC-001: locks', async ({ page }) => {",
            "  await page.waitForTimeout(500);",
            "  await expect(page.getByRole('alert')).toBeVisible();",
            "});",
        ]
    )
    report = check_project(script(page_object_code=None, config_code=None, test_code=code), [])
    warnings = [finding for finding in report.findings if finding.level == "warning"]
    assert len(warnings) == 1
    assert warnings[0].line == 2
    assert warnings[0].file == "tests/login.spec.ts"
    assert warnings[0].message == WAIT_MESSAGE


def test_a_python_sleep_is_a_warning() -> None:
    code = "import time\n\n\ndef test_tc_001():\n    time.sleep(2)\n"
    report = check_project(
        script(
            framework="Selenium (Python)",
            page_object_code=None,
            config_code=None,
            test_file_name="tests/test_login.py",
            test_code=code,
        ),
        [],
    )
    warnings = [finding for finding in report.findings if finding.level == "warning"]
    assert [(warning.line, warning.message) for warning in warnings] == [(5, WAIT_MESSAGE)]


def test_waiting_for_a_named_request_is_not_a_warning() -> None:
    code = "test('TC-001: locks', () => {\n  cy.wait('@api');\n});\n"
    report = check_project(script(page_object_code=None, config_code=None, test_code=code), [])
    assert [finding for finding in report.findings if finding.level == "warning"] == []


def test_a_text_file_is_not_checked() -> None:
    report = check_project(
        script(page_object_code=None, config_code=None, requirements_txt="pytest\n"), []
    )
    assert report.syntax["requirements.txt"] == "not checked"


def test_broken_json_is_an_error() -> None:
    report = check_project(
        script(
            page_object_code=None,
            config_file_name="tsconfig.json",
            config_code='{"compilerOptions": }',
        ),
        [],
    )
    assert report.syntax["tsconfig.json"] == "error"
