"""The pairwise engine: every allowed pair covered, every rule respected, no randomness."""

import random
import time

import pytest

from qagenius.pairwise import (
    MAX_ATTEMPTS,
    Factor,
    Matrix,
    Rule,
    build_matrix,
    validate,
)


def grid(factors: int, values: int) -> list[Factor]:
    return [
        Factor(f"F{i + 1}", tuple(f"v{j + 1}" for j in range(values)))
        for i in range(factors)
    ]


BIG = [
    Factor("A", ("a1", "a2", "a3")),
    Factor("B", ("b1", "b2", "b3")),
    Factor("C", ("c1", "c2", "c3")),
    Factor("D", ("d1", "d2", "d3")),
    Factor("E", ("e1", "e2", "e3", "e4")),
]
LOGIN = [
    Factor("Browser", ("Chrome", "Firefox", "Safari")),
    Factor("OS", ("Windows", "Android", "macOS")),
    Factor("Device", ("Desktop", "Phone")),
]
NO_SAFARI_ON_ANDROID = Rule(
    "Browser", "Safari", "OS", "Android", "Safari does not run on Android."
)


def pairs_in(matrix: Matrix) -> set:
    """Every (factor, value index) pair the rows actually put together."""
    index = [
        {value: at for at, value in enumerate(factor.values)}
        for factor in matrix.factors
    ]
    found = set()
    for row in matrix.rows:
        for i in range(len(row)):
            for j in range(i + 1, len(row)):
                found.add((i, index[i][row[i]], j, index[j][row[j]]))
    return found


def breaks(matrix: Matrix, rule: Rule) -> bool:
    names = [factor.name for factor in matrix.factors]
    left, right = names.index(rule.if_factor), names.index(rule.then_factor)
    return any(
        row[left] == rule.if_value and row[right] == rule.then_value
        for row in matrix.rows
    )


# ------------------------------------------------------------------ coverage


def test_two_factors_need_a_row_for_every_pair():
    matrix = build_matrix(grid(2, 3), [])
    assert len(matrix.rows) == 9
    assert matrix.covered_pairs == matrix.valid_pairs == 9


def test_three_by_three_fits_in_ten_rows():
    matrix = build_matrix(grid(3, 3), [])
    assert len(matrix.rows) <= 10
    assert matrix.covered_pairs == matrix.valid_pairs == 27


def test_four_by_three_fits_in_eleven_rows():
    matrix = build_matrix(grid(4, 3), [])
    assert len(matrix.rows) <= 11
    assert matrix.covered_pairs == matrix.valid_pairs == 54


def test_the_324_combination_case_fits_in_sixteen_rows():
    """Five factors, 324 combinations, and the point of the whole desk."""
    matrix = build_matrix(BIG, [])
    assert matrix.all_combinations == 324
    assert matrix.valid_combinations == 324
    assert len(matrix.rows) <= 16
    assert matrix.covered_pairs == matrix.valid_pairs


def test_every_valid_pair_really_appears_in_a_row():
    matrix = build_matrix(BIG, [])
    found = pairs_in(matrix)
    missing = [
        (i, a, j, b)
        for i in range(len(BIG))
        for j in range(i + 1, len(BIG))
        for a in range(len(BIG[i].values))
        for b in range(len(BIG[j].values))
        if (i, a, j, b) not in found
    ]
    assert missing == []


def test_the_row_values_come_back_as_words_not_indices():
    matrix = build_matrix(LOGIN, [])
    for row in matrix.rows:
        assert row[0] in LOGIN[0].values
        assert row[1] in LOGIN[1].values
        assert row[2] in LOGIN[2].values


# --------------------------------------------------------------------- rules


def test_a_rule_keeps_the_pair_out_of_every_row():
    matrix = build_matrix(LOGIN, [NO_SAFARI_ON_ANDROID])
    assert not breaks(matrix, NO_SAFARI_ON_ANDROID)
    assert matrix.impossible_pairs == (("Browser", "Safari", "OS", "Android"),)
    assert matrix.covered_pairs == matrix.valid_pairs


