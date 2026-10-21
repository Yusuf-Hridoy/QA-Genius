"""The senior-tester reviewers. Deterministic, no AI, no network, under 50 ms."""

import time

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
    PROFILE_CRITERIA,
    PROFILE_STORY,
    case,
    script,
    suite,
)

from qagenius.automation_checks import ProjectFile
from qagenius.models import FailureMode, RiskAnalysis
from qagenius.risk_radar import score_risks
from qagenius.shadow_qa.review import (
    MAX_ADDED,
    MAX_ADDED_RISKS,
    MAX_QUALITY_NOTES,
    PRINCIPAL_SOURCE,
    PRINCIPAL_TAG,
    DISPUTED_OUTCOME,
    checklist_block,
    limit_conflicts,
    with_context,
    is_principal,
    reason_for,
    review_automation,
    review_risks,
    review_test_cases,
    risk_titles,
)
from qagenius.test_cases import number_criteria

PROFILE = number_criteria(PROFILE_CRITERIA)
LOCKOUT = number_criteria(LOCKOUT_CRITERIA)
# A reviewer must never cost the user a visible pause.
BUDGET_MS = 50


def _risk(title: str, **overrides) -> FailureMode:
    values = {
        "id": "R1",
        "title": title,
        "category": "security",
        "effect": "Something bad happens.",
        "cause": "It was built that way.",
        "severity": 3,
        "likelihood": 3,
        "detectability": 3,
    }
    values.update(overrides)
    return FailureMode(**values)


def _file(name: str, code: str) -> ProjectFile:
    return ProjectFile(name=name, code=code)


def _timed(call) -> tuple[object, float]:
    start = time.perf_counter()
    value = call()
    return value, (time.perf_counter() - start) * 1000


# ── the checklist that goes out with the prompt ───────────────────────────────


def test_the_checklist_is_capped_and_names_its_check_ids():
    block, ids = checklist_block(PROFILE_STORY, PROFILE)
    lines = [line for line in block.splitlines() if line.startswith("- [")]
    assert 0 < len(lines) <= 12
    assert len(ids) == len(lines)
    assert "PRINCIPAL QA CHECKLIST" in block
    assert block.startswith("\n\n\n")
    for check_id, line in zip(ids, lines):
        assert line.startswith(f"- [{check_id}] ")


def test_the_checklist_puts_high_severity_first_and_boundaries_last():
    block, ids = checklist_block(LOCKOUT_STORY, LOCKOUT)
    boundaries = [index for index, one in enumerate(ids) if one.startswith("boundary:")]
    others = [index for index, one in enumerate(ids) if not one.startswith("boundary:")]
    assert boundaries and others
    assert min(boundaries) > max(others)
    assert "login.enumeration" in ids
    assert "4 / 5 / 6 failed sign-in attempts" in block


def test_a_story_with_no_active_pack_asks_for_nothing():
    block, ids = checklist_block("As a reader, I want a quiet page so that I can think.", [])
    assert block == "" and ids == []


# ── coverage ──────────────────────────────────────────────────────────────────


def test_a_tagged_case_covers_its_check():
    tagged = case(
        case_id="TC-001",
        title="Something unrelated",
        tags=["qa:LOGIN.Email_Case"],
    )
    review = review_test_cases(LOCKOUT_STORY, LOCKOUT, suite(tagged))
    assert "login.email_case" in review.covered
    assert all("login.email_case" not in (tag for tag in one.tags) for one in review.added)


def test_a_keyword_in_the_case_covers_its_check():
    covered = case(
        case_id="TC-001",
        title="Unknown email and wrong password give the same message",
        steps=["Sign in with an unknown email", "Compare the two messages"],
        expected_result="Both show the same message",
    )
    review = review_test_cases(LOCKOUT_STORY, LOCKOUT, suite(covered))
    assert "login.enumeration" in review.covered


def test_an_uncovered_check_becomes_an_added_case():
    review = review_test_cases(LOCKOUT_STORY, LOCKOUT, suite(case()))
    added_ids = {
        tag for one in review.added for tag in one.tags if tag.startswith("qa:")
    }
    assert "qa:login.enumeration" in added_ids


# ── what gets added ───────────────────────────────────────────────────────────


def test_at_most_eight_cases_are_added_and_the_rest_are_listed():
    review = review_test_cases(PROFILE_STORY, PROFILE, suite(case()))
    assert len(review.added) == MAX_ADDED
    assert review.more
    added_ids = {
        tag[3:] for one in review.added for tag in one.tags if tag.startswith("qa:")
    }
    assert not (added_ids & {gap.check_id for gap in review.more})


def test_high_severity_gaps_are_added_before_low_ones():
    review = review_test_cases(PROFILE_STORY, PROFILE, suite(case()))
    assert all(gap.severity in ("high", "medium", "low") for gap in review.more)
    severities = [gap.severity for gap in review.more]
    assert "high" not in severities or severities.index("high") == 0


def test_added_ids_continue_the_numbering():
    existing = suite(*[case(case_id=f"TC-{n:03d}") for n in range(1, 12)])
    review = review_test_cases(LOCKOUT_STORY, LOCKOUT, existing)
    assert review.added[0].id == "TC-012"
    assert [one.id for one in review.added] == [
        f"TC-{12 + offset:03d}" for offset in range(len(review.added))
    ]


def test_added_cases_carry_their_tags_and_a_traceability():
    review = review_test_cases(LOCKOUT_STORY, LOCKOUT, suite(case()))
    for one in review.added:
        assert PRINCIPAL_TAG in one.tags
        assert any(tag.startswith("qa:") for tag in one.tags)
        assert any(tag.startswith("pack:") for tag in one.tags)
        assert one.traceability.startswith("AC-")
        assert is_principal(one)
        assert len(one.steps) >= 2
        assert one.expected_result.strip()


def test_added_cases_carry_a_reason():
    review = review_test_cases(LOCKOUT_STORY, LOCKOUT, suite(case()))
    assert all(reason_for(one) for one in review.added)
    assert not reason_for(case())


def test_an_uncovered_boundary_becomes_one_case_listing_the_missing_values():
    criteria = number_criteria(["The account locks after 5 failed sign-in attempts"])
    review = review_test_cases(
        "As a shopper, I want my account to lock so that it stays safe.",
        criteria,
        suite(case(case_id="TC-001", title="Lock after 5 attempts", test_data="attempts=5")),
    )
    boundary_cases = [one for one in review.added if "pack:boundary" in one.tags]
    assert len(boundary_cases) == 1
    text = boundary_cases[0].test_data + " ".join(boundary_cases[0].steps)
    assert "4 attempts" in text and "6 attempts" in text
    assert boundary_cases[0].traceability == "AC-1"


def test_no_boundary_case_is_added_when_the_ai_already_wrote_the_values():
    """The AI's own words for the limit count, whichever way it wrote them."""
    criteria = number_criteria(
        [
            "Enabling two-factor shows a 6-digit verification code step",
            "An avatar must be a JPEG, PNG or WebP image under 5MB",
        ]
    )
    written = suite(
        case(
            case_id="TC-011",
            title="Verification codes of the wrong length are refused",
            steps=[
                "Enter a 5-digit code '12345'",
                "Enter the correct code '123456'",
                "Enter a 7-digit code '1234567'",
            ],
            expected_result="Only the six-digit code is accepted.",
        ),
        case(
            case_id="TC-012",
            title="An avatar at the size limit",
            steps=[
                "Upload an avatar of 4.99 MB",
                "Upload an avatar of exactly 5.00 megabytes",
                "Upload an avatar of 5.00 megabytes and 1 byte",
            ],
            expected_result="The first two are saved and the third is refused.",
        ),
    )
    review = review_test_cases(BIG_STORY, criteria, written)
    assert [one for one in review.added if "pack:boundary" in one.tags] == []


