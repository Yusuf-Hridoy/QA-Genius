"""Duel logic tests. The LLM is faked; no network."""

from qagenius.duel import (
    NOT_STATED_A,
    NOT_STATED_B,
    DuelResult,
    build_highlights,
    drop_false_forks,
    format_number_facts,
    ground_forks,
    run_duel,
)
from qagenius.models import DuelComparison, Fork, Interpretation, NumberReading
from qagenius.numbers import match_numbers
from qagenius.prompts import duel_compare_prompt
from qagenius.web import _highlight_duel_story

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
    out = str(_highlight_duel_story(story, highlights, forks))
    assert "<script>" not in out
    assert "<img" not in out
    assert "<b>evil rewrite</b>" not in out
    assert "&lt;script&gt;" in out
    assert "&lt;b&gt;" in out
    assert "&amp;" in out
    assert "&lt;img" in out
    assert "&lt;b&gt;evil rewrite&lt;/b&gt;" in out
    assert 'class="fork-mark"' in out
    assert 'data-fork="0"' in out


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


def test_fork_severity_is_tolerant() -> None:
    def make(severity):
        return Fork(
            topic="t",
            reading_a="a",
            reading_b="b",
            source_phrase="quickly",
            severity=severity,
            suggested_rewrite="rewrite",
        )

    assert make("High").severity == "high"
    assert make(" MEDIUM ").severity == "medium"
    assert make("critical").severity == "high"
    assert make("unknown").severity == "medium"


def _reading_with_numbers(*values: str) -> Interpretation:
    return Interpretation(
        numbers=[
            NumberReading(name=f"n{i}", value=v, source_phrase="too many")
            for i, v in enumerate(values)
        ]
    )


def _fork_sides(topic: str, side_a: str, side_b: str) -> DuelComparison:
    return DuelComparison(
        forks=[
            Fork(
                topic=topic,
                reading_a=side_a,
                reading_b=side_b,
                source_phrase="too many",
                severity="high",
                suggested_rewrite="after 5 wrong passwords within 10 minutes",
            )
        ],
        agreements=[],
    )


def test_unsupported_number_is_removed() -> None:
    reading_a = _reading_with_numbers("3 attempts")
    reading_b = Interpretation()
    comparison = _fork_sides("threshold", "3 attempts", "5 attempts")
    cleaned, removed, notes = ground_forks(comparison, reading_a, reading_b)
    assert cleaned.forks[0].reading_a == "3 attempts"
    assert cleaned.forks[0].reading_b == NOT_STATED_B
    assert removed == 1
    assert len(notes) == 1 and "Reader B" in notes[0]


def test_supported_numbers_kept() -> None:
    reading_a = _reading_with_numbers("3 attempts")
    reading_b = _reading_with_numbers("5 attempts")
    comparison = _fork_sides("threshold", "3 attempts", "5 attempts")
    cleaned, removed, notes = ground_forks(comparison, reading_a, reading_b)
    assert cleaned.forks[0].reading_a == "3 attempts"
    assert cleaned.forks[0].reading_b == "5 attempts"
    assert removed == 0
    assert notes == []


def test_both_unsupported_drops_fork() -> None:
    comparison = _fork_sides("window", "7 minutes", "9 minutes")
    cleaned, removed, _ = ground_forks(
        comparison, Interpretation(), Interpretation()
    )
    assert cleaned.forks == []
    assert removed == 2


def test_not_stated_normalised() -> None:
    reading_a = _reading_with_numbers("3 attempts")
    comparison = _fork_sides("threshold", "3 attempts", "Not stated")
    cleaned, removed, _ = ground_forks(comparison, reading_a, Interpretation())
    assert len(cleaned.forks) == 1
    assert cleaned.forks[0].reading_b == NOT_STATED_B
    assert removed == 0


def test_number_match_is_whole_number() -> None:
    reading_b = _reading_with_numbers("15 minutes")
    comparison = _fork_sides("window", "3 attempts", "5 minutes")
    reading_a = _reading_with_numbers("3 attempts")
    cleaned, removed, _ = ground_forks(comparison, reading_a, reading_b)
    assert cleaned.forks[0].reading_b == NOT_STATED_B
    assert removed == 1


def test_text_only_claims_kept() -> None:
    comparison = _fork_sides("effect", "locks fast", "permanent until admin unlock")
    cleaned, removed, _ = ground_forks(
        comparison, Interpretation(), Interpretation()
    )
    assert len(cleaned.forks) == 1
    assert cleaned.forks[0].reading_b == "permanent until admin unlock"
    assert removed == 0


def test_input_not_mutated() -> None:
    comparison = _fork_sides("threshold", "3 attempts", "5 attempts")
    ground_forks(comparison, _reading_with_numbers("3 attempts"), Interpretation())
    assert comparison.forks[0].reading_b == "5 attempts"


