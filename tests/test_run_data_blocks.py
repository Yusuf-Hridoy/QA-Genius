"""Every tool leaves its result in the page as JSON, so Ship check can see it.

These blocks are the only contract between a tool's result card and
sessionStorage["qag.run"]; the browser copies them, it never re-derives them.
"""

import json
import re

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)

_BLOCK = re.compile(
    r'<script type="application/json" id="(?P<id>[a-z-]+)">(?P<body>.*?)</script>',
    re.DOTALL,
)


def _block(body: str, block_id: str):
    for match in _BLOCK.finditer(body):
        if match.group("id") == block_id:
            return json.loads(match.group("body"))
    raise AssertionError(f'no JSON block with id="{block_id}"')


def test_story_result_carries_the_whole_analysis():
    body = client.post("/requirements/story/example").text
    assert 'id="story-analysis-data"' in body
    analysis = _block(body, "story-analysis-data")
    assert isinstance(analysis["ambiguity_score"], int)
    assert "vague_phrases" in analysis
    assert "generated_acceptance_criteria" in analysis


def test_duel_result_carries_the_agreement_and_the_forks():
    body = client.post("/requirements/story/example").text
    assert 'id="duel-data"' in body
    duel = _block(body, "duel-data")
    assert isinstance(duel["agreement_pct"], int)
    assert isinstance(duel["forks"], list)
    for fork in duel["forks"]:
        assert set(fork) == {"topic", "severity"}
        assert fork["severity"] in ("high", "medium", "low")


def test_the_duel_block_carries_nothing_but_those_two_keys():
    duel = _block(client.post("/requirements/story/example").text, "duel-data")
    assert set(duel) == {"agreement_pct", "forks"}


def test_automation_result_carries_the_script_and_the_selected_ids():
    body = client.post("/requirements/automation/example").text
    data = _block(body, "automation-data")
    assert set(data) == {"script", "selected_ids"}
    assert data["script"]["test_code"]


def test_insights_result_carries_the_computed_facts():
    body = client.post("/insights/example").text
    facts = _block(body, "insights-facts")
    assert set(facts) >= {"runs", "overall", "groups", "flaky", "slowest"}