def test_only_the_missing_value_is_asked_for_and_named():
    criteria = number_criteria(["An avatar must be an image under 5MB"])
    written = suite(
        case(
            case_id="TC-001",
            title="An avatar at the size limit",
            steps=["Upload 4.99 MB", "Upload exactly 5 MB"],
            expected_result="Both are saved.",
        )
    )
    review = review_test_cases(BIG_STORY, criteria, written)
    added = [one for one in review.added if "pack:boundary" in one.tags]
    assert len(added) == 1
    text = " ".join([added[0].title, added[0].test_data, *added[0].steps])
    assert "5.01 MB" in text
    assert "4.99 MB" not in text
    # "Data to use" is the card's own label; the value says itself.
    assert added[0].test_data == "5.01 MB"


def test_the_ai_cases_are_never_modified():
    original = case(case_id="TC-001")
    before = original.model_dump()
    result = suite(original)
    review_test_cases(LOCKOUT_STORY, LOCKOUT, result)
    assert result.test_cases[0].model_dump() == before
    assert len(result.test_cases) == 1


# ── quality notes on the AI's own cases ───────────────────────────────────────


def test_an_expected_result_with_no_checkable_outcome_is_noted():
    weak = case(case_id="TC-004", expected_result="It works correctly as expected")
    review = review_test_cases(LOCKOUT_STORY, LOCKOUT, suite(weak))
    assert "TC-004: expected result has no checkable outcome" in review.quality


def test_a_quoted_message_or_a_number_counts_as_an_outcome():
    strong = case(case_id="TC-004", expected_result='The page shows "Account locked"')
    review = review_test_cases(LOCKOUT_STORY, LOCKOUT, suite(strong))
    assert not any("TC-004" in note for note in review.quality)


def test_a_single_step_case_is_noted():
    thin = case(case_id="TC-005", steps=["Sign in"])
    review = review_test_cases(LOCKOUT_STORY, LOCKOUT, suite(thin))
    assert "TC-005: fewer than 2 steps" in review.quality


def test_a_case_that_types_data_without_test_data_is_noted():
    bare = case(
        case_id="TC-006",
        steps=["Open the page", "Enter an email and a password"],
        test_data=None,
    )
    review = review_test_cases(LOCKOUT_STORY, LOCKOUT, suite(bare))
    assert "TC-006: the steps enter data but no test data is given" in review.quality


def test_near_duplicate_titles_are_noted():
    first = case(case_id="TC-001", title="Account locks after five wrong passwords")
    second = case(case_id="TC-002", title="Account locks after five wrong passwords")
    review = review_test_cases(LOCKOUT_STORY, LOCKOUT, suite(first, second))
    assert "TC-002: near-duplicate of TC-001" in review.quality


def test_there_are_never_more_than_six_quality_notes():
    weak = [case(case_id=f"TC-{n:03d}", steps=["Only one"]) for n in range(1, 15)]
    review = review_test_cases(LOCKOUT_STORY, LOCKOUT, suite(*weak))
    assert len(review.quality) == MAX_QUALITY_NOTES


# ── automation ────────────────────────────────────────────────────────────────


def test_a_test_with_no_assertion_is_an_error():
    code = "test('TC-001: it signs in', async ({ page }) => {\n  await page.goto('/');\n});\n"
    findings = review_automation(script(), [_file("tests/login.spec.ts", code)])
    assert any(
        one.level == "error" and "never asserts" in one.message for one in findings
    )


def test_a_test_with_an_assertion_is_not_flagged():
    code = (
        "test('TC-001: it signs in', async ({ page }) => {\n"
        "  await page.goto('/');\n  await expect(page).toHaveTitle('Home');\n});\n"
    )
    findings = review_automation(script(), [_file("tests/login.spec.ts", code)])
    assert not any("never asserts" in one.message for one in findings)


def test_only_is_an_error():
    code = "test.only('TC-001', async () => { expect(1).toBe(1); });\n"
    findings = review_automation(script(), [_file("tests/login.spec.ts", code)])
    assert any(one.level == "error" and "`.only`" in one.message for one in findings)


def test_fit_is_an_error():
    code = "fit('TC-001', async () => { expect(1).toBe(1); });\n"
    findings = review_automation(script(), [_file("tests/login.spec.ts", code)])
    assert any(one.level == "error" and "`.only`" in one.message for one in findings)


def test_a_hard_coded_secret_is_a_warning():
    code = "const password = 'Harbour-Lantern-42';\nexpect(password).toBeTruthy();\n"
    findings = review_automation(script(), [_file("tests/login.spec.ts", code)])
    assert any(
        one.level == "warning" and "hard-coded secret" in one.message for one in findings
    )


def test_a_secret_read_from_the_environment_is_not_flagged():
    code = (
        "const password = process.env.PASSWORD;\n"
        "const token = os.environ['API_TOKEN'];\n"
        "expect(password).toBeTruthy();\n"
    )
    findings = review_automation(script(), [_file("tests/login.spec.ts", code)])
    assert not any("hard-coded secret" in one.message for one in findings)


def test_brittle_selectors_are_warnings():
    code = (
        "test('TC-001', async ({ page }) => {\n"
        "  await page.locator('ul li:nth-child(3)').click();\n"
        "  await page.locator('//html/body/div/span').click();\n"
        "  await page.locator('.app > .main > .card > .row > .btn').click();\n"
        "  await expect(page).toHaveURL('/next');\n});\n"
    )
    messages = " ".join(one.message for one in review_automation(script(), [_file("a.ts", code)]))
    assert "nth-child" in messages
    assert "fragile locator (full XPath)" in messages
    assert "levels deep" in messages


def test_a_short_selector_is_not_flagged():
    code = (
        "test('TC-001', async ({ page }) => {\n"
        "  await page.locator('.card .btn').click();\n"
        "  await expect(page).toHaveURL('/next');\n});\n"
    )
    assert review_automation(script(), [_file("a.ts", code)]) == []


def test_a_python_test_without_an_assertion_is_flagged():
    code = "def test_locks_the_account(page):\n    page.goto('/')\n"
    findings = review_automation(script(), [_file("tests/test_login.py", code)])
    assert any("never asserts" in one.message for one in findings)


def test_every_automation_finding_is_labelled():
    code = "test.only('TC-001', async () => {});\n"
    findings = review_automation(script(), [_file("a.ts", code)])
    assert findings and all(one.message.startswith("Senior tester: ") for one in findings)


# ── risks ─────────────────────────────────────────────────────────────────────


def test_classic_risks_are_added_to_an_empty_analysis():
    added = review_risks(PROFILE_STORY, PROFILE_CRITERIA, RiskAnalysis())
    assert 0 < len(added) <= MAX_ADDED_RISKS
    assert all(one.source == PRINCIPAL_SOURCE for one in added)
    assert all(1 <= one.severity <= 5 for one in added)


