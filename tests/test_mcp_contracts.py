"""The shapes on the wire are a promise, so changing one has to be deliberate.

An agent builds its calls from these schemas. A field that quietly changes
name breaks every caller that already works, and nobody finds out until
somebody's tool call comes back empty. These tests compare the live schema
with the saved one and fail on any difference; `python scripts/update_contracts.py`
is how you accept a change you meant.
"""

import json
from pathlib import Path

import pytest

from qagenius.mcp_server.schemas import (
    CONTRACTS,
    MAX_CRITERIA,
    MAX_TESTS,
    SCHEMA_VERSION,
    STORY_MAX,
    ShipOut,
    TestIn,
    ToolOut,
    problem_id,
)

CONTRACTS_DIR = Path(__file__).resolve().parent / "contracts"


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_the_saved_schema_still_matches_the_model(name):
    path = CONTRACTS_DIR / f"{name}.json"
    assert path.exists(), (
        f"tests/contracts/{name}.json is missing. "
        "Run: python scripts/update_contracts.py"
    )
    saved = json.loads(path.read_text(encoding="utf-8"))
    live = json.loads(json.dumps(CONTRACTS[name].model_json_schema(), sort_keys=True))
    assert live == saved, (
        f"The schema for {name} changed. If you meant it, run: "
        "python scripts/update_contracts.py"
    )


def test_no_saved_schema_is_left_behind():
    saved = {path.stem for path in CONTRACTS_DIR.glob("*.json")}
    assert saved == set(CONTRACTS)


def test_every_field_an_agent_reads_has_a_description():
    # The description is the only instruction an agent gets. A field without
    # one is a field it has to guess at.
    for name, model in CONTRACTS.items():
        schema = model.model_json_schema()
        for field, body in schema.get("properties", {}).items():
            assert body.get("description"), f"{name}.{field} has no description"


def test_an_unknown_field_is_refused_not_ignored():
    # A typo in a field name is a quiet half-request otherwise.
    with pytest.raises(ValueError):
        TestIn(
            id="TC-1",
            title="x",
            steps=["a"],
            expected="b",
            stpes=["a"],  # the typo
        )


def test_a_test_needs_at_least_one_step():
    with pytest.raises(ValueError):
        TestIn(id="TC-1", title="x", steps=[], expected="b")


def test_the_limits_are_in_the_schema_an_agent_reads():
    schema = CONTRACTS["story_in"].model_json_schema()
    assert schema["properties"]["story"]["maxLength"] == STORY_MAX
    tests = CONTRACTS["tests_in"].model_json_schema()
    assert tests["properties"]["criteria"]["maxItems"] == MAX_CRITERIA
    assert tests["properties"]["test_cases"]["maxItems"] == MAX_TESTS


def test_ship_adds_four_fields_and_changes_nothing_else():
    extra = set(ShipOut.model_fields) - set(ToolOut.model_fields)
    assert extra == {"decision", "grade", "checks", "path_to_ready"}
    for name in ToolOut.model_fields:
        assert name in ShipOut.model_fields


def test_the_schema_version_is_on_every_answer():
    assert ToolOut(tool="check_story", summary="x").schema_version == SCHEMA_VERSION


# ──────────────────────────────────────────────────────────────────────────────
# Problem ids
# ──────────────────────────────────────────────────────────────────────────────


def test_the_same_problem_keeps_the_same_id():
    first = problem_id("limit", "Nobody says what happens at exactly $50", ["AC-1"], [])
    second = problem_id("limit", "Nobody says what happens at exactly $50", ["AC-1"], [])
    assert first == second


def test_the_id_starts_with_the_kind_and_is_four_hex():
    found = problem_id("limit", "something", [], [])
    assert found.startswith("L-")
    assert len(found) == len("L-") + 4
    int(found.split("-")[1], 16)


def test_spacing_and_case_in_the_sentence_do_not_change_the_id():
    assert problem_id("gap", "The  limit\napplies", [], []) == problem_id(
        "gap", "the limit applies", [], []
    )


def test_the_order_the_ids_arrive_in_does_not_change_it():
    assert problem_id("depth", "x", ["AC-2", "AC-1"], ["TC-2", "TC-1"]) == problem_id(
        "depth", "x", ["AC-1", "AC-2"], ["TC-1", "TC-2"]
    )


def test_a_different_problem_gets_a_different_id():
    assert problem_id("limit", "a", [], []) != problem_id("limit", "b", [], [])
    assert problem_id("limit", "a", [], []) != problem_id("gap", "a", [], [])
    assert problem_id("limit", "a", ["AC-1"], []) != problem_id("limit", "a", [], [])
