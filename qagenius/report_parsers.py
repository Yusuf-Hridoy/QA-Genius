"""Read JUnit XML and Playwright JSON reports into one simple shape.

Uploaded files are untrusted, so the XML goes through defusedxml: never
xml.etree or lxml directly. Nothing here calls an AI or touches the disk.
"""

import json
import re
from dataclasses import dataclass
from xml.etree.ElementTree import ParseError

import defusedxml.ElementTree as DefusedET
from defusedxml.common import DefusedXmlException

MAX_TESTS = 20_000
DETAILS_LIMIT = 2000
LABEL_LIMIT = 60

# Playwright writes colour codes into error messages; they are noise in HTML.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
# A rerun that ended green. A final <failure>/<error> still wins over these.
_FLAKY_TAGS = ("flakyFailure", "flakyError", "rerunFailure")
_PLAYWRIGHT_STATUS = {
    "expected": "passed",
    "unexpected": "failed",
    "flaky": "flaky",
    "skipped": "skipped",
}


@dataclass(frozen=True)
class TestResult:
    __test__ = False  # a result row, not something for pytest to collect

    test_id: str
    name: str
    suite: str
    status: str
    duration_s: float
    message: str
    details: str


@dataclass(frozen=True)
class RunReport:
    label: str
    format: str
    tests: list[TestResult]


class ReportError(ValueError):
    """The file could not be read. The message is shown to the user as-is."""


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text or "")


def _label(file_name: str) -> str:
    """The file name without folders or extension, trimmed to 60 characters."""
    name = (file_name or "").replace("\\", "/").rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return (stem.strip() or "report")[:LABEL_LIMIT]


def parse_report(file_name: str, content: bytes) -> RunReport:
    """One uploaded file as one run. Raises ReportError with a message for the user."""
    text = content.decode("utf-8", errors="replace").lstrip("﻿").strip()
    label = _label(file_name)

    if text.startswith("<"):
        return _parse_junit(file_name, label, text)

    if text.startswith("{") or text.startswith("["):
        try:
            data = json.loads(text)
        except ValueError as e:
            raise ReportError(f"Could not read {file_name}: not valid JSON.") from e
        if isinstance(data, dict) and "suites" in data and "config" in data:
            return _parse_playwright(label, data, file_name)

    raise ReportError(
        f"Unsupported file: {file_name}. Upload JUnit XML or Playwright JSON."
    )


def _check_size(file_name: str, tests: list[TestResult]) -> list[TestResult]:
    if len(tests) > MAX_TESTS:
        raise ReportError(f"Too many tests in {file_name} (max 20,000).")
    return tests


# ---------- JUnit XML ----------


def _tag(node) -> str:
    """The local tag name, without any {namespace} prefix."""
    tag = node.tag if isinstance(node.tag, str) else ""
    return tag.rsplit("}", 1)[-1]


def _seconds(raw: str | None) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return value if value == value and abs(value) != float("inf") else 0.0


def _message_and_details(node) -> tuple[str, str]:
    """The message attribute (or the first non-empty line of the text) and the text."""
    if node is None:
        return "", ""
    body = (node.text or "").strip()
    message = (node.get("message") or "").strip()
    if not message:
        for line in body.splitlines():
            if line.strip():
                message = line.strip()
                break
    return strip_ansi(message), strip_ansi(body)[:DETAILS_LIMIT]


def _junit_case(node, suite_name: str) -> TestResult:
    suite = (node.get("classname") or suite_name or "").strip()
    name = (node.get("name") or "").strip()
    failure = skipped = flaky = None
    for child in node:
        tag = _tag(child)
        if tag in ("failure", "error") and failure is None:
            failure = child
        elif tag == "skipped" and skipped is None:
            skipped = child
        elif tag in _FLAKY_TAGS and flaky is None:
            flaky = child

    if failure is not None:
        status, holder = "failed", failure
    elif skipped is not None:
        status, holder = "skipped", None
    elif flaky is not None:
        status, holder = "flaky", flaky
    else:
        status, holder = "passed", None

    message, details = _message_and_details(holder)
    return TestResult(
        test_id=f"{suite}::{name}",
        name=name,
        suite=suite,
        status=status,
        duration_s=_seconds(node.get("time")),
        message=message,
        details=details,
    )