def test_a_risk_the_ai_already_named_is_not_added_again():
    analysis = RiskAnalysis(
        failure_modes=[_risk("Error message reveals whether an email is registered")]
    )
    added = review_risks(LOCKOUT_STORY, LOCKOUT_CRITERIA, analysis)
    assert not any("reveals whether an email" in one.title for one in added)


def test_a_differently_worded_duplicate_is_still_one_risk():
    """R9 and R2 of the real run: one problem, two names, two words in common."""
    ai = _risk("OAuth account linking email collision takeover")
    analysis = RiskAnalysis(failure_modes=[ai])
    story = (
        "As a registered user, I want to link my Google or GitHub account "
        "so that I can sign in with either."
    )
    added = review_risks(story, [], analysis)
    assert not any("takes over an existing account" in one.title for one in added)
    # The risk that stayed carries the words that mean a test reaches it.
    assert "same email" in ai.covered_if
    assert "takeover" in ai.covered_if


def test_the_navbar_duplicate_is_one_risk_linked_to_the_test_that_covers_it():
    """R1 and R7 of the nav-bar run: one problem, two names, one test.

    The AI's R1 and the rule packs' R7 are both "the menu hides it but the
    server does not check". Only one of them belongs on the page, and the
    one that stays has to be the one TC-007 can be matched to.
    """
    ai = _risk(
        "The sidebar hides the admin link client-side only",
        effect="Anyone who knows the address opens the admin page.",
        cause="The menu hides the link in the browser and the backend never "
        "checks the role.",
    )
    added = review_risks(NAVBAR_STORY, NAVBAR_CRITERIA, RiskAnalysis(failure_modes=[ai]))
    assert not any("user interface only" in one.title for one in added)
    tested = case(
        case_id="TC-007",
        title="A reader without the admin role is refused the admin URL",
        steps=["Open the admin URL directly as a reader"],
        expected_result="The server answers 403 and changes nothing.",
    )
    report = score_risks(RiskAnalysis(failure_modes=[ai] + added), [tested])
    assert len([one for one in report.risks if "admin" in one.risk.title]) == 1
    scored = report.risks[0]
    assert scored.coverage == "covered"
    assert [row[0] for row in scored.covered_tests] == ["TC-007"]


def test_near_duplicate_titles_are_skipped():
    analysis = RiskAnalysis(
        failure_modes=[_risk("Error message reveals whether an email is registered here")]
    )
    added = review_risks(LOCKOUT_STORY, LOCKOUT_CRITERIA, analysis)
    assert not any("reveals whether an email" in one.title for one in added)


def test_risks_are_added_worst_first():
    added = review_risks(PROFILE_STORY, PROFILE_CRITERIA, RiskAnalysis())
    rpns = [one.severity * one.likelihood * one.detectability for one in added]
    assert rpns == sorted(rpns, reverse=True)


def test_risk_titles_for_the_prompt_are_capped():
    titles = risk_titles(PROFILE_STORY, PROFILE_CRITERIA)
    assert 0 < len(titles) <= 6
    assert len(set(titles)) == len(titles)


def test_a_story_with_no_active_pack_adds_no_risk():
    assert review_risks("As a reader, I want a quiet page.", [], RiskAnalysis()) == []


# ── speed ─────────────────────────────────────────────────────────────────────


def test_every_reviewer_is_under_fifty_milliseconds_on_the_profile_story():
    cases = suite(*[case(case_id=f"TC-{n:03d}") for n in range(1, 13)])
    # Warm every cache first: the budget is per request, not per process, and
    # the first call of all pays for compiling each pack word once.
    checklist_block(PROFILE_STORY, PROFILE)
    review_test_cases(PROFILE_STORY, PROFILE, cases)
    review_risks(PROFILE_STORY, PROFILE_CRITERIA, RiskAnalysis())

    _, checklist_ms = _timed(lambda: checklist_block(PROFILE_STORY, PROFILE))
    _, cases_ms = _timed(lambda: review_test_cases(PROFILE_STORY, PROFILE, cases))
    _, risks_ms = _timed(
        lambda: review_risks(PROFILE_STORY, PROFILE_CRITERIA, RiskAnalysis())
    )
    code = "test('TC-001', async () => { await expect(page).toHaveTitle('x'); });\n" * 40
    _, automation_ms = _timed(
        lambda: review_automation(script(), [_file("tests/a.spec.ts", code)])
    )
    for name, elapsed in (
        ("checklist_block", checklist_ms),
        ("review_test_cases", cases_ms),
        ("review_risks", risks_ms),
        ("review_automation", automation_ms),
    ):
        assert elapsed < BUDGET_MS, f"{name} took {elapsed:.1f} ms"


# ── the story outranks the criteria ───────────────────────────────────────────

UPLOAD_STORY = "As a user, I want to upload an avatar so that my profile looks right."
UPLOAD_CRITERIA = number_criteria(
    ["The account locks after 5 failed sign-in attempts", "The avatar must be under 5MB"]
)


def _pack_of(one) -> str:
    return next(tag[5:] for tag in one.tags if tag.startswith("pack:"))


def test_a_pack_the_story_named_is_added_before_one_only_a_criterion_named():
    review = review_test_cases(UPLOAD_STORY, UPLOAD_CRITERIA, suite(case()))
    packs = [_pack_of(one) for one in review.added]
    assert "file_upload" in packs
    # login and rate_limiting live in AC-1 only, so they queue behind the
    # feature the story is actually about.
    assert packs.index("file_upload") < min(
        [packs.index(name) for name in ("login", "rate_limiting") if name in packs]
        or [len(packs)]
    )


def test_the_checklist_asks_for_the_story_s_own_packs_first():
    _, ids = checklist_block(UPLOAD_STORY, UPLOAD_CRITERIA)
    upload = [index for index, one in enumerate(ids) if one.startswith("file_upload.")]
    login = [index for index, one in enumerate(ids) if one.startswith("login.")]
    assert upload and login
    assert min(upload) < min(login)


def test_severity_still_wins_over_where_the_pack_was_found():
    _, ids = checklist_block(UPLOAD_STORY, UPLOAD_CRITERIA)
    from qagenius.shadow_qa.packs import SEVERITY_RANK, check_by_id

    ranks = [
        SEVERITY_RANK[check_by_id(one).severity]
        for one in ids
        if not one.startswith("boundary:")
    ]
    assert ranks == sorted(ranks)


# ── brittle selectors ─────────────────────────────────────────────────────────


def _selector_messages(code: str) -> str:
    return " ".join(
        one.message for one in review_automation(script(), [_file("a.ts", code)])
    )


def test_a_five_element_tag_chain_is_flagged():
    code = "await page.locator('div > ul > li > a > span').click();"
    assert "levels deep" in _selector_messages(code)


def test_four_descendant_spaces_are_four_combinators():
    code = "await page.locator('div ul li a span').click();"
    assert "levels deep" in _selector_messages(code)


def test_sibling_combinators_count_too():
    code = "await page.locator('.a + .b ~ .c > .d .e').click();"
    assert "levels deep" in _selector_messages(code)


def test_three_combinators_are_not_flagged():
    code = "await page.locator('.app > .main > .card > .btn').click();"
    assert "levels deep" not in _selector_messages(code)


