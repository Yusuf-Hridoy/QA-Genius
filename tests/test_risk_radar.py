"""Risk scoring: the AI proposes, code computes. No network."""

import pytest

from qagenius.models import FailureMode, RiskAnalysis
from qagenius.prompts import risk_radar_prompt
from qagenius.risk_radar import (
    MATCH_FLOOR,
    MAX_MATCHED_WORDS,
    case_lines,
    clean_analysis,
    criteria_lines,
    match_score,
    risk_level,
    score_risks,
)
from qagenius.test_cases import number_criteria
from tests.factories import case


def mode(
    risk_id: str = "R1",
    severity: int = 5,
    likelihood: int = 4,
    detectability: int = 4,
    **overrides,
) -> FailureMode:
    values = {
        "id": risk_id,
        "title": "Lockout counter not shared across servers",
        "category": "security",
        "effect": "An attacker keeps guessing passwords past the limit",
        "cause": "Each server keeps its own counter in memory",
        "severity": severity,
        "likelihood": likelihood,
        "detectability": detectability,
        "severity_reason": "Account takeover",
        "likelihood_reason": "Two servers are already running",
        "detectability_reason": "Only shows under a load balancer",
        "related_criteria": ["AC-1"],
        "covered_by": [],
        "test_idea": "Send failed sign-ins through both servers",
    }
    values.update(overrides)
    return FailureMode(**values)


def analysis(*modes: FailureMode) -> RiskAnalysis:
    return RiskAnalysis(failure_modes=list(modes))


# ---------- validators ----------


def test_scores_are_read_from_whatever_the_ai_wrote() -> None:
    risk = mode(severity="4/5", likelihood=7, detectability="high")
    assert (risk.severity, risk.likelihood, risk.detectability) == (4, 5, 3)


def test_a_zero_score_is_clamped_to_one() -> None:
    assert mode(severity=0).severity == 1


def test_a_float_score_is_rounded() -> None:
    assert mode(severity=3.6).severity == 4


def test_categories_are_normalised() -> None:
    assert mode(category="a11y").category == "accessibility"
    assert mode(category=" PERF ").category == "performance"
    assert mode(category="data integrity").category == "data"
    assert mode(category="weird").category == "functional"


# ---------- risk_level ----------


def test_risk_level_counts_the_rpn() -> None:
    assert risk_level(5, 4, 4) == "high"  # 80
    assert risk_level(4, 4, 4) == "high"  # 64
    assert risk_level(4, 3, 3) == "medium"  # 36
    assert risk_level(2, 2, 2) == "low"  # 8


def test_a_severe_likely_failure_is_high_however_easy_it_is_to_spot() -> None:
    assert risk_level(5, 3, 1) == "high"  # rpn 15


# ---------- coverage ----------


def test_a_tagged_case_verifies_the_risk() -> None:
    tagged = case(case_id="TC-012", tags=["login", "RISK:r1"])
    report = score_risks(analysis(mode()), [tagged])
    item = report.risks[0]
    assert item.coverage == "verified"
    assert item.covered_tests == [("TC-012", "Case TC-012", 1.0, [])]


def test_a_claimed_case_about_the_same_thing_covers_the_risk() -> None:
    matching = case(
        case_id="TC-005",
        title="Lockout counter shared across every server",
        expected_result="The counter is shared, so the fifth attempt locks",
    )
    report = score_risks(analysis(mode(covered_by=["TC-005"])), [matching])
    assert report.risks[0].coverage == "covered"
    assert report.risks[0].covered_tests[0][2] > 0


def test_a_claimed_case_about_something_else_is_a_weak_link() -> None:
    unrelated = case(
        case_id="TC-003",
        title="Newsletter footer shows the current year",
        expected_result="The footer prints 2026",
        steps=["Scroll down"],
    )
    report = score_risks(analysis(mode(covered_by=["TC-003"])), [unrelated])
    assert report.risks[0].coverage == "weak"
    assert report.risks[0].covered_tests[0][0] == "TC-003"


def test_a_claimed_id_that_does_not_exist_is_ignored() -> None:
    report = score_risks(analysis(mode(covered_by=["TC-999"])), [case()])
    assert report.risks[0].coverage == "none"
    assert report.risks[0].covered_tests == []


def test_match_score_is_zero_for_unrelated_text() -> None:
    unrelated = case(
        title="Newsletter footer shows the current year",
        expected_result="The footer prints 2026",
        steps=["Scroll down"],
    )
    assert match_score(mode(), unrelated) == (0.0, [])


