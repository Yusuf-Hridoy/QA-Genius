import qagenius.prompts as prompts

SAMPLE = {
    "test_cases_prompt": {"user_story": "As a shopper I want to check out."},
    "bug_report_prompt": {"raw_bug": "Checkout button does nothing on click."},
    "quality_prompt": {"exec_summary": "100 passed, 5 failed, 1 blocked."},
    "automation_prompt": {
        "scenario": "Login flow",
        "framework": "Playwright",
        "language": "Python",
        "structure": "POM",
        "browsers": "Chromium",
        "site_type": "Aurora Storefront",
    },
    "story_check_prompt": {"user_story": "As a shopper I want to check out quickly."},
    "schema_validation_prompt": {
        "json_payload": '{"a": 1}',
        "schema_desc": "Object with integer a.",
        "validation_layers": "Structural",
    },
    "security_prompt": {"app_desc": "Aurora Storefront web app."},
    "performance_prompt": {
        "framework": "k6",
        "expected_users": "100",
        "peak_event_type": "Daily Peak",
        "sla_targets": "p95 < 300ms",
        "endpoint_slas": "none",
        "output_config": "k6 only",
        "user_flows": "Browse and checkout.",
    },
}


def test_all_prompts_return_two_non_empty_strings() -> None:
    for name, kwargs in SAMPLE.items():
        system, user = getattr(prompts, name)(**kwargs)
        assert isinstance(system, str) and system.strip(), name
        assert isinstance(user, str) and user.strip(), name


def test_story_prompt_user_text_contains_story() -> None:
    story = "As a shopper I want to check out quickly."
    _, user = prompts.story_check_prompt(user_story=story)
    assert story in user


def test_duel_reader_prompts_non_empty() -> None:
    story = "As a shopper, I want my account to lock quickly."
    for persona in ("A", "B"):
        system, user = prompts.duel_reader_prompt(
            user_story=story, story_type="User story", context="Aurora Storefront",
            persona=persona,
        )
        assert system.strip()
        assert user.strip()
        assert story in user


def test_duel_reader_personas_differ_only_in_persona_line() -> None:
    story = "As a shopper, I want my account to lock quickly."
    system_a, _ = prompts.duel_reader_prompt(user_story=story, persona="A")
    system_b, _ = prompts.duel_reader_prompt(user_story=story, persona="B")
    lines_a = system_a.strip().splitlines()
    lines_b = system_b.strip().splitlines()
    assert len(lines_a) == len(lines_b)
    diffs = [i for i, (x, y) in enumerate(zip(lines_a, lines_b)) if x != y]
    assert len(diffs) == 1
    assert "strictest" in lines_a[diffs[0]]
    assert "relaxed" in lines_b[diffs[0]]


def test_duel_compare_prompt_contains_story() -> None:
    story = "As a shopper, I want my account to lock quickly."
    system, user = prompts.duel_compare_prompt(
        user_story=story, reading_a_json='{"rules": []}', reading_b_json='{"rules": []}',
    )
    assert system.strip()
    assert user.strip()
    assert story in user


def test_reader_prompt_demands_numbers_and_units() -> None:
    system, _ = prompts.duel_reader_prompt(user_story="As a shopper I want to check out.")
    assert 'at least 3 entries in "numbers"' in system
    assert "NEVER restate" in system
