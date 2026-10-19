"""The rule-pack format and loader. No AI, no network."""

import pytest

from qagenius.shadow_qa import packs as packs_module
from qagenius.shadow_qa.detect import mentions
from qagenius.shadow_qa.packs import (
    PACKS_DIR,
    SEVERITIES,
    TEST_CATEGORIES,
    TEST_PRIORITIES,
    PackError,
    load_packs,
    read_pack,
)

GOOD_PACK = """
id = "demo"
name = "Demo"
triggers = ["demo feature"]

[[checks]]
id = "one"
title = "Something a principal QA insists on"
severity = "high"
why = "Because it breaks in production every time."
covered_if = ["demo word"]
  [checks.test]
  title = "Do the thing"
  category = "Edge Case"
  priority = "High"
  pre_conditions = "An account exists for user@example.com"
  steps = ["Open the page", "Press the button"]
  expected_result = "The thing happens and is visible on the page."
  test_data = "email=user@example.com"
"""


def _write(tmp_path, body: str, name: str = "demo.toml"):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def _bad(tmp_path, body: str, name: str = "broken.toml") -> str:
    with pytest.raises(PackError) as error:
        read_pack(_write(tmp_path, body, name))
    message = str(error.value)
    assert message.startswith(name + ":"), message
    return message


# ── every shipped pack ────────────────────────────────────────────────────────


def test_every_pack_file_loads():
    files = sorted(PACKS_DIR.glob("*.toml"))
    assert len(files) >= 17
    assert len(load_packs()) == len(files)


def test_pack_ids_are_unique():
    ids = [pack.id for pack in load_packs()]
    assert len(ids) == len(set(ids))
    assert ids == sorted(ids)


def test_check_ids_are_unique_within_and_across_packs():
    full_ids = [check.id for pack in load_packs() for check in pack.checks]
    assert len(full_ids) == len(set(full_ids))
    for pack in load_packs():
        short = [check.short_id for check in pack.checks]
        assert len(short) == len(set(short)), pack.id


def test_every_check_is_complete():
    for pack in load_packs():
        for check in pack.checks:
            assert check.id == f"{pack.id}.{check.short_id}"
            assert check.severity in SEVERITIES
            assert check.why.strip()
            assert check.covered_if
            test = check.test
            assert test.category in TEST_CATEGORIES
            assert test.priority in TEST_PRIORITIES
            assert len(test.steps) >= 2, check.id
            assert test.expected_result.strip()
            assert test.test_data.strip()


def test_every_risk_scores_in_range():
    for pack in load_packs():
        for risk in pack.risks:
            for score in (risk.severity, risk.likelihood, risk.detectability):
                assert 1 <= score <= 5, risk.title
            assert risk.covered_if
            assert risk.rpn == risk.severity * risk.likelihood * risk.detectability


def test_loading_twice_uses_the_cache():
    assert load_packs() is load_packs()


def test_helpers_find_a_known_check():
    assert packs_module.check_by_id("login.email_case") is not None
    assert packs_module.check_by_id("login.does_not_exist") is None
    assert len(packs_module.all_checks()) == sum(
        len(pack.checks) for pack in load_packs()
    )


# ── a broken pack names its file ──────────────────────────────────────────────


def test_a_good_pack_reads(tmp_path):
    pack = read_pack(_write(tmp_path, GOOD_PACK))
    assert pack.id == "demo"
    assert pack.checks[0].id == "demo.one"
    assert pack.exclude == ()


def test_invalid_toml_names_the_file(tmp_path):
    assert "not valid TOML" in _bad(tmp_path, "id = = 'demo'\n")


def test_unknown_severity_names_the_file(tmp_path):
    message = _bad(tmp_path, GOOD_PACK.replace('severity = "high"', 'severity = "urgent"'))
    assert "severity" in message and "urgent" in message