def test_a_sentence_in_quotes_is_not_a_selector():
    code = (
        "test('the shopper signs in and sees the basket', async () => {\n"
        "  await expect(page).toHaveTitle('Account locked. Try again in 15 minutes.');\n"
        "});\n"
    )
    assert "levels deep" not in _selector_messages(code)


def test_a_role_selector_is_never_called_brittle():
    code = (
        "test('TC-001', async ({ page }) => {\n"
        "  await page.getByRole('button', { name: 'Sign in and continue now' }).click();\n"
        "  await expect(page.getByLabel('Email or user name goes here')).toBeVisible();\n"
        "});\n"
    )
    assert "levels deep" not in _selector_messages(code)


# ── phase 13: the reviewer reads the story before it speaks ───────────────────


def test_a_risk_the_ai_said_in_other_words_is_not_added_again():
    """The real run: the AI called it a timing side-channel, the pack calls it
    a response time. The titles share almost nothing, so what the AI says the
    risk does is what matches: two of the pack's own words, not one."""
    analysis = RiskAnalysis(
        failure_modes=[
            _risk(
                "Timing side-channel attack distinguishes valid vs invalid emails",
                effect="The response time alone tells an attacker which emails exist.",
                cause="The sign-in path is not constant time for an unknown email.",
            )
        ]
    )
    added = review_risks(LOCKOUT_STORY, LOCKOUT_CRITERIA, analysis)
    assert not any("Response time differs" in one.title for one in added)


def test_the_words_are_looked_for_in_the_effect_and_cause_too():
    analysis = RiskAnalysis(
        failure_modes=[
            _risk(
                "Sign-in is not constant work",
                effect="An attacker measures the response time to find real accounts.",
                cause="The timing differs because hashing only runs for a known email.",
            )
        ]
    )
    added = review_risks(LOCKOUT_STORY, LOCKOUT_CRITERIA, analysis)
    assert not any("Response time differs" in one.title for one in added)


def test_one_shared_word_does_not_make_two_risks_one():
    """The real run: an AI risk about timing said "enumerate" in passing, and
    swallowed the quite separate risk that the error message names an account."""
    analysis = RiskAnalysis(
        failure_modes=[
            _risk(
                "Attackers enumerate emails by response times",
                effect="An attacker can enumerate which emails are registered.",
                cause="The sign-in path returns sooner for an unknown email.",
            )
        ]
    )
    added = review_risks(LOCKOUT_STORY, LOCKOUT_CRITERIA, analysis)
    assert any("reveals whether an email is registered" in one.title for one in added)


def test_two_words_in_the_two_titles_are_enough_to_be_one_risk():
    """"Enumeration of registered emails" is the pack's risk under a shorter name.

    The AI often puts the whole problem in the title and leaves the effect
    and the cause saying something general, so the names are compared in
    their plain form: "registered" and "emails" are "register" and "email".
    """
    ai = _risk(
        "Enumeration of registered emails",
        effect="Something bad happens.",
        cause="It was built that way.",
    )
    added = review_risks(LOCKOUT_STORY, LOCKOUT_CRITERIA, RiskAnalysis(failure_modes=[ai]))
    assert not any("reveals whether an email is registered" in one.title for one in added)
    # The risk that stayed can now be linked to the test that covers it.
    assert "enumeration" in ai.covered_if


def test_a_genuinely_new_risk_is_still_added():
    analysis = RiskAnalysis(failure_modes=[_risk("The audit log fills the disk")])
    added = review_risks(LOCKOUT_STORY, LOCKOUT_CRITERIA, analysis)
    assert any("reveals whether an email" in one.title for one in added)


def test_an_added_risk_carries_the_words_that_mean_it_is_tested():
    added = review_risks(LOCKOUT_STORY, LOCKOUT_CRITERIA, RiskAnalysis())
    assert added and all(one.covered_if for one in added)


def test_a_lockout_story_gets_no_case_about_email_language():
    """only_if: a check about one narrow thing waits until the story raises it."""
    review = review_test_cases(LOCKOUT_STORY, LOCKOUT, suite(case()))
    titles = " ".join(one.title.lower() for one in review.added + [])
    listed = " ".join(one.title.lower() for one in review.more)
    assert "language" not in titles and "language" not in listed


def test_a_story_about_languages_does_get_that_check():
    story = (
        "As a shopper, I want the emails Aurora Storefront sends me to arrive in "
        "my own language so that I can read them."
    )
    criteria = number_criteria(
        [
            "A notification email uses the language set on the account",
            "An email is queued and sent by a background job",
        ]
    )
    review = review_test_cases(story, criteria, suite(case()))
    offered = [one.title.lower() for one in review.added] + [
        one.title.lower() for one in review.more
    ]
    assert any("language" in title for title in offered)


def test_an_added_case_is_linked_to_the_criterion_it_is_about():
    """The real run linked "two devices" to the unlock criterion, not the limit."""
    criteria = number_criteria(
        [
            "The account locks after 5 failed sign-in attempts in 15 minutes",
            "Support can unlock the account for the user straight away",
        ]
    )
    # Cover the checks that would otherwise fill the eight slots first.
    already = suite(
        case(case_id="TC-001", title="Sign in with the email in capital letters"),
        case(case_id="TC-002", title="Unknown email gives the same message"),
        case(case_id="TC-003", title="A script in the email field is escaped"),
        case(case_id="TC-004", title="The nth attempt locks, the one below does not"),
        case(case_id="TC-005", title="The counter resets once the window has passed"),
        case(case_id="TC-006", title="A trailing space in the email is trimmed"),
    )
    review = review_test_cases(LOCKOUT_STORY, criteria, already)
    by_check = {
        tag[len("qa:") :]: one
        for one in review.added
        for tag in one.tags
        if tag.startswith("qa:")
    }
    per_account = by_check["rate_limiting.per_account"]
    assert "two devices" in per_account.title
    assert per_account.traceability == "AC-1"


# ── a limit case anybody can run ─────────────────────────────────────────────


def _photo_limit_case(*written):
    """The limit case the reviewer adds to a photo suite."""
    review = review_test_cases(
        PHOTO_STORY, number_criteria(PHOTO_CRITERIA), suite(*written)
    )
    added = [one for one in review.added if "pack:boundary" in one.tags]
    assert added, "no limit case was added"
    return added[0]


def test_a_limit_case_is_the_criterion_written_out_as_steps():
    """Test B: "Exercise it at 1.99 MB" is not a test anybody can run.

    The criterion is already the test in English, so its When lines are the
    steps and its Then lines are what should happen.
    """
    limit = _photo_limit_case(
        case(
            case_id="TC-001",
            title="Upload a small JPEG photo",
            steps=["Choose a 1 MB JPEG photo and upload it"],
            expected_result="The photo is shown.",
            traceability="AC-1",
        ),
        case(
            case_id="TC-005",
            title="At the size limit",
            steps=["Choose a 2 MB JPEG photo and upload it"],
            expected_result="It is rejected with a message.",
            traceability="AC-1",
        ),
        case(
            case_id="TC-006",
            title="Over the size limit",
            steps=["Choose a 2.01 MB JPEG photo and upload it"],
            expected_result="It is rejected with a message.",
            traceability="AC-3",
        ),
    )
    assert limit.steps == [
        "Select a JPEG photo of 1.99 MB.",
        "Upload the photo.",
        "Check the result.",
    ]
    # The Given line is what has to be true first, not a step.
    assert limit.pre_conditions == "The user is on the profile page."
    for word in ("cropped", "saved", "shown"):
        assert word in limit.expected_result, word
    assert "JPEG photo" in limit.test_data and "1.99 MB" in limit.test_data


