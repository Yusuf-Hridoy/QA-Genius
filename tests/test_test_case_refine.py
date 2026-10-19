"""Refine and strengthen tests: prompt text and the additive merge."""

from qagenius.test_case_depth import compute_depth
from qagenius.models import FailureMode
from qagenius.risk_radar import ScoredRisk
from qagenius.test_case_refine import (
    add_risk_tags,
    current_cases_block,
    merge_strengthened,
    next_case_id,
    refine_user_text,
    risk_instruction,
    strengthen_instruction,
)
from qagenius.test_cases import number_criteria
from tests.factories import case, real_run, suite

REAL_RUN_INSTRUCTION = """Add new test cases only. Do not change or remove any existing test case.
For AC-1: add a negative case and a boundary case.
For AC-2: add a boundary case and at least one more case.
For AC-4: add at least one more case.
For AC-5: add at least one more case.
For AC-6: add at least one more case.
Use exact values (counts, times, lengths) at and around every limit in the story."""


def test_current_cases_block_lines() -> None:
    criteria = number_criteria(["one", "two"])
    current = suite(
        case("TC-001", "Functional", "AC-1", title="Account locks after five attempts"),
        case("TC-002", "Negative", "AC-9", title="Unknown email is refused"),
    )
    block = current_cases_block(current, criteria)
    lines = block.split("\n")
    assert lines[0] == ""
    assert lines[1] == ""
    assert lines[2].startswith("CURRENT TEST CASES (keep the id of every case you keep;")
    assert lines[3] == "TC-001 | Functional | High | AC-1 | Account locks after five attempts"
    # AC-9 is not a real criterion, so the case shows no coverage.
    assert lines[4] == "TC-002 | Negative | High | - | Unknown email is refused"


def test_strengthen_instruction_for_the_real_run() -> None:
    result, criteria = real_run()
    assert strengthen_instruction(compute_depth(result, criteria)) == REAL_RUN_INSTRUCTION


def test_strengthen_instruction_covers_an_uncovered_criterion() -> None:
    """And asks only for the kinds the criterion can really have."""
    criteria = number_criteria(
        [
            "The name is shown",
            "The password field takes at most 64 characters",
            "Breadcrumbs show the path to the current page",
        ]
    )
    depth = compute_depth(suite(case("TC-001", "Functional", "AC-1")), criteria)
    text = strengthen_instruction(depth)
    assert (
        "For AC-2: cover this criterion with at least one positive, one negative "
        "and one boundary case." in text
    )
    assert "For AC-3: cover this criterion with at least one positive case." in text


def test_strengthen_instruction_skips_solid_criteria() -> None:
    criteria = number_criteria(["one"])
    depth = compute_depth(
        suite(
            case("TC-001", "Functional", "AC-1"),
            case("TC-002", "Negative", "AC-1"),
            case("TC-003", "Boundary", "AC-1"),
        ),
        criteria,
    )
    text = strengthen_instruction(depth)
    assert "For AC-1" not in text
    assert text.startswith("Add new test cases only.")


def test_refine_user_text_shape() -> None:
    result, criteria = real_run()
    text = refine_user_text("BASE PROMPT", result, criteria, "Use exact times.")
    assert text.startswith("BASE PROMPT")
    assert "CURRENT TEST CASES" in text
    assert "REFINE INSTRUCTION:\nUse exact times." in text
    assert text.endswith(
        "Return the COMPLETE updated list of test cases, not only the changes."
    )


def test_merge_keeps_edited_case_and_takes_the_new_one() -> None:
    current = suite(case("TC-001", title="Account locks after five attempts"))
    proposed = suite(
        case("TC-001", title="Totally rewritten by the AI", expected_result="changed"),
        case("TC-009", "Boundary", title="Four attempts then a correct password"),
    )
    merged = merge_strengthened(current, proposed)
    assert [c.id for c in merged.test_cases] == ["TC-001", "TC-009"]
    assert merged.test_cases[0].title == "Account locks after five attempts"
    assert merged.test_cases[0].expected_result == "The account locks for 30 minutes"


def test_merge_restores_a_dropped_case() -> None:
    current = suite(
        case("TC-001", title="Account locks after five attempts"),
        case("TC-002", title="Locked account refuses the correct password"),
    )
    proposed = suite(case("TC-001", title="Account locks after five attempts"))
    merged = merge_strengthened(current, proposed)
    assert [c.id for c in merged.test_cases] == ["TC-001", "TC-002"]


