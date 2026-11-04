"""The tool reference in docs/mcp.md is generated, so it cannot go stale.

A hand-written field list is a field list that is wrong by the third
release. This fails the moment a schema changes without the docs being
rebuilt — `python scripts/update_mcp_docs.py` is how you rebuild them.
"""

from pathlib import Path

import pytest

from qagenius.mcp_server import server
from qagenius.mcp_server.schemas import MAX_CRITERIA, MAX_TESTS
from scripts.update_mcp_docs import DOCS, built

ROOT = Path(__file__).resolve().parent.parent
TEXT = DOCS.read_text(encoding="utf-8")


def test_the_generated_section_matches_the_schemas():
    found = TEXT.partition("<!-- tools:start -->")[2].partition("<!-- tools:end -->")[0]
    want = built().partition("<!-- tools:start -->")[2].partition("<!-- tools:end -->")[0]
    assert found == want, (
        "docs/mcp.md is out of date. Run: python scripts/update_mcp_docs.py"
    )


@pytest.mark.parametrize("spec", server.SPECS, ids=lambda one: one.name)
def test_every_tool_is_in_the_docs(spec):
    assert f"### `{spec.name}`" in TEXT


def test_the_order_to_call_them_in_is_written_down():
    for name in (one.name for one in server.SPECS):
        assert name in TEXT


def test_how_to_connect_is_written_down():
    assert "claude mcp add --transport http qa-genius" in TEXT
    assert "Add custom connector" in TEXT


def test_the_limits_in_the_docs_are_the_limits_in_the_code():
    assert f"| test cases | {MAX_TESTS} |" in TEXT
    assert f"| criteria | {MAX_CRITERIA} |" in TEXT


def test_the_error_sentences_in_the_docs_are_the_ones_the_code_sends():
    from qagenius.mcp_server.transport import BODY_TOO_BIG, TOO_MANY_TESTS

    assert TOO_MANY_TESTS in TEXT
    assert BODY_TOO_BIG in TEXT


def test_the_privacy_promise_is_stated():
    assert "Nothing is stored" in TEXT
    assert "Logs hold counts, never content" in TEXT
    assert "mcp tool=review_tests" in TEXT


def test_turning_it_on_in_production_is_documented():
    assert "QAG_MCP_ENABLED=1" in TEXT
    assert "Environment Variables (Production)" in TEXT
    assert "Vercel Firewall rate-limit rule" in TEXT


def test_the_readme_points_at_the_docs():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Use QA-Genius from Claude" in readme
    assert "docs/mcp.md" in readme


def test_the_changelog_has_this_version():
    from qagenius.mcp_server.server import version

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## {version()}" in changelog


def test_the_skill_exists_and_names_every_tool():
    skill = (
        ROOT / "integrations" / "claude" / "qa-genius" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert skill.startswith("---\nname: qa-genius\n")
    assert "description:" in skill.split("---")[1]
    for spec in server.SPECS:
        assert spec.name in skill
    # The three promises the skill exists to keep.
    assert "ask_the_po" in skill
    assert "previous_report_link" in skill
    assert "report_link" in skill
    assert "not_checked_in_this_call" in skill
    # The two things the skill exists to stop an agent doing.
    assert "Never say a check passed, or a problem was fixed" in skill
    assert "only ever compared against itself" in skill


def test_the_skill_readme_says_how_to_install_it():
    readme = (
        ROOT / "integrations" / "claude" / "qa-genius" / "README.md"
    ).read_text(encoding="utf-8")
    assert "claude mcp add --transport http qa-genius" in readme
    assert ".claude/skills" in readme
