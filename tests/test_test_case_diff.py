"""Diff tests: what changed between the current and the proposed list."""

from qagenius.test_case_diff import diff_cases
from tests.factories import case, suite


def _counts(diff):
    return (diff.added, diff.changed, diff.removed, diff.unchanged)


def test_identical_lists_are_unchanged() -> None:
    current = suite(case("TC-001"), case("TC-002", traceability="AC-2"))
    proposed = suite(case("TC-001"), case("TC-002", traceability="AC-2"))
    diff = diff_cases(current, proposed)
    assert _counts(diff) == (0, 0, 0, 2)
    assert {item.status for item in diff.items} == {"unchanged"}


def test_new_id_is_added() -> None:
    diff = diff_cases(
        suite(case("TC-001")),
        suite(case("TC-001"), case("TC-009", title="A brand new boundary case")),
    )
    assert _counts(diff) == (1, 0, 0, 1)
    assert diff.items[1].status == "added"
    assert diff.items[1].before is None


def test_missing_id_is_removed_and_listed_last() -> None:
    diff = diff_cases(
        suite(case("TC-001"), case("TC-002", title="Second case about lockout")),
        suite(case("TC-001")),
    )
    assert _counts(diff) == (0, 0, 1, 1)
    assert diff.items[-1].status == "removed"
    assert diff.items[-1].after is None
    assert diff.items[-1].before.id == "TC-002"


def test_changed_expected_result() -> None:
    diff = diff_cases(
        suite(case("TC-001")),
        suite(case("TC-001", expected_result="The account locks for 15 minutes")),
    )
    assert _counts(diff) == (0, 1, 0, 0)
    changes = diff.items[0].changes
    assert len(changes) == 1
    assert changes[0].field == "expected_result"
    assert changes[0].before == "The account locks for 30 minutes"
    assert changes[0].after == "The account locks for 15 minutes"


def test_whitespace_and_letter_case_are_not_changes() -> None:
    diff = diff_cases(
        suite(case("TC-001", priority="High")),
        suite(
            case(
                "TC-001",
                priority="high",
                expected_result="The account   locks for 30 minutes  ",
            )
        ),
    )
    assert _counts(diff) == (0, 0, 0, 1)


def test_renamed_id_with_same_title_is_a_change() -> None:
    diff = diff_cases(
        suite(case("TC-003", title="Locked account refuses the correct password")),
        suite(
            case(
                "TC-03A",
                title="Locked account refuses the correct password",
                expected_result="Sign-in is refused",
            )
        ),
    )
    assert _counts(diff) == (0, 1, 0, 0)
    assert diff.items[0].before.id == "TC-003"
    assert diff.items[0].after.id == "TC-03A"


def test_unrelated_title_is_added_and_removed() -> None:
    diff = diff_cases(
        suite(case("TC-003", title="Locked account refuses the correct password")),
        suite(case("TC-04B", title="Shipping address accepts a long street name")),
    )
    assert _counts(diff) == (1, 0, 1, 0)


def test_reordered_steps_are_a_change() -> None:
    diff = diff_cases(
        suite(case("TC-001", steps=["First step", "Second step"])),
        suite(case("TC-001", steps=["Second step", "First step"])),
    )
    assert _counts(diff) == (0, 1, 0, 0)
    assert [change.field for change in diff.items[0].changes] == ["steps"]
    assert diff.items[0].changes[0].before == "First step\nSecond step"


def test_none_optional_field_reads_as_empty() -> None:
    diff = diff_cases(
        suite(case("TC-001", test_data=None)),
        suite(case("TC-001", test_data="email=dana.reed@example.com")),
    )
    change = diff.items[0].changes[0]
    assert change.field == "test_data"
    assert change.before == ""


def test_inputs_are_not_modified() -> None:
    current = suite(case("TC-001"))
    proposed = suite(case("TC-002", title="Another case entirely about shipping"))
    diff_cases(current, proposed)
    assert [c.id for c in current.test_cases] == ["TC-001"]
    assert [c.id for c in proposed.test_cases] == ["TC-002"]
