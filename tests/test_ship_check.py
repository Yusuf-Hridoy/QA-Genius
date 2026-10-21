"""Ship check: every status, every boundary, every verdict rule. No AI anywhere."""

import pytest

from qagenius.models import (
    AmbiguityAnalysis,
    DuelSummary,
    FailureMode,
    RiskAnalysis,
    VaguePhrase,
)
from qagenius.ship_check import (
    CHECK_IDS,
    MatrixRun,
    CORE_CHECKS,
    VERDICT_LABELS,
    ShipInputs,
    compute_ship_report,
)
from tests.factories import case, script, suite

CRITERIA = [
    "The account locks after 5 failed attempts",
    "The lock lasts 30 minutes",
]


def report(**overrides):
    return compute_ship_report(ShipInputs(**overrides))


def status_of(result, check_id: str) -> str:
    return {item.id: item.status for item in result.items}[check_id]


def item_of(result, check_id: str):
    return {item.id: item for item in result.items}[check_id]


# ---------- story clarity ----------


def analysis(ambiguity_score: int, vague: int = 0) -> AmbiguityAnalysis:
    return AmbiguityAnalysis(
        ambiguity_score=ambiguity_score,
        clarity_label="Clear",
        invest_overall="Mostly fine",
        invest_independent="Pass",
        invest_negotiable="Pass",
        invest_valuable="Pass",
        invest_estimable="Pass",
        invest_small="Pass",
        invest_testable="Pass",
        vague_phrases=[
            VaguePhrase(
                phrase=f"quickly {n}",
                severity="High",
                suggestion="Give a number",
                replacement="within 2 seconds",
            )
            for n in range(vague)
        ],
        missing_elements=[],
        suggested_rewrites=[],
        generated_acceptance_criteria=CRITERIA,
        risks=[],
    )


@pytest.mark.parametrize(
    "clarity,expected",
    [(100, "pass"), (70, "pass"), (69, "warn"), (50, "warn"), (49, "fail"), (0, "fail")],
)
def test_clarity_boundaries(clarity, expected):
    result = report(story_analysis=analysis(100 - clarity))
    assert status_of(result, "clarity") == expected


def test_clarity_summary_names_the_number_and_the_vague_phrases():
    result = report(story_analysis=analysis(18, vague=2))
    item = item_of(result, "clarity")
    assert item.summary == "How clear: 82 of 100, 2 unclear words"
    assert len(item.details) == 2


# ---------- ambiguity duel ----------


def duel(agreement: int, *severities: str) -> DuelSummary:
    return DuelSummary(
        agreement_pct=agreement,
        forks=[{"topic": f"Topic {n}", "severity": s} for n, s in enumerate(severities)],
    )


@pytest.mark.parametrize(
    "agreement,expected", [(100, "pass"), (70, "pass"), (69, "warn"), (40, "warn"), (39, "warn")]
)
def test_duel_agreement_boundaries(agreement, expected):
    assert status_of(report(duel=duel(agreement)), "duel") == expected


def test_only_low_forks_with_high_agreement_still_passes():
    assert status_of(report(duel=duel(80, "low", "low")), "duel") == "pass"


def test_a_medium_fork_warns_however_high_the_agreement():
    assert status_of(report(duel=duel(100, "medium")), "duel") == "warn"


def test_a_high_fork_only_warns_however_high_the_agreement():
    # Two AI readers are two opinions, so this check never fails.
    assert status_of(report(duel=duel(100, "high")), "duel") == "warn"



# ---------- criteria coverage ----------


def test_full_coverage_passes():
    cases = suite(case(case_id="TC-001", traceability="AC-1"),
                  case(case_id="TC-002", traceability="AC-2"))
    assert status_of(report(test_cases=cases, criteria=CRITERIA), "coverage") == "pass"


def test_an_uncovered_criterion_fails_and_is_named():
    cases = suite(case(case_id="TC-001", traceability="AC-1"))
    item = item_of(report(test_cases=cases, criteria=CRITERIA), "coverage")
    assert item.status == "fail"
    assert "AC-2" in item.summary
    assert any("AC-2" in line for line in item.details)


