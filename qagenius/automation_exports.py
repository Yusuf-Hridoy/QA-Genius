"""Pack a generated automation project, and what the checks found, into a ZIP."""

import io
import re
import zipfile

from qagenius.automation_checks import CheckReport, ProjectFile, safe_file_name
from qagenius.models import AutomationScript

TOP_FOLDER = "qa-genius-automation"
BASIC_CHECK_NOTE = (
    "Python is parsed; TypeScript/JavaScript get a basic bracket and quote check, "
    "not a full compile."
)

# One line, because a tester on Windows needs the other half of it.
ACTIVATE = r"source .venv/bin/activate  # Windows: .venv\Scripts\activate"


def _is_typescript(files: list[ProjectFile]) -> bool:
    """The language the project was written in, read off its own file names.

    AutomationScript has no language field, and the AI's framework string says
    "Playwright (JavaScript)" even for a TypeScript project.
    """
    return any(file.name.endswith((".ts", ".tsx")) for file in files)


def run_steps(script: AutomationScript, files: list[ProjectFile]) -> list[str]:
    """How to run the project that was actually downloaded.

    A real run told the user to `mkdir aurora-automation && npm init -y`, which
    builds an empty project beside the one they just unzipped. These steps are
    computed from the framework and the files in the ZIP, never from the AI.
    """
    framework = (script.framework or "").lower()
    names = {file.name for file in files}
    steps = [f"cd {TOP_FOLDER}"]

    if "python" in framework:
        steps.append("python -m venv .venv")
        steps.append(ACTIVATE)
        if "requirements.txt" in names:
            steps.append("pip install -r requirements.txt")
        elif "selenium" in framework:
            steps.append("pip install pytest selenium")
        else:
            steps.append("pip install pytest pytest-playwright")
        if "selenium" not in framework:
            steps.append("playwright install")
        steps.append("pytest")
        return steps

    if "cypress" in framework:
        if "package.json" in names:
            steps.append("npm install")
        else:
            steps.append("npm init -y && npm install -D cypress")
        steps.append("npx cypress run")
        return steps

    # Playwright on Node, whichever language the tests are written in.
    if "package.json" in names:
        steps.append("npm install")
    else:
        extra = " typescript" if _is_typescript(files) else ""
        steps.append(f"npm init -y && npm install -D @playwright/test{extra}")
    steps.append("npx playwright install")
    steps.append("npx playwright test")
    return steps


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


# What an AI note is about when it contradicts the run steps above it: it
# builds a second, empty project beside the one that was just unzipped, or
# moves into a folder that is not there. A real run told the reader to
# `mkdir aurora-automation && npm init -y` directly under steps that say to
# cd into the folder and npm install.
_CONFLICTS_WITH_STEPS = ("mkdir", "npm init", "yarn init", "pnpm init", "git clone")
_WRONG_FOLDER = re.compile(r"(?<![\w-])cd\s+(?!" + re.escape(TOP_FOLDER) + r"\b)\S", re.IGNORECASE)


def useful_notes(instructions: list[str]) -> list[str]:
    """The AI's setup notes, minus the ones the real run steps disprove."""
    kept = []
    for instruction in instructions or []:
        said = str(instruction or "")
        lowered = said.lower()
        if any(word in lowered for word in _CONFLICTS_WITH_STEPS):
            continue
        if _WRONG_FOLDER.search(said):
            continue
        kept.append(said)
    return kept


def build_readme(script: AutomationScript, report: CheckReport) -> str:
    """The README that ships inside the ZIP."""
    lines = [
        "# QA-Genius automation",
        "",
        f"Framework: {script.framework}",
        "",
        "## Run it",
        "",
        "```",
    ]
    lines += run_steps(script, report.files)
    lines += ["```", ""]
    notes = useful_notes(script.setup_instructions)
    if notes:
        lines += ["### Notes from the AI", ""]
        for number, instruction in enumerate(notes, start=1):
            lines.append(f"{number}. {instruction}")
        lines.append("")
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
