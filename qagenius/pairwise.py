"""All-pairs (pairwise) test matrix: fewest rows covering every valid pair of values.

Most bugs that depend on the environment need only two things to coincide --
Safari *and* a phone, Arabic *and* a right-to-left layout -- so a set of runs
where every pair of values appears together at least once finds them without
running all 324 combinations.

Everything here is arithmetic. The AI may propose which factors matter; the
rows, the counts and the coverage proof are computed, and the same input always
produces the same output.
"""

import itertools
from dataclasses import dataclass

MIN_FACTORS, MAX_FACTORS = 2, 8
MIN_VALUES, MAX_VALUES = 2, 10
MAX_RULES = 40
MAX_NAME = 40
# Above this, counting the valid combinations one by one is not worth the wait.
COUNT_LIMIT = 200_000
# A single row never explores more than this many choices before giving up.
MAX_ATTEMPTS = 200


@dataclass(frozen=True)
class Factor:
    name: str  # "Browser"
    values: tuple[str, ...]  # ("Chrome", "Firefox", "Safari")


@dataclass(frozen=True)
class Rule:
    """<if_factor> = <if_value> never with <then_factor> = <then_value>."""

    if_factor: str
    if_value: str
    then_factor: str
    then_value: str
    reason: str = ""
    # "standard" (a fact about the tools) or "ai" (a guess worth checking).
    source: str = "standard"


@dataclass(frozen=True)
class Matrix:
    factors: tuple[Factor, ...]
    rows: tuple[tuple[str, ...], ...]  # one value per factor, in factor order
    all_combinations: int
    valid_combinations: int | None  # exact below COUNT_LIMIT, else None
    valid_pairs: int
    covered_pairs: int  # must equal valid_pairs for any workable input
    impossible_pairs: tuple[tuple[str, str, str, str], ...]
    pinned_rows: int


# ──────────────────────────────────────────────────────────────────────────────
# Validation: everything a user could get wrong, said in their words
# ──────────────────────────────────────────────────────────────────────────────


def _clean(text: str) -> str:
    return " ".join(str(text or "").split())


def validate(factors: list[Factor], rules: list[Rule]) -> list[str]:
    """Problems to show the user. An empty list means the matrix can be built."""
    problems: list[str] = []

    if len(factors) < MIN_FACTORS:
        problems.append(f"A matrix needs at least {MIN_FACTORS} factors.")
    if len(factors) > MAX_FACTORS:
        problems.append(f"Keep it to {MAX_FACTORS} factors or fewer.")

    seen_names: dict[str, str] = {}
    for factor in factors:
        name = _clean(factor.name)
        if not name:
            problems.append("Every factor needs a name.")
            continue
        if len(name) > MAX_NAME:
            problems.append(f"Factor name '{name[:20]}…' is longer than {MAX_NAME} characters.")
        if name.lower() in seen_names:
            problems.append(f"There are two factors called '{name}'.")
        seen_names[name.lower()] = name

        values = [_clean(value) for value in factor.values]
        if any(not value for value in values):
            problems.append(f"Factor '{name}' has an empty value.")
        if len(values) < MIN_VALUES:
            problems.append(f"Factor '{name}' needs at least {MIN_VALUES} values.")
        if len(values) > MAX_VALUES:
            problems.append(f"Factor '{name}' has more than {MAX_VALUES} values.")
        if any(len(value) > MAX_NAME for value in values):
            problems.append(f"Factor '{name}' has a value longer than {MAX_NAME} characters.")
        lowered = [value.lower() for value in values if value]
        if len(set(lowered)) != len(lowered):
            problems.append(f"Factor '{name}' lists the same value twice.")

    if len(rules) > MAX_RULES:
        problems.append(f"Keep it to {MAX_RULES} rules or fewer.")

    by_name = {_clean(factor.name).lower(): factor for factor in factors}
    for rule in rules:
        left, right = _clean(rule.if_factor), _clean(rule.then_factor)
        if left.lower() == right.lower():
            problems.append(f"A rule cannot point '{left}' at itself.")
            continue
        for factor_name, value in ((left, rule.if_value), (right, rule.then_value)):
            found = by_name.get(factor_name.lower())
            if found is None:
                problems.append(f"Rule mentions '{factor_name}', which is not a factor.")
                continue
            values = {_clean(one).lower() for one in found.values}
            if _clean(value).lower() not in values:
                problems.append(
                    f"Rule mentions '{factor_name} = {_clean(value)}', "
                    f"which is not one of its values."
                )

    if problems:
        return problems

    # Rules that leave a value with nowhere to go would send the search round
    # in circles, so they are refused here rather than hit at build time.
    blocked = _blocked_pairs(factors, rules)
    for i, factor in enumerate(factors):
        for a, value in enumerate(factor.values):
            for j, other in enumerate(factors):
                if i == j:
                    continue
                low, high = (i, j) if i < j else (j, i)
                open_values = [
                    b
                    for b in range(len(other.values))
                    if ((low, a if i < j else b, high, b if i < j else a)) not in blocked
                ]
                if not open_values:
                    problems.append(
                        f"No value of '{_clean(other.name)}' is allowed with "
                        f"'{_clean(factor.name)} = {_clean(value)}'."
                    )
    return problems


