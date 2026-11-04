"""What the three tools say, where the golden files do not reach.

The goldens freeze five whole answers. These are the rules behind them: the
things that have to stay true for a story nobody has written yet.
"""

import pytest

from qagenius.mcp_server import adapters, tools
from qagenius.mcp_server.schemas import ShipIn, StoryIn, TestsIn
from qagenius.test_case_depth import NO_KIND, NOT_COVERED, ONLY_ONE

STORY = "As a shopper I want to pay with a saved card so that checkout is one step."


def _tests_in(**over) -> TestsIn:
    body = {
        "story": STORY,
        "context": "",
        "criteria": [{"text": "A saved card pays without re-entering the number"}],
        "test_cases": [
            {
                "id": "TC-1",
                "title": "A saved card pays",
                "steps": ["Open the cart", "Choose the saved card", "Press Pay"],
                "expected": "The order is placed and the card is charged once",
                "covers": ["AC-1"],
            }
        ],
    }
    body.update(over)
    return TestsIn.model_validate(body)


def _ship_in(**over) -> ShipIn:
    body = _tests_in().model_dump()
    body.update(over)
    return ShipIn.model_validate(body)


# ──────────────────────────────────────────────────────────────────────────────
# check_story
# ──────────────────────────────────────────────────────────────────────────────


def test_a_clear_story_is_told_it_is_clear():
    found = tools.check_story(
        StoryIn(
            story=(
                "As a shopper I want to pay with a saved card so that checkout "
                "is one step. An expired card is refused with a message naming "
                "the card."
            )
        )
    )
    assert [one for one in found.problems if one.kind == "clarity"] == []
    assert "No untestable words found." in found.notes


def test_the_story_type_does_not_change_the_answer():
    first = tools.check_story(StoryIn(story=STORY, story_type="user story"))
    second = tools.check_story(StoryIn(story=STORY, story_type="bug"))
    assert first.model_dump() == second.model_dump()


def test_every_unclear_word_comes_with_something_to_say_instead():
    found = tools.check_story(
        StoryIn(story="The cart updates quickly and handles too many items safely.")
    )
    words = [one for one in found.problems if one.fix.startswith("Say ")]
    assert {"quickly", "too many"} <= {
        one.says.split("“")[1].split("”")[0] for one in words
    }
    for problem in words:
        assert problem.fix != "Say  instead."
        assert problem.fix.endswith(" instead.")


def test_check_story_never_proposes_tests():
    # There are no criteria yet. A tool that wrote tests here would be
    # writing them against words it has just called untestable.
    assert tools.check_story(StoryIn(story=STORY)).add_tests == []


def test_the_summary_says_how_many_there_are_to_fix():
    found = tools.check_story(StoryIn(story="The page loads quickly."))
    assert "to fix" in found.summary.split(" · ")[0]
    clean = tools.check_story(
        StoryIn(
            story=(
                "As a shopper I want to pay with a saved card so that checkout "
                "is one step. An expired card is refused with a message."
            )
        )
    )
    assert clean.summary.startswith("nothing to fix")


# ──────────────────────────────────────────────────────────────────────────────
# review_tests
# ──────────────────────────────────────────────────────────────────────────────


def test_a_criterion_with_no_test_is_a_high_problem():
    found = tools.review_tests(
        _tests_in(
            criteria=[
                {"text": "A saved card pays without re-entering the number"},
                {"text": "A card that has expired is refused"},
            ]
        )
    )
    missing = [one for one in found.problems if one.kind == "missing"]
    assert missing
    assert missing[0].level == "high"
    assert "AC-2" in missing[0].criteria


def test_the_depth_reported_is_the_suite_that_was_sent():
    # The tests in add_tests are a proposal the agent has not taken. Counting
    # them would report the gaps as already filled.
    found = tools.review_tests(_tests_in())
    assert found.add_tests, "this fixture is only useful while there is a gap"
    assert "100% of criteria have at least one test." in found.notes
    assert any(one.kind == "depth" for one in found.problems)


def test_the_fix_for_a_thin_criterion_names_what_is_missing():
    found = tools.review_tests(
        _tests_in(
            criteria=[{"text": "A card is refused when the entered CVV is wrong"}],
            test_cases=[
                {
                    "id": "TC-1",
                    "title": "A saved card pays",
                    "steps": ["Open the cart", "Press Pay"],
                    "expected": "The order is placed",
                    "covers": ["AC-1"],
                }
            ],
        )
    )
    depth = [one for one in found.problems if one.kind == "depth"]
    assert depth
    assert "wrong input" in depth[0].fix


