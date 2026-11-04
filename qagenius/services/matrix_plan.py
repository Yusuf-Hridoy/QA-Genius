"""The fewest runs that still put every allowed pair of values together.

No AI. Whoever asks names the factors and what cannot go with what; the
arithmetic is the same pairwise builder the Test matrix page uses, so the
website and an agent plan the same runs for the same factors.
"""

from dataclasses import dataclass, field

from qagenius.pairwise import Factor, Matrix, Rule, build_matrix, validate
from qagenius.test_matrix_defaults import playwright_project

# A run Playwright cannot drive is still a run somebody has to do; it is
# marked rather than dropped, and this is why.
MANUAL_REASON = (
    "Playwright has no device profile for this browser and device together, "
    "so this run is done by hand."
)


@dataclass(frozen=True)
class Run:
    """One row of the matrix: one value per factor, and what it is worth."""

    values: dict[str, str]
    # How many pairs this run is the first to cover. The numbers add up to
    # pairs_covered, so a reader can see why a run is in the list at all.
    new_pairs: int = 0
    manual_only: bool = False
    manual_reason: str = ""


@dataclass(frozen=True)
class MatrixPlan:
    """A planned matrix, or the reasons it could not be planned."""

    # Said in the words of whoever asked, when the input cannot be built.
    problems: list[str] = field(default_factory=list)
    matrix: Matrix | None = None
    runs: list[Run] = field(default_factory=list)
    combinations: int = 0
    pairs_possible: int = 0
    pairs_covered: int = 0
    impossible_pairs: list[tuple[str, str, str, str]] = field(default_factory=list)
    manual_only: int = 0
    summary: str = ""


def _summary(plan_runs: int, combinations: int, covered: int, possible: int) -> str:
    """"216 combinations → 16 runs, 85 of 85 pairs.\""""
    runs = "1 run" if plan_runs == 1 else f"{plan_runs} runs"
    return (
        f"{combinations:,} combinations → {runs}, "
        f"{covered} of {possible} pairs."
    )


def plan_matrix(
    factors: list[Factor],
    rules: list[Rule] | None = None,
    pinned: list[dict[str, str]] | None = None,
) -> MatrixPlan:
    """Plan the runs. Anything wrong with the input comes back as words.

    A bad set of factors is not an error: it is a list of things to fix,
    in the same shape as everything else this engine answers with.
    """
    rules = list(rules or [])
    problems = validate(factors, rules)
    if problems:
        return MatrixPlan(problems=problems)

    matrix = build_matrix(factors, rules, pinned)
    names = [factor.name for factor in matrix.factors]
    runs: list[Run] = []
    for index, row in enumerate(matrix.rows):
        values = dict(zip(names, row))
        project = playwright_project(values)
        manual = bool(project.get("manual_only"))
        runs.append(
            Run(
                values=values,
                new_pairs=(
                    matrix.new_pairs[index] if index < len(matrix.new_pairs) else 0
                ),
                manual_only=manual,
                manual_reason=MANUAL_REASON if manual else "",
            )
        )

    return MatrixPlan(
        matrix=matrix,
        runs=runs,
        combinations=matrix.all_combinations,
        pairs_possible=matrix.valid_pairs,
        pairs_covered=matrix.covered_pairs,
        impossible_pairs=[tuple(pair) for pair in matrix.impossible_pairs],
        manual_only=sum(1 for run in runs if run.manual_only),
        summary=_summary(
            len(runs),
            matrix.all_combinations,
            matrix.covered_pairs,
            matrix.valid_pairs,
        ),
    )
