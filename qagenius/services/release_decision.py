"""The release verdict, and the letter beside it.

Both already live in code with no AI anywhere near them. This module is the
one place either door asks for them, so Ship check on the website and
ship_check over MCP can never disagree about the same inputs.
"""

from qagenius.ship_check import ShipInputs, ShipReport, compute_ship_report
from qagenius.ship_grade import Grade, grade_for

__all__ = ["ShipInputs", "ShipReport", "Grade", "decide_release", "release_grade"]


def decide_release(inputs: ShipInputs) -> ShipReport:
    """The whole verdict for one release, from code alone."""
    return compute_ship_report(inputs)


def release_grade(report: ShipReport) -> Grade | None:
    """The letter for a report, or None when no check ran at all."""
    return grade_for(report)