# ──────────────────────────────────────────────────────────────────────────────
# The matrix
# ──────────────────────────────────────────────────────────────────────────────


def _blocked_pairs(factors: list[Factor], rules: list[Rule]) -> set[tuple[int, int, int, int]]:
    """Pairs a rule forbids, as (factor i, value a, factor j, value b) with i < j.

    Rules are symmetric: "Safari never with Android" forbids both orders.
    """
    index = {_clean(factor.name).lower(): i for i, factor in enumerate(factors)}
    values = [
        {_clean(value).lower(): a for a, value in enumerate(factor.values)}
        for factor in factors
    ]
    blocked: set[tuple[int, int, int, int]] = set()
    for rule in rules:
        i = index.get(_clean(rule.if_factor).lower())
        j = index.get(_clean(rule.then_factor).lower())
        if i is None or j is None or i == j:
            continue
        a = values[i].get(_clean(rule.if_value).lower())
        b = values[j].get(_clean(rule.then_value).lower())
        if a is None or b is None:
            continue
        blocked.add((i, a, j, b) if i < j else (j, b, i, a))
    return blocked


def _all_pairs(factors: list[Factor]) -> list[tuple[int, int, int, int]]:
    pairs = []
    for i in range(len(factors)):
        for j in range(i + 1, len(factors)):
            for a in range(len(factors[i].values)):
                for b in range(len(factors[j].values)):
                    pairs.append((i, a, j, b))
    return pairs


def _pair_key(i: int, a: int, j: int, b: int) -> tuple[int, int, int, int]:
    return (i, a, j, b) if i < j else (j, b, i, a)


def _row_allowed(row: list[int | None], blocked: set) -> bool:
    chosen = [(i, value) for i, value in enumerate(row) if value is not None]
    for (i, a), (j, b) in itertools.combinations(chosen, 2):
        if _pair_key(i, a, j, b) in blocked:
            return False
    return True


def _value_ok(row: list[int | None], k: int, vi: int, blocked: set) -> bool:
    for i, value in enumerate(row):
        if value is None or i == k:
            continue
        if _pair_key(i, value, k, vi) in blocked:
            return False
    return True


def _count_valid(factors: list[Factor], blocked: set) -> int | None:
    total = 1
    for factor in factors:
        total *= len(factor.values)
    if total > COUNT_LIMIT:
        return None
    ranges = [range(len(factor.values)) for factor in factors]
    return sum(
        1 for combo in itertools.product(*ranges) if _row_allowed(list(combo), blocked)
    )


