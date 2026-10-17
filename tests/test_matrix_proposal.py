"""The AI proposes factors; this module decides what is usable."""

import qagenius.prompts as prompts
from qagenius.models import MatrixProposal, ProposedFactor, ProposedRule
from qagenius.pairwise import validate
from qagenius.test_matrix_defaults import STANDARD_FACTORS
from qagenius.test_matrix_proposal import (
    FALLBACK_NOTE,
    clean_proposal,
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
    assert [one.name for one in factors] == ["Device", "Signed in"]
    assert notes == ["Dropped 1 suggested factor with fewer than two values."]


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
    _, _, _ = clean_proposal(proposal([factor("Browser", ["Chrome", "Safari"])]))
    factors, rules, notes = clean_proposal(
        proposal([factor("Browser", ["Chrome", "Safari"])])
    )
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