def test_unknown_category_names_the_file(tmp_path):
    message = _bad(tmp_path, GOOD_PACK.replace('category = "Edge Case"', 'category = "Smoke"'))
    assert "category" in message and "Smoke" in message


def test_unknown_priority_names_the_file(tmp_path):
    message = _bad(tmp_path, GOOD_PACK.replace('priority = "High"', 'priority = "Urgent"'))
    assert "priority" in message and "Urgent" in message


def test_empty_covered_if_names_the_file(tmp_path):
    message = _bad(tmp_path, GOOD_PACK.replace('covered_if = ["demo word"]', "covered_if = []"))
    assert "covered_if" in message


def test_one_step_is_not_enough(tmp_path):
    message = _bad(tmp_path, GOOD_PACK.replace(
        'steps = ["Open the page", "Press the button"]', 'steps = ["Open the page"]'
    ))
    assert "steps" in message


def test_missing_expected_result_names_the_file(tmp_path):
    message = _bad(tmp_path, GOOD_PACK.replace(
        'expected_result = "The thing happens and is visible on the page."',
        'expected_result = ""',
    ))
    assert "expected_result" in message


def test_repeated_check_id_names_the_file(tmp_path):
    body = GOOD_PACK + GOOD_PACK.split("[[checks]]", 1)[1].join(["[[checks]]", ""])
    message = _bad(tmp_path, body)
    assert "used twice" in message


def test_a_pack_needs_a_check(tmp_path):
    message = _bad(tmp_path, 'id = "demo"\nname = "Demo"\ntriggers = ["x"]\n')
    assert "at least one" in message


def test_risk_score_out_of_range_names_the_file(tmp_path):
    body = GOOD_PACK + """
[[risks]]
title = "Something fails"
category = "security"
severity = 9
likelihood = 3
detectability = 3
effect = "It is bad."
cause = "It was built that way."
covered_if = ["something"]
"""
    message = _bad(tmp_path, body)
    assert "severity" in message and "1-5" in message


# ── strong and weak triggers ──────────────────────────────────────────────────


def test_a_pack_may_declare_weak_triggers(tmp_path):
    body = GOOD_PACK.replace(
        'triggers = ["demo feature"]',
        'triggers = ["demo feature"]\nweak_triggers = ["demo", "thing"]',
    )
    pack = read_pack(_write(tmp_path, body))
    assert pack.triggers == ("demo feature",)
    assert pack.weak_triggers == ("demo", "thing")


def test_weak_triggers_default_to_none(tmp_path):
    assert read_pack(_write(tmp_path, GOOD_PACK)).weak_triggers == ()


def test_a_pack_with_only_weak_triggers_is_allowed(tmp_path):
    body = GOOD_PACK.replace(
        'triggers = ["demo feature"]', 'weak_triggers = ["demo", "thing"]'
    )
    pack = read_pack(_write(tmp_path, body))
    assert pack.triggers == () and len(pack.weak_triggers) == 2


def test_a_pack_with_no_trigger_at_all_names_the_file(tmp_path):
    message = _bad(tmp_path, GOOD_PACK.replace('triggers = ["demo feature"]', ""))
    assert "trigger" in message


def test_a_word_cannot_be_both_strong_and_weak(tmp_path):
    body = GOOD_PACK.replace(
        'triggers = ["demo feature"]',
        'triggers = ["demo feature"]\nweak_triggers = ["Demo Feature"]',
    )
    message = _bad(tmp_path, body)
    assert "both a trigger and a weak_trigger" in message


def test_the_over_common_words_are_weak_everywhere():
    """The words half the stories in the world contain must never be strong."""
    too_common = {
        "email", "emails", "list", "lists", "page", "link", "links", "file",
        "files", "image", "images", "device", "devices",
        "settings", "admin", "role", "roles", "find", "table", "token",
        # "Card" is not on this list: a card is the thing a payment is made
        # with, and the payment pack is the only one that claims the word.
    }
    for pack in load_packs():
        strong = {word.lower() for word in pack.triggers}
        assert not (strong & too_common), f"{pack.id}: {sorted(strong & too_common)}"


