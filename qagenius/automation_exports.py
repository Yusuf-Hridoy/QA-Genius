"""Pack a generated automation project, and what the checks found, into a ZIP."""

import io
import zipfile

from qagenius.automation_checks import CheckReport, safe_file_name
from qagenius.models import AutomationScript

TOP_FOLDER = "qa-genius-automation"
BASIC_CHECK_NOTE = (
    "Python is parsed; TypeScript/JavaScript get a basic bracket and quote check, "
    "not a full compile."
)


def _traceability_lines(report: CheckReport) -> list[str]:
    total = len(report.traced) + len(report.missing)
    lines = [
        "### Traceability",
        "",
        f"{len(report.traced)} of {total} selected test cases have a matching test.",
        "",
    ]
    if report.traced:
        lines += [f"- Found: {', '.join(report.traced)}", ""]
    for missing_id in report.missing:
        lines.append(f"- No test mentions {missing_id}")
    if report.missing:
        lines.append("")
    return lines


def _syntax_lines(report: CheckReport) -> list[str]:
    lines = ["### Syntax", ""]
    for file in report.files:
        lines.append(f"- {file.name} — {report.syntax.get(file.name, 'not checked')}")
    lines += ["", BASIC_CHECK_NOTE, ""]
    return lines


def _finding_lines(report: CheckReport) -> list[str]:
    lines = ["### Warnings and errors", ""]
    if not report.findings:
        lines += ["None.", ""]
        return lines
    for finding in report.findings:
        where = f"{finding.file}:{finding.line}" if finding.line else finding.file
        lines.append(f"- {finding.level}: {where} — {finding.message}")
    lines.append("")
    return lines


def build_readme(script: AutomationScript, report: CheckReport) -> str:
    """The README that ships inside the ZIP."""
    lines = [
        "# QA-Genius automation",
        "",
        f"Framework: {script.framework}",
        "",
        "## Setup",
        "",
    ]
    for number, instruction in enumerate(script.setup_instructions, start=1):
        lines.append(f"{number}. {instruction}")
    lines += ["", "## Run it", "", "```", script.execution_command, "```", ""]
    if (script.design_notes or "").strip():
        lines += ["## Design notes", "", script.design_notes.strip(), ""]
    lines += ["## Checks", "", "QA-Genius worked these out from the code, without AI.", ""]
    lines += _traceability_lines(report)
    lines += _syntax_lines(report)
    lines += _finding_lines(report)
    return "\n".join(lines)


def build_zip(script: AutomationScript, report: CheckReport) -> bytes:
    """The project as a ZIP, every file under one top folder, plus a README."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in report.files:
            # project_files already cleaned these; never write a name that did not pass.
            assert safe_file_name(file.name) == file.name
            archive.writestr(f"{TOP_FOLDER}/{file.name}", file.code)
        archive.writestr(f"{TOP_FOLDER}/README.md", build_readme(script, report))
    return buffer.getvalue()
