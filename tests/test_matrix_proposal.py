"""The AI proposes factors; this module decides what is usable."""

import qagenius.prompts as prompts
from tests.factories import (
    COUPON_CONTEXT,
    COUPON_CRITERIA,
    COUPON_STORY,
)
from qagenius.models import MatrixProposal, ProposedFactor, ProposedRule
from qagenius.pairwise import validate
from qagenius.test_matrix_defaults import STANDARD_FACTORS
from qagenius.test_matrix_proposal import (
    GUEST_RULE_NOTE,
    ADDED_NOTE,
    ADDED_ONE_NOTE,
    FALLBACK_NOTE,
    clean_proposal,
    is_backend_only,
    reasons_for,
    standard_set,
)


def proposal(factors=None, rules=None) -> MatrixProposal:
    return MatrixProposal(factors=factors or [], rules=rules or [])


def factor(name, values, reason="") -> ProposedFactor:
    return ProposedFactor(name=name, values=list(values), reason=reason)


GOOD = [
    factor("Browser", ["Chrome", "Safari"], "The story is a web page."),
    factor("Device", ["Desktop", "Phone"], "The bar collapses on narrow screens."),
    factor("Signed in", ["Yes", "No"], "Signed-out users see fewer modules."),
]


# -------------------------------------------------------------------- prompt


def test_the_prompt_asks_for_the_right_shape():
    system, _ = prompts.test_matrix_prompt("story", "AC-1: x", "TC-001 | Functional | y")
    assert "3 to 6 factors" in system
    assert "Only add a rule when you are sure" in system
    assert "2 to 5 realistic values" in system


def test_the_prompt_carries_the_story_criteria_and_cases():
    _, user = prompts.test_matrix_prompt("As a shopper", "AC-1: locks", "TC-001 | Functional | x")
    assert "As a shopper" in user
    assert "AC-1: locks" in user
    assert "TC-001 | Functional | x" in user


def test_an_empty_run_still_makes_a_prompt():
    _, user = prompts.test_matrix_prompt("story", "", "")
    assert user.count("(none yet)") == 2


# --------------------------------------------------------------------- guard


def test_a_good_proposal_comes_through_unchanged():
    factors, rules, notes = clean_proposal(proposal(GOOD))
    assert [one.name for one in factors] == ["Browser", "Device", "Signed in"]
    assert factors[0].values == ("Chrome", "Safari")
    assert notes == []
    assert validate(factors, rules) == []


def test_at_most_six_factors_are_kept():
    many = [factor(f"F{i}", ["a", "b"]) for i in range(9)]
    factors, _, _ = clean_proposal(proposal(many))
    assert len(factors) == 6


def test_at_most_five_values_are_kept():
    wide = [factor("Browser", [f"b{i}" for i in range(9)]), factor("Device", ["a", "b"])]
    factors, _, _ = clean_proposal(proposal(wide))
    assert len(factors[0].values) == 5


def test_values_are_trimmed_and_deduped_case_insensitively():
    messy = [
        factor("Browser", ["  Chrome ", "chrome", "CHROME", "Safari"]),
        factor("Device", ["Desktop", "Phone"]),
    ]
    factors, _, _ = clean_proposal(proposal(messy))
    assert factors[0].values == ("Chrome", "Safari")


def test_a_repeated_factor_name_is_dropped():
    twice = [
        factor("Browser", ["Chrome", "Safari"]),
        factor("browser", ["Edge", "Firefox"]),
        factor("Device", ["Desktop", "Phone"]),
    ]
    factors, _, _ = clean_proposal(proposal(twice))
    assert [one.name for one in factors] == ["Browser", "Device"]


def test_a_factor_with_one_value_is_dropped_with_a_note():
    thin = [
        factor("Browser", ["Chrome"]),
        factor("Device", ["Desktop", "Phone"]),
        factor("Signed in", ["Yes", "No"]),
    ]
    factors, _, notes = clean_proposal(proposal(thin))
    # Browser is dropped for having one value, then put back with the standard
    # four: a screen is still opened in a browser.
    assert [one.name for one in factors] == ["Device", "Signed in", "Browser"]
    assert factors[2].values == ("Chrome", "Firefox", "Safari", "Edge")
    assert notes == [
        "Dropped 1 suggested factor with fewer than two values.",
        ADDED_ONE_NOTE.format(name="Browser"),
    ]


