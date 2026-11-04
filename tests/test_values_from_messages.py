"""A number inside a quoted message is not the value a test is using.

The run this came from: TC-2 puts $40.00 in the cart and expects
"Refused with 'This coupon needs an order of at least $50.'" — and the
senior tester read the $50 out of the product's own error message and
reported that TC-2 had decided what happens at exactly $50. It had decided
nothing; it is a test about forty dollars.

The same run had two tests doing the identical thing with the identical
data under different names, and neither the title check nor anything else
said so.
"""

from qagenius import web
from qagenius.mcp_server import tools
from qagenius.mcp_server.schemas import TestsIn
from qagenius.shadow_qa.boundaries import case_values, without_quoted
from qagenius.shadow_qa.review import limit_conflicts, review_test_cases, with_context
from qagenius.test_cases import number_criteria
from tests.factories import (
    COUPON_CONTEXT,
    COUPON_CRITERIA,
    COUPON_STORY,
    case,
    suite,
)

CRITERIA = number_criteria(COUPON_CRITERIA)
RULED = with_context(CRITERIA, COUPON_CONTEXT)

REFUSAL = "Refused with 'This coupon needs an order of at least $50.'"
STEPS = ["Put $40.00 of items in the cart", "Enter a valid coupon code"]


def _tc(case_id: str, title: str) -> object:
    return case(
        case_id=case_id,
        title=title,
        traceability="AC-2",
        steps=list(STEPS),
        test_data="cart_total=40.00",
        expected_result=REFUSAL,
    )


TC_1 = _tc("TC-1", "A coupon on a cart under the minimum")
TC_2 = _tc("TC-2", "A small cart is refused the coupon")


def _about(notes: list[str], case_id: str) -> list[str]:
    return [one for one in notes if one.startswith(f"{case_id} ")]


# ──────────────────────────────────────────────────────────────────────────────
# The message is not the value
# ──────────────────────────────────────────────────────────────────────────────


def test_a_forty_dollar_test_does_not_decide_what_happens_at_fifty():
    notes = limit_conflicts(RULED, [TC_2])
    assert _about(notes, "TC-2") == []
    assert not any("TC-2" in one and "$50" in one for one in notes)


def test_the_criteria_still_argue_about_fifty_dollars():
    # The fix must not quiet the note that matters. AC-1 and AC-2 really do
    # leave exactly $50 undecided, and that is worth saying whatever the
    # tests look like.
    notes = limit_conflicts(RULED, [TC_2])
    assert any("Nobody says what happens at exactly $50" in one for one in notes)
    assert any('The context says "at least $50"' in one for one in notes)


def test_a_test_that_really_uses_fifty_dollars_is_still_caught():
    # The quoted message goes; a cart of exactly fifty does not.
    decider = case(
        case_id="TC-9",
        title="A coupon on a cart of exactly fifty",
        traceability="AC-1",
        steps=["Put $50.00 of items in the cart", "Enter a valid coupon code"],
        test_data="cart_total=50.00",
        expected_result="The discount is applied",
    )
    notes = limit_conflicts(RULED, [decider])
    assert _about(notes, "TC-9") == [
        "TC-9 decides $50 is accepted while that question is still open."
    ]


def test_the_value_is_read_from_the_data_when_the_steps_disagree():
    # "an order over $50" is the name of the rule; 40.00 is the cart.
    mixed = case(
        case_id="TC-3",
        title="A coupon on an order over $50",
        traceability="AC-2",
        steps=["Open the cart worth $50.00", "Enter a valid coupon code"],
        test_data="cart_total=40.00",
        expected_result=REFUSAL,
    )
    assert case_values(mixed) == ["cart_total=40.00"]
    assert _about(limit_conflicts(RULED, [mixed]), "TC-3") == []


# ──────────────────────────────────────────────────────────────────────────────
# What counts as a quoted message
# ──────────────────────────────────────────────────────────────────────────────


def test_both_kinds_of_quote_are_blanked():
    assert "50" not in without_quoted("Refused with 'at least $50.'")
    assert "50" not in without_quoted('Refused with "at least $50."')
    assert "50" not in without_quoted("Refused with “at least $50.”")


def test_the_blanks_keep_the_length_of_what_they_replace():
    said = "Refused with 'at least $50.'"
    assert len(without_quoted(said)) == len(said)


def test_an_apostrophe_is_not_an_opening_quote():
    # "the user's cart has 5 items" must keep its five.
    assert "5" in without_quoted("The user's cart has 5 items")
    assert "5" in without_quoted("It's 5 attempts, not 6")