# ---------- the report ----------


def test_risks_are_sorted_by_rpn_then_severity_then_id() -> None:
    report = score_risks(
        analysis(
            mode("R1", severity=2, likelihood=2, detectability=2),  # 8
            mode("R2", severity=5, likelihood=4, detectability=4),  # 80
            mode("R3", severity=4, likelihood=4, detectability=5),  # 80
            mode("R4", severity=4, likelihood=2, detectability=1),  # 8
        ),
        [],
    )
    assert [item.risk.id for item in report.risks] == ["R2", "R3", "R4", "R1"]


def test_the_heat_map_has_every_cell_and_puts_the_risk_in_its_own() -> None:
    report = score_risks(analysis(mode(severity=5, likelihood=4)), [])
    assert len(report.heatmap) == 25
    assert report.heatmap[(5, 4)] == ["R1"]
    assert report.heatmap[(1, 1)] == []


def test_counts_only_call_a_high_risk_untested_when_no_test_matches() -> None:
    covered = case(
        case_id="TC-005",
        title="Lockout counter shared across every server",
        expected_result="The counter is shared, so the fifth attempt locks",
    )
    report = score_risks(
        analysis(
            mode("R1", covered_by=["TC-005"]),  # high, covered
            mode("R2", title="Lock email arrives late"),  # high, none
            mode("R3", severity=2, likelihood=2, detectability=2),  # low, none
        ),
        [covered],
    )
    assert report.counts == {
        "total": 3,
        "high": 2,
        "medium": 0,
        "low": 1,
        "untested_high": 1,
    }


def test_by_category_keeps_the_fixed_order_and_drops_empty_ones() -> None:
    report = score_risks(
        analysis(
            mode("R1", category="functional"),
            mode("R2", category="security"),
            mode("R3", category="security"),
        ),
        [],
    )
    assert list(report.by_category.items()) == [("security", 2), ("functional", 1)]


# ---------- the prompt ----------


def test_the_prompt_asks_for_breadth_and_forbids_guessing() -> None:
    system, _ = risk_radar_prompt("story", "AC-1: locks", "TC-001 | Functional | lock")
    assert "FMEA" in system
    assert "at least three different categories" in system
    assert "Do not guess" in system


def test_the_user_text_lists_the_criteria_and_the_cases() -> None:
    criteria = number_criteria(["The account locks\nafter 5 attempts", "It stays locked"])
    cases = [case(case_id="TC-001", title="Lock after five"), case(case_id="TC-002")]
    _, user = risk_radar_prompt(
        "As a shopper...", criteria_lines(criteria), case_lines(cases)
    )
    assert "AC-1: The account locks / after 5 attempts" in user
    assert "AC-2: It stays locked" in user
    assert "TC-001 | Functional | Lock after five" in user
    assert user.startswith("User story:\nAs a shopper...")


def test_without_test_cases_the_prompt_says_none_yet() -> None:
    _, user = risk_radar_prompt("story", criteria_lines([]), case_lines([]))
    assert "Existing test cases:\n(none yet)" in user


# ---------- clean_analysis ----------


def test_clean_analysis_renumbers_in_order() -> None:
    cleaned, notes = clean_analysis(
        analysis(mode("R7", title="Second"), mode("", title="First")),
        {"AC-1"},
        set(),
    )
    assert [risk.id for risk in cleaned.failure_modes] == ["R1", "R2"]
    assert [risk.title for risk in cleaned.failure_modes] == ["Second", "First"]
    assert notes == []


def test_clean_analysis_caps_the_list_at_fifteen() -> None:
    many = analysis(*[mode(f"R{n}", title=f"Failure {n}") for n in range(1, 21)])
    cleaned, notes = clean_analysis(many, set(), set())
    assert len(cleaned.failure_modes) == 15
    assert "Kept the first 15 failure modes." in notes


def test_clean_analysis_drops_failure_modes_without_a_title() -> None:
    cleaned, notes = clean_analysis(
        analysis(mode("R1", title="Real"), mode("R2", title="  ")), set(), set()
    )
    assert len(cleaned.failure_modes) == 1
    assert "Dropped 1 failure modes without a title." in notes