def test_the_fix_wording_is_built_from_the_engines_own_reasons():
    # If NO_KIND were reworded and this module kept a copy of the old words,
    # every thin criterion would quietly get the vague fallback instead.
    class Row:
        id = "AC-1"
        reasons = [ONLY_ONE, NO_KIND["Negative"], NO_KIND["Boundary"]]
        needs_wrong_input = True
        needs_limit = True

    fix = tools._depth_fix(Row())
    assert "a second test" in fix
    assert "wrong input" in fix
    assert "at the limit" in fix


def test_a_criterion_with_nothing_at_all_is_told_to_write_one_test():
    class Row:
        id = "AC-9"
        reasons = [NOT_COVERED]
        needs_wrong_input = False
        needs_limit = False

    assert tools._depth_fix(Row()) == "Write at least one test that covers AC-9."


def test_added_tests_go_straight_back_into_test_cases():
    found = tools.review_tests(_tests_in())
    assert found.add_tests
    again = tools.review_tests(
        _tests_in(
            test_cases=[
                *_tests_in().model_dump()["test_cases"],
                *[one.model_dump() for one in found.add_tests],
            ]
        )
    )
    # Taking the proposal makes the suite better, not worse.
    assert len(again.problems) <= len(found.problems)


def test_weak_input_is_a_finding_not_a_refusal():
    found = tools.review_tests(
        _tests_in(
            test_cases=[
                {
                    "id": "TC-3",
                    "title": "Enter the card number and pay",
                    "steps": ["Type the card number into the field", "Press Pay"],
                    "expected": "The order is placed",
                    "covers": ["AC-1"],
                }
            ]
        )
    )
    weak = [one for one in found.problems if one.kind == "weak"]
    assert any("TC-3" in one.says for one in weak)
    # The id is on the problem as data too, not only inside the sentence.
    assert any("TC-3" in one.tests for one in weak)


def test_an_ac_shaped_id_the_agent_chose_is_kept():
    found = tools.review_tests(
        _tests_in(
            criteria=[
                {"id": "AC-4", "text": "A saved card pays"},
                {"id": "AC-9", "text": "An expired card is refused"},
            ],
            test_cases=[
                {
                    "id": "TC-1",
                    "title": "A saved card pays",
                    "steps": ["Open the cart", "Press Pay"],
                    "expected": "The order is placed",
                    "covers": ["AC-4"],
                }
            ],
        )
    )
    missing = [one for one in found.problems if one.kind == "missing"]
    assert missing and missing[0].criteria == ["AC-9"]
    assert not any("renumbered" in note for note in found.notes)


def test_an_id_the_engine_cannot_read_is_renumbered_and_said_so():
    # The checks read "AC-<number>" and nothing else. Leaving "PAY-7" alone
    # would report a fully tested criterion as having no tests at all —
    # silently, which is the worst way for a tool to be wrong.
    found = tools.review_tests(
        _tests_in(
            criteria=[{"id": "PAY-7", "text": "A saved card pays"}],
            test_cases=[
                {
                    "id": "TC-1",
                    "title": "A saved card pays",
                    "steps": ["Open the cart", "Press Pay"],
                    "expected": "The order is placed",
                    "covers": ["PAY-7"],
                }
            ],
        )
    )
    assert "100% of criteria have at least one test." in found.notes
    note = next(one for one in found.notes if "renumbered" in one)
    assert "PAY-7 → AC-1" in note


def test_the_renumbering_note_comes_first_so_every_id_below_is_read_right():
    found = tools.review_tests(
        _tests_in(criteria=[{"id": "story-3", "text": "A saved card pays"}])
    )
    assert "renumbered" in found.notes[0]


def test_ship_check_renumbers_the_same_way():
    found = tools.ship_check(
        _ship_in(
            criteria=[{"id": "PAY-7", "text": "A saved card pays"}],
            test_cases=[
                {
                    "id": "TC-1",
                    "title": "A saved card pays",
                    "steps": ["Open the cart", "Press Pay"],
                    "expected": "The order is placed",
                    "covers": ["PAY-7"],
                }
            ],
        )
    )
    coverage = next(one for one in found.checks if one.id == "coverage")
    assert coverage.status == "pass"
    assert "renumbered" in found.notes[0]


# ──────────────────────────────────────────────────────────────────────────────
# ship_check
# ──────────────────────────────────────────────────────────────────────────────


