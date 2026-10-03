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