def test_the_value_only_goes_in_the_line_that_states_the_limit():
    limit = _photo_limit_case(
        case(case_id="TC-001", title="A 1 MB photo", traceability="AC-1")
    )
    assert "Upload the photo." in limit.steps
    assert "Upload the photo at 1.99 MB." not in limit.steps


def test_the_outcome_over_the_limit_comes_from_the_rejecting_criterion():
    limit = _photo_limit_case(
        case(case_id="TC-001", title="A 1 MB photo", traceability="AC-1")
    )
    assert "rejected with a message about the 2 MB limit (AC-3)" in limit.expected_result


def test_a_time_limit_is_waited_out_not_exercised():
    """The lockout example: 29 and 31 minutes have to read as real steps."""
    criteria = number_criteria(["A locked account stays locked for 30 minutes"])
    review = review_test_cases(
        "As a shopper, I want my account to lock so that it stays safe.",
        criteria,
        suite(case(case_id="TC-001", traceability="AC-1")),
    )
    added = [one for one in review.added if "pack:boundary" in one.tags]
    assert added
    assert added[0].steps == ["Wait 29 minutes.", "Wait 31 minutes.", "Check the result."]


def test_a_count_limit_uses_the_criterion_own_words():
    criteria = number_criteria(["The account locks after 5 failed sign-in attempts"])
    review = review_test_cases(
        "As a shopper, I want my account to lock so that it stays safe.",
        criteria,
        suite(case(case_id="TC-001", traceability="AC-1")),
    )
    added = [one for one in review.added if "pack:boundary" in one.tags]
    assert added
    assert "Reach 4 failed sign-in attempts." in added[0].steps
    assert not any("Exercise it" in step for step in added[0].steps)


# ── a test that disagrees with the limit ─────────────────────────────────────


def _at_the_limit(expected: str):
    return case(
        case_id="TC-005",
        title="A photo at the size limit",
        steps=["Choose a 2MB JPEG photo and upload it"],
        expected_result=expected,
        traceability="AC-1",
    )


def _about_the_case(notes: list[str]) -> list[str]:
    """The notes about a test case, not the ones about the criteria."""
    return [one for one in notes if one.startswith("TC-")]


def test_a_test_that_disagrees_with_the_limit_is_called_out():
    """Test B: AC-1 says "under 2 megabytes" and TC-005 accepts exactly 2 MB."""
    notes = _about_the_case(
        limit_conflicts(
            number_criteria(PHOTO_CRITERIA),
            [_at_the_limit("The exact 2MB file is accepted and saved.")],
        )
    )
    assert len(notes) == 1
    note = notes[0]
    assert "TC-005 expects a JPEG photo of exactly 2 MB to be accepted" in note
    assert 'AC-1 says "under 2 megabytes"' in note
    assert "exactly 2 MB should be refused" in note
    assert "ask which is meant" in note


def test_only_the_sentence_about_the_limit_itself_is_read():
    """"A 2.01 MB photo is rejected" says nothing about a photo of 2 MB."""
    both = case(
        case_id="TC-007",
        title="Around the size limit",
        steps=["Upload a 2.01 MB photo", "Upload a 2 MB photo"],
        expected_result=(
            "The 2.01 MB photo is rejected. The 2 MB photo is accepted and saved."
        ),
        traceability="AC-1",
    )
    notes = _about_the_case(limit_conflicts(number_criteria(PHOTO_CRITERIA), [both]))
    assert len(notes) == 1
    assert "exactly 2 MB to be accepted" in notes[0]


def test_a_case_only_about_a_hair_over_the_limit_is_left_alone():
    """"2 MB and 1 byte" is the value past the limit, not the limit."""
    over = case(
        case_id="TC-008",
        title="Just over the size limit",
        steps=["Upload a photo of 2 MB and 1 byte"],
        expected_result="It is rejected with a message about the 2 MB limit.",
        traceability="AC-3",
    )
    assert _about_the_case(
        limit_conflicts(number_criteria(PHOTO_CRITERIA), [over])
    ) == []


def test_two_criteria_that_disagree_about_the_limit_are_called_out():
    """AC-1 refuses exactly 2 MB; AC-3 only refuses what is larger."""
    notes = limit_conflicts(number_criteria(PHOTO_CRITERIA), [])
    assert len(notes) == 1
    assert notes[0] == (
        'AC-1 says "under 2 megabytes" (so exactly 2 MB is refused) but AC-3 '
        'only refuses photos "larger than 2 megabytes" (so exactly 2 MB is '
        "accepted). Decide which is right."
    )


def test_criteria_that_agree_about_the_limit_say_nothing():
    criteria = number_criteria(
        [
            "When the user selects a JPEG photo up to 2 megabytes, "
            "Then the photo is saved",
            "When the user selects a photo larger than 2 megabytes, "
            "Then the upload is rejected",
        ]
    )
    assert limit_conflicts(criteria, []) == []


def test_a_limit_that_includes_its_own_value_agrees_with_that_test():
    criteria = number_criteria(
        ["The user can select a JPEG photo up to 2 megabytes and upload it"]
    )
    assert limit_conflicts(criteria, [_at_the_limit("The 2MB file is accepted.")]) == []


def test_a_test_that_refuses_the_limit_value_agrees_with_under():
    criteria = number_criteria(PHOTO_CRITERIA)
    assert _about_the_case(
        limit_conflicts(criteria, [_at_the_limit("The 2MB file is rejected with a message.")])
    ) == []


def test_the_conflict_is_a_note_not_a_new_test_case():
    criteria = number_criteria(PHOTO_CRITERIA)
    review = review_test_cases(
        PHOTO_STORY, criteria, suite(_at_the_limit("The exact 2MB file is accepted."))
    )
    assert _about_the_case(review.conflicts)
    assert not any("disagree" in one.title.lower() for one in review.added)


# ── the added limit test follows the limit rule ──────────────────────────────

UP_TO_2MB = (
    "Given the user is on the profile page, When the user selects a JPEG "
    "photo up to 2 megabytes And uploads the photo, Then the photo is saved"
)


def _limit_case_for(*texts):
    """The limit case the reviewer adds for these criteria."""
    review = review_test_cases(
        PHOTO_STORY,
        number_criteria(list(texts)),
        suite(case(case_id="TC-001", title="A 1 MB photo", traceability="AC-1")),
    )
    added = [one for one in review.added if "pack:boundary" in one.tags]
    assert added, "no limit case was added"
    return added[0]


def test_at_the_limit_a_criterion_that_excludes_it_asks_for_a_refusal():
    """AC-1 says "under 2 megabytes", so the added test must not accept 2 MB."""
    limit = _limit_case_for(PHOTO_CRITERIA[0])
    # The line opens with the value, so it is not prefixed with it again.
    assert '2 MB is refused: AC-1 says "under 2 megabytes"' in (
        limit.expected_result
    )
    assert "At 2 MB: the photo is" not in limit.expected_result


def test_at_the_limit_a_criterion_that_includes_it_asks_for_a_success():
    limit = _limit_case_for(UP_TO_2MB)
    assert "At 2 MB: the photo is saved" in limit.expected_result
    assert "At 2 MB: 2 MB is refused" not in limit.expected_result


