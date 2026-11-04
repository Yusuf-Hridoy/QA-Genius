"""The five reference runs, frozen.

Every one of these is a story the rest of the suite already argues about.
The golden file holds what the tools said about it last time; this fails on
any difference, so a change in what an agent is told about a real story has
to be made on purpose. `python scripts/update_golden.py` accepts one.

The named assertions underneath are the ones worth stating out loud: they
are the findings these fixtures exist for, and a golden file that still
matched while one of them disappeared would be a green test over a broken
tool.
"""

import json
from pathlib import Path

import pytest

from qagenius.mcp_server.transport import call_tool
from tests.golden_inputs import GOLDEN

GOLDEN_DIR = Path(__file__).resolve().parent / "mcp_golden"


def saved(name: str) -> dict:
    return json.loads((GOLDEN_DIR / f"{name}.json").read_text(encoding="utf-8"))


def answer(name: str) -> dict:
    """What the tools say about one fixture right now."""
    case = GOLDEN[name]
    return call_tool(case["tool"], case["input"]).structured_content


def says(name: str) -> list[str]:
    """Every sentence in one answer, so a note can be looked for anywhere."""
    found = answer(name)
    lines = [found["summary"], *found["notes"], *found["ask_the_po"]]
    for problem in found["problems"]:
        lines.extend([problem["says"], problem["fix"]])
    return lines


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_the_saved_answer_still_matches(name):
    path = GOLDEN_DIR / f"{name}.json"
    assert path.exists(), (
        f"tests/mcp_golden/{name}.json is missing. "
        "Run: python scripts/update_golden.py"
    )
    body = saved(name)
    assert body["input"] == GOLDEN[name]["input"], (
        f"The input for {name} changed. Run: python scripts/update_golden.py"
    )
    assert answer(name) == body["output"], (
        f"What {name} answers changed. If you meant it, run: "
        "python scripts/update_golden.py — then read the diff."
    )


def test_no_saved_answer_is_left_behind():
    assert {path.stem for path in GOLDEN_DIR.glob("*.json")} == set(GOLDEN)


# ── the findings these fixtures exist for ────────────────────────────────


def test_coupon_says_nobody_decided_exactly_fifty_dollars():
    assert any("Nobody says what happens at exactly $50" in one for one in says("coupon"))


def test_coupon_says_the_context_and_ac1_disagree():
    found = [
        one
        for one in says("coupon")
        if "context says" in one and '"at least $50"' in one and "AC-1" in one
    ]
    assert found, "the context-vs-AC-1 note is gone"


def test_the_coupon_questions_reach_the_product_owner():
    # A limit nobody decided is not something the agent should guess at.
    asked = answer("coupon")["ask_the_po"]
    assert any("exactly $50" in one for one in asked)


def test_the_nav_bar_suite_gets_no_extra_tests():
    # The whole point of a complete suite: a tool that always finds
    # something to add is a tool nobody believes the second time.
    found = answer("navbar")
    assert found["add_tests"] == []
    assert found["problems"] == []
    assert found["summary"].startswith("nothing to fix")


def test_the_big_story_is_called_an_epic_and_two_factor_is_named():
    found = answer("big_story")
    epics = [one for one in found["problems"] if one["kind"] == "epic"]
    assert len(epics) == 1
    assert "Two-factor" in epics[0]["says"]
    assert epics[0]["level"] == "high"


def test_the_big_story_names_every_feature_it_counted():
    said = answer("big_story")["problems"][0]["says"]
    # The number in the sentence and the names after it are one list.
    count = int(said.split("really ")[1].split(" ")[0])
    named = said.split(": ", 1)[1].split(", ")
    assert len(named) == count


def test_the_photo_run_says_exactly_two_megabytes_is_undecided():
    found = [one for one in says("photo") if "exactly 2 MB" in one]
    assert found, "the 2 MB boundary note is gone"


def test_the_photo_note_never_uses_scientific_notation():
    assert not any("e+" in one.lower() for one in says("photo"))


def test_the_lockout_run_does_not_invent_a_disagreement():
    # Five tries and thirty minutes are two things in two units. A run once
    # read them as one number arguing with itself.
    for line in says("lockout"):
        said = line.lower()
        if "minute" in said and ("tries" in said or "attempt" in said):
            assert "disagree" not in said and "but" not in said, line


def test_the_lockout_run_reports_no_limit_problem_at_all():
    assert [one for one in answer("lockout")["problems"] if one["kind"] == "limit"] == []


# ── the three later tools, on the same stories ───────────────────────────


def test_a_risk_a_test_really_reaches_is_not_called_untested():
    # R2 names TC-02, and TC-02's words are about the thing R2 says goes
    # wrong. A tool that cried wolf here would be ignored on R1 too.
    found = answer("coupon_risks")
    by_id = {one["id"]: one for one in found["risks"]}
    assert by_id["R2"]["coverage"] == "tested"
    assert "R2" not in found["untested_high"]


