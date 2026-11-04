"""The service layer is one engine, and both doors turn the same crank.

The parity tests matter most: whatever the web route works out for an input
and whatever the service works out for the same input have to be the same
object, or the website and an agent will disagree about one story.
"""

from datetime import date

from qagenius import web
from qagenius.models import AmbiguityAnalysis
from qagenius.services.release_decision import decide_release, release_grade
from qagenius.services.story_review import (
    SAY_INSTEAD,
    NO_FAILURE_TITLE,
    review_story_text,
)
from qagenius.services.test_review import as_criteria, review_tests
from qagenius.shadow_qa.review import review_test_cases
from qagenius.shadow_qa.story_rules import review_story
from qagenius.ship_check import ShipInputs, compute_ship_report
from qagenius.ship_grade import grade_for
from qagenius.test_cases import Criterion, compute_coverage, number_criteria
from qagenius.vague import VAGUE_WORDS
from tests.factories import REAL_RUN_CRITERIA, real_run, suite

STORY = (
    "As a shopper I want to sign in to Aurora Storefront so that I can see "
    "my orders. The account locks quickly after too many wrong passwords."
)
CONTEXT = "Lockout applies to the storefront only, not the admin console."


# ──────────────────────────────────────────────────────────────────────────────
# Story review
# ──────────────────────────────────────────────────────────────────────────────


def test_every_vague_word_has_something_to_say_instead():
    # A word the rules catch with no replacement written for it sends the
    # reader away with "that is vague" and nothing to do about it.
    assert set(VAGUE_WORDS) <= set(SAY_INSTEAD)
    assert all(SAY_INSTEAD[word].strip() for word in VAGUE_WORDS)


def test_unclear_words_come_back_with_a_replacement():
    review = review_story_text(STORY)
    words = [item.word for item in review.unclear]
    assert "quickly" in words
    assert "too many" in words
    said = {item.word: item.say_instead for item in review.unclear}
    assert "2 seconds" in said["quickly"]
    assert "5" in said["too many"]


def test_unclear_words_are_read_from_the_context_too():
    review = review_story_text("As a shopper I want to sign in.", "It must be fast.")
    assert "fast" in [item.word for item in review.unclear]


def test_a_story_on_its_own_is_told_when_nothing_says_what_fails():
    review = review_story_text("As a shopper I want to sign in so that I see orders.")
    assert NO_FAILURE_TITLE in [note.title for note in review.notes]


def test_a_story_that_says_what_fails_is_not_told_that_it_does_not():
    review = review_story_text(
        "As a shopper I want to sign in so that I see orders. "
        "An invalid password is rejected with a message."
    )
    assert NO_FAILURE_TITLE not in [note.title for note in review.notes]


def test_criteria_answer_the_failure_question_instead_of_the_story():
    # With criteria in hand the rules judge them, exactly as the page does,
    # and the story's own wording is not read for it a second time.
    review = review_story_text(
        "As a shopper I want to sign in so that I see orders.",
        criteria=["An invalid password is rejected"],
    )
    assert NO_FAILURE_TITLE not in [note.title for note in review.notes]


def test_the_epic_warning_is_the_one_the_rules_wrote():
    big = (
        "As an admin I want to sign in, reset my password, set up two-factor, "
        "upload a photo, search the catalogue, change my preferences and "
        "delete my account so that I can run the shop."
    )
    review = review_story_text(big)
    from_rules = review_story(big, [], "")
    assert review.epic is not None
    assert review.epic == next(note for note in from_rules if note.epic)


def test_criteria_come_back_numbered_in_order():
    review = review_story_text(STORY, criteria=REAL_RUN_CRITERIA)
    assert [one.id for one in review.criteria] == [
        f"AC-{n}" for n in range(1, len(REAL_RUN_CRITERIA) + 1)
    ]
    assert review.criteria == number_criteria(REAL_RUN_CRITERIA)


def test_blank_criteria_are_dropped_before_numbering():
    review = review_story_text(STORY, criteria=["  ", "A real one", ""])
    assert review.criteria == [Criterion(id="AC-1", text="A real one")]


def test_story_type_changes_nothing():
    # It is carried for the caller's wording. A bug and a feature are equally
    # untestable when they are written in words nobody can measure.
    first = review_story_text(STORY, CONTEXT, "user story")
    second = review_story_text(STORY, CONTEXT, "bug")
    assert first == second


# ──────────────────────────────────────────────────────────────────────────────
# Test review
# ──────────────────────────────────────────────────────────────────────────────


def test_the_suite_is_the_ai_cases_then_the_added_ones():
    result, criteria = real_run()
    reviewed = review_tests(STORY, CONTEXT, criteria, result)
    assert reviewed.suite.test_cases[: len(result.test_cases)] == result.test_cases
    assert reviewed.suite.test_cases[len(result.test_cases) :] == reviewed.added