def test_at_the_limit_criteria_that_disagree_send_the_reader_to_the_note():
    limit = _limit_case_for(PHOTO_CRITERIA[0], PHOTO_CRITERIA[2])
    assert f"At 2 MB: {DISPUTED_OUTCOME}" in limit.expected_result
    # And the note it points at is on the card above it.
    review = review_test_cases(
        PHOTO_STORY,
        number_criteria([PHOTO_CRITERIA[0], PHOTO_CRITERIA[2]]),
        suite(case(case_id="TC-001", title="A 1 MB photo", traceability="AC-1")),
    )
    assert any("Decide which is right." in one for one in review.conflicts)


def test_a_rejection_rule_leaves_the_limit_value_itself_allowed():
    """"Larger than 2 megabytes is rejected" accepts a photo of exactly 2 MB.

    And its own words are about the photo that was refused, so they are not
    the answer for the one that was not.
    """
    limit = _limit_case_for(PHOTO_CRITERIA[2])
    assert "2 MB is inside the limit AC-1 states, so it is accepted" in (
        limit.expected_result
    )
    assert "At 2 MB: the upload is rejected" not in limit.expected_result


# ── nobody decided what happens at the limit ─────────────────────────────────


def test_a_value_both_criteria_step_around_is_called_a_gap():
    """The coupon run: AC-1 starts above $50, AC-2 stops below it."""
    notes = limit_conflicts(number_criteria(COUPON_CRITERIA), [])
    assert notes == [
        'AC-1 covers "more than $50" and AC-2 covers "less than $50". Nobody '
        "says what happens at exactly $50. Decide, then add it to a criterion."
    ]


def test_the_context_is_read_as_a_rule_of_its_own():
    criteria = with_context(number_criteria(COUPON_CRITERIA), COUPON_CONTEXT)
    notes = limit_conflicts(criteria, [])
    assert any(
        one
        == 'The context says "at least $50" (so exactly $50 works) but AC-1 '
        'says "more than $50" (so exactly $50 doesn\'t). Decide which is right.'
        for one in notes
    ), notes


def test_criteria_that_meet_at_the_value_leave_no_gap():
    criteria = number_criteria(
        [
            "Given a cart of $50 or more When a coupon is entered Then the "
            "discount is applied",
            "Given a cart of less than $50 When a coupon is entered Then it "
            "is refused",
        ]
    )
    assert limit_conflicts(criteria, []) == []


def test_a_limit_test_at_an_undecided_value_says_so():
    """Asking for a test at $50 would be asking for a guess."""
    review = review_test_cases(
        COUPON_STORY,
        number_criteria(COUPON_CRITERIA),
        suite(case(case_id="TC-001", title="A $90 cart", traceability="AC-1")),
        COUPON_CONTEXT,
    )
    limit = next(
        one
        for one in review.added
        if "pack:boundary" in one.tags and "$50" in one.title
    )
    assert f"At $50.00: {DISPUTED_OUTCOME}" in limit.expected_result
    assert DISPUTED_OUTCOME == "Not decided yet — see the note above."


def test_the_cap_nobody_wrote_down_becomes_a_test():
    """20% off, capped at $30, changes behaviour at a $150 order."""
    review = review_test_cases(
        COUPON_STORY,
        number_criteria(COUPON_CRITERIA),
        suite(case(case_id="TC-001", title="A $90 cart", traceability="AC-1")),
        COUPON_CONTEXT,
    )
    titles = [one.title for one in review.added if "pack:boundary" in one.tags]
    assert any("$149.99" in one and "$150.01" in one for one in titles), titles


# ── a check inside a page object is still a check ────────────────────────────

_PAGE_OBJECT = """
export class CheckoutPage {
  async expectErrorMessage(text) {
    await expect(this.page.getByRole('alert')).toHaveText(text);
  }
  async applyCoupon(code) {
    await this.page.getByLabel('Coupon').fill(code);
  }
}
"""

_POM_SPEC = """
test('TC-002: a short cart refuses the coupon', async ({ page }) => {
  const checkout = new CheckoutPage(page);
  await checkout.applyCoupon('SAVE20');
  await checkout.expectErrorMessage('This coupon needs an order of at least $50.');
});
"""

_CLICK_ONLY = """
test('TC-003: the apply button is there', async ({ page }) => {
  await page.getByRole('button', { name: 'Apply' }).click();
});
"""


def test_a_test_that_checks_through_a_page_object_is_not_flagged():
    """The false alarm from the coupon run: the expect( is one file over."""
    findings = review_automation(
        script(),
        [
            _file("pages/checkout_page.ts", _PAGE_OBJECT),
            _file("tests/coupon.spec.ts", _POM_SPEC),
        ],
    )
    assert [one for one in findings if "never asserts" in one.message] == []


def test_a_test_that_only_clicks_is_still_flagged():
    findings = review_automation(
        script(),
        [
            _file("pages/checkout_page.ts", _PAGE_OBJECT),
            _file("tests/coupon.spec.ts", _CLICK_ONLY),
        ],
    )
    assert [one for one in findings if "never asserts" in one.message]


def test_a_method_named_for_checking_counts_even_without_its_file():
    """`verifyTotal(...)` says what it does; the file it lives in may be the AI's."""
    spec = """
test('TC-004: the total is right', async ({ page }) => {
  await cart.verifyTotal('$47.99');
});
"""
    findings = review_automation(script(), [_file("tests/cart.spec.ts", spec)])
    assert [one for one in findings if "never asserts" in one.message] == []


def test_the_context_switches_on_the_checks_it_describes():
    """"Guests can use coupons too" is in the context, not in a criterion."""
    ai = suite(
        case(case_id="TC-001", title="A valid coupon on a $90 cart", traceability="AC-1")
    )
    criteria = number_criteria(COUPON_CRITERIA)
    without = review_test_cases(COUPON_STORY, criteria, ai)
    with_it = review_test_cases(COUPON_STORY, criteria, ai, COUPON_CONTEXT)
    titles = " | ".join(one.title for one in with_it.added)
    assert "guest" in titles.lower()
    assert "Two tabs" in titles
    assert "guest" not in " | ".join(one.title for one in without.added).lower()


def test_the_coupon_run_adds_the_tests_the_senior_tester_missed():
    """The owner's re-test, in one place."""
    ai = suite(
        case(case_id="TC-001", title="A valid coupon on a $90 cart", traceability="AC-1"),
        case(case_id="TC-002", title="A $30 cart is refused", traceability="AC-2"),
    )
    review = review_test_cases(
        COUPON_STORY, number_criteria(COUPON_CRITERIA), ai, COUPON_CONTEXT
    )
    titles = " | ".join(one.title for one in review.added)
    for wanted in ("$49.99", "$149.99", "Removing items after the coupon", "15% of $59.99"):
        assert wanted in titles or wanted.lower() in titles.lower(), wanted
    # And nothing about a card: this story never pays for anything.
    assert "declined" not in titles.lower()
    assert "double click" not in titles.lower()


# ── which side of the limit works ────────────────────────────────────────────