def test_coverage_needs_both_the_cases_and_the_criteria():
    cases = suite(case(case_id="TC-001"))
    assert status_of(report(test_cases=cases), "coverage") == "not_checked"
    assert status_of(report(criteria=CRITERIA), "coverage") == "not_checked"


# ---------- test depth ----------


def _deep(ac_id: str, number: int):
    """Three cases for one criterion: functional, negative and boundary."""
    return [
        case(case_id=f"TC-{number}0{n}", category=kind, traceability=ac_id)
        for n, kind in enumerate(("Functional", "Negative", "Boundary"))
    ]


def test_no_thin_criteria_passes():
    cases = suite(*_deep("AC-1", 1), *_deep("AC-2", 2))
    assert status_of(report(test_cases=cases, criteria=CRITERIA), "depth") == "pass"


def test_thin_but_not_more_than_half_warns():
    cases = suite(*_deep("AC-1", 1), case(case_id="TC-200", traceability="AC-2"))
    item = item_of(report(test_cases=cases, criteria=CRITERIA), "depth")
    assert item.status == "warn"
    assert item.summary.startswith("1 of 2 criteria needs more tests")


def test_more_than_half_thin_fails():
    cases = suite(case(case_id="TC-001", traceability="AC-1"),
                  case(case_id="TC-002", traceability="AC-2"))
    assert status_of(report(test_cases=cases, criteria=CRITERIA), "depth") == "fail"


# ---------- risk coverage ----------


def failure_mode(risk_id: str, severity: int, likelihood: int, covered_by=None) -> FailureMode:
    return FailureMode(
        id=risk_id,
        title=f"{risk_id} two servers count tries separately",
        category="security",
        effect="The lock never protects the account",
        cause="Each server counts in its own memory",
        severity=severity,
        likelihood=likelihood,
        detectability=4,
        covered_by=list(covered_by or []),
    )


HIGH = failure_mode("R1", 5, 4)
MEDIUM = failure_mode("R2", 3, 2)


def test_a_high_risk_with_no_test_fails():
    item = item_of(report(risk_analysis=RiskAnalysis(failure_modes=[HIGH])), "risks")
    assert item.status == "fail"
    assert item.summary == "1 high risk has no test"
    assert item.details == [
        "High · R1 R1 two servers count tries separately — no test"
    ]


def test_a_medium_risk_with_no_test_warns():
    assert status_of(
        report(risk_analysis=RiskAnalysis(failure_modes=[MEDIUM])), "risks"
    ) == "warn"


def test_a_high_risk_the_ai_claimed_but_cannot_match_counts_as_untested():
    """covered_by names a case about something else: "weak", not covered.

    Risk radar has always counted this one in its untested-high number, and
    a run showed Ship check saying 1 while Risk radar said 2.
    """
    unrelated = case(case_id="TC-900", title="Shopper updates a delivery address")
    unrelated = unrelated.model_copy(
        update={
            "expected_result": "The address book shows the new street",
            "steps": ["Open the address book", "Edit the street"],
        }
    )
    risk = failure_mode("R1", 5, 4, covered_by=["TC-900"])
    item = item_of(
        report(
            risk_analysis=RiskAnalysis(failure_modes=[risk]),
            test_cases=suite(unrelated),
            criteria=CRITERIA,
        ),
        "risks",
    )
    assert item.status == "fail"
    assert item.summary == "1 high risk untested or weak"
    assert "AI claim doesn't match its test" in item.details[0]
    assert item.details[0].startswith("High · ")


def test_a_case_tagged_for_the_risk_counts_as_verified():
    tagged = case(case_id="TC-010", tags=["login", "risk:R1"])
    result = report(
        risk_analysis=RiskAnalysis(failure_modes=[HIGH]),
        test_cases=suite(tagged),
        criteria=CRITERIA,
    )
    assert status_of(result, "risks") == "pass"