def test_a_rule_about_an_unknown_value_is_dropped_with_a_note():
    rules = [ProposedRule(if_factor="Browser", if_value="Netscape",
                          then_factor="Device", then_value="Phone")]
    _, kept, notes = clean_proposal(proposal(GOOD, rules))
    assert kept == []
    assert notes == ["Ignored 1 rule that referred to an unknown value."]


def test_a_rule_pointing_a_factor_at_itself_is_dropped():
    rules = [ProposedRule(if_factor="Browser", if_value="Chrome",
                          then_factor="Browser", then_value="Safari")]
    _, kept, notes = clean_proposal(proposal(GOOD, rules))
    assert kept == []
    assert notes == ["Ignored 1 rule that referred to an unknown value."]


def test_a_good_rule_is_kept_with_its_reason():
    rules = [ProposedRule(if_factor="Browser", if_value="Safari",
                          then_factor="Device", then_value="Phone",
                          reason="Only on Apple hardware.")]
    _, kept, _ = clean_proposal(proposal(GOOD, rules))
    assert len(kept) == 1
    assert kept[0].reason == "Only on Apple hardware."


def test_the_standard_rules_are_merged_in_when_their_factors_exist():
    wide = [
        factor("Browser", ["Chrome", "Firefox", "Edge"]),
        factor("Device", ["Desktop", "Tablet", "Phone"]),
    ]
    _, rules, _ = clean_proposal(proposal(wide))
    pairs = {(one.if_value, one.then_value) for one in rules}
    assert ("Firefox", "Phone") in pairs
    assert ("Edge", "Tablet") in pairs


def test_the_standard_rules_stay_out_when_the_values_are_absent():
    _, rules, _ = clean_proposal(proposal(GOOD))
    assert rules == []  # no Firefox and no Tablet in this proposal


def test_a_rule_is_not_added_twice_in_either_direction():
    rules = [
        ProposedRule(if_factor="Browser", if_value="Safari",
                     then_factor="Device", then_value="Phone"),
        ProposedRule(if_factor="Device", if_value="Phone",
                     then_factor="Browser", then_value="Safari"),
    ]
    _, kept, _ = clean_proposal(proposal(GOOD, rules))
    assert len(kept) == 1


def test_an_unusable_proposal_falls_back_to_the_standard_set():
    """An API story gets no screen factors, so one factor stays unusable."""
    one = proposal([factor("Payload", ["Valid", "Malformed"])])
    factors, rules, notes = clean_proposal(one, "The orders API endpoint")
    assert [one.name for one in factors] == [one.name for one in STANDARD_FACTORS]
    assert FALLBACK_NOTE in notes
    assert validate(factors, rules) == []


def test_an_empty_proposal_falls_back_too():
    factors, rules, notes = clean_proposal(proposal())
    assert factors == list(STANDARD_FACTORS)
    assert notes == [FALLBACK_NOTE]


def test_the_standard_set_is_what_a_user_with_no_key_gets():
    factors, rules = standard_set()
    assert validate(factors, rules) == []
    assert [one.name for one in factors] == ["Browser", "Device", "Signed in"]


def test_the_reasons_come_back_for_the_editor():
    found = reasons_for(proposal(GOOD))
    assert found["browser"] == "The story is a web page."
    assert reasons_for(None) == {}


# ── a screen is always opened in a browser, on a device ──────────────────────

LOCKOUT = (
    "As a shopper, I want my account locked after too many wrong passwords. "
    "The sign-in page shows how many attempts are left."
)


def _lockout_proposal() -> MatrixProposal:
    """What a real run suggested for the lockout story: no Browser, no Device."""
    return proposal(
        [
            factor("Signed in", ["Yes", "No"], "The page differs when signed in."),
            factor("Role", ["Shopper", "Admin"], "Admins unlock accounts."),
            factor("Language", ["en", "bn"], "The message is translated."),
        ]
    )


def test_browser_and_device_are_put_back_when_the_ai_forgets_them():
    factors, rules, notes = clean_proposal(_lockout_proposal(), LOCKOUT)
    names = [one.name for one in factors]
    assert "Browser" in names and "Device" in names
    assert names[:3] == ["Signed in", "Role", "Language"]
    assert ADDED_NOTE in notes
    assert validate(factors, rules) == []


