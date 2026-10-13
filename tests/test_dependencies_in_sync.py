"""requirements.txt and pyproject.toml must list the same runtime libraries.

Vercel installs from whichever it finds. A library in one file and not the
other means the app imports fine locally and dies on deploy.
"""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# "json-repair>=0.30 ; python_version>='3.12'" -> "json-repair"
_NAME = re.compile(r"^[A-Za-z0-9._-]+")


def _package_name(line: str) -> str:
    cleaned = line.split("#", 1)[0].strip()
    match = _NAME.match(cleaned)
    return match.group(0).lower().replace("_", "-") if match else ""


def _requirements() -> set[str]:
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    names = {_package_name(line) for line in text.splitlines()}
    return {name for name in names if name}


def _pyproject() -> set[str]:
    with open(ROOT / "pyproject.toml", "rb") as handle:
        data = tomllib.load(handle)
    names = {_package_name(item) for item in data["project"]["dependencies"]}
    return {name for name in names if name}


def test_the_two_files_list_the_same_runtime_packages():
    assert _requirements() == _pyproject()


def test_the_libraries_the_exports_need_are_listed():
    # openpyxl writes the Excel exports, defusedxml reads the JUnit uploads.
    assert {"openpyxl", "defusedxml"} <= _pyproject()