def _parse_junit(file_name: str, label: str, text: str) -> RunReport:
    try:
        root = DefusedET.fromstring(text)
    except DefusedXmlException as e:
        raise ReportError(
            f"Could not read {file_name}: it uses XML features that are not allowed."
        ) from e
    except ParseError as e:
        raise ReportError(f"Could not read {file_name}: not valid XML.") from e

    tests: list[TestResult] = []
    # Explicit stack, children reversed, so testcases come out in document order
    # and a deeply nested file cannot blow the Python stack.
    stack = [(root, "")]
    while stack:
        node, suite_name = stack.pop()
        tag = _tag(node)
        if tag == "testcase":
            tests.append(_junit_case(node, suite_name))
            continue
        if tag == "testsuite":
            suite_name = (node.get("name") or "").strip() or suite_name
        for child in reversed(list(node)):
            stack.append((child, suite_name))

    return RunReport(label=label, format="junit", tests=_check_size(file_name, tests))


# ---------- Playwright JSON ----------


def _playwright_error(results: list) -> tuple[str, str]:
    """The last result that carries an error wins, like the Playwright reporters."""
    for result in reversed(results):
        error = result.get("error") if isinstance(result, dict) else None
        if isinstance(error, dict):
            message = strip_ansi(str(error.get("message") or "")).strip()
            details = strip_ansi(str(error.get("stack") or "")).strip()
            return message, details[:DETAILS_LIMIT]
    return "", ""


def _playwright_status(raw: str, results: list) -> str:
    status = _PLAYWRIGHT_STATUS.get(raw, "passed")
    if status == "passed" and results:
        if all(
            isinstance(r, dict) and r.get("status") == "skipped" for r in results
        ):
            return "skipped"
    return status


def _playwright_specs(suites: list, titles: list[str], out: list[TestResult]) -> None:
    for suite in suites:
        if not isinstance(suite, dict):
            continue
        suite_titles = titles + [str(suite.get("title") or "")]
        for spec in suite.get("specs") or []:
            if isinstance(spec, dict):
                _playwright_spec(spec, suite_titles, out)
        _playwright_specs(suite.get("suites") or [], suite_titles, out)


def _playwright_spec(spec: dict, titles: list[str], out: list[TestResult]) -> None:
    file_name = str(spec.get("file") or "")
    # The outermost suite title is the file itself; it would only repeat the suite column.
    parts = [title for title in titles if title and title != file_name]
    parts.append(str(spec.get("title") or ""))
    name = " › ".join(part for part in parts if part)

    for test in spec.get("tests") or []:
        if not isinstance(test, dict):
            continue
        project = str(test.get("projectName") or "")
        results = [r for r in (test.get("results") or []) if isinstance(r, dict)]
        message, details = _playwright_error(results)
        duration = sum(_seconds(r.get("duration")) for r in results) / 1000
        # A config without a `projects` array reports an empty project name; the
        # trailing separator would then only make the id harder to match.
        test_id = f"{file_name}::{name}::{project}" if project else f"{file_name}::{name}"
        out.append(
            TestResult(
                test_id=test_id,
                name=f"{name} [{project}]" if project else name,
                suite=file_name,
                status=_playwright_status(str(test.get("status") or ""), results),
                duration_s=duration,
                message=message,
                details=details,
            )
        )


def _parse_playwright(label: str, data: dict, file_name: str) -> RunReport:
    tests: list[TestResult] = []
    suites = data.get("suites")
    _playwright_specs(suites if isinstance(suites, list) else [], [], tests)
    return RunReport(
        label=label, format="playwright", tests=_check_size(file_name, tests)
    )