def test_a_check_with_nothing_sent_for_it_is_never_fine():
    found = tools.ship_check(_ship_in())
    risks = next(one for one in found.checks if one.id == "risks")
    assert risks.status == "not_checked"
    assert "fine" not in risks.summary.lower()
    assert any("not done yet" in one.lower() for one in found.notes)


def test_the_decision_is_said_in_words_an_agent_can_branch_on():
    assert tools.ship_check(_ship_in()).decision in (
        "ready",
        "ready with known risks",
        "not ready",
    )


def test_sending_risks_makes_the_risk_check_run():
    found = tools.ship_check(
        _ship_in(
            risks=[
                {
                    "id": "R1",
                    "title": "A saved card is charged twice",
                    "category": "data",
                    "effect": "The shopper pays twice",
                    "cause": "The Pay button sends two requests",
                    "severity": 5,
                    "likelihood": 3,
                    "detectability": 4,
                }
            ]
        )
    )
    risks = next(one for one in found.checks if one.id == "risks")
    assert risks.status != "not_checked"


def test_an_accepted_risk_stops_counting_as_untested():
    risk = {
        "id": "R1",
        "title": "A saved card is charged twice",
        "category": "data",
        "effect": "The shopper pays twice",
        "cause": "The Pay button sends two requests",
        "severity": 5,
        "likelihood": 5,
        "detectability": 5,
    }
    before = tools.ship_check(_ship_in(risks=[risk]))
    after = tools.ship_check(_ship_in(risks=[risk], accepted=["R1"]))
    risks_before = next(one for one in before.checks if one.id == "risks")
    risks_after = next(one for one in after.checks if one.id == "risks")
    assert risks_before.status == "fail"
    assert risks_after.status != "fail"


def test_sending_a_matrix_makes_the_matrix_check_run():
    found = tools.ship_check(
        _ship_in(
            matrix_summary={
                "runs": 4,
                "valid_pairs": 6,
                "covered_pairs": 6,
                "manual_only": 0,
                "factors": ["browser", "device"],
            }
        )
    )
    matrix = next(one for one in found.checks if one.id == "matrix")
    assert matrix.status == "pass"


def test_the_path_to_ready_only_holds_steps_the_caller_can_take():
    found = tools.ship_check(_ship_in())
    # The three checks that need the website are named in notes, not asked
    # for in a list of instructions nobody reading this could follow.
    assert not any("Story check" in step for step in found.path_to_ready)
    assert any("website" in note for note in found.notes)


def test_the_grade_is_none_when_nothing_could_be_scored():
    found = tools.ship_check(
        ShipIn.model_validate(
            {"story": STORY, "criteria": [], "test_cases": []}
        )
    )
    assert found.grade is None or found.grade.max > 0


def test_every_check_comes_back_in_a_fixed_order():
    first = [one.id for one in tools.ship_check(_ship_in()).checks]
    second = [one.id for one in tools.ship_check(_ship_in()).checks]
    assert first == second
    assert first[0] == "clarity" and first[-1] == "matrix"


# ──────────────────────────────────────────────────────────────────────────────
# Adapters
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "kind,category",
    [
        ("normal", "Functional"),
        ("wrong input", "Negative"),
        ("at the limit", "Boundary"),
        ("unusual", "Edge Case"),
    ],
)
def test_each_kind_becomes_the_category_the_engine_counts(kind, category):
    from qagenius.mcp_server.schemas import TestIn

    case = adapters.case_from(
        TestIn(id="TC-1", title="t", steps=["a"], expected="b", kind=kind)
    )
    assert case.category == category
    # ... and comes back out as the kind it went in as.
    assert adapters.test_out(case).kind == kind


def test_criteria_without_ids_are_numbered_in_order():
    from qagenius.mcp_server.schemas import CriterionIn

    found = adapters.criteria_from(
        [CriterionIn(text="one"), CriterionIn(id="AC-9", text="two"), CriterionIn(text="three")]
    )
    assert [one.id for one in found] == ["AC-1", "AC-9", "AC-3"]


def test_no_risks_means_no_analysis_at_all():
    # None is what makes the risk check say "not done yet" rather than "fine".
    assert adapters.risks_from([]) is None
    assert adapters.matrix_from(None) is None


def test_a_risk_without_an_id_is_given_one():
    from qagenius.mcp_server.schemas import RiskIn

    analysis = adapters.risks_from([RiskIn(title="A risk")])
    assert analysis.failure_modes[0].id == "R1"
