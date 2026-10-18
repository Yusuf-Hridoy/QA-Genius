"""The rule-pack format and loader. No AI, no network."""

import pytest

from qagenius.shadow_qa import packs as packs_module
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
