"""Checks on generated automation code, computed without AI."""

import ast
import json
import re
from dataclasses import dataclass

from qagenius.models import AutomationScript

JS_SUFFIXES = (".ts", ".js", ".tsx", ".jsx", ".mjs", ".cjs")

# A path part the ZIP is allowed to carry.
_PART = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_MAX_PARTS = 3

# A test case id split into its prefix and number, e.g. TC-001 -> TC, 001.
_ID_PARTS = re.compile(r"^([A-Za-z]+)[-_ ]?(\d+)$")

# Fixed waits the generated code should not contain.
_WAIT_PATTERNS = (
    re.compile(r"waitForTimeout\s*\("),
    re.compile(r"\btime\.sleep\s*\("),
    re.compile(r"\bcy\.wait\s*\(\s*\d"),
    re.compile(r"Thread\.sleep\s*\("),
)
WAIT_MESSAGE = "Fixed wait — prefer waiting for an element or response"

_CLOSERS = {")": "(", "]": "[", "}": "{"}

_BACKTICK = "`"

# After one of these, a / opens a regex literal. After anything else (a name, a
# number, a closing bracket) it divides.
_REGEX_AFTER = set("(,=:[!&|?{};+-*%<>~^")
_REGEX_WORDS = {"return", "typeof", "case", "in", "of"}
_REGEX_FLAGS = "gimsuyd"
_WORD_CHARS = "_$"


@dataclass(frozen=True)
class ProjectFile:
    name: str
    code: str


@dataclass(frozen=True)
class Finding:
    file: str
    line: int  # 1-based; 0 when not line-specific
    message: str
    level: str  # "error" | "warning"


@dataclass(frozen=True)
class CheckReport:
    files: list[ProjectFile]
    traced: list[str]  # selected ids found in the test code
    missing: list[str]  # selected ids NOT found
    syntax: dict[str, str]  # name -> "valid" | "basic check passed" | "error" | "not checked"
    findings: list[Finding]


def safe_file_name(name: str) -> str | None:
    """A name that may go into the ZIP, or None. The AI writes these names, so distrust them."""
    cleaned = (name or "").replace("\\", "/").strip()
    while cleaned.startswith("/") or cleaned.startswith("./"):
        cleaned = cleaned[1:] if cleaned.startswith("/") else cleaned[2:]
    if ":" in cleaned:
        return None
    parts = cleaned.split("/")
    if len(parts) > _MAX_PARTS:
        return None
    if any(part == ".." or not _PART.match(part) for part in parts):
        return None
    return cleaned


def _extension(script: AutomationScript, seen: list[str]) -> str:
    """The extension a fallback file name should use."""
    framework = (script.framework or "").lower()
    if "python" in framework:
        return ".py"
    if "typescript" in framework:
        return ".ts"
    # Playwright TypeScript calls itself "Playwright (JavaScript)", so trust the
    # extensions the project already uses before falling back to .js.
    for name in seen:
        for suffix in (".ts", ".js", ".py"):
            if name.endswith(suffix):
                return suffix
    return ".js"


def _unique(name: str, used: set[str]) -> str:
    """name, or name_2 / name_3 before the extension when that name is taken."""
    if name not in used:
        return name
    head, slash, tail = name.rpartition("/")
    stem, dot, ext = tail.rpartition(".")
    if not dot:
        stem, ext = tail, ""
    counter = 2
    while f"{head}{slash}{stem}_{counter}{dot}{ext}" in used:
        counter += 1
    return f"{head}{slash}{stem}_{counter}{dot}{ext}"


def project_files(script: AutomationScript) -> list[ProjectFile]:
    """Every file the AI wrote, under names that are safe to put in a ZIP."""
    parts: list[tuple[str | None, str | None, str]] = [
        (script.page_object_file_name, script.page_object_code, "page_object"),
        (script.test_file_name, script.test_code, "test_cases"),
        (script.conftest_file_name, script.conftest_code, "conftest"),
        (script.config_file_name, script.config_code, "config"),
        ("requirements.txt", script.requirements_txt, "requirements"),
    ]
    files: list[ProjectFile] = []
    used: set[str] = set()
    for raw_name, code, fallback in parts:
        if not (code or "").strip():
            continue
        name = safe_file_name(raw_name or "")
        if name is None:
            if fallback == "conftest":
                name = "conftest.py"
            elif fallback == "requirements":
                name = "requirements.txt"
            else:
                name = fallback + _extension(script, [file.name for file in files])
        name = _unique(name, used)
        used.add(name)
        files.append(ProjectFile(name=name, code=code))
    return files


def _id_pattern(selected_id: str) -> str:
    """TC-001 also matches TC_001, TC 001 and TC001, the way Python test names spell it."""
    match = _ID_PARTS.match(selected_id.strip())
    if match:
        core = re.escape(match.group(1)) + r"[-_ ]?" + re.escape(match.group(2))
    else:
        core = re.escape(selected_id)
    return r"(?<![A-Za-z0-9-])" + core + r"(?![A-Za-z0-9])"


def _is_traced(selected_id: str, code: str) -> bool:
    return re.search(_id_pattern(selected_id), code, re.IGNORECASE) is not None


def _python_syntax(file: ProjectFile) -> tuple[str, list[Finding]]:
    try:
        ast.parse(file.code)
    except SyntaxError as e:
        return "error", [
            Finding(
                file=file.name,
                line=e.lineno or 0,
                message=f"Python syntax error: {e.msg}",
                level="error",
            )
        ]
    return "valid", []