def test_run_duel_applies_guard_and_recomputes_agreement() -> None:
    reading_a = _reading_with_numbers("3 attempts")
    reading_b = _reading_with_numbers("5 attempts")

    def fake(keys, system, user, schema):
        if schema.__name__ == "Interpretation":
            if "strictest" in system:
                return reading_a, 0, []
            return reading_b, 0, []
        return DuelComparison(
            forks=[
                Fork(
                    topic="threshold",
                    reading_a="3 attempts",
                    reading_b="5 attempts",
                    source_phrase="too many",
                    severity="high",
                    suggested_rewrite="after 5 wrong passwords within 10 minutes",
                ),
                Fork(
                    topic="window",
                    reading_a="7 minutes",
                    reading_b="9 minutes",
                    source_phrase="quickly",
                    severity="medium",
                    suggested_rewrite="within 60 seconds",
                ),
            ],
            agreements=["agree one", "agree two"],
        ), 0, []

    result = run_duel(KEYS, STORY, "", "", generate=fake)
    assert len(result.comparison.forks) == 1
    assert result.agreement_pct == 67
    assert result.removed_claims == 2


def test_vague_rewrite_detected() -> None:
    reading_a = _reading_with_numbers("3 attempts")
    reading_b = _reading_with_numbers("5 attempts")

    def fake(keys, system, user, schema):
        if schema.__name__ == "Interpretation":
            if "strictest" in system:
                return reading_a, 0, []
            return reading_b, 0, []
        return DuelComparison(
            forks=[
                Fork(
                    topic="threshold",
                    reading_a="3 attempts",
                    reading_b="5 attempts",
                    source_phrase="too many",
                    severity="high",
                    suggested_rewrite="lock quickly after 3 wrong passwords",
                )
            ],
            agreements=[],
        ), 0, []

    result = run_duel(KEYS, STORY, "", "", generate=fake)
    assert result.vague_rewrites == {0: ["quickly"]}


def _real_readers() -> tuple[Interpretation, Interpretation]:
    """The numbers a real Gemini run produced for the example story."""
    reading_a = Interpretation(
        numbers=[
            NumberReading(
                name="Failed Password Attempt Limit",
                value="5 attempts",
                source_phrase="too many wrong passwords",
            ),
            NumberReading(
                name="Lockout Response Time", value="1 second", source_phrase="quickly"
            ),
            NumberReading(
                name="Account Lockout Duration", value="30 minutes", source_phrase="lock"
            ),
        ]
    )
    reading_b = Interpretation(
        numbers=[
            NumberReading(
                name="Failed password threshold",
                value="5 attempts",
                source_phrase="too many wrong passwords",
            ),
            NumberReading(
                name="Lock execution time limit",
                value="3 seconds",
                source_phrase="quickly",
            ),
            NumberReading(
                name="Account lockout duration",
                value="30 minutes",
                source_phrase="lock",
            ),
        ]
    )
    return reading_a, reading_b


def _false_fork() -> Fork:
    return Fork(
        topic="Account lock behavior and duration",
        reading_a=NOT_STATED_A,
        reading_b="locks the account for 30 minutes",
        source_phrase="lock",
        severity="high",
        suggested_rewrite="a clear rewrite",
    )


def _real_fork() -> Fork:
    return Fork(
        topic="Lock speed",
        reading_a="1 second",
        reading_b="3 seconds",
        source_phrase="quickly",
        severity="high",
        suggested_rewrite="a clear rewrite",
    )


def test_compare_prompt_contains_facts() -> None:
    facts = format_number_facts(match_numbers(*_real_readers()))
    system, user = duel_compare_prompt(STORY, "{}", "{}", number_facts=facts)
    _, marker, tail = user.partition("FACTS COMPUTED BY CODE")
    assert marker
    assert facts in tail
    assert "-> SAME" in facts
    assert "-> DIFFERENT" in facts
    assert "Values marked SAME in the facts are agreements, not forks" in system


def test_drop_false_fork_real_run() -> None:
    matches = match_numbers(*_real_readers())
    comparison = DuelComparison(forks=[_false_fork()], agreements=[])
    cleaned, notes = drop_false_forks(comparison, matches)
    assert cleaned.forks == []
    assert len(notes) == 1
    assert "30 minutes" in notes[0]
    assert "Account lock behavior and duration" in notes[0]
    # The input is left alone.
    assert len(comparison.forks) == 1


def test_keep_real_fork() -> None:
    matches = match_numbers(*_real_readers())
    fork = _real_fork()
    cleaned, notes = drop_false_forks(DuelComparison(forks=[fork]), matches)
    assert cleaned.forks == [fork]
    assert notes == []


def _real_run_generate(captured: list | None = None):
    reading_a, reading_b = _real_readers()

    def _generate(keys, system, user, schema):
        if schema.__name__ == "Interpretation":
            return (reading_a if "strictest" in system else reading_b), 0, []
        if captured is not None:
            captured.append(user)
        comparison = DuelComparison(
            forks=[_false_fork(), _real_fork()],
            agreements=[
                "Both readers agree the shopper must be registered.",
                "Both readers agree a visible message is shown.",
            ],
        )
        return comparison, 0, []

    return _generate


def test_run_duel_real_run_shape() -> None:
    result = run_duel(KEYS, STORY, "", "", generate=_real_run_generate())
    assert len(result.comparison.forks) == 1
    assert result.comparison.forks[0].topic == "Lock speed"
    assert len(result.number_matches) == 3
    # 2 AI agreements + 2 code-matched same values, against 1 fork.
    assert result.agreement_pct == 80
    assert any("30 minutes" in note for note in result.notes)


def test_matches_computed_before_compare() -> None:
    captured: list = []
    run_duel(KEYS, STORY, "", "", generate=_real_run_generate(captured))
    assert len(captured) == 1
    assert "-> DIFFERENT" in captured[0]