def _fill_row(
    row: list[int | None],
    free: list[int],
    position: int,
    factors: list[Factor],
    blocked: set,
    uncovered: set,
    attempts: list[int],
) -> bool:
    """Depth-first fill, best-covering value first, backtracking when stuck."""
    if position == len(free):
        return True
    k = free[position]
    options: list[tuple[int, int]] = []
    for vi in range(len(factors[k].values)):
        if not _value_ok(row, k, vi, blocked):
            continue
        gain = sum(
            1
            for i, value in enumerate(row)
            if value is not None and _pair_key(i, value, k, vi) in uncovered
        )
        options.append((-gain, vi))  # most new pairs first, then lowest index
    options.sort()
    for _, vi in options:
        attempts[0] += 1
        if attempts[0] > MAX_ATTEMPTS:
            return False
        row[k] = vi
        if _fill_row(row, free, position + 1, factors, blocked, uncovered, attempts):
            return True
        row[k] = None
    return False


def _covered_by(row: tuple[int, ...]) -> set[tuple[int, int, int, int]]:
    return {
        (i, row[i], j, row[j])
        for i in range(len(row))
        for j in range(i + 1, len(row))
    }


def _pinned_rows(
    factors: list[Factor], pinned: list[dict[str, str]] | None, blocked: set
) -> list[tuple[int, ...]]:
    """The rows the user forced in, as value indices. Raises on a bad one."""
    if not pinned:
        return []
    index = {_clean(factor.name).lower(): i for i, factor in enumerate(factors)}
    values = [
        {_clean(value).lower(): a for a, value in enumerate(factor.values)}
        for factor in factors
    ]
    rows: list[tuple[int, ...]] = []
    for entry in pinned:
        row: list[int | None] = [None] * len(factors)
        for name, value in (entry or {}).items():
            i = index.get(_clean(name).lower())
            if i is None:
                continue
            a = values[i].get(_clean(value).lower())
            if a is not None:
                row[i] = a
        if any(value is None for value in row):
            raise ValueError("A pinned run has to name a value for every factor.")
        if not _row_allowed(row, blocked):
            raise ValueError("A pinned run breaks one of your rules.")
        rows.append(tuple(value for value in row if value is not None))
    return rows


def build_matrix(
    factors: list[Factor],
    rules: list[Rule],
    pinned: list[dict[str, str]] | None = None,
) -> Matrix:
    """The fewest rows that still put every allowed pair of values together."""
    factors = list(factors)
    blocked = _blocked_pairs(factors, list(rules))

    all_pairs = _all_pairs(factors)
    impossible = sorted(pair for pair in all_pairs if pair in blocked)
    uncovered = {pair for pair in all_pairs if pair not in blocked}
    valid_pairs = len(uncovered)

    rows: list[tuple[int, ...]] = _pinned_rows(factors, pinned, blocked)
    pinned_count = len(rows)
    for row in rows:
        uncovered -= _covered_by(row)

    # One row per seed pair, each row filled to cover as much else as it can.
    while uncovered:
        i, a, j, b = min(uncovered)
        row: list[int | None] = [None] * len(factors)
        row[i], row[j] = a, b
        # Fill the factor with the most left to cover first: it has the widest
        # choice while the row is still empty, and that is worth a row or two
        # over filling in declaration order. Ties keep factor order, so the
        # result stays the same for the same input.
        free = sorted(
            (k for k in range(len(factors)) if k not in (i, j)),
            key=lambda k: (
                -sum(1 for pair in uncovered if pair[0] == k or pair[2] == k),
                k,
            ),
        )
        if not _fill_row(row, free, 0, factors, blocked, uncovered, [0]):
            # Only reachable with contradictory rules, which validate() refuses.
            uncovered.discard((i, a, j, b))
            continue
        filled = tuple(value for value in row if value is not None)
        rows.append(filled)
        uncovered -= _covered_by(filled)

    total = 1
    for factor in factors:
        total *= len(factor.values)

    covered = {pair for row in rows for pair in _covered_by(row)} - blocked
    return Matrix(
        factors=tuple(factors),
        rows=tuple(
            tuple(factors[i].values[value] for i, value in enumerate(row)) for row in rows
        ),
        all_combinations=total,
        valid_combinations=_count_valid(factors, blocked),
        valid_pairs=valid_pairs,
        covered_pairs=len(covered),
        impossible_pairs=tuple(
            (
                factors[i].name,
                factors[i].values[a],
                factors[j].name,
                factors[j].values[b],
            )
            for i, a, j, b in impossible
        ),
        pinned_rows=pinned_count,
    )