def test_the_risk_pages_own_cases_are_used_when_the_run_has_none():
    tagged = case(case_id="TC-010", tags=["risk:R1"])
    result = report(risk_analysis=RiskAnalysis(failure_modes=[HIGH]), risk_cases=[tagged])
    assert status_of(result, "risks") == "pass"


# ---------- automation ----------


def test_a_traced_script_with_clean_syntax_passes():
    result = report(automation_script=script(), automation_selected_ids=["TC-001"])
    assert status_of(result, "automation") == "pass"


def test_a_selected_case_missing_from_the_code_warns():
    result = report(
        automation_script=script(), automation_selected_ids=["TC-001", "TC-002"]
    )
    item = item_of(result, "automation")
    assert item.status == "warn"
    assert "TC-002" in item.summary


def test_a_fixed_wait_warns():
    code = "test('TC-001: the account locks', async () => { await page.waitForTimeout(5000); });\n"
    result = report(
        automation_script=script(test_code=code), automation_selected_ids=["TC-001"]
    )
    assert status_of(result, "automation") == "warn"


def test_broken_syntax_fails():
    broken = script(
        framework="Playwright · Python",
        test_file_name="tests/test_login.py",
        test_code="def test_TC_001(:\n    pass\n",
        page_object_file_name=None,
        page_object_code=None,
        config_file_name=None,
        config_code=None,
    )
    result = report(automation_script=broken, automation_selected_ids=["TC-001"])
    assert status_of(result, "automation") == "fail"


# ---------- the test matrix ----------


def matrix_run(runs=14, valid=96, covered=96, manual=0, factors=("Browser", "Device")):
    return MatrixRun(
        runs=runs,
        valid_pairs=valid,
        covered_pairs=covered,
        manual_only=manual,
        factors=list(factors),
    )


def test_no_matrix_is_not_checked():
    item = item_of(report(), "matrix")
    assert item.status == "not_checked"
    assert item.summary == (
        "No test matrix yet — build one to know which browsers and devices to run."
    )


def test_an_empty_matrix_is_still_not_checked():
    assert status_of(report(matrix=MatrixRun()), "matrix") == "not_checked"


def test_full_coverage_with_nothing_manual_passes():
    item = item_of(report(matrix=matrix_run()), "matrix")
    assert item.status == "pass"
    assert item.summary == "14 runs cover every pair of values"
    assert "14 runs cover 96 of 96 pairs" in item.details


def test_manual_only_runs_warn_without_failing():
    item = item_of(report(matrix=matrix_run(manual=2)), "matrix")
    assert item.status == "warn"
    assert item.summary == "14 runs cover every pair; 2 of them must be tested by hand"
    assert "2 cannot be driven by Playwright" in item.details


def test_a_matrix_that_misses_pairs_warns():
    item = item_of(report(matrix=matrix_run(runs=10, covered=90)), "matrix")
    assert item.status == "warn"
    assert item.summary == "10 runs planned, 90 of 96 pairs covered"


def test_a_matrix_never_fails_a_release():
    """It tells you where to point the effort; it does not block the ship."""
    for run in (matrix_run(), matrix_run(manual=5), matrix_run(covered=1)):
        assert status_of(report(matrix=run), "matrix") != "fail"


def test_the_factors_are_listed_in_the_details():
    item = item_of(report(matrix=matrix_run(factors=("Browser", "Language"))), "matrix")
    assert "Factors: Browser, Language" in item.details


def test_the_matrix_is_not_a_core_check():
    assert "matrix" not in CORE_CHECKS


# ---------- nothing run at all ----------


def test_an_empty_run_leaves_every_check_not_checked():
    result = report()
    assert [item.status for item in result.items] == ["not_checked"] * len(CHECK_IDS)
    assert result.checked == 0
    assert result.counts["not_checked"] == len(CHECK_IDS)


def test_the_not_checked_line_names_the_tool_to_open():
    result = report()
    assert item_of(result, "risks").summary == "Not run yet — open Risk radar to include it."
    assert (
        item_of(result, "automation").summary
        == "Not run yet — open Automation to include it."
    )