def test_the_risk_nothing_reaches_is_the_one_reported_high():
    found = answer("coupon_risks")
    assert found["untested_high"] == ["R1"]
    high = [one for one in found["problems"] if one["level"] == "high"]
    assert len(high) == 1
    assert "R1" in high[0]["says"]
    assert found["ask_the_po"], "a high risk with no test is the PO's call"


def test_every_risk_is_scored_out_of_a_hundred_and_twenty_five():
    for risk in answer("coupon_risks")["risks"]:
        assert 1 <= risk["score"] <= 125
        assert risk["max_score"] == 125
        assert risk["coverage"] in ("tested", "probably tested", "no test")


def test_the_matrix_covers_every_pair_it_is_allowed_to():
    found = answer("navbar_matrix")
    assert found["pairs_covered"] == found["pairs_possible"]
    assert found["pairs_covered"] > 0
    assert found["problems"] == []


def test_the_matrix_runs_are_fewer_than_the_combinations():
    # The whole point: 24 combinations do not need 24 runs.
    found = answer("navbar_matrix")
    assert len(found["runs"]) < found["combinations"]


def test_every_new_pair_count_adds_up_to_what_is_covered():
    found = answer("navbar_matrix")
    assert sum(one["new_pairs"] for one in found["runs"]) == found["pairs_covered"]


def test_the_pairs_the_rules_forbid_are_named_not_hidden():
    found = answer("navbar_matrix")
    assert "Browser=Firefox + Device=Phone" in found["impossible_pairs"]


def test_a_run_playwright_cannot_drive_says_why():
    found = answer("navbar_matrix")
    manual = [one for one in found["runs"] if one["manual_only"]]
    assert manual
    assert all(one["manual_reason"] for one in manual)


def test_the_leftover_only_is_the_worst_thing_in_the_code():
    found = answer("lockout_code")
    only = [one for one in found["findings"] if ".only" in one["says"]]
    assert only and only[0]["level"] == "error"


def test_a_test_that_checks_nothing_is_reported():
    said = [one["says"] for one in answer("lockout_code")["findings"]]
    assert any("never asserts anything" in one for one in said)


def test_a_password_in_the_source_is_reported():
    said = [one["says"] for one in answer("lockout_code")["findings"]]
    assert any("hard-coded secret" in one for one in said)


def test_a_fixed_pause_is_reported():
    said = [one["says"] for one in answer("lockout_code")["findings"]]
    assert any("Fixed pause" in one for one in said)


def test_a_test_case_the_code_never_names_is_reported():
    found = answer("lockout_code")
    assert found["untraced"] == ["TC-03"]
    assert any(one["kind"] == "missing" for one in found["problems"])


def test_the_quick_syntax_check_says_it_is_not_a_compile():
    # A reader who thinks "passed" means "compiles" has been misled.
    syntax = answer("lockout_code")["syntax"]
    assert all("not a full compile" in one for one in syntax.values())
    assert any("Nothing in these files was run" in one for one in answer("lockout_code")["notes"])


# ── every answer is shaped the way the contract says ─────────────────────


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_every_answer_carries_the_schema_version_and_its_own_name(name):
    found = answer(name)
    assert found["schema_version"] == "1.0"
    assert found["tool"] == GOLDEN[name]["tool"]
    assert found["summary"]


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_every_problem_has_an_id_and_something_to_do(name):
    for problem in answer(name)["problems"]:
        assert problem["id"]
        assert problem["says"].strip()
        assert problem["fix"].strip()
        assert problem["level"] in ("high", "medium", "low")


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_problem_ids_are_unique_within_one_answer(name):
    ids = [problem["id"] for problem in answer(name)["problems"]]
    assert len(ids) == len(set(ids)), f"{name} reports the same id twice"


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_problems_come_back_worst_first(name):
    rank = {"high": 0, "medium": 1, "low": 2}
    levels = [rank[one["level"]] for one in answer(name)["problems"]]
    assert levels == sorted(levels)


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_added_tests_can_be_sent_straight_back_in(name):
    # add_tests is TestIn-shaped on purpose: an agent should not have to
    # translate anything to use them.
    from qagenius.mcp_server.schemas import TestIn

    for test in answer(name)["add_tests"]:
        rebuilt = TestIn.model_validate(test)
        assert rebuilt.steps
        assert rebuilt.id


def test_the_ids_in_one_answer_survive_a_second_call():
    # The same problem keeps the same id, which is what lets an agent say
    # "I fixed L-b225" and be understood.
    first = {one["id"] for one in answer("coupon")["problems"]}
    second = {one["id"] for one in answer("coupon")["problems"]}
    assert first == second