def _coupon_limit_case(title: str):
    """The added boundary case whose title names this value."""
    review = review_test_cases(
        COUPON_STORY,
        number_criteria(COUPON_CRITERIA),
        suite(case(case_id="TC-001", title="A $90 cart", traceability="AC-1")),
        COUPON_CONTEXT,
    )
    return next(
        one
        for one in review.added
        if "pack:boundary" in one.tags and title in one.title
    )


def test_a_minimum_refuses_the_value_under_it_and_accepts_the_one_over():
    """"More than $50" is a floor: $49.99 is the refusal, $50.01 the success.

    Read as a ceiling it asks for a test that expects a $49.99 order to be
    discounted, which is the bug the whole reviewer exists to catch.
    """
    limit = _coupon_limit_case("$49.99")
    assert (
        "At $49.99: the coupon is refused with the message "
        '"This coupon needs an order of at least $50." (AC-2)'
    ) in limit.expected_result
    assert "At $50.01: the discount is applied" in limit.expected_result


# ── the cap test does the sum ────────────────────────────────────────────────


def test_the_cap_case_works_out_each_discount_to_the_cent():
    """The $150 nobody wrote down, with the arithmetic that found it.

    A tester asked to try "one cent under the cap total" still has to work
    out what should come back. Three numbers, three answers, and the one
    that rounds is named as the one to go and ask about.
    """
    limit = _coupon_limit_case("$149.99")
    said = limit.expected_result
    assert (
        "At $149.99: 20% is $29.998, so the discount is $30.00 after rounding "
        "to the cent — check the shop rounds this way (it could also be "
        "$29.99)."
    ) in said
    assert "At $150.00: 20% is exactly $30.00 — the cap." in said
    assert (
        "At $150.01: 20% is $30.002, so the cap applies and the discount "
        "stays $30.00."
    ) in said


# ── windows are not limits ───────────────────────────────────────────────────

WINDOW_CRITERIA = [
    "After 5 failed sign-in attempts within 10 minutes, the account is "
    "locked for 15 minutes.",
]


def _outcome_at(criteria: list[str], value: str) -> str:
    from qagenius.shadow_qa.boundaries import find_boundaries
    from qagenius.shadow_qa.review import Setting, _boundary_outcome

    ruled = number_criteria(criteria)
    boundary = next(
        one for one in find_boundaries(ruled) if one.values[1] == value
    )
    setting = Setting(page="", criteria=ruled, rules=(), disputed=frozenset())
    return _boundary_outcome(boundary, boundary.values[2], setting)


def test_just_outside_a_window_the_rule_does_not_apply():
    # The run this came from asked for a test expecting a lock at 11 minutes,
    # which is the one minute at which the rule stops reaching the attempts.
    said = _outcome_at(WINDOW_CRITERIA, "10 minutes")
    assert "does not apply" in said
    assert "NOT locked" in said
    assert "refused" not in said


def test_just_past_a_plain_limit_the_rule_still_bites():
    said = _outcome_at(["A locked account stays locked for 30 minutes"], "30 minutes")
    assert "window" not in said


def test_a_window_is_only_a_window_when_something_is_counted_inside_it():
    from qagenius.shadow_qa.boundaries import find_boundaries
    from qagenius.shadow_qa.review import is_window

    plain = number_criteria(["The page loads within 2 seconds"])
    boundary = find_boundaries(plain)[0]
    assert not is_window(boundary, plain[0].text)


# ── the senior tester reads the test's real values ───────────────────────────


def test_a_number_only_in_the_title_is_not_the_test_s_value():
    # A real run called a $75 cart "exactly $50" because the title said
    # "order over $50".
    cases = [
        case(
            case_id="TC-005",
            title="Discount applied for an order over $50",
            traceability="AC-1",
            steps=["Add items to the cart", "Enter the coupon code"],
            test_data="cart_total=75.00, coupon=SAVE20",
            expected_result="The discount is applied and the new total is shown",
        )
    ]
    notes = limit_conflicts(
        with_context(number_criteria(COUPON_CRITERIA), COUPON_CONTEXT), cases
    )
    assert not any("TC-005" in note for note in notes)


def test_the_test_data_is_read_for_the_limit_value():
    cases = [
        case(
            case_id="TC-008",
            title="Coupon on a small cart",
            traceability="AC-2",
            steps=["Enter the coupon code"],
            test_data="cart_total=50.00",
            expected_result="The coupon is refused",
        )
    ]
    criteria = number_criteria(
        ["Given a cart of at least $50 When a valid coupon is entered "
         "Then the discount is applied"]
    )
    notes = limit_conflicts(criteria, cases)
    assert any("TC-008" in note and "50" in note for note in notes)


# ── no duplicate count tests ─────────────────────────────────────────────────


def test_a_count_the_ai_already_used_is_not_asked_for_again():
    from qagenius.shadow_qa.boundaries import find_boundaries, missing_values

    ruled = number_criteria(["The account locks after 5 failed sign-in attempts"])
    boundary = next(one for one in find_boundaries(ruled) if one.kind == "count")
    assert boundary.values == ["4 attempts", "5 attempts", "6 attempts"]
    cases = [
        case(
            case_id="TC-001",
            steps=["Sign in wrongly 4 times", "Try a 5th time"],
            test_data="attempts=6",
            expected_result="The account is locked",
        )
    ]
    assert missing_values(boundary, cases) == []


def test_every_way_a_tester_writes_a_count_is_read():
    from qagenius.shadow_qa.boundaries import scan, states

    for said in ("the 6th attempt", "the sixth wrong password", "6 times",
                 "6 wrong passwords", "attempts=6", "6 attempts"):
        assert states("6 attempts", scan(said)), said


# ── two tests that disagree about the same rule ──────────────────────────────


def test_two_cases_that_lock_at_different_counts_are_named():
    from qagenius.shadow_qa.review import trigger_disagreements

    cases = [
        case(
            case_id="TC-001",
            traceability="AC-1",
            steps=["Enter a wrong password 5 times", "Enter it once more"],
            test_data="attempts=6",
            expected_result="The account is locked and sign-in is refused",
        ),
        case(
            case_id="TC-007",
            traceability="AC-1",
            steps=["Enter a wrong password 5 times"],
            test_data="attempts=5",
            expected_result="The account is locked and sign-in is refused",
        ),
    ]
    notes = trigger_disagreements(cases)
    assert len(notes) == 1
    assert "TC-001" in notes[0] and "6th" in notes[0]
    assert "TC-007" in notes[0] and "5th" in notes[0]
    assert "Decide which is right." in notes[0]


def test_two_cases_that_agree_say_nothing():
    from qagenius.shadow_qa.review import trigger_disagreements

    cases = [
        case(case_id="TC-001", traceability="AC-1", test_data="attempts=6",
             expected_result="The account is locked and sign-in is refused"),
        case(case_id="TC-002", traceability="AC-1", test_data="attempts=6",
             expected_result="The account is locked and sign-in is refused"),
    ]
    assert trigger_disagreements(cases) == []


def test_the_boundary_reason_names_only_the_values_that_were_missing():
    from qagenius.shadow_qa.review import reason_for

    added = case(
        case_id="TC-009",
        category="Boundary",
        title="Boundary value at 6 attempts (AC-1)",
        tags=["principal-qa", "pack:boundary"],
    )
    assert reason_for(added) == (
        "The limit is where this breaks, and no case uses 6 attempts."
    )


# ── coupon and data rules ───────────────────────────────────────────────────