def test_clean_analysis_keeps_the_first_of_two_identical_titles() -> None:
    cleaned, notes = clean_analysis(
        analysis(
            mode("R1", title="Counter not shared", effect="first"),
            mode("R2", title="counter NOT shared", effect="second"),
        ),
        set(),
        set(),
    )
    assert len(cleaned.failure_modes) == 1
    assert cleaned.failure_modes[0].effect == "first"
    assert "Removed 1 repeated failure modes." in notes


def test_clean_analysis_removes_ids_the_ai_invented() -> None:
    cleaned, notes = clean_analysis(
        analysis(
            mode(
                "R1",
                related_criteria=["AC-1", "AC-9"],
                covered_by=["tc-001", "TC-404", "TC-405"],
            )
        ),
        {"AC-1", "AC-2"},
        {"TC-001"},
    )
    risk = cleaned.failure_modes[0]
    assert risk.related_criteria == ["AC-1"]
    assert risk.covered_by == ["TC-001"]
    assert "Removed 1 unknown acceptance criteria ids from the AI's list." in notes
    assert "Removed 2 unknown test case ids from the AI's coverage claims." in notes


def test_clean_analysis_does_not_touch_what_it_was_given() -> None:
    original = analysis(mode("R9", covered_by=["TC-404"]))
    clean_analysis(original, set(), set())
    assert original.failure_modes[0].id == "R9"
    assert original.failure_modes[0].covered_by == ["TC-404"]


# ---------- the real run that moved the floor ----------

# R3 and TC-003 from a live run. The two texts share only "focus", "keyboard"
# and "navigation"; TC-003 never opens the mobile overlay the risk is about.
R3_TITLE = "Focus trap inside expanded mobile overlay"
R3_CAUSE = "The overlay does not constrain keyboard focus to its own children"
R3_EFFECT = "A keyboard user tabs behind the overlay and cannot reach the close control"
TC3_TITLE = "Keyboard navigation and focus indicator rings"
TC3_EXPECTED = "Every navigation link shows a visible focus ring in tab order"


def test_the_real_run_claim_is_now_below_the_floor() -> None:
    risk = mode(title=R3_TITLE, cause=R3_CAUSE, effect=R3_EFFECT, covered_by=["TC-003"])
    shallow = case(
        case_id="TC-003",
        title=TC3_TITLE,
        expected_result=TC3_EXPECTED,
        steps=["Press Tab through the navigation"],
    )
    score, words = match_score(risk, shallow)
    assert score < MATCH_FLOOR
    assert "focus" in words and "keyboard" in words
    report = score_risks(analysis(risk), [shallow])
    assert report.risks[0].coverage == "weak"


def test_a_real_overlap_still_counts_as_covered_at_the_new_floor() -> None:
    risk = mode(title=R3_TITLE, cause=R3_CAUSE, effect=R3_EFFECT, covered_by=["TC-007"])
    real = case(
        case_id="TC-007",
        title="Focus stays trapped inside the expanded mobile overlay",
        expected_result="Keyboard focus never leaves the overlay children until it closes",
        steps=["Open the mobile overlay", "Tab through every child"],
    )
    score, _ = match_score(risk, real)
    assert score >= MATCH_FLOOR
    assert score_risks(analysis(risk), [real]).risks[0].coverage == "covered"


def test_matched_words_skip_stopwords_and_short_tokens() -> None:
    risk = mode(title="The overlay traps focus", cause="It is a bug", effect="of the app")
    shared = case(
        case_id="TC-008",
        title="The overlay traps focus",
        expected_result="It is a bug of the app",
        steps=[],
    )
    _, words = match_score(risk, shared)
    assert "the" not in words
    assert "of" not in words
    assert all(len(word) >= 3 for word in words)
    assert words == sorted(words)


def test_at_most_six_matched_words_are_kept() -> None:
    text = "overlay focus keyboard navigation drawer sidebar header footer banner"
    risk = mode(title=text, cause=text, effect=text)
    twin = case(case_id="TC-009", title=text, expected_result=text, steps=[])
    _, words = match_score(risk, twin)
    assert len(words) == MAX_MATCHED_WORDS


# ---------- filler words are not evidence ----------


def test_matched_words_leave_out_the_words_that_join_a_sentence():
    """A real run offered "matched on: and, duration, lockout, message"."""
    risk = mode(title="focus and keyboard", cause="", effect="")
    shared = case(
        case_id="TC-020",
        title="keyboard and focus rings",
        expected_result="",
        steps=[],
    )
    score, words = match_score(risk, shared)
    assert "and" not in words
    assert words == ["focus", "keyboard"]
    assert score > 0