# ---------- risk acceptance ----------


REASON = "Shipping behind a feature flag for internal users only this week."


def test_an_accepted_fail_becomes_accepted_and_keeps_the_reason():
    result = report(
        risk_analysis=RiskAnalysis(failure_modes=[HIGH]), acceptances={"risks": REASON}
    )
    item = item_of(result, "risks")
    assert item.status == "accepted"
    assert item.accepted_note == REASON
    assert result.counts["fail"] == 0
    assert result.counts["accepted"] == 1


def test_an_acceptance_on_a_warn_is_ignored():
    result = report(
        risk_analysis=RiskAnalysis(failure_modes=[MEDIUM]), acceptances={"risks": REASON}
    )
    item = item_of(result, "risks")
    assert item.status == "warn"
    assert item.accepted_note == ""


def test_a_reason_shorter_than_ten_characters_is_ignored():
    result = report(
        risk_analysis=RiskAnalysis(failure_modes=[HIGH]), acceptances={"risks": "   ok   "}
    )
    assert status_of(result, "risks") == "fail"


def test_a_reason_longer_than_three_hundred_characters_is_ignored():
    result = report(
        risk_analysis=RiskAnalysis(failure_modes=[HIGH]), acceptances={"risks": "x" * 301}
    )
    assert status_of(result, "risks") == "fail"


def test_an_accepted_check_never_counts_as_a_pass():
    result = report(
        risk_analysis=RiskAnalysis(failure_modes=[HIGH]), acceptances={"risks": REASON}
    )
    assert result.counts["pass"] == 0
    assert result.verdict == "ship_with_risks"


# ---------- the verdict ----------


def _everything_passes(**overrides) -> dict:
    cases = suite(*_deep("AC-1", 1), *_deep("AC-2", 2))
    inputs = {
        "story_analysis": analysis(10),
        "duel": duel(90),
        "test_cases": cases,
        "criteria": CRITERIA,
        "risk_analysis": RiskAnalysis(failure_modes=[]),
        "automation_script": script(),
        "automation_selected_ids": ["TC-001"],
        "matrix": matrix_run(),
    }
    inputs.update(overrides)
    return inputs


def test_everything_passing_ships():
    result = report(**_everything_passes())
    assert [item.status for item in result.items] == ["pass"] * len(CHECK_IDS)
    assert result.verdict == "ship"
    assert result.verdict_reason == "All checks passed."
    assert result.checked == len(CHECK_IDS)


def test_one_warn_ships_with_risks():
    result = report(**_everything_passes(duel=duel(60)))
    assert result.verdict == "ship_with_risks"
    assert result.verdict_reason == "Nothing blocks the release, but 1 thing still needs a look."


def test_two_warns_read_as_plural():
    result = report(**_everything_passes(duel=duel(60), risk_analysis=RiskAnalysis(failure_modes=[MEDIUM])))
    assert result.verdict_reason == "Nothing blocks the release, but 2 things still need a look."


def test_a_fail_beats_everything_else():
    result = report(**_everything_passes(risk_analysis=RiskAnalysis(failure_modes=[HIGH])))
    assert result.verdict == "dont_ship"
    assert result.verdict_reason == "1 check failed: Risks with a test."


def test_a_two_reader_problem_alone_never_blocks_a_release():
    result = report(**_everything_passes(duel=duel(20, "high", "high")))
    assert result.verdict == "ship_with_risks"
    assert VERDICT_LABELS[result.verdict] == "Release with known risks"


def test_every_failed_check_is_named():
    # Clarity cannot fail here: _everything_passes carries criteria, and
    # written criteria hold a low score at warn. The duel can no longer fail
    # at all, so a thin one-case suite and an untested high risk do the work.
    result = report(
        **_everything_passes(
            criteria=CRITERIA,
            test_cases=suite(case(case_id="TC-001", traceability="AC-1")),
            risk_analysis=RiskAnalysis(failure_modes=[HIGH]),
        )
    )
    assert result.verdict == "dont_ship"
    assert result.verdict_reason == (
        "3 checks failed: Criteria with a test, How well tested, Risks with a test."
    )


