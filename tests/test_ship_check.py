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
    PerformanceLine,
    PerformanceRun,
    CORE_CHECKS,
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
    assert item.summary == "Clarity 82, 2 vague phrases"
    assert len(item.details) == 2


# ---------- ambiguity duel ----------


def duel(agreement: int, *severities: str) -> DuelSummary:
    return DuelSummary(
        agreement_pct=agreement,
        forks=[{"topic": f"Topic {n}", "severity": s} for n, s in enumerate(severities)],
    )


@pytest.mark.parametrize(
    "agreement,expected", [(100, "pass"), (70, "pass"), (69, "warn"), (40, "warn"), (39, "fail")]
)
def test_duel_agreement_boundaries(agreement, expected):
    assert status_of(report(duel=duel(agreement)), "duel") == expected


def test_only_low_forks_with_high_agreement_still_passes():
    assert status_of(report(duel=duel(80, "low", "low")), "duel") == "pass"


def test_a_medium_fork_warns_however_high_the_agreement():
    assert status_of(report(duel=duel(100, "medium")), "duel") == "warn"


def test_a_high_fork_fails_however_high_the_agreement():
    assert status_of(report(duel=duel(100, "high")), "duel") == "fail"


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
    assert item.summary.startswith("1 of 2 criteria thin")


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


def test_a_high_risk_the_ai_claimed_but_cannot_match_warns():
    """covered_by names a case about something else: "weak", not covered."""
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
    assert item.status == "warn"
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


# ---------- the performance budget ----------


def perf_line(line_id, label, limit, unit, source, measured, status, measured_from="lab"):
    return PerformanceLine(
        id=line_id,
        label=label,
        limit=limit,
        unit=unit,
        source=source,
        measured=measured,
        measured_from=measured_from,
        status=status,
    )


LCP_OVER = perf_line(
    "lcp", "Largest contentful paint (LCP)", 2500, "ms",
    "Core Web Vitals 'good' threshold", 3820, "over", "real users (28 days)",
)
LCP_WITHIN = perf_line(
    "lcp", "Largest contentful paint (LCP)", 2500, "ms",
    "Core Web Vitals 'good' threshold", 2100, "within",
)
INP_WITHIN = perf_line("inp", "Interaction to next paint (INP)", 200, "ms", "AC-2", 184, "within")
TTFB_WITHIN = perf_line("ttfb", "Server response time (TTFB)", 800, "ms", "default", 410, "within")
WEIGHT_UNMEASURED = perf_line("weight", "Page weight", 1600, "KB", "default", None, "not_measured")
LAYOUT = perf_line("custom-1", "Layout at 768 px", 768, "px", "AC-4", None, "not_measurable", "")


def performance_run(*lines, gaps=()):
    return PerformanceRun(
        results=list(lines),
        gaps=list(gaps),
        url="https://aurora-storefront.example/dashboard",
        strategy="mobile",
        fetched_at="2026-01-14T09:21:44+00:00",
    )


def test_no_measurement_leaves_performance_not_checked():
    item = item_of(report(), "performance")
    assert item.status == "not_checked"
    assert item.summary == "Not run yet — open Performance to include it."


def test_an_empty_measurement_is_still_not_checked():
    assert status_of(report(performance=performance_run()), "performance") == "not_checked"


def test_every_line_within_budget_passes():
    result = report(performance=performance_run(LCP_WITHIN, INP_WITHIN, TTFB_WITHIN))
    item = item_of(result, "performance")
    assert item.status == "pass"
    assert item.summary == "Every line within budget (3 lines)"


def test_a_line_over_budget_fails_and_names_it():
    item = item_of(
        report(performance=performance_run(LCP_OVER, INP_WITHIN, TTFB_WITHIN)),
        "performance",
    )
    assert item.status == "fail"
    assert item.summary == "LCP 3.82 s over the 2.5 s budget · 2 within"


def test_two_lines_over_budget_are_counted_not_listed():
    other = perf_line("ttfb", "Server response time (TTFB)", 800, "ms", "default", 1200, "over")
    item = item_of(report(performance=performance_run(LCP_OVER, other)), "performance")
    assert item.status == "fail"
    assert item.summary == "2 budget lines over"


