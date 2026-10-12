"""Write the scored risks out as a CSV or an FMEA workbook."""

import csv
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from qagenius.risk_radar import RiskReport, ScoredRisk
from qagenius.test_case_exports import safe_cell

COLUMNS = (
    "ID",
    "Failure mode",
    "Category",
    "Effect",
    "Cause",
    "Severity",
    "Likelihood",
    "Detectability",
    "RPN",
    "Level",
    "Coverage",
    "Covered by",
    "Related criteria",
    "Test idea",
    "Severity reason",
    "Likelihood reason",
    "Detectability reason",
)

HEAT_SHEET = "Heat map"
REGISTER_SHEET = "Risk register"

LEVEL_FILLS = {
    "high": PatternFill("solid", fgColor="F7DEDA"),
    "medium": PatternFill("solid", fgColor="F6E9CF"),
    "low": PatternFill("solid", fgColor="DDEBE3"),
}

_WIDTHS = {
    "ID": 8,
    "Failure mode": 40,
    "Effect": 44,
    "Cause": 40,
    "Test idea": 44,
    "Severity reason": 30,
    "Likelihood reason": 30,
    "Detectability reason": 30,
    "Covered by": 22,
    "Related criteria": 18,
}
_DEFAULT_WIDTH = 14
_WRAP_COLUMNS = (
    "Failure mode",
    "Effect",
    "Cause",
    "Test idea",
    "Severity reason",
    "Likelihood reason",
    "Detectability reason",
)
# Columns Excel should treat as numbers, not text.
_NUMBER_COLUMNS = ("Severity", "Likelihood", "Detectability", "RPN")


def _row(item: ScoredRisk) -> list:
    risk = item.risk
    return [
        safe_cell(risk.id),
        safe_cell(risk.title),
        safe_cell(risk.category),
        safe_cell(risk.effect),
        safe_cell(risk.cause),
        risk.severity,
        risk.likelihood,
        risk.detectability,
        item.rpn,
        safe_cell(item.level),
        safe_cell(item.coverage),
        safe_cell(", ".join(case_id for case_id, _, _ in item.covered_tests)),
        safe_cell(", ".join(risk.related_criteria)),
        safe_cell(risk.test_idea),
        safe_cell(risk.severity_reason),
        safe_cell(risk.likelihood_reason),
        safe_cell(risk.detectability_reason),
    ]


def to_csv(report: RiskReport) -> bytes:
    """UTF-8 with a BOM, so Excel opens it without an import step."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for item in report.risks:
        writer.writerow(_row(item))
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def _write_register_sheet(sheet, report: RiskReport) -> None:
    sheet.append(list(COLUMNS))
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    sheet.freeze_panes = "A2"
    for index, name in enumerate(COLUMNS, start=1):
        letter = get_column_letter(index)
        sheet.column_dimensions[letter].width = _WIDTHS.get(name, _DEFAULT_WIDTH)
    level_column = COLUMNS.index("Level") + 1
    for item in report.risks:
        sheet.append(_row(item))
        fill = LEVEL_FILLS.get(item.level)
        if fill is not None:
            sheet.cell(row=sheet.max_row, column=level_column).fill = fill
    wrap = Alignment(wrap_text=True, vertical="top")
    for name in _WRAP_COLUMNS:
        letter = get_column_letter(COLUMNS.index(name) + 1)
        for row in range(2, sheet.max_row + 1):
            sheet[f"{letter}{row}"].alignment = wrap
    centre = Alignment(horizontal="center")
    for name in _NUMBER_COLUMNS:
        letter = get_column_letter(COLUMNS.index(name) + 1)
        for row in range(2, sheet.max_row + 1):
            sheet[f"{letter}{row}"].alignment = centre


def _write_heat_sheet(sheet, report: RiskReport) -> None:
    """Severity down the side, 5 at the top; likelihood across the bottom."""
    sheet.append(["Severity \ Likelihood"] + [f"L{n}" for n in range(1, 6)])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    sheet.column_dimensions["A"].width = 22
    for severity in range(5, 0, -1):
        ids = [
            ", ".join(report.heatmap.get((severity, likelihood), []))
            for likelihood in range(1, 6)
        ]
        sheet.append([f"S{severity}"] + [safe_cell(value) for value in ids])
        sheet.cell(row=sheet.max_row, column=1).font = Font(bold=True)
    for column in range(2, 7):
        sheet.column_dimensions[get_column_letter(column)].width = 16


def to_xlsx(report: RiskReport) -> bytes:
    """A workbook with the register and the heat map it is drawn from."""
    book = Workbook()
    register = book.active
    register.title = REGISTER_SHEET
    _write_register_sheet(register, report)
    _write_heat_sheet(book.create_sheet(HEAT_SHEET), report)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()