@pytest.mark.parametrize("core", CORE_CHECKS)
def test_a_core_check_not_run_blocks_ship_even_when_all_the_rest_pass(core):
    drop = {
        "coverage": {"test_cases": None, "criteria": []},
        "risks": {"risk_analysis": None},
    }[core]
    result = report(**_everything_passes(**drop))
    assert result.verdict == "ship_with_risks"
    assert "Not enough to go on" in result.verdict_reason
    assert result.verdict != "ship"


def test_a_non_core_check_not_run_does_not_block_ship():
    result = report(**_everything_passes(automation_script=None))
    assert result.verdict == "ship"


def test_the_items_come_back_in_check_ids_order():
    result = report(**_everything_passes())
    assert tuple(item.id for item in result.items) == CHECK_IDS


def test_every_check_has_a_title_and_a_link():
    for item in report().items:
        assert item.title
        assert item.link.startswith("/")


def test_details_are_capped_at_eight_lines():
    result = report(story_analysis=analysis(50, vague=20))
    assert len(item_of(result, "clarity").details) == 8


# ---------- the real run: one high risk, five loose medium ones ----------


def _weak_pair(risk_id: str, severity: int, likelihood: int, title: str):
    """A risk the AI claims is covered by a case about something else."""
    case_id = "TC-9" + risk_id[1:].zfill(2)
    claimed = case(case_id=case_id, title="Shopper updates a delivery address")
    claimed = claimed.model_copy(
        update={
            "expected_result": "The address book shows the new street",
            "steps": ["Open the address book", "Edit the street"],
        }
    )
    risk = failure_mode(risk_id, severity, likelihood, covered_by=[case_id])
    return risk.model_copy(update={"title": title}), claimed


def test_the_summary_counts_medium_risks_that_are_weak_as_well_as_untested():
    uncaught = failure_mode("R5", 5, 4).model_copy(
        update={"title": "Uncaught exception in the navigation reducer"}
    )
    r8, r8_case = _weak_pair("R8", 3, 2, "Unauthorized module access")
    mediums = [
        failure_mode(f"R{n}", 3, 2).model_copy(update={"title": f"Medium risk {n}"})
        for n in (2, 3, 4, 6)
    ]
    item = item_of(
        report(
            risk_analysis=RiskAnalysis(failure_modes=[uncaught, r8, *mediums]),
            test_cases=suite(r8_case),
            criteria=CRITERIA,
        ),
        "risks",
    )
    assert item.status == "fail"
    assert item.summary == "1 high risk has no test · 5 medium risks untested or weak"


def test_every_risk_detail_carries_its_level_worst_first():
    uncaught = failure_mode("R5", 5, 4).model_copy(
        update={"title": "Uncaught exception in the navigation reducer"}
    )
    high_weak, high_case = _weak_pair("R1", 5, 4, "Focus trap in the overlay")
    medium_none = failure_mode("R2", 3, 2).model_copy(
        update={"title": "Slow first paint"}
    )
    medium_weak, medium_case = _weak_pair("R8", 3, 2, "Unauthorized module access")
    item = item_of(
        report(
            risk_analysis=RiskAnalysis(
                failure_modes=[uncaught, high_weak, medium_none, medium_weak]
            ),
            test_cases=suite(high_case, medium_case),
            criteria=CRITERIA,
        ),
        "risks",
    )
    assert item.details == [
        "High · R5 Uncaught exception in the navigation reducer — no test",
        "High · R1 Focus trap in the overlay — AI claim doesn't match its test",
        "Medium · R2 Slow first paint — no test",
        "Medium · R8 Unauthorized module access — AI claim doesn't match its test",
    ]