def test_a_rule_lowers_the_pair_count_by_exactly_one_pair():
    free = build_matrix(LOGIN, [])
    ruled = build_matrix(LOGIN, [NO_SAFARI_ON_ANDROID])
    assert ruled.valid_pairs == free.valid_pairs - 1


def test_a_rule_is_symmetric():
    """"Safari never with Android" also means "Android never with Safari"."""
    backwards = Rule("OS", "Android", "Browser", "Safari")
    matrix = build_matrix(LOGIN, [backwards])
    assert not breaks(matrix, NO_SAFARI_ON_ANDROID)


def test_the_valid_combination_count_drops_with_a_rule():
    free = build_matrix(LOGIN, [])
    ruled = build_matrix(LOGIN, [NO_SAFARI_ON_ANDROID])
    assert free.valid_combinations == 18
    assert ruled.valid_combinations == 16  # the two Safari/Android rows go


def test_a_huge_space_does_not_get_counted_one_by_one():
    matrix = build_matrix(grid(8, 8), [])
    assert matrix.all_combinations == 8**8
    assert matrix.valid_combinations is None


# ---------------------------------------------------------------- validation


def test_a_matrix_needs_two_factors():
    assert validate([Factor("Browser", ("Chrome", "Safari"))], []) == [
        "A matrix needs at least 2 factors."
    ]


def test_a_factor_needs_two_values():
    problems = validate(
        [Factor("Device", ("Desktop",)), Factor("Browser", ("Chrome", "Safari"))], []
    )
    assert "Factor 'Device' needs at least 2 values." in problems


def test_repeated_names_and_values_are_refused():
    problems = validate(
        [
            Factor("Browser", ("Chrome", "chrome")),
            Factor("browser", ("Desktop", "Phone")),
        ],
        [],
    )
    assert "There are two factors called 'browser'." in problems
    assert "Factor 'Browser' lists the same value twice." in problems


def test_an_empty_or_overlong_name_is_refused():
    problems = validate(
        [Factor("  ", ("a", "b")), Factor("B" * 41, ("a", "b"))], []
    )
    assert "Every factor needs a name." in problems
    assert any("longer than 40 characters" in one for one in problems)


def test_a_rule_about_an_unknown_factor_is_refused():
    problems = validate(LOGIN, [Rule("Planet", "Mars", "Browser", "Chrome")])
    assert "Rule mentions 'Planet', which is not a factor." in problems


def test_a_rule_about_an_unknown_value_is_refused():
    problems = validate(LOGIN, [Rule("Browser", "Netscape", "OS", "Windows")])
    assert any("Netscape" in one for one in problems)


def test_a_rule_cannot_point_a_factor_at_itself():
    problems = validate(LOGIN, [Rule("Browser", "Chrome", "Browser", "Safari")])
    assert "A rule cannot point 'Browser' at itself." in problems


def test_rules_that_leave_a_value_nowhere_to_go_are_refused_not_looped():
    """Three rules can block every OS for Safari; that must be an error."""
    rules = [
        Rule("Browser", "Safari", "OS", "Windows"),
        Rule("Browser", "Safari", "OS", "Android"),
        Rule("Browser", "Safari", "OS", "macOS"),
    ]
    problems = validate(LOGIN, rules)
    assert "No value of 'OS' is allowed with 'Browser = Safari'." in problems


def test_too_many_rules_are_refused():
    rules = [Rule("Browser", "Chrome", "OS", "Windows")] * 41
    assert "Keep it to 40 rules or fewer." in validate(LOGIN, rules)


def test_too_many_factors_are_refused():
    assert "Keep it to 8 factors or fewer." in validate(grid(9, 2), [])


def test_a_workable_set_has_no_problems():
    assert validate(LOGIN, [NO_SAFARI_ON_ANDROID]) == []


# ------------------------------------------------------------------- pinning


def test_a_pinned_row_comes_first_and_coverage_still_completes():
    pinned = [{"Browser": "Chrome", "OS": "Windows", "Device": "Desktop"}]
    matrix = build_matrix(LOGIN, [], pinned)
    assert matrix.rows[0] == ("Chrome", "Windows", "Desktop")
    assert matrix.pinned_rows == 1
    assert matrix.covered_pairs == matrix.valid_pairs


