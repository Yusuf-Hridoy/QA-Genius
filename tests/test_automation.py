"""The automation request text: exact scenario format, truncation, and the appended rules."""

from qagenius.automation import (
    DEFAULT_BASE_URL,
    FRAMEWORK_OPTIONS,
    SCENARIO_LIMIT,
    STRUCTURE_OPTIONS,
    TRUNCATION_NOTE,
    build_scenario,
    build_user_text,
)
from tests.factories import case


def test_scenario_format_for_two_cases() -> None:
    with_data = case(
        case_id="TC-001",
        title="Account locks after 5 consecutive incorrect password attempts",
        pre_conditions="The shopper has an active account",
        steps=["Open the sign-in page", "Submit a wrong password 5 times"],
        expected_result="The account is locked",
        test_data="email=dana.reed@example.com",
    )
    without_data = case(
        case_id="TC-002",
        title="Locked account refuses the correct password",
        pre_conditions="The account is locked",
        steps=["Submit the correct password"],
        expected_result="Sign-in is refused",
        test_data=None,
    )
    assert build_scenario([with_data, without_data]) == (
        "TC-001: Account locks after 5 consecutive incorrect password attempts\n"
        "Pre-conditions: The shopper has an active account\n"
        "Steps:\n"
        "1. Open the sign-in page\n"
        "2. Submit a wrong password 5 times\n"
        "Expected result: The account is locked\n"
        "Test data: email=dana.reed@example.com\n"
        "\n"
        "TC-002: Locked account refuses the correct password\n"
        "Pre-conditions: The account is locked\n"
        "Steps:\n"
        "1. Submit the correct password\n"
        "Expected result: Sign-in is refused"
    )


def test_blank_test_data_adds_no_line() -> None:
    scenario = build_scenario([case(case_id="TC-007", test_data="   ")])
    assert "Test data:" not in scenario


def test_long_selection_keeps_whole_cases_and_says_so() -> None:
    cases = [
        case(case_id=f"TC-{index:03d}", pre_conditions="x" * 2000) for index in range(1, 13)
    ]
    scenario = build_scenario(cases)

    assert scenario.endswith(TRUNCATION_NOTE)
    body = scenario[: -len("\n\n" + TRUNCATION_NOTE)]
    assert len(body) <= SCENARIO_LIMIT
    # Every case that survived is whole: a header line and an expected result line.
    blocks = body.split("\n\n")
    assert blocks
    for block in blocks:
        assert block.startswith("TC-")
        assert "Pre-conditions: " in block
        assert "\nExpected result: " in block
    # Nothing was cut in half: the kept ids are the first ones, in order.
    kept_ids = [block.split(":", 1)[0] for block in blocks]
    assert kept_ids == [c.id for c in cases][: len(kept_ids)]
    assert len(kept_ids) < len(cases)


def test_short_selection_is_not_truncated() -> None:
    scenario = build_scenario([case(case_id="TC-001"), case(case_id="TC-002")])
    assert TRUNCATION_NOTE not in scenario


def test_user_text_carries_base_url_and_the_one_test_rule() -> None:
    text = build_user_text("Test Scenario:\nTC-001: x", [case()], "https://shop.example.com")

    assert text.startswith("Test Scenario:\nTC-001: x")
    assert "\n\nBase URL: https://shop.example.com\n" in text
    assert "Write exactly one automated test per test case above." in text
    assert text.endswith("wait for elements or network instead.")


def test_empty_base_url_falls_back_to_the_sample_site() -> None:
    assert f"Base URL: {DEFAULT_BASE_URL}" in build_user_text("base", [case()], "   ")


def test_framework_options_map_to_v1_prompt_values() -> None:
    assert FRAMEWORK_OPTIONS == {
        "Playwright · TypeScript": ("Playwright (JavaScript)", "TypeScript"),
        "Playwright · JavaScript": ("Playwright (JavaScript)", "JavaScript"),
        "Playwright · Python": ("Playwright (Python)", "Python"),
        "Cypress · JavaScript": ("Cypress (JavaScript)", "JavaScript"),
        "Selenium · Python": ("Selenium (Python)", "Python"),
    }


def test_structure_options_map_to_v1_prompt_values() -> None:
    assert STRUCTURE_OPTIONS == {
        "Page Object Model": "Page Object Model",
        "Flat scripts": "Flat scripts (no POM)",
    }