def test_a_gap_warns_without_failing():
    gap = 'Risk R1 "Race condition on rapid double-clicking" is a performance risk with no target.'
    item = item_of(
        report(performance=performance_run(LCP_WITHIN, INP_WITHIN, gaps=[gap])),
        "performance",
    )
    assert item.status == "warn"
    assert item.summary == "1 gap · 2 within"


def test_a_line_that_could_not_be_measured_warns():
    item = item_of(
        report(performance=performance_run(LCP_WITHIN, WEIGHT_UNMEASURED)), "performance"
    )
    assert item.status == "warn"
    assert item.summary == "1 not measured · 1 within"


def test_a_layout_line_is_never_judged():
    """768 px is not something PageSpeed measures, so it cannot fail the check."""
    result = report(performance=performance_run(LCP_WITHIN, INP_WITHIN, LAYOUT))
    item = item_of(result, "performance")
    assert item.status == "pass"
    assert all("768" not in line for line in item.details)


def test_the_details_name_the_number_the_limit_and_the_source():
    item = item_of(
        report(performance=performance_run(LCP_OVER, INP_WITHIN)), "performance"
    )
    assert item.details == [
        "Over · Largest contentful paint (LCP) 3.82 s / 2.5 s "
        "(Core Web Vitals 'good' threshold)",
        "Within · Interaction to next paint (INP) 184 ms / 200 ms (AC-2)",
    ]


def test_performance_is_not_a_core_check():
    """A release can still ship without a measurement; coverage and risks cannot."""
    assert "performance" not in CORE_CHECKS


def test_the_latest_test_run_check_is_gone():
    assert "test_run" not in CHECK_IDS


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
        "performance": performance_run(LCP_WITHIN, INP_WITHIN, TTFB_WITHIN),
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
    assert result.verdict_reason == "No blockers, but 1 item needs attention."


def test_two_warns_read_as_plural():
    result = report(**_everything_passes(duel=duel(60), risk_analysis=RiskAnalysis(failure_modes=[MEDIUM])))
    assert result.verdict_reason == "No blockers, but 2 items need attention."


def test_a_fail_beats_everything_else():
    result = report(**_everything_passes(risk_analysis=RiskAnalysis(failure_modes=[HIGH])))
    assert result.verdict == "dont_ship"
    assert result.verdict_reason == "1 check failed: Risk coverage."


def test_two_fails_are_both_named():
    # Clarity cannot fail here: _everything_passes carries criteria, and
    # written criteria hold a low score at warn. The duel can.
    result = report(
        **_everything_passes(
            duel=duel(30, "high"),
            risk_analysis=RiskAnalysis(failure_modes=[HIGH]),
        )
    )
    assert result.verdict_reason == "2 checks failed: Ambiguity duel, Risk coverage."


@pytest.mark.parametrize("core", CORE_CHECKS)
def test_a_core_check_not_run_blocks_ship_even_when_all_the_rest_pass(core):
    drop = {
        "coverage": {"test_cases": None, "criteria": []},
        "risks": {"risk_analysis": None},
    }[core]
    result = report(**_everything_passes(**drop))
    assert result.verdict == "ship_with_risks"
    assert "Not enough evidence" in result.verdict_reason
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
    assert item.summary == "Clarity 42 — vague story, but 4 acceptance criteria pin it down"


def test_without_criteria_a_failing_clarity_score_still_fails():
    item = item_of(report(story_analysis=analysis(58)), "clarity")
    assert item.status == "fail"
    assert item.summary == "Clarity 42"


def test_one_criterion_reads_as_one():
    item = item_of(
        report(story_analysis=analysis(58), criteria=REAL_RUN_CRITERIA[:1]), "clarity"
    )
    assert item.summary == "Clarity 42 — vague story, but 1 acceptance criterion pins it down"


def test_criteria_do_not_lift_a_warn_to_a_pass():
    """They cap the damage; they never make a vague story a clear one."""
    item = item_of(
        report(story_analysis=analysis(40), criteria=REAL_RUN_CRITERIA), "clarity"
    )
    assert item.status == "warn"
    assert item.summary == "Clarity 60"


def test_criteria_leave_a_passing_score_alone():
    item = item_of(
        report(story_analysis=analysis(10), criteria=REAL_RUN_CRITERIA), "clarity"
    )
    assert item.status == "pass"
    assert item.summary == "Clarity 90"


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