def test_counts_are_taken_from_the_merged_suite_not_the_ai_summary():
    result, criteria = real_run()
    reviewed = review_tests(STORY, CONTEXT, criteria, result)
    # The factory's summary says 999 on purpose.
    assert result.summary.total_generated == 999
    assert reviewed.counts.total == len(reviewed.suite.test_cases)


def test_coverage_and_depth_are_computed_over_the_merged_suite():
    result, criteria = real_run()
    reviewed = review_tests(STORY, CONTEXT, criteria, result)
    assert reviewed.coverage == compute_coverage(reviewed.suite, criteria)
    assert reviewed.depth_line


def test_plain_strings_and_numbered_criteria_give_the_same_answer():
    result, criteria = real_run()
    from_objects = review_tests(STORY, CONTEXT, criteria, result)
    from_strings = review_tests(STORY, CONTEXT, REAL_RUN_CRITERIA, result)
    assert from_objects.suite == from_strings.suite
    assert from_objects.coverage == from_strings.coverage


def test_as_criteria_leaves_numbered_criteria_alone():
    criteria = number_criteria(REAL_RUN_CRITERIA)
    assert as_criteria(criteria) == criteria


def test_a_suite_with_no_cases_is_read_not_refused():
    reviewed = review_tests(STORY, CONTEXT, REAL_RUN_CRITERIA, None)
    assert reviewed.counts.total == len(reviewed.added)
    assert reviewed.coverage.percent >= 0


# ──────────────────────────────────────────────────────────────────────────────
# Release decision
# ──────────────────────────────────────────────────────────────────────────────


def _ship_inputs() -> ShipInputs:
    result, criteria = real_run()
    return ShipInputs(
        story=STORY,
        context=CONTEXT,
        test_cases=result,
        criteria=[one.text for one in criteria],
        today=date(2026, 11, 4),
    )


def test_the_decision_is_the_ship_check_rules():
    inputs = _ship_inputs()
    assert decide_release(inputs) == compute_ship_report(inputs)


def test_the_grade_is_the_ship_grade():
    report = decide_release(_ship_inputs())
    assert release_grade(report) == grade_for(report)


def test_a_report_with_nothing_checked_has_no_grade():
    report = decide_release(ShipInputs(story=STORY, today=date(2026, 11, 4)))
    assert release_grade(report) is None


# ──────────────────────────────────────────────────────────────────────────────
# Parity: the web route and the service work the same input out the same way
# ──────────────────────────────────────────────────────────────────────────────


def test_story_parity_with_the_rules_the_page_used_to_call_directly():
    found = review_story(STORY, REAL_RUN_CRITERIA, CONTEXT)
    service = review_story_text(STORY, CONTEXT, criteria=REAL_RUN_CRITERIA)
    assert service.epic == next((n for n in found if n.epic), None)
    assert service.notes == [note for note in found if not note.epic]


def test_test_case_parity_between_the_route_helper_and_the_service():
    result, criteria = real_run()
    merged, review = web._with_principal_cases(STORY, criteria, result, CONTEXT)
    service = review_tests(STORY, CONTEXT, criteria, result)
    assert merged == service.suite
    assert review == service.review


def test_test_case_parity_with_the_rules_the_page_used_to_call_directly():
    result, criteria = real_run()
    direct = review_test_cases(STORY, criteria, result, CONTEXT)
    assert review_tests(STORY, CONTEXT, criteria, result).review == direct


def test_the_story_card_context_still_reads_the_same_notes():
    # The card, the reason list and the stored data are built from one read
    # of the story now. They must still agree with each other.
    analysis = AmbiguityAnalysis(
        ambiguity_score=40,
        clarity_label="Needs work",
        invest_overall="ok",
        invest_independent="ok",
        invest_negotiable="ok",
        invest_valuable="ok",
        invest_estimable="ok",
        invest_small="ok",
        invest_testable="ok",
        vague_phrases=[],
        missing_elements=[],
        suggested_rewrites=[],
        generated_acceptance_criteria=list(REAL_RUN_CRITERIA),
        risks=[],
    )
    context = web._story_result_context(
        None, STORY, analysis, [], "saved example", CONTEXT
    )
    service = review_story_text(STORY, CONTEXT, criteria=REAL_RUN_CRITERIA)
    assert context["epic"] == service.epic
    assert context["shadow_notes"] == service.notes
    assert context["limit_notes"] == service.limit_notes
    assert context["notes_data"]["limit_notes"] == service.limit_notes


def test_the_service_never_touches_what_it_was_given():
    result, criteria = real_run()
    before = result.model_dump()
    review_tests(STORY, CONTEXT, criteria, result)
    assert result.model_dump() == before


def test_an_empty_suite_object_is_accepted():
    reviewed = review_tests(STORY, CONTEXT, REAL_RUN_CRITERIA, suite())
    assert reviewed.coverage.uncovered