def test_the_standard_rules_come_with_them():
    _, rules, _ = clean_proposal(_lockout_proposal(), LOCKOUT)
    pairs = {(one.if_value, one.then_value) for one in rules}
    assert ("Firefox", "Phone") in pairs


def test_only_the_missing_one_is_added():
    half = proposal(
        [
            factor("Browser", ["Chrome", "Safari"]),
            factor("Signed in", ["Yes", "No"]),
        ]
    )
    factors, _, notes = clean_proposal(half, LOCKOUT)
    assert [one.name for one in factors] == ["Browser", "Signed in", "Device"]
    assert notes == [ADDED_ONE_NOTE.format(name="Device")]


def test_a_proposal_that_already_has_both_is_left_alone():
    factors, _, notes = clean_proposal(proposal(GOOD), LOCKOUT)
    assert [one.name for one in factors] == ["Browser", "Device", "Signed in"]
    assert notes == []


def test_an_api_story_keeps_the_factors_the_ai_chose():
    api = (
        "As a partner system, I want the orders API endpoint to reject a "
        "malformed payload so that bad data never reaches the backend."
    )
    factors, _, notes = clean_proposal(_lockout_proposal(), api)
    assert [one.name for one in factors] == ["Signed in", "Role", "Language"]
    assert notes == []


def test_a_webhook_story_is_backend_too():
    assert is_backend_only("The webhook retries three times.")
    assert is_backend_only("A service-to-service call carries the token.")
    assert not is_backend_only("The shopper opens the sign-in page.")


def test_the_six_factor_cap_still_holds_when_two_are_added():
    many = proposal([factor(f"F{i}", ["a", "b"]) for i in range(6)])
    factors, rules, _ = clean_proposal(many, LOCKOUT)
    assert len(factors) == 6
    assert [one.name for one in factors][-2:] == ["Browser", "Device"]
    assert validate(factors, rules) == []


# ── a suggested rule is labelled, and checked against the story ──────────────


def test_a_suggested_rule_says_it_was_suggested():
    proposal = MatrixProposal(
        factors=[
            ProposedFactor(
                name="Browser", values=["Chrome", "Firefox", "Safari"], reason="Web."
            ),
            ProposedFactor(name="Device", values=["Desktop", "Phone"], reason="Both."),
        ],
        rules=[
            ProposedRule(
                if_factor="Browser",
                if_value="Safari",
                then_factor="Device",
                then_value="Desktop",
                reason="A guess worth checking.",
            )
        ],
    )
    _, rules, _ = clean_proposal(proposal, "A web story.")
    suggested = [one for one in rules if one.source == "ai"]
    assert len(suggested) == 1
    assert all(one.source == "standard" for one in rules if one not in suggested)


def test_a_rule_that_argues_with_the_story_about_guests_is_dropped():
    """The coupon run: the context says guests can use coupons."""
    proposal = MatrixProposal(
        factors=[
            ProposedFactor(name="Signed in", values=["Yes", "No"], reason="Guests too."),
            ProposedFactor(name="Cart value", values=["Low", "High"], reason="Minimum."),
        ],
        rules=[
            ProposedRule(
                if_factor="Signed in",
                if_value="No",
                then_factor="Cart value",
                then_value="Low",
                reason="Guests cannot use coupons.",
            )
        ],
    )
    text = "\n".join([COUPON_STORY, COUPON_CONTEXT, *COUPON_CRITERIA])
    _, rules, notes = clean_proposal(proposal, text)
    assert not any(one.source == "ai" for one in rules)
    assert GUEST_RULE_NOTE in notes


def test_the_same_rule_stays_when_the_story_says_nothing_about_guests():
    proposal = MatrixProposal(
        factors=[
            ProposedFactor(name="Signed in", values=["Yes", "No"], reason="Both."),
            ProposedFactor(name="Cart value", values=["Low", "High"], reason="Minimum."),
        ],
        rules=[
            ProposedRule(
                if_factor="Signed in",
                if_value="No",
                then_factor="Cart value",
                then_value="Low",
                reason="Only members see the cheap tier.",
            )
        ],
    )
    _, rules, notes = clean_proposal(proposal, "As a member, I want the member price.")
    assert any(one.source == "ai" for one in rules)
    assert GUEST_RULE_NOTE not in notes