def test_a_pinned_row_that_misses_a_factor_is_refused():
    with pytest.raises(ValueError, match="every factor"):
        build_matrix(LOGIN, [], [{"Browser": "Chrome"}])


def test_a_pinned_row_that_breaks_a_rule_is_refused():
    pinned = [{"Browser": "Safari", "OS": "Android", "Device": "Phone"}]
    with pytest.raises(ValueError, match="breaks one of your rules"):
        build_matrix(LOGIN, [NO_SAFARI_ON_ANDROID], pinned)


# ------------------------------------------------------- determinism & speed


def test_the_same_input_gives_the_same_rows():
    first = build_matrix(BIG, [])
    second = build_matrix(BIG, [])
    assert first.rows == second.rows


def test_eight_factors_of_eight_values_finish_quickly():
    start = time.time()
    matrix = build_matrix(grid(8, 8), [])
    assert time.time() - start < 1.0
    assert matrix.covered_pairs == matrix.valid_pairs


def test_every_row_is_allowed_across_many_small_inputs():
    """A property test: whatever the shape, no row may break a rule."""
    rng = random.Random(20260117)
    for _ in range(50):
        count = rng.randint(2, 5)
        factors = [
            Factor(f"F{i + 1}", tuple(f"v{j + 1}" for j in range(rng.randint(2, 4))))
            for i in range(count)
        ]
        rules = []
        for _ in range(rng.randint(0, 2)):
            i, j = rng.sample(range(count), 2)
            rules.append(
                Rule(
                    factors[i].name,
                    rng.choice(factors[i].values),
                    factors[j].name,
                    rng.choice(factors[j].values),
                )
            )
        if validate(factors, rules):
            continue
        matrix = build_matrix(factors, rules)
        for rule in rules:
            assert not breaks(matrix, rule), (factors, rules)
        assert matrix.covered_pairs == matrix.valid_pairs, (factors, rules)
        assert len(matrix.rows) <= matrix.all_combinations


def test_the_attempt_limit_is_small_enough_to_never_hang():
    assert MAX_ATTEMPTS <= 200


# ── how many pairs each run is the first to cover ────────────────────────────


def test_new_pairs_adds_up_to_every_pair_covered() -> None:
    """A pair belongs to the first run that covers it, and to only one run."""
    matrix = build_matrix(
        [
            Factor("Browser", ("Chrome", "Firefox", "Safari")),
            Factor("Device", ("Desktop", "Phone")),
            Factor("Role", ("Guest", "Member", "Admin")),
        ],
        [],
    )
    assert len(matrix.new_pairs) == len(matrix.rows)
    assert sum(matrix.new_pairs) == matrix.covered_pairs
    assert matrix.covered_pairs == matrix.valid_pairs


def test_the_first_run_covers_the_most() -> None:
    matrix = build_matrix(
        [
            Factor("Browser", ("Chrome", "Firefox")),
            Factor("Device", ("Desktop", "Phone")),
            Factor("Role", ("Guest", "Member")),
        ],
        [],
    )
    assert matrix.new_pairs[0] == max(matrix.new_pairs)
    assert matrix.new_pairs[0] == 3  # three factors, three pairs in one row


def test_a_run_that_covers_nothing_new_says_zero() -> None:
    """A pinned run the rest already covers still shows up, honestly at 0."""
    factors = [
        Factor("Browser", ("Chrome", "Firefox")),
        Factor("Device", ("Desktop", "Phone")),
    ]
    matrix = build_matrix(
        factors,
        [],
        pinned=[
            {"Browser": "Chrome", "Device": "Desktop"},
            {"Browser": "Chrome", "Device": "Desktop"},
        ],
    )
    assert matrix.new_pairs[0] == 1
    assert matrix.new_pairs[1] == 0
    assert sum(matrix.new_pairs) == matrix.covered_pairs


def test_an_impossible_pair_is_never_counted_as_new() -> None:
    matrix = build_matrix(
        [
            Factor("Browser", ("Chrome", "Safari")),
            Factor("Device", ("Desktop", "Phone")),
        ],
        [Rule("Browser", "Safari", "Device", "Desktop")],
    )
    assert sum(matrix.new_pairs) == matrix.valid_pairs
