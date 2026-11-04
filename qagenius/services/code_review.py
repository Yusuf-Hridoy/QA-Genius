"""What a senior tester sends back on a set of automation files.

No AI. Python is parsed for real; TypeScript and JavaScript get a quick
check that the brackets and quotes match, which is not a compile and says
so wherever the answer is shown.
"""

from dataclasses import dataclass, field

from qagenius.automation_checks import CheckReport, Finding, ProjectFile, check_files
from qagenius.shadow_qa.review import review_files

# What each framework is written in, so the right syntax check runs and the
# answer can say how far it goes.
FRAMEWORKS = {
    "playwright-ts": "TypeScript",
    "playwright-js": "JavaScript",
    "playwright-py": "Python",
    "cypress": "JavaScript",
    "selenium-py": "Python",
    "selenium-java": "Java",
}

# What the syntax answer really means, in the words the result uses.
SYNTAX_WORDS = {
    "valid": "parsed, no syntax errors",
    "basic check passed": (
        "quick check: brackets and quotes match, not a full compile"
    ),
    "error": "syntax error",
    "not checked": "not checked — this file type has no checker here",
}


@dataclass(frozen=True)
class CodeReview:
    """One set of files, checked every way the Automation desk checks them."""

    framework: str
    language: str
    report: CheckReport
    # The senior tester's own findings: no assertion, `.only`, a secret in
    # the source, a selector that will break on the next redesign.
    findings: list[Finding] = field(default_factory=list)
    # Test case ids named in the code, and the ones that are not.
    traced: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    # file name -> what its syntax check actually proved.
    syntax: dict[str, str] = field(default_factory=dict)


def language_of(framework: str) -> str:
    """What the files are written in, for a framework name."""
    return FRAMEWORKS.get(str(framework or "").strip().lower(), "")


def syntax_words(status: str) -> str:
    """What a syntax answer proves, said so nobody reads more into it."""
    return SYNTAX_WORDS.get(str(status or ""), str(status or ""))


def review_code(
    framework: str,
    files: list[ProjectFile],
    test_case_ids: list[str] | None = None,
) -> CodeReview:
    """Check a set of automation files. No AI, no key, nothing run.

    Nothing here executes a line of what it is given. Every answer comes
    from reading the text.
    """
    files = list(files or [])
    report = check_files(files, list(test_case_ids or []))
    # The two sets of findings are one list: the syntax and fixed-wait
    # findings from the project check, and the senior tester's own.
    findings = sorted(
        [*report.findings, *review_files(files)],
        key=lambda one: (one.file, one.line, one.message),
    )
    return CodeReview(
        framework=str(framework or ""),
        language=language_of(framework),
        report=report,
        findings=findings,
        traced=list(report.traced),
        missing=list(report.missing),
        syntax=dict(report.syntax),
    )