@pytest.mark.parametrize(
    "filler",
    ["and", "or", "but", "not", "no", "when", "then", "than", "that", "this",
     "these", "those", "from", "into", "onto", "by", "as", "at", "it", "its",
     "if", "so", "can", "will", "should", "must", "has", "have", "was", "were",
     "each", "any", "all"],
)
def test_no_filler_word_can_be_a_matched_word(filler):
    risk = mode(title=f"overlay {filler} focus", cause="", effect="")
    shared = case(
        case_id="TC-021",
        title=f"focus {filler} overlay",
        expected_result="",
        steps=[],
    )
    _, words = match_score(risk, shared)
    assert filler not in words
    assert words == ["focus", "overlay"]


def test_filler_words_alone_are_not_a_match():
    risk = mode(title="it has to be and", cause="", effect="")
    unrelated = case(
        case_id="TC-022", title="and it was all", expected_result="", steps=[]
    )
    assert match_score(risk, unrelated) == (0.0, [])


# ── a senior tester's own risk knows the words that cover it ──────────────────


def _pack_risk(title: str, words: list[str], **overrides) -> FailureMode:
    """A risk as review_risks adds it: from the rule packs, with its own words."""
    overrides.setdefault("covered_by", [])
    return mode(title=title, source="principal-qa", covered_if=words, **overrides)


def test_a_senior_tester_risk_is_covered_by_a_case_that_says_its_words():
    """The real run: "System prevents email enumeration" tests exactly this risk."""
    risk = _pack_risk(
        "Error message reveals whether an email is registered",
        ["enumeration", "same message", "reveals whether"],
    )
    tested = case(case_id="TC-003", title="System prevents email enumeration")
    report = score_risks(RiskAnalysis(failure_modes=[risk]), [tested])
    assert report.risks[0].coverage == "covered"
    assert [row[0] for row in report.risks[0].covered_tests] == ["TC-003"]


def test_a_senior_tester_risk_is_covered_by_a_case_that_says_its_words_in_a_step():
    risk = _pack_risk(
        "The attempt limit is counted per IP address rather than per account",
        ["per ip", "two devices", "same account"],
    )
    tested = case(
        case_id="TC-022",
        title="Attempts from two devices count against the same account",
    )
    report = score_risks(RiskAnalysis(failure_modes=[risk]), [tested])
    assert report.risks[0].coverage == "covered"
    assert [row[0] for row in report.risks[0].covered_tests] == ["TC-022"]


def test_a_senior_tester_risk_no_case_mentions_stays_untested():
    risk = _pack_risk(
        "Response time differs between a known and an unknown email",
        ["timing", "response time", "constant time"],
    )
    other = case(case_id="TC-001", title="The account locks after five attempts")
    report = score_risks(RiskAnalysis(failure_modes=[risk]), [other])
    assert report.risks[0].coverage == "none"
    assert report.risks[0].covered_tests == []


def test_the_ai_s_own_risk_is_never_matched_by_words_alone():
    """Only a rule-pack risk carries words that mean a test reaches it."""
    risk = mode(title="Anything", covered_if=["enumeration"], covered_by=[])
    tested = case(case_id="TC-003", title="System prevents email enumeration")
    report = score_risks(RiskAnalysis(failure_modes=[risk]), [tested])
    assert report.risks[0].coverage == "none"


def test_a_tagged_case_still_wins_over_a_word_match():
    risk = _pack_risk(
        "Error message reveals whether an email is registered", ["enumeration"]
    )
    written = case(case_id="TC-050", title="Written for R1", tags=["risk:R1"])
    mentioned = case(case_id="TC-003", title="System prevents email enumeration")
    report = score_risks(RiskAnalysis(failure_modes=[risk]), [written, mentioned])
    scored = report.risks[0]
    assert scored.coverage == "verified"
    assert [row[0] for row in scored.covered_tests] == ["TC-050", "TC-003"]


def test_a_word_match_is_listed_once_even_when_the_ai_also_claimed_it():
    risk = _pack_risk(
        "Error message reveals whether an email is registered",
        ["enumeration"],
        covered_by=["TC-003"],
    )
    tested = case(case_id="TC-003", title="System prevents email enumeration")
    report = score_risks(RiskAnalysis(failure_modes=[risk]), [tested])
    assert [row[0] for row in report.risks[0].covered_tests] == ["TC-003"]
