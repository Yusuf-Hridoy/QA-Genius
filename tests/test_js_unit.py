"""Run the JavaScript unit tests from the Python suite.

public/run_state.js decides what every desk says about its freshness, so it is
worth real tests. Node's own test runner does it with no dependencies; if node
is not installed the tests are skipped rather than silently not run.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS_TESTS = ROOT / "tests" / "js"

node = shutil.which("node")
pytestmark = pytest.mark.skipif(node is None, reason="node is not installed")


def _run_node() -> str:
    # Explicit paths, not a glob: node is handed the pattern verbatim here and
    # would exit 0 having run nothing at all.
    files = sorted(str(path.relative_to(ROOT)) for path in JS_TESTS.glob("*.test.mjs"))
    assert files, "no JS test files to run"
    result = subprocess.run(
        [node, "--test", *files],
        cwd=ROOT,
        capture_output=True,
        # node writes UTF-8; the Windows default would mangle its ℹ markers.
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    # Windows line endings would defeat the anchored search below.
    output = (result.stdout + result.stderr).replace(chr(13), "")
    assert result.returncode == 0, output
    return output


def test_the_run_state_module_passes_its_own_tests() -> None:
    output = _run_node()
    passed = re.search(r"^.\s*pass (\d+)$", output, re.MULTILINE)
    failed = re.search(r"^.\s*fail (\d+)$", output, re.MULTILINE)
    assert passed and failed, f"node printed no counts:\n{output}"
    # A green run that ran nothing is not a green run.
    assert int(passed.group(1)) > 0, output
    assert int(failed.group(1)) == 0, output


def test_every_javascript_test_file_is_collected() -> None:
    assert list(JS_TESTS.glob("*.test.mjs")), "no JS tests found to run"