def test_a_weak_medium_risk_is_listed_even_though_the_rules_are_unchanged():
    """A weak medium on its own still passes; it is just no longer invisible."""
    medium_weak, medium_case = _weak_pair("R8", 3, 2, "Unauthorized module access")
    item = item_of(
        report(
            risk_analysis=RiskAnalysis(failure_modes=[medium_weak]),
            test_cases=suite(medium_case),
            criteria=CRITERIA,
        ),
        "risks",
    )
    assert item.status == "pass"
    assert item.details == [
        "Medium · R8 Unauthorized module access — AI claim doesn't match its test"
    ]


# ---------- the real run: a vague story with concrete criteria ----------

# Clarity 42 sent a story to "Don't ship" while four criteria already named
# 200 ms, 768 px and focus rings. Written criteria outrank the score.

REAL_RUN_CRITERIA = [
    "The active link is highlighted within 200 ms of the route changing",
    "Below 768 px the bar collapses into a toggle",
    "Every link shows a visible focus ring in tab order",
    "The current page is announced to screen readers",
]


def test_criteria_hold_a_failing_clarity_score_at_warn():
    item = item_of(
        report(story_analysis=analysis(58), criteria=REAL_RUN_CRITERIA), "clarity"
    )
    assert item.status == "warn"
    assert item.summary == (
        "How clear: 42 of 100 — unclear, but 4 acceptance criteria pin it down"
    )


def test_without_criteria_a_failing_clarity_score_still_fails():
    item = item_of(report(story_analysis=analysis(58)), "clarity")
    assert item.status == "fail"
    assert item.summary == "How clear: 42 of 100"


def test_one_criterion_reads_as_one():
    item = item_of(
        report(story_analysis=analysis(58), criteria=REAL_RUN_CRITERIA[:1]), "clarity"
    )
    assert item.summary == (
        "How clear: 42 of 100 — unclear, but 1 acceptance criterion pins it down"
    )


def test_criteria_do_not_lift_a_warn_to_a_pass():
    """They cap the damage; they never make a vague story a clear one."""
    item = item_of(
        report(story_analysis=analysis(40), criteria=REAL_RUN_CRITERIA), "clarity"
    )
    assert item.status == "warn"
    assert item.summary == "How clear: 60 of 100"


def test_criteria_leave_a_passing_score_alone():
    item = item_of(
        report(story_analysis=analysis(10), criteria=REAL_RUN_CRITERIA), "clarity"
    )
    assert item.status == "pass"
    assert item.summary == "How clear: 90 of 100"


def test_the_missing_acceptance_criteria_line_goes_when_there_are_criteria():
    missing = ["Acceptance criteria (Given/When/Then format)", "A measurable budget"]
    story = analysis(58).model_copy(update={"missing_elements": missing})
    with_criteria = item_of(
        report(story_analysis=story, criteria=REAL_RUN_CRITERIA), "clarity"
    )
    assert "Missing: A measurable budget" in with_criteria.details
    assert not any("cceptance criteria" in line for line in with_criteria.details)

    without = item_of(report(story_analysis=story), "clarity")
    assert "Missing: Acceptance criteria (Given/When/Then format)" in without.details


@pytest.mark.parametrize(
    "clarity,expected", [(70, "pass"), (69, "warn"), (50, "warn"), (49, "fail")]
)
def test_the_clarity_boundaries_still_hold_without_criteria(clarity, expected):
    assert status_of(report(story_analysis=analysis(100 - clarity)), "clarity") == expected


def test_the_two_desks_count_untested_high_risks_the_same_way():
    from qagenius.risk_radar import loose_risks, score_risks

    high_weak, high_case = _weak_pair("R1", 5, 4, "Focus trap in the overlay")
    none = failure_mode("R5", 5, 4).model_copy(update={"title": "Uncaught exception"})
    analysis = RiskAnalysis(failure_modes=[none, high_weak])
    cases = suite(high_case)

    radar = score_risks(analysis, list(cases.test_cases))
    item = item_of(
        report(risk_analysis=analysis, test_cases=cases, criteria=CRITERIA), "risks"
    )
    assert radar.counts["untested_high"] == len(loose_risks(radar.risks, "high")) == 2
    assert item.summary.startswith("2 high risks untested or weak")
    assert item.status == "fail"
