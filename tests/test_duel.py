"""Duel logic tests. The LLM is faked; no network."""

from qagenius.duel import DuelResult, build_highlights, highlight_story, run_duel
from qagenius.models import DuelComparison, Fork, Interpretation

KEYS = [{"provider": "gemini", "key": "k1", "label": ""}]

STORY = "As a shopper, I want my account to lock quickly after too many wrong passwords."


def _fork(phrase, topic="lock timing"):
    return Fork(
        topic=topic,
        reading_a="strict reading",
        reading_b="relaxed reading",
        source_phrase=phrase,
        severity="high",
        suggested_rewrite="a clear rewrite",
    )


def test_readers_run_before_compare_and_receive_both_readings() -> None:
    calls: list = []

    def fake(keys, system, user, schema):
        calls.append((schema.__name__, system, user))
        if schema.__name__ == "Interpretation":
            if "strictest" in system:
                return Interpretation(actors=["strict-actor"]), 0, ["note-a"]
            return Interpretation(actors=["relaxed-actor"]), 0, ["note-b"]
        assert schema.__name__ == "DuelComparison"
        # Compare must see both readings serialised in the prompt.
        assert "strict-actor" in user
        assert "relaxed-actor" in user
        assert STORY in user
        return DuelComparison(forks=[], agreements=["same actor"]), 0, ["note-c"]

    result = run_duel(KEYS, STORY, "User story", "", generate=fake)
    assert isinstance(result, DuelResult)
    assert [c[0] for c in calls[:2]] == ["Interpretation", "Interpretation"]
    assert calls[2][0] == "DuelComparison"
    assert result.agreement_pct == 100
    assert result.notes == ["note-a", "note-b", "note-c"]


def test_agreement_math() -> None:
    def fake(forks, agreements):
        def _generate(keys, system, user, schema):
            if schema.__name__ == "Interpretation":
                return Interpretation(), 0, []
            return DuelComparison(forks=forks, agreements=agreements), 0, []

        return _generate

    r = run_duel(KEYS, STORY, "", "", generate=fake([], []))
    assert r.agreement_pct == 100  # 0/0 edge

    r = run_duel(
        KEYS, STORY, "", "",
        generate=fake([_fork("quickly")], ["a", "b"]),
    )
    assert r.agreement_pct == round(100 * 2 / 3)

    r = run_duel(
        KEYS, STORY, "", "",
        generate=fake([_fork("quickly"), _fork("too many wrong passwords")], ["a"]),
    )
    assert r.agreement_pct == round(100 * 1 / 3)


def test_phrases_not_in_story_are_skipped() -> None:
    forks = [_fork("quickly"), _fork("not in the story")]
    highlights = build_highlights(STORY, forks)
    assert len(highlights) == 1
    start, end, idx = highlights[0]
    assert STORY[start:end].lower() == "quickly"
    assert idx == 0


def test_overlaps_keep_longer_one() -> None:
    story = "please lock quickly after five attempts"
    forks = [_fork("quickly", topic="t1"), _fork("lock quickly after", topic="t2")]
    highlights = build_highlights(story, forks)
    assert len(highlights) == 1
    start, end, idx = highlights[0]
    assert story[start:end] == "lock quickly after"
    assert idx == 1


def test_highlights_sorted_by_start() -> None:
    story = "alpha then beta then gamma"
    forks = [_fork("gamma"), _fork("alpha")]
    highlights = build_highlights(story, forks)
    assert [h[2] for h in highlights] == [1, 0]
    assert highlights[0][0] < highlights[1][0]


def test_html_in_story_and_ai_text_is_escaped() -> None:
    story = 'Lock <b>quickly</b> & safely <script>alert(1)</script>'
    forks = [
        Fork(
            topic="t",
            reading_a='<img src=x onerror=alert(1)> strict',
            reading_b='<script>alert(2)</script> relaxed',
            source_phrase="quickly",
            severity="high",
            suggested_rewrite='<b>evil rewrite</b>',
        )
    ]
    highlights = build_highlights(story, forks)
    out = str(highlight_story(story, highlights, forks))
    assert "<script>" not in out
    assert "<img" not in out
    assert "&lt;script&gt;" in out
    assert "&lt;b&gt;" in out
    assert "&amp;" in out
    assert 'class="fork-mark"' in out
    assert 'data-fork="0"' in out
    # AI text is never rendered by highlight_story.
    assert "evil rewrite" not in out
    assert "strict" not in out


def test_reader_failure_aborts_duel() -> None:
    from qagenius import llm

    def fake(keys, system, user, schema):
        if schema.__name__ == "Interpretation" and "strictest" in system:
            raise llm.AllKeysBusyError(["busy"])
        if schema.__name__ == "Interpretation":
            return Interpretation(), 0, []
        raise AssertionError("compare must not run after a reader failure")

    try:
        run_duel(KEYS, STORY, "", "", generate=fake)
    except llm.AllKeysBusyError:
        pass
    else:
        raise AssertionError("expected AllKeysBusyError")
