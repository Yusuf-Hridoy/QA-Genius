"""Refine and strengthen tests: prompt text and the additive merge."""

from qagenius.test_case_depth import compute_depth
from qagenius.test_case_refine import (
    current_cases_block,
    merge_strengthened,
    next_case_id,
    refine_user_text,
    strengthen_instruction,
)
from qagenius.test_cases import number_criteria
from tests.factories import case, real_run, suite

REAL_RUN_INSTRUCTION = """Add new test cases only. Do not change or remove any existing test case.
For AC-1: add a negative case and a boundary case.
For AC-2: add a negative case, a boundary case and at least one more case.
For AC-3: add a boundary case.
For AC-4: add a negative case and at least one more case.
For AC-5: add a negative case, a boundary case and at least one more case.
For AC-6: add a negative case, a boundary case and at least one more case.
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
    criteria = number_criteria(["one", "two"])
    depth = compute_depth(suite(case("TC-001", "Functional", "AC-1")), criteria)
    text = strengthen_instruction(depth)
    assert (
        "For AC-2: cover this criterion with at least one positive, one negative "
        "and one boundary case." in text
    )


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