def test_merge_skips_a_near_duplicate_title() -> None:
    current = suite(case("TC-001", title="Account locks after five wrong attempts"))
    proposed = suite(
        case("TC-001", title="Account locks after five wrong attempts"),
        case("TC-009", title="Account locks after five wrong attempts today"),
    )
    merged = merge_strengthened(current, proposed)
    assert [c.id for c in merged.test_cases] == ["TC-001"]


def test_merge_renumbers_a_colliding_new_id() -> None:
    current = suite(case("TC-001", title="Account locks after five attempts"))
    proposed = suite(
        case("TC-009", "Negative", title="Unknown email is refused politely"),
        case("TC-009", "Boundary", title="Fifteen minutes exactly still refuses"),
    )
    merged = merge_strengthened(current, proposed)
    assert [c.id for c in merged.test_cases] == ["TC-001", "TC-009", "TC-010"]


def test_merge_never_mutates_its_inputs() -> None:
    current = suite(case("TC-001", title="Account locks after five attempts"))
    proposed = suite(case("TC-009", title="A completely different shipping case"))
    merge_strengthened(current, proposed)
    assert [c.id for c in current.test_cases] == ["TC-001"]
    assert [c.id for c in proposed.test_cases] == ["TC-009"]


def test_next_case_id() -> None:
    assert next_case_id(["TC-001", "TC-12", "TC7"]) == "TC-013"
    assert next_case_id([]) == "TC-001"
    assert next_case_id(["no numbers here"]) == "TC-001"


RISK_INSTRUCTION = """Add new test cases only. Do not change or remove any existing test case.
Write at least one test case for each of these risks. Put the risk id in the test case's tags as "risk:R1" (exactly this format).
R1 (security): Lockout counter is not shared across servers — Test idea: Fail five times across two servers
R2 (performance): Lockout email arrives late — Test idea: Lock 200 accounts in one minute
Use exact values (counts, times, sizes) and include at least one negative or boundary case per risk where it makes sense."""


def _scored(risk_id: str, category: str, title: str, test_idea: str) -> ScoredRisk:
    return ScoredRisk(
        risk=FailureMode(
            id=risk_id,
            title=title,
            category=category,
            effect="Shoppers suffer",
            cause="Something slipped",
            severity=5,
            likelihood=4,
            detectability=4,
            test_idea=test_idea,
        ),
        rpn=80,
        level="high",
        coverage="none",
        covered_tests=[],
    )


ASKED = [
    _scored(
        "R1",
        "security",
        "Lockout counter is not shared across servers",
        "Fail five times across two servers",
    ),
    _scored(
        "R2",
        "performance",
        "Lockout email arrives late",
        "Lock 200 accounts in one minute",
    ),
]


def test_risk_instruction_names_every_risk_and_the_tag_format() -> None:
    assert risk_instruction(ASKED) == RISK_INSTRUCTION


def test_risk_instruction_leaves_out_a_missing_test_idea() -> None:
    asked = [_scored("R1", "data", "Counter is never cleared", "")]
    assert "R1 (data): Counter is never cleared\n" in risk_instruction(asked) + "\n"


def test_a_new_case_that_names_its_risk_gets_the_tag() -> None:
    current = suite(case(case_id="TC-001"))
    proposed = suite(
        case(case_id="TC-001"),
        case(case_id="TC-002", traceability="AC-1, R2", tags=["login"]),
    )
    merged = add_risk_tags(current, proposed, ["R1", "R2"])
    assert merged.test_cases[1].tags == ["login", "risk:R2"]


def test_the_tag_is_not_added_twice() -> None:
    current = suite(case(case_id="TC-001"))
    proposed = suite(
        case(case_id="TC-001"),
        case(case_id="TC-002", title="Covers R1", tags=["risk:R1"]),
    )
    merged = add_risk_tags(current, proposed, ["R1"])
    assert merged.test_cases[1].tags == ["risk:R1"]


def test_an_existing_case_is_left_alone() -> None:
    current = suite(case(case_id="TC-001", title="Covers R1", tags=["login"]))
    proposed = suite(case(case_id="TC-001", title="Covers R1", tags=["login"]))
    merged = add_risk_tags(current, proposed, ["R1"])
    assert merged.test_cases[0].tags == ["login"]


def test_a_risk_id_nobody_asked_for_is_not_tagged() -> None:
    current = suite(case(case_id="TC-001"))
    proposed = suite(case(case_id="TC-001"), case(case_id="TC-002", title="About R9"))
    merged = add_risk_tags(current, proposed, ["R1"])
    assert merged.test_cases[1].tags == ["login"]
