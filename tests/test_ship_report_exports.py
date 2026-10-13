"""The Markdown a reader pastes into the release thread."""

from datetime import date

from qagenius.ship_check import ShipCheckItem, ShipReport
from qagenius.ship_report_exports import to_markdown

STORY = "As a shopper, I want my Aurora Storefront account to lock after wrong passwords."


def item(check_id, title, status, summary, details=None, note="") -> ShipCheckItem:
    return ShipCheckItem(
        id=check_id,
        title=title,
        status=status,
        summary=summary,
        details=list(details or []),
        link="/risks",
        accepted_note=note,
    )


def small_report(*items, verdict="dont_ship", reason="1 check failed: Risk coverage.") -> ShipReport:
    items = list(items)
    return ShipReport(
        verdict=verdict,
        verdict_reason=reason,
        items=items,
        counts={
            name: sum(1 for one in items if one.status == name)
            for name in ("pass", "warn", "fail", "accepted", "not_checked")
        },
        checked=sum(1 for one in items if one.status != "not_checked"),
    )


PASS = item("clarity", "Story clarity", "pass", "Clarity 82")
FAIL = item(
    "risks",
    "Risk coverage",
    "fail",
    "2 high risks have no test",
    ["R1 Lockout counter is not shared — no test"],
)
NOT_RUN = item("automation", "Automation", "not_checked", "Not run yet")


def test_the_header_and_the_table():
    text = to_markdown(small_report(PASS, FAIL, NOT_RUN), STORY)
    head, rest = text.split("\n## Details", 1)
    assert head.rstrip("\n").split("\n") == [
        "# Ship check — Don't ship",
        "1 check failed: Risk coverage.",
        "",
        f"**Story:** {STORY}",
        f"**Checked:** 2 of 3 · {date.today().isoformat()}",
        "",
        "| Check | Status | Summary |",
        "|---|---|---|",
        "| Story clarity | ✅ Pass | Clarity 82 |",
        "| Risk coverage | ❌ Fail | 2 high risks have no test |",
        "| Automation | ⚪ Not checked | Not run yet |",
    ]
    assert rest


def test_each_verdict_gets_its_own_title():
    for verdict, label in (
        ("ship", "Ship"),
        ("ship_with_risks", "Ship with risks"),
        ("dont_ship", "Don't ship"),
    ):
        text = to_markdown(small_report(PASS, verdict=verdict, reason="x"), STORY)
        assert text.startswith(f"# Ship check — {label}\n")


def test_a_pipe_in_a_summary_is_escaped():
    row = item("depth", "Test depth", "warn", "1 of 2 thin | AC-2")
    text = to_markdown(small_report(row), STORY)
    assert r"| Test depth | ⚠️ Warn | 1 of 2 thin \| AC-2 |" in text


def test_a_pipe_in_the_story_is_escaped():
    text = to_markdown(small_report(PASS), "Sign in | or register")
    assert r"**Story:** Sign in \| or register" in text


def test_the_story_is_cut_at_two_hundred_characters():
    text = to_markdown(small_report(PASS), "x" * 500)
    line = [one for one in text.split("\n") if one.startswith("**Story:**")][0]
    assert line == "**Story:** " + "x" * 200


def test_an_accepted_check_shows_its_reason_in_the_table_and_the_details():
    reason = "Behind a feature flag for internal users until Thursday."
    accepted = item(
        "risks", "Risk coverage", "accepted", "2 high risks have no test", ["R1 — no test"], reason
    )
    text = to_markdown(small_report(accepted), STORY)
    assert (
        f'| Risk coverage | 🟡 Accepted | 2 high risks have no test — accepted: "{reason}" |'
        in text
    )
    assert f'- Accepted: "{reason}"' in text


def test_details_lists_only_the_checks_that_did_not_pass():
    text = to_markdown(small_report(PASS, FAIL, NOT_RUN), STORY)
    details = text.split("## Details", 1)[1]
    assert "### Risk coverage — Fail" in details
    assert "### Automation — Not checked" in details
    assert "Story clarity" not in details


def test_a_check_with_no_detail_lines_falls_back_to_its_summary():
    text = to_markdown(small_report(NOT_RUN), STORY)
    assert "### Automation — Not checked\n- Not run yet" in text


def test_an_all_pass_report_has_no_details_section():
    text = to_markdown(small_report(PASS, verdict="ship", reason="All checks passed."), STORY)
    assert "## Details" not in text


def test_the_markdown_ends_with_one_newline():
    text = to_markdown(small_report(PASS, FAIL), STORY)
    assert text.endswith("\n") and not text.endswith("\n\n")
