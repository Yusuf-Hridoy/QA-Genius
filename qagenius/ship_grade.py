"""One letter for a Ship check report, worked out by code.

The grade is arithmetic on checks that ran. It adds nothing to the decision
and never overrules it -- it is a shorthand for "how much of what we checked
came back fine", so a reader can compare two releases at a glance.

Two rules keep it honest:

* a check that never ran scores nothing and is not counted against you, so
  a release with one check run is not graded as if six had failed;
* a release the rules call Not ready cannot be graded above D, whatever the
  arithmetic says. A grade that disagrees with the decision is worse than
  no grade at all.
"""

from __future__ import annotations

from dataclasses import dataclass

from qagenius.ship_check import ShipReport

# What one check is worth. A check nobody ran is not in here at all.
POINTS = {"pass": 2, "warn": 1, "accepted": 1, "fail": 0}
MOST_PER_CHECK = 2

# The same words the page uses for a status, so the explanation reads like
# the row it explains.
WORDS = {
    "pass": "fine",
    "warn": "check this",
    "accepted": "accepted",
    "fail": "needs fixing",
}

# Band floors, best first.
BANDS = (("A", 90), ("B", 80), ("C", 70), ("D", 60))
CAP_LETTER = "D"
CAP_LINE = "Capped at D because the decision is Not ready."


@dataclass(frozen=True)
class Grade:
    letter: str          # "A+", "A", "A-", ... "F"
    points: int
    max_points: int
    percent: int
    capped: bool         # True when lowered because the decision is "Not ready"
    lines: list[str]     # plain-words explanation, one line per check


def letter_for(percent: int) -> str:
    """The band, and where in the band: top third is +, bottom third is -."""
    for letter, floor in BANDS:
        if percent >= floor:
            inside = percent - floor
            if inside >= 7:
                return letter + "+"
            if inside >= 3:
                return letter
            return letter + "-"
    return "F"


def grade_for(report: ShipReport) -> Grade | None:
    """The grade for a report, or None when no check ran."""
    scored = [item for item in report.items if item.status in POINTS]
    if not scored:
        return None

    points = sum(POINTS[item.status] for item in scored)
    max_points = len(scored) * MOST_PER_CHECK
    percent = round(points / max_points * 100)
    lines = [
        f"{item.title}: {WORDS[item.status]} "
        f"({POINTS[item.status]} of {MOST_PER_CHECK})"
        for item in scored
    ]

    letter = letter_for(percent)
    capped = False
    if report.verdict == "dont_ship" and percent >= 70:
        letter = CAP_LETTER
        capped = True
        lines.append(CAP_LINE)

    return Grade(
        letter=letter,
        points=points,
        max_points=max_points,
        percent=percent,
        capped=capped,
        lines=lines,
    )