def test_a_success_test_whose_data_breaks_the_rule_is_named():
    from qagenius.shadow_qa.review import precondition_notes

    criteria = with_context(number_criteria(COUPON_CRITERIA), COUPON_CONTEXT)
    bad = case(
        case_id="TC-008",
        traceability="AC-1",
        title="Coupon applies to a small cart",
        pre_conditions="A cart with one item",
        steps=["Enter the coupon code", "Apply it"],
        test_data="cart_total=19.99, coupon=SAVE20",
        expected_result="The discount is applied and the new total is shown",
    )
    notes = precondition_notes(criteria, [bad])
    assert len(notes) == 1
    assert "TC-008 uses $19.99" in notes[0]
    assert "can't pass as written" in notes[0]


def test_a_success_test_whose_data_fits_is_left_alone():
    from qagenius.shadow_qa.review import precondition_notes

    criteria = with_context(number_criteria(COUPON_CRITERIA), COUPON_CONTEXT)
    good = case(
        case_id="TC-005",
        traceability="AC-1",
        test_data="cart_total=75.00, coupon=SAVE20",
        expected_result="The discount is applied and the new total is shown",
    )
    assert precondition_notes(criteria, [good]) == []


def test_two_tests_that_round_the_same_sum_differently_are_named():
    from qagenius.shadow_qa.review import rounding_notes

    first = case(
        case_id="TC-003",
        title="15% off a 59.99 cart",
        test_data="cart=59.99, coupon=15%",
        expected_result="The discount is 8.99 and the total is 51.00",
    )
    second = case(
        case_id="TC-004",
        title="15% off a 59.99 cart at payment",
        test_data="cart=59.99, coupon=15%",
        expected_result="The discount is 9.00 and the total is 50.99",
    )
    notes = rounding_notes([first, second])
    assert len(notes) == 1
    assert "TC-003 expects 8.99 off" in notes[0]
    assert "TC-004 expects 9.00 off" in notes[0]
    assert "how the shop rounds the cent" in notes[0]


def test_two_tests_that_round_the_same_way_say_nothing():
    from qagenius.shadow_qa.review import rounding_notes

    first = case(
        case_id="TC-003",
        test_data="cart=59.99, coupon=15%",
        expected_result="The discount is 9.00",
    )
    second = case(
        case_id="TC-004",
        test_data="cart=59.99, coupon=15%",
        expected_result="The discount is 9.00",
    )
    assert rounding_notes([first, second]) == []


def test_word_stem_duplicates_are_one_risk():
    from qagenius.shadow_qa.packs import PackRisk
    from qagenius.shadow_qa.review import _twin

    written = FailureMode(
        id="R1",
        title="Coupon removed on refresh",
        category="functional",
        effect="The shopper loses the discount",
        cause="The cart reloads without the coupon",
        severity=4,
        likelihood=3,
        detectability=3,
    )
    same = PackRisk(
        pack_id="coupon",
        title="Coupon removes itself when the page refreshes",
        category="functional",
        effect="The discount is lost",
        cause="A refresh drops it",
        severity=4,
        likelihood=3,
        detectability=3,
        covered_if=("refresh",),
    )
    assert _twin(same, [written]) is written


# ── a duration that says how long a state lasts ─────────────────────────────

LOCK_LASTS = [
    "The account locks after 5 failed sign-in attempts",
    "A locked account stays locked for 15 minutes",
    "When 15 minutes have passed Then the shopper can sign in with the "
    "correct password",
]


def _outcomes(criteria: list[str], value: str) -> list[str]:
    """What the added limit test expects at each of a boundary's values."""
    from qagenius.shadow_qa.boundaries import find_boundaries
    from qagenius.shadow_qa.review import Setting, _boundary_outcome

    ruled = number_criteria(criteria)
    boundary = next(
        one for one in find_boundaries(ruled) if one.values[1] == value
    )
    setting = Setting(page="", criteria=ruled, rules=(), disputed=frozenset())
    return [_boundary_outcome(boundary, one, setting) for one in boundary.values]


def test_before_the_lock_ends_the_account_is_still_locked():
    before, _, _ = _outcomes(LOCK_LASTS, "15 minutes")
    assert "14 minutes" in before
    assert "still locked" in before
    assert "sign in" not in before


def test_at_the_end_the_criterion_that_describes_it_answers():
    _, at, _ = _outcomes(LOCK_LASTS, "15 minutes")
    assert "At exactly 15 minutes it stops being locked" in at
    assert "the shopper can sign in with the correct password" in at


def test_after_the_lock_ends_the_correct_password_signs_in():
    # A run asked for a test expecting a locked account at 16 minutes of a
    # 15-minute lock, which is the one minute at which the lock is over.
    _, _, after = _outcomes(LOCK_LASTS, "15 minutes")
    assert "16 minutes" in after
    assert "no longer locked" in after
    assert "sign in" in after
    assert "refused" not in after


def test_with_no_criterion_about_the_end_the_moment_itself_is_a_question():
    _, at, after = _outcomes(["A locked account stays locked for 15 minutes"], "15 minutes")
    assert at == (
        "Check what happens at exactly 15 minutes — the criteria do not say "
        "whether it is still locked the moment the time runs out"
    )
    assert "no longer locked: it works again" in after


def test_a_validity_period_runs_the_other_way():
    before, _, after = _outcomes(["A coupon is valid for 30 days"], "30 days")
    assert "29 days" in before and "still valid" in before and "works" in before
    assert "31 days" in after
    assert "no longer valid" in after
    assert "refused" in after


def test_something_that_expires_after_a_time_was_valid_until_then():
    before, _, after = _outcomes(
        ["A password reset link expires after 24 hours"], "24 hours"
    )
    assert "still valid" in before
    assert "no longer valid" in after and "refused" in after


def test_a_lock_duration_is_not_read_as_the_window_beside_it():
    story = [
        "After 5 failed login attempts within 10 minutes, the account is "
        "locked for 15 minutes."
    ]
    _, _, window_after = _outcomes(story, "10 minutes")
    assert "does not apply" in window_after  # the window the attempts fall in
    before, _, lock_after = _outcomes(story, "15 minutes")
    assert "still locked" in before
    assert "no longer locked" in lock_after


def test_a_plain_limit_is_still_a_limit():
    outcomes = _outcomes(["The page loads within 2 seconds"], "2 seconds")
    assert not any("stays" in one for one in outcomes)
    assert "refused" in outcomes[2]


def test_the_same_stretch_said_from_the_other_side_is_read_the_same_way():
    # The saved sample writes the lock duration as "30 minutes have not yet
    # passed", and the added test used to expect a refusal at 31 minutes.
    before, _, after = _outcomes(
        [
            "Given a locked account When 30 minutes have not yet passed "
            "Then sign-in is refused even with the correct password"
        ],
        "30 minutes",
    )
    assert "still locked" in before
    assert "sign-in is refused even with the correct password" in before
    assert "no longer locked" in after
    assert "refused" not in after


def test_a_value_that_opens_a_line_is_not_said_twice():
    from qagenius.web import _example_suite

    _, _, review, _ = _example_suite()
    lock = next(
        one
        for one in review.added
        if one.category == "Boundary" and "minutes" in one.title
    )
    assert "At 29 minutes: 29 minutes" not in lock.expected_result
    assert lock.expected_result.startswith("29 minutes is inside")