def test_durations_are_not_date_triggers():
    """Durations belong to the boundary rules; the date pack must leave them alone."""
    date_pack = next(pack for pack in load_packs() if pack.id == "datetime")
    words = {one.lower() for one in date_pack.triggers + date_pack.weak_triggers}
    assert not (words & {"minute", "minutes", "hour", "hours", "date", "dates", "expires"})
    for expected in ("timezone", "utc", "dst", "calendar", "deadline", "due date"):
        assert expected in words


def test_the_permissions_pack_splits_its_triggers_as_the_brief_says():
    pack = next(one for one in load_packs() if one.id == "permissions")
    assert set(pack.triggers) == {
        "permission", "permissions", "unauthorized", "unauthorised",
        "forbidden", "access control", "privileges",
    }
    assert set(pack.weak_triggers) == {"admin", "admins", "role", "roles"}


def test_a_risk_can_only_name_a_check_its_own_pack_has(tmp_path):
    body = GOOD_PACK + """
[[risks]]
title = "Something goes wrong"
category = "security"
severity = 4
likelihood = 3
detectability = 3
effect = "People lose work."
cause = "Nobody checked."
covered_if = ["demo word"]
tested_by = ["not_a_check"]
"""
    with pytest.raises(PackError) as error:
        read_pack(_write(tmp_path, body))
    assert "not_a_check" in str(error.value)


def test_every_risk_shares_its_words_with_the_check_that_tests_it():
    """A risk whose own test case it cannot recognise reads as untested.

    That is the bug this guard exists for: QA-Genius adds the check's test
    case, the risk's words never turn up in it, and Risk radar says "no test
    for this yet" about the test it wrote itself.
    """
    for pack in load_packs():
        checks = {check.short_id: check for check in pack.checks}
        for risk in pack.risks:
            for named in risk.tested_by:
                check = checks[named]
                shared = {word.lower() for word in risk.covered_if} & {
                    word.lower() for word in check.covered_if
                }
                assert shared, f"{pack.id}: {risk.title!r} and {named!r} share no word"
                written = check.test
                text = " ".join(
                    [
                        written.title,
                        written.pre_conditions,
                        *written.steps,
                        written.expected_result,
                        written.test_data,
                    ]
                )
                assert any(mentions(text, word) for word in risk.covered_if), (
                    f"{pack.id}: {risk.title!r} would not recognise the test "
                    f"{named!r} writes for it"
                )


def test_every_pack_risk_that_has_a_check_names_it():
    """The link is data, not a guess, so a new risk has to say which check."""
    linked = {
        ("account_deletion", "Deletion leaves orphaned data behind"): False,
        ("file_upload", "A file at the size limit exhausts server memory while it is processed"): False,
        ("login", "Response time differs between a known and an unknown email"): False,
        ("two_factor", "Verification codes are not rate limited"): False,
    }
    for pack in load_packs():
        for risk in pack.risks:
            expected = linked.get((pack.id, risk.title), True)
            assert bool(risk.tested_by) == expected, (
                f"{pack.id}: {risk.title!r} — a risk with no check of its own "
                "belongs in this list, and one with a check must name it"
            )


def test_a_word_that_names_a_page_is_never_strong():
    """A page holds many features, so its name says nothing about any of them.

    "Profile" switched the profile-form rules on for a story that only
    uploaded a photo, and the checklist then asked for bio and two-tab tests.
    """
    page_words = {
        "profile", "profiles", "settings", "setting", "dashboard",
        "account", "accounts", "page", "pages", "my account", "home",
    }
    for pack in load_packs():
        strong = {word.lower() for word in pack.triggers}
        assert not (strong & page_words), f"{pack.id}: {sorted(strong & page_words)}"
