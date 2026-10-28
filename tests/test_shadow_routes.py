"""Shadow QA inside the real routes: same click, one AI call, no extra step."""

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

import main
from qagenius import llm
from qagenius.models import AmbiguityAnalysis, FailureMode, RiskAnalysis
from tests.factories import (
    BIG_STORY,
    COUPON_CONTEXT,
    COUPON_CRITERIA,
    COUPON_STORY,
    PHOTO_CRITERIA,
    PHOTO_STORY,
    NAVBAR_CRITERIA,
    NAVBAR_STORY,
    LOCKOUT_CRITERIA,
    LOCKOUT_STORY,
    PROFILE_STORY,
    case,
    script,
    suite,
)

client = TestClient(main.app)

KEYS_HEADER = {"X-QAG-Keys": json.dumps([{"provider": "gemini", "key": "first"}])}

STORY_SAMPLE = json.loads(
    Path("qagenius/samples/story_check.json").read_text(encoding="utf-8")
)
STORY_RESULT = AmbiguityAnalysis.model_validate(STORY_SAMPLE["result"])


def _fake_story(calls: list):
    def fake(keys, system, user, schema):
        calls.append(user)
        return STORY_RESULT, 0, []

    return fake


# ── story check ───────────────────────────────────────────────────────────────


def test_the_profile_story_shows_the_epic_banner(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(llm, "generate_json", _fake_story(calls))
    response = client.post(
        "/requirements/story/run",
        data={"user_story": PROFILE_STORY},
        headers=KEYS_HEADER,
    )
    body = response.text
    assert response.status_code == 200
    assert "pq-epic" in body
    assert "This story is really" in body
    assert body.count('class="pill warn plain"') >= 7
    assert "This is too much for one story" in body
    # Same click, still exactly one AI call.
    assert len(calls) == 1


def test_the_big_story_names_every_feature_it_counts(monkeypatch) -> None:
    """The number in the title and the pills under it are one list."""
    monkeypatch.setattr(llm, "generate_json", _fake_story([]))
    response = client.post(
        "/requirements/story/run",
        data={"user_story": BIG_STORY},
        headers=KEYS_HEADER,
    )
    body = response.text
    counted = re.search(r"This story is really (\d+) features", body)
    assert counted, body
    assert body.count('class="pill warn plain"') == int(counted.group(1))
    assert ">Two-factor</span>" in body


def test_the_banner_sits_above_the_score(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _fake_story([]))
    body = client.post(
        "/requirements/story/run",
        data={"user_story": PROFILE_STORY},
        headers=KEYS_HEADER,
    ).text
    # The banner is swapped into its own slot above both columns, so it is
    # still the first thing on the page and the first thing in the answer.
    assert body.index("pq-epic") < body.index('class="clarity-num"')


def test_the_lockout_story_shows_no_banner(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _fake_story([]))
    body = client.post(
        "/requirements/story/run",
        data={"user_story": LOCKOUT_STORY},
        headers=KEYS_HEADER,
    ).text
    assert "pq-epic" not in body


def test_the_banner_links_to_the_suggested_split(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _fake_story([]))
    body = client.post(
        "/requirements/story/run",
        data={"user_story": PROFILE_STORY},
        headers=KEYS_HEADER,
    ).text
    if 'id="recommended-split"' in body:
        assert "See the suggested split" in body
        assert 'href="#recommended-split"' in body


def test_a_story_without_an_actor_gets_a_principal_qa_note(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _fake_story([]))
    body = client.post(
        "/requirements/story/run",
        data={"user_story": "The profile page shows a name and a bio."},
        headers=KEYS_HEADER,
    ).text
    assert "Notes from the senior tester" in body
    assert "No actor" in body


def test_the_story_example_runs_the_rules_without_a_key() -> None:
    response = client.post("/requirements/story/example")
    assert response.status_code == 200
    # The saved story is a small one, so the rules run and find nothing to warn
    # about. What matters here is that they ran without a key and without an AI.
    assert "pq-epic" not in response.text


# ── test cases ────────────────────────────────────────────────────────────────

TC_FORM = {
    "user_story": LOCKOUT_STORY,
    "criteria_json": json.dumps(LOCKOUT_CRITERIA),
    "coverage_focus": ["Functional", "Negative"],
}


def _fake_cases(calls: list, result=None):
    answer = result if result is not None else suite(case(case_id="TC-001"))

    def fake(keys, system, user, schema):
        calls.append(user)
        return answer, 0, []

    return fake


def _shown_cases(body: str) -> list[dict]:
    raw = body.split('<script type="application/json" id="tc-data">')[1]
    return json.loads(raw.split("</script>")[0])["result"]["test_cases"]


def test_the_checklist_is_appended_to_the_user_text(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(llm, "generate_json", _fake_cases(calls))
    client.post("/requirements/test-cases/run", data=TC_FORM, headers=KEYS_HEADER)
    assert len(calls) == 1
    user = calls[0]
    assert "PRINCIPAL QA CHECKLIST" in user
    assert "[login.enumeration]" in user
    assert 'tags as "qa:<id>"' in user
    # The v1 prompt text is still there, untouched, in front of it.
    assert user.index("Test Coverage Focus") < user.index("PRINCIPAL QA CHECKLIST")


def test_the_result_holds_the_ai_cases_plus_the_added_ones(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _fake_cases([]))
    body = client.post(
        "/requirements/test-cases/run", data=TC_FORM, headers=KEYS_HEADER
    ).text
    cases = _shown_cases(body)
    assert cases[0]["id"] == "TC-001"
    assert len(cases) > 1
    added = [one for one in cases if "principal-qa" in one["tags"]]
    assert added
    assert all(one["id"].startswith("TC-") for one in added)
    assert [one["id"] for one in cases] == sorted({one["id"] for one in cases})


def test_the_counts_are_computed_on_the_merged_list(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _fake_cases([]))
    body = client.post(
        "/requirements/test-cases/run", data=TC_FORM, headers=KEYS_HEADER
    ).text
    total = len(_shown_cases(body))
    assert f">{total}</div>\n    <div class=\"lbl\">Test cases</div>" in body.replace(
        "><div", ">\n    <div"
    ) or f"{total}" in body


def test_a_check_the_ai_already_tagged_is_not_added_again(monkeypatch) -> None:
    tagged = suite(
        case(
            case_id="TC-001",
            title="Sign in with the email in capitals",
            tags=["qa:login.email_case"],
        )
    )
    monkeypatch.setattr(llm, "generate_json", _fake_cases([], tagged))
    body = client.post(
        "/requirements/test-cases/run", data=TC_FORM, headers=KEYS_HEADER
    ).text
    added = [one for one in _shown_cases(body) if "principal-qa" in one["tags"]]
    assert not any("qa:login.email_case" in one["tags"] for one in added)


def test_the_review_card_and_labels_are_shown(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _fake_cases([]))
    body = client.post(
        "/requirements/test-cases/run", data=TC_FORM, headers=KEYS_HEADER
    ).text
    assert 'id="pq-review"' in body
    assert "Added " in body and "the AI missed" in body
    assert body.count("pq-label") >= 2
    assert "Why a senior tester always asks for this" in body


NAVBAR_FORM = {
    "user_story": NAVBAR_STORY,
    "criteria_json": json.dumps(NAVBAR_CRITERIA),
    "coverage_focus": ["Functional", "Negative"],
}

# The nav-bar run, where the AI followed the checklist and tagged every check
# it answered. Nothing is left for the senior tester to add.
_COVERED_BY_THE_AI = (
    ("TC-007", "A reader without the admin role is refused the admin URL",
     ["qa:permissions.ui_and_api", "qa:permissions.direct_url"]),
    ("TC-009", "Browser back and forward keep the right item active",
     ["qa:navigation.back_forward"]),
    ("TC-010", "Tab order follows the sidebar and the focus ring is visible",
     ["qa:navigation.keyboard_focus"]),
    ("TC-011", "A role change takes effect without signing out again",
     ["qa:permissions.role_change_live"]),
    ("TC-012", "The active item is still correct after a refresh",
     ["qa:navigation.active_after_refresh"]),
)


def _navbar_suite():
    return suite(
        *[
            case(case_id=case_id, title=title, tags=tags, traceability="AC-5")
            for case_id, title, tags in _COVERED_BY_THE_AI
        ]
    )


def test_the_senior_tester_box_shows_even_when_nothing_was_added(monkeypatch) -> None:
    """The nav-bar run: the rules ran, found nothing, and have to say so."""
    monkeypatch.setattr(llm, "generate_json", _fake_cases([], _navbar_suite()))
    body = client.post(
        "/requirements/test-cases/run", data=NAVBAR_FORM, headers=KEYS_HEADER
    ).text
    assert 'id="pq-review"' in body
    assert (
        "The AI already covered all 6 things a senior tester checks for this "
        "story. Nothing to add." in body
    )
    assert not [one for one in _shown_cases(body) if "principal-qa" in one["tags"]]
    # Nothing was added, so the label does not claim anything was.
    assert "Checked by senior tester" in body
    assert "Added by senior tester" not in body


def test_a_test_that_disagrees_with_the_limit_is_shown_first(monkeypatch) -> None:
    """Test B: TC-005 accepted exactly 2 MB where AC-1 says "under 2 MB"."""
    written = suite(
        case(
            case_id="TC-005",
            title="A photo at the size limit",
            steps=["Choose a 2MB JPEG photo and upload it"],
            expected_result="The exact 2MB file is accepted and saved.",
            traceability="AC-1",
        )
    )
    monkeypatch.setattr(llm, "generate_json", _fake_cases([], written))
    body = client.post(
        "/requirements/test-cases/run",
        data={
            "user_story": PHOTO_STORY,
            "criteria_json": json.dumps(PHOTO_CRITERIA),
            "coverage_focus": ["Functional", "Negative"],
        },
        headers=KEYS_HEADER,
    ).text
    assert "2 disagreements about a limit" in body
    assert "Disagreements about a limit" in body
    assert "exactly 2 MB should be refused" in body
    # The criteria argue with each other about the same limit.
    assert "Decide which is right." in body
    # It comes before the other detail blocks in the box.
    assert body.index("Disagreements about a limit") < body.index("Found by QA-Genius")


def test_the_story_box_shows_a_limit_nobody_decided(monkeypatch) -> None:
    """The coupon run: the story page is the cheapest place to fix this."""
    analysis = STORY_RESULT.model_copy(
        update={"generated_acceptance_criteria": COUPON_CRITERIA}
    )

    def fake(keys, system, user, schema):
        return analysis, 0, []

    monkeypatch.setattr(llm, "generate_json", fake)
    body = client.post(
        "/requirements/story/run",
        data={"user_story": COUPON_STORY, "context": COUPON_CONTEXT},
        headers=KEYS_HEADER,
    ).text
    assert "Disagreements about a limit" in body
    assert "Nobody says what happens at exactly $50" in body
    assert "The context says" in body


def test_the_test_cases_box_shows_the_same_limit_notes(monkeypatch) -> None:
    written = suite(case(case_id="TC-001", title="A $90 cart", traceability="AC-1"))
    monkeypatch.setattr(llm, "generate_json", _fake_cases([], written))
    body = client.post(
        "/requirements/test-cases/run",
        data={
            "user_story": COUPON_STORY,
            "context": COUPON_CONTEXT,
            "criteria_json": json.dumps(COUPON_CRITERIA),
            "coverage_focus": ["Functional", "Negative"],
        },
        headers=KEYS_HEADER,
    ).text
    assert "Nobody says what happens at exactly $50" in body
    assert "The context says" in body
    # And the limit tests nobody wrote: the $50 edge and the $150 cap.
    cases = _shown_cases(body)
    titles = " ".join(one["title"] for one in cases)
    assert "$49.99" in titles and "$50.01" in titles
    assert "$149.99" in titles and "$150.01" in titles


def test_remove_buttons_sit_only_on_principal_qa_cases(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _fake_cases([]))
    body = client.post(
        "/requirements/test-cases/run", data=TC_FORM, headers=KEYS_HEADER
    ).text
    added = [one for one in _shown_cases(body) if "principal-qa" in one["tags"]]
    assert body.count('class="btn btn-small btn-danger pq-remove"') == len(added)
    for one in added:
        assert f'pq-remove" data-case-id="{one["id"]}"' in body
    assert 'pq-remove" data-case-id="TC-001"' not in body


def test_the_render_route_keeps_the_labels_without_a_review_card() -> None:
    payload = {
        "result": suite(
            case(case_id="TC-001"),
            case(
                case_id="TC-002",
                title="Unknown email and wrong password give the same message",
                tags=["principal-qa", "qa:login.enumeration", "pack:login"],
            ),
        ).model_dump(),
        "criteria": LOCKOUT_CRITERIA,
    }
    body = client.post("/requirements/test-cases/render", json=payload).text
    assert "pq-case" in body
    assert "pq-remove" in body
    assert 'id="pq-review"' not in body


def test_refine_appends_the_checklist_and_adds_cases_to_the_proposal(monkeypatch) -> None:
    calls: list = []
    current = suite(case(case_id="TC-001"), case(case_id="TC-002", category="Negative"))
    proposed = suite(
        case(case_id="TC-001"),
        case(case_id="TC-002", category="Negative"),
        case(case_id="TC-003", category="Boundary", title="Exactly five attempts"),
    )
    monkeypatch.setattr(llm, "generate_json", _fake_cases(calls, proposed))
    body = client.post(
        "/requirements/test-cases/refine",
        data={
            "user_story": LOCKOUT_STORY,
            "criteria_json": json.dumps(LOCKOUT_CRITERIA),
            "current_json": current.model_dump_json(),
            "mode": "strengthen",
            "coverage_focus": ["Functional", "Negative"],
        },
        headers=KEYS_HEADER,
    ).text
    assert len(calls) == 1
    assert "PRINCIPAL QA CHECKLIST" in calls[0]
    raw = body.split('<script type="application/json" id="tc-proposed">')[1]
    cases = json.loads(raw.split("</script>")[0])["result"]["test_cases"]
    assert any("principal-qa" in one["tags"] for one in cases)
    assert "Exactly five attempts" in body


# ── automation ────────────────────────────────────────────────────────────────

AUTO_FORM = {
    "selected_json": json.dumps([case(case_id="TC-001").model_dump()]),
    "framework_choice": "Playwright · TypeScript",
    "structure_choice": "Page Object Model",
    "browsers": ["chromium"],
    "base_url": "https://example.com",
}

BAD_SPEC = (
    "test.only('TC-001: it signs in', async ({ page }) => {\n"
    "  const password = 'Harbour-Lantern-42';\n"
    "  await page.goto('/');\n"
    "});\n"
)


def _fake_script(calls: list, code: str = BAD_SPEC):
    answer = script(test_file_name="tests/login.spec.ts", test_code=code)

    def fake(keys, system, user, schema):
        calls.append(user)
        return answer, 0, []

    return fake


def test_the_coding_rules_are_appended_to_the_automation_prompt(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(llm, "generate_json", _fake_script(calls))
    client.post("/requirements/automation/run", data=AUTO_FORM, headers=KEYS_HEADER)
    assert len(calls) == 1
    assert "PRINCIPAL QA CODING RULES" in calls[0]
    assert "Never leave .only" in calls[0]


def test_a_test_with_only_and_no_assertion_is_flagged(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _fake_script([]))
    body = client.post(
        "/requirements/automation/run", data=AUTO_FORM, headers=KEYS_HEADER
    ).text
    assert "`.only` leaves the rest of the suite unrun" in body
    assert "this test never asserts anything" in body
    assert "hard-coded secret" in body
    assert "pq-label" in body
    assert ">Senior tester</div>" in body


def test_clean_automation_code_is_not_flagged(monkeypatch) -> None:
    clean = (
        "test('TC-001: it signs in', async ({ page }) => {\n"
        "  await page.goto('/');\n"
        "  await expect(page.getByRole('heading')).toBeVisible();\n"
        "});\n"
    )
    monkeypatch.setattr(llm, "generate_json", _fake_script([], clean))
    body = client.post(
        "/requirements/automation/run", data=AUTO_FORM, headers=KEYS_HEADER
    ).text
    assert "Senior tester: " not in body
    assert '<div class="num">0</div><div class="lbl">Senior tester</div>' in body


# ── risk radar ────────────────────────────────────────────────────────────────

RISK_FORM = {
    "user_story": LOCKOUT_STORY,
    "criteria_json": json.dumps(LOCKOUT_CRITERIA),
    "cases_json": json.dumps([case(case_id="TC-001").model_dump()]),
}


def _one_risk() -> RiskAnalysis:
    return RiskAnalysis(
        failure_modes=[
            FailureMode(
                id="R1",
                title="The lock never lifts",
                category="reliability",
                effect="Shoppers cannot sign in again.",
                cause="The unlock job never runs.",
                severity=4,
                likelihood=3,
                detectability=3,
            )
        ]
    )


def _fake_risks(calls: list):
    def fake(keys, system, user, schema):
        calls.append(user)
        return _one_risk(), 0, []

    return fake


def test_the_typical_risks_are_appended_to_the_risk_prompt(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(llm, "generate_json", _fake_risks(calls))
    client.post("/risks/run", data=RISK_FORM, headers=KEYS_HEADER)
    assert len(calls) == 1
    assert "Typical risks for this kind of feature" in calls[0]
    assert "Error message reveals whether an email is registered" in calls[0]


def test_principal_qa_risks_are_added_scored_and_labelled(monkeypatch) -> None:
    monkeypatch.setattr(llm, "generate_json", _fake_risks([]))
    body = client.post("/risks/run", data=RISK_FORM, headers=KEYS_HEADER).text
    # The AI's own risk is still there, and the classics sit beside it.
    assert "The lock never lifts" in body
    assert "Error message reveals whether an email is registered" in body
    assert "pq-label" in body
    assert "The AI did not raise this one" in body
    # Scored and numbered like every other risk.
    assert "Risk score " in body
    assert "R2" in body


def test_a_senior_tester_risk_says_where_its_scores_come_from(monkeypatch) -> None:
    """They are not a guess, and the three reasons were one sentence apart."""
    monkeypatch.setattr(llm, "generate_json", _fake_risks([]))
    body = client.post("/risks/run", data=RISK_FORM, headers=KEYS_HEADER).text
    assert "These scores come from QA-Genius's testing rules." in body
    assert "Typical scores for this kind of problem." in body
    assert "A senior tester's rule" not in body


def test_a_risk_the_ai_already_named_is_not_doubled(monkeypatch) -> None:
    def fake(keys, system, user, schema):
        return (
            RiskAnalysis(
                failure_modes=[
                    FailureMode(
                        id="R1",
                        title="Error message reveals whether an email is registered",
                        category="security",
                        effect="Attackers can list accounts.",
                        cause="Two different messages.",
                        severity=4,
                        likelihood=4,
                        detectability=3,
                    )
                ]
            ),
            0,
            [],
        )

    monkeypatch.setattr(llm, "generate_json", fake)
    body = client.post("/risks/run", data=RISK_FORM, headers=KEYS_HEADER).text
    # One risk card, not two. (The title also appears once in the saved JSON.)
    assert body.count("· Error message reveals whether an email is registered") == 1