def test_a_quote_with_no_partner_is_left_alone():
    # Blanking to the end of the line would take real data with it.
    assert "40" in without_quoted("The cart is $40.00 and shows 'Refused")


def test_text_outside_the_quotes_survives():
    said = without_quoted("A 2 MB photo is refused with 'the 5 MB limit'")
    assert "2 MB" in said
    assert "5 MB" not in said


# ──────────────────────────────────────────────────────────────────────────────
# Which source a value comes from
# ──────────────────────────────────────────────────────────────────────────────


def test_test_data_wins_over_the_steps_and_the_title():
    assert case_values(TC_1) == ["cart_total=40.00"]


def test_the_steps_are_read_when_the_data_has_no_number():
    no_data = case(
        case_id="TC-4",
        title="A cart over the $50 minimum",
        steps=["Put $60.00 of items in the cart", "Enter a valid coupon code"],
        test_data="coupon=SPRING",
        expected_result="The discount is applied",
    )
    assert case_values(no_data) == [
        "Put $60.00 of items in the cart",
        "Enter a valid coupon code",
    ]


def test_the_title_is_the_last_resort():
    bare = case(
        case_id="TC-5",
        title="A cart of exactly $50",
        steps=["Open the cart", "Enter a valid coupon code"],
        test_data="",
        expected_result="The discount is applied",
    )
    assert case_values(bare) == ["A cart of exactly $50"]


def test_a_case_with_no_number_anywhere_offers_nothing():
    nothing = case(
        case_id="TC-6",
        title="A coupon is applied",
        steps=["Open the cart", "Enter a valid coupon code"],
        test_data="",
        expected_result="The discount is applied",
    )
    assert case_values(nothing) == []


def test_the_quoted_message_is_out_of_the_steps_too():
    talking = case(
        case_id="TC-7",
        title="A refusal names the minimum",
        steps=["Open the cart", "Read the message 'needs at least $50'"],
        test_data="",
        expected_result="The coupon is refused",
    )
    assert all("$50" not in one for one in case_values(talking))


# ──────────────────────────────────────────────────────────────────────────────
# Two tests that are one test
# ──────────────────────────────────────────────────────────────────────────────


def test_the_two_forty_dollar_tests_are_flagged_as_copies():
    review = review_test_cases(COUPON_STORY, CRITERIA, suite(TC_1, TC_2), COUPON_CONTEXT)
    assert "TC-2: same steps and test data as TC-1" in review.quality


def test_one_of_them_on_its_own_is_not_a_copy():
    review = review_test_cases(COUPON_STORY, CRITERIA, suite(TC_1), COUPON_CONTEXT)
    assert not any("same steps and test data" in one for one in review.quality)


# ──────────────────────────────────────────────────────────────────────────────
# Both doors, one engine
# ──────────────────────────────────────────────────────────────────────────────


def _mcp_answer():
    return tools.review_tests(
        TestsIn.model_validate(
            {
                "story": COUPON_STORY,
                "context": COUPON_CONTEXT,
                "criteria": [{"text": one} for one in COUPON_CRITERIA],
                "test_cases": [
                    {
                        "id": one.id,
                        "title": one.title,
                        "steps": list(STEPS),
                        "expected": REFUSAL,
                        "test_data": "cart_total=40.00",
                        "covers": ["AC-2"],
                        "kind": "wrong input",
                    }
                    for one in (TC_1, TC_2)
                ],
            }
        )
    )


def test_the_website_and_the_mcp_door_say_the_same_thing():
    # One engine, two doors. The website's own helper and the MCP tool are
    # given the same suite and have to agree about it.
    merged, review = web._with_principal_cases(
        COUPON_STORY, CRITERIA, suite(TC_1, TC_2), COUPON_CONTEXT
    )
    answer = _mcp_answer()

    # Neither says a $40 test decided what happens at $50.
    assert _about(review.conflicts, "TC-2") == []
    assert not any(
        one.kind == "limit" and "TC-2" in one.says for one in answer.problems
    )

    # Both say the second test is a copy of the first.
    assert "TC-2: same steps and test data as TC-1" in review.quality
    copies = [one for one in answer.problems if one.kind == "copy"]
    assert any("TC-2" in one.says and "TC-1" in one.says for one in copies)
    assert any("TC-2" in one.tests for one in copies)


def test_both_doors_still_report_the_criteria_disagreement():
    _, review = web._with_principal_cases(
        COUPON_STORY, CRITERIA, suite(TC_1, TC_2), COUPON_CONTEXT
    )
    answer = _mcp_answer()
    assert any("exactly $50" in one for one in review.conflicts)
    assert any("exactly $50" in one for one in answer.ask_the_po)