def _json_syntax(file: ProjectFile) -> tuple[str, list[Finding]]:
    try:
        json.loads(file.code)
    except ValueError as e:
        return "error", [
            Finding(
                file=file.name,
                line=getattr(e, "lineno", 0) or 0,
                message=f"JSON error: {e}",
                level="error",
            )
        ]
    return "valid", []


def _starts_regex(code: str, index: int) -> bool:
    """True when the / at index opens a regex literal, false when it divides."""
    back = index - 1
    while back >= 0 and code[back] in " \t\r":
        back -= 1
    if back < 0 or code[back] == "\n":
        return True
    char = code[back]
    if char in _REGEX_AFTER:
        return True
    if char.isalnum() or char in _WORD_CHARS:
        end = back + 1
        while back >= 0 and (code[back].isalnum() or code[back] in _WORD_CHARS):
            back -= 1
        return code[back + 1 : end] in _REGEX_WORDS
    return False


def basic_js_check(code: str) -> tuple[int, str] | None:
    """None when brackets, quotes and comments line up, else (line, message) of the first problem.

    A character scan, not a parser: it never compiles or type-checks anything.
    """
    stack: list[tuple[str, int]] = []  # open "(", "[", "{", "${" and template strings
    mode = "code"  # code, a quote character, regex, line-comment or block-comment
    opened_at = 0  # the line the current string, regex or block comment started on
    in_class = False  # inside a [...] character class of a regex literal
    line = 1
    index = 0
    length = len(code)

    while index < length:
        char = code[index]
        step = 1
        if char == "\n":
            line += 1
            if mode == "line-comment":
                mode = "code"
            elif mode in ("'", '"', "regex"):
                shown = "/" if mode == "regex" else mode
                return opened_at, f"Unclosed {shown} opened on line {opened_at}"
        elif mode == "line-comment":
            pass
        elif mode == "block-comment":
            if code.startswith("*/", index):
                mode, step = "code", 2
        elif mode == "regex":
            if char == "\\":
                step = 2
            elif char == "[":
                in_class = True
            elif char == "]":
                in_class = False
            elif char == "/" and not in_class:
                mode = "code"
                while index + step < length and code[index + step] in _REGEX_FLAGS:
                    step += 1
        elif mode in ("'", '"', _BACKTICK):
            if char == "\\":
                step = 2
            elif mode == _BACKTICK and code.startswith("${", index):
                stack.append(("${", line))
                mode, step = "code", 2
            elif char == mode:
                if mode == _BACKTICK:
                    stack.pop()
                mode = "code"
        elif code.startswith("//", index):
            mode, step = "line-comment", 2
        elif code.startswith("/*", index):
            mode, opened_at, step = "block-comment", line, 2
        elif char == "/" and _starts_regex(code, index):
            mode, opened_at, in_class = "regex", line, False
        elif char in ("'", '"'):
            mode, opened_at = char, line
        elif char == _BACKTICK:
            mode, opened_at = _BACKTICK, line
            stack.append((_BACKTICK, line))
        elif char in "([{":
            stack.append((char, line))
        elif char in _CLOSERS:
            if char == "}" and stack and stack[-1][0] == "${":
                stack.pop()
                mode = _BACKTICK
            elif stack and stack[-1][0] == _CLOSERS[char]:
                stack.pop()
            elif stack:
                opener, where = stack[-1]
                return line, f"Unexpected {char}; {opener} opened on line {where} is still open"
            else:
                return line, f"Unexpected {char}"
        index += step

    if mode in ("'", '"', _BACKTICK):
        return opened_at, f"Unclosed {mode} opened on line {opened_at}"
    if mode == "regex":
        return opened_at, f"Unclosed / opened on line {opened_at}"
    if mode == "block-comment":
        return opened_at, f"Unclosed /* opened on line {opened_at}"
    if stack:
        opener, where = stack[0]
        return where, f"Unclosed {opener} opened on line {where}"
    return None


def _js_syntax(file: ProjectFile) -> tuple[str, list[Finding]]:
    problem = basic_js_check(file.code)
    if problem is None:
        return "basic check passed", []
    line, message = problem
    return "error", [Finding(file=file.name, line=line, message=message, level="error")]


def _wait_findings(file: ProjectFile) -> list[Finding]:
    """One warning per line that waits for a fixed number of seconds."""
    findings: list[Finding] = []
    for number, text in enumerate(file.code.splitlines(), start=1):
        if any(pattern.search(text) for pattern in _WAIT_PATTERNS):
            findings.append(
                Finding(file=file.name, line=number, message=WAIT_MESSAGE, level="warning")
            )
    return findings


def check_project(script: AutomationScript, selected_ids: list[str]) -> CheckReport:
    """Traceability, syntax and fixed waits. Code works all of this out, never the AI."""
    files = project_files(script)
    all_code = "\n".join(file.code for file in files)

    wanted: list[str] = []
    for selected_id in selected_ids:
        if selected_id and selected_id not in wanted:
            wanted.append(selected_id)
    traced = [one for one in wanted if _is_traced(one, all_code)]
    missing = [one for one in wanted if one not in traced]

    syntax: dict[str, str] = {}
    findings: list[Finding] = []
    for file in files:
        if file.name.endswith(".py"):
            status, errors = _python_syntax(file)
        elif file.name.endswith(JS_SUFFIXES):
            status, errors = _js_syntax(file)
        elif file.name.endswith(".json"):
            status, errors = _json_syntax(file)
        else:
            status, errors = "not checked", []
        syntax[file.name] = status
        findings.extend(errors)
        findings.extend(_wait_findings(file))

    return CheckReport(
        files=files, traced=traced, missing=missing, syntax=syntax, findings=findings
    )
