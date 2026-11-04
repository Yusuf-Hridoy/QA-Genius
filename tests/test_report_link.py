"""The report link: a whole report carried where the server never sees it.

Everything after a `#` stays in the browser — it is not sent with the
request. That is the only reason this app can hand somebody a shareable
report while storing nothing, so these tests guard both halves: that it
packs and unpacks faithfully, and that nothing we would not want to read
gets read.
"""

import json

import pytest

from qagenius.mcp_server import tools
from qagenius.mcp_server.report_link import (
    MAX_PACKED,
    PREFIX,
    TOO_BIG_NOTE,
    LinkTrouble,
    compare,
    link_for,
    pack,
    problem_ids,
    safe_host,
    scheme_for,
    unpack,
)
from qagenius.mcp_server.schemas import TestsIn

HOST = "qa-genius-ashy.vercel.app"

SUITE = {
    "story": "As a shopper I want my account locked after wrong passwords.",
    "criteria": [
        {"text": "The account locks after 5 consecutive incorrect password attempts"},
        {"text": "A locked account stays locked for 30 minutes"},
    ],
    "test_cases": [
        {
            "id": "TC-1",
            "title": "Locks on the fifth wrong password",
            "steps": ["Open sign-in", "Enter a wrong password five times"],
            "expected": "The page shows: Account locked for 30 minutes",
            "test_data": "attempts=5",
            "covers": ["AC-1"],
            "kind": "at the limit",
        }
    ],
}


# ──────────────────────────────────────────────────────────────────────────────
# Packing
# ──────────────────────────────────────────────────────────────────────────────


def test_what_goes_in_comes_back_out():
    data = {"tool": "review_tests", "problems": [{"id": "L-1234"}], "notes": ["hi"]}
    assert unpack(pack(data)) == data


def test_the_packed_text_is_url_safe():
    packed = pack({"story": "A café, a naïve “quote” & a + and a /"})
    assert packed.startswith(PREFIX)
    body = packed[len(PREFIX) :]
    assert set(body) <= set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    )


def test_unicode_survives_the_round_trip():
    data = {"summary": "2 to fix · “quickly” · café — naïve"}
    assert unpack(pack(data)) == data


def test_packing_actually_makes_it_smaller():
    # A report is repetitive text; if this ever stopped helping, the links
    # would quietly get too long to paste.
    data = {"notes": ["the account locks after five wrong passwords"] * 50}
    raw = len(json.dumps(data))
    assert len(pack(data)) < raw / 2


def test_a_whole_url_a_fragment_or_the_data_all_read():
    packed = pack({"tool": "check_story"})
    assert unpack(packed)["tool"] == "check_story"
    assert unpack(f"#{packed}")["tool"] == "check_story"
    assert unpack(f"https://host/report#{packed}")["tool"] == "check_story"


# ──────────────────────────────────────────────────────────────────────────────
# What we refuse to read
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "nope", "v1.", "v1.zzzz", "v2.abcd", "https://x/report#v2.abc"],
)
def test_bad_data_is_refused_in_one_sentence(bad):
    with pytest.raises(LinkTrouble) as trouble:
        unpack(bad)
    assert str(trouble.value).strip()
    assert "Traceback" not in str(trouble.value)


def test_a_link_longer_than_we_would_ever_make_is_refused():
    with pytest.raises(LinkTrouble):
        unpack(PREFIX + "A" * 200_001)


def test_something_that_inflates_forever_is_refused():
    # A few hundred bytes of the right zeros become gigabytes otherwise.
    import zlib

    maker = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    bomb = maker.compress(b"\0" * (8 * 1024 * 1024)) + maker.flush()
    import base64

    text = PREFIX + base64.urlsafe_b64encode(bomb).decode().rstrip("=")
    with pytest.raises(LinkTrouble):
        unpack(text)


def test_valid_deflate_that_is_not_json_is_refused():
    import base64
    import zlib

    maker = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    raw = maker.compress(b"not json at all") + maker.flush()
    with pytest.raises(LinkTrouble):
        unpack(PREFIX + base64.urlsafe_b64encode(raw).decode().rstrip("="))


def test_json_that_is_not_an_object_is_refused():
    with pytest.raises(LinkTrouble):
        unpack(pack([1, 2, 3]))  # type: ignore[arg-type]


# ──────────────────────────────────────────────────────────────────────────────
# Where the link points
# ──────────────────────────────────────────────────────────────────────────────


def test_a_plain_host_is_used():
    assert safe_host("qa-genius-ashy.vercel.app") == "qa-genius-ashy.vercel.app"
    assert safe_host("localhost:8000") == "localhost:8000"


def test_only_the_first_host_of_a_proxy_chain():
    assert safe_host("first.example, second.example") == "first.example"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "   ",
        "evil.example/path",
        "host with spaces",
        "host\nInjected: header",
        'host"',
        "a" * 300,
    ],
)
def test_a_host_we_would_not_put_in_a_link_is_dropped(bad):
    assert safe_host(bad) == ""


def test_no_host_means_no_link_rather_than_a_broken_one():
    link, note = link_for("", {"tool": "check_story"})
    assert link == ""
    assert note == ""


def test_the_link_points_at_the_report_page():
    link, _ = link_for(HOST, {"tool": "check_story"})
    assert link.startswith(f"https://{HOST}/report#{PREFIX}")


@pytest.mark.parametrize(
    "host", ["localhost:8000", "127.0.0.1:8000", "127.0.0.1", "[::1]:8000", "localhost"]
)
def test_a_machine_you_are_sitting_at_gets_a_plain_http_link(host):
    # An https link to a dev server opens nothing at all.
    assert scheme_for(host) == "http"
    link, _ = link_for(host, {"tool": "check_story"})
    assert link.startswith(f"http://{host}/report#")


@pytest.mark.parametrize(
    "host", ["qa-genius-ashy.vercel.app", "example.com:8443", "localhost.evil.com"]
)
def test_everything_else_gets_https(host):
    assert scheme_for(host) == "https"


def test_a_hostile_host_header_never_reaches_the_link():
    link, _ = link_for("attacker.example/evil?", {"tool": "check_story"})
    assert link == ""


# ──────────────────────────────────────────────────────────────────────────────
# When it will not all fit
# ──────────────────────────────────────────────────────────────────────────────


def _huge() -> dict:
    """A report at the published limits, written so it does not squeeze flat.

    Real test cases are all different from each other. A fixture that
    repeats one sentence 900 times compresses to nothing and proves the
    opposite of what this is here to prove.
    """
    import random
    import string

    rng = random.Random(7)

    def words(count: int) -> str:
        return " ".join(
            "".join(rng.choices(string.ascii_lowercase, k=rng.randint(3, 10)))
            for _ in range(count)
        )

    return {
        "schema_version": "1.0",
        "tool": "review_tests",
        "summary": "lots",
        "problems": [{"id": f"D-{n:04x}", "says": words(12)} for n in range(20)],
        "notes": ["a note"],
        "ask_the_po": [],
        "criteria": [{"id": f"AC-{n + 1}", "text": words(18)} for n in range(60)],
        "test_cases": [
            {
                "id": f"TC-{n:03d}",
                "title": words(10),
                "steps": [words(12) for _ in range(6)],
                "expected": words(14),
                "test_data": words(6),
            }
            for n in range(300)
        ],
    }


def test_an_oversize_report_drops_the_inputs_and_says_so():
    link, note = link_for(HOST, _huge())
    assert note == TOO_BIG_NOTE
    packed = link.partition("#")[2]
    assert len(packed) <= MAX_PACKED
    found = unpack(packed)
    assert "test_cases" not in found
    assert found["problems"]
    assert found["summary"] == "lots"
    assert found["report_note"] == TOO_BIG_NOTE


def test_a_normal_report_keeps_everything_and_says_nothing():
    link, note = link_for(HOST, {"tool": "review_tests", **SUITE})
    assert note == ""
    found = unpack(link)
    assert len(found["test_cases"]) == 1


# ──────────────────────────────────────────────────────────────────────────────
# What changed since last time
# ──────────────────────────────────────────────────────────────────────────────


def test_problem_ids_come_back_in_order_without_repeats():
    report = {"problems": [{"id": "A-1"}, {"id": "B-2"}, {"id": "A-1"}, {}]}
    assert problem_ids(report) == ["A-1", "B-2"]


def test_fixed_and_still_open_are_worked_out_from_the_old_link():
    before = pack(
        {
            "problems": [
                {"id": "A-1", "says": "AC-1 has no tests yet."},
                {"id": "B-2", "says": "Two tests are the same test."},
                {"id": "C-3", "says": "Nobody decided what happens at $50."},
            ]
        }
    )
    rounds = compare(before, ["B-2", "D-4"])
    assert rounds.fixed == ["A-1", "C-3"]
    assert rounds.still_open == ["B-2"]


def test_what_a_fixed_problem_used_to_say_travels_with_its_id():
    # "L-ff63 · Fixed" on its own is a row nobody can check.
    before = pack({"problems": [{"id": "A-1", "says": "AC-1 has no tests yet."}]})
    rounds = compare(before, [])
    assert rounds.fixed_said == {"A-1": "AC-1 has no tests yet."}


def test_no_previous_link_means_no_claims_either_way():
    rounds = compare("", ["A-1"])
    assert (rounds.fixed, rounds.still_open, rounds.fixed_said) == ([], [], {})


def test_a_previous_link_we_cannot_read_is_not_an_error():
    # The agent still gets an answer about this round. A refusal it cannot
    # act on would be worse than a round it is not told about.
    rounds = compare("v1.rubbish", ["A-1"])
    assert (rounds.fixed, rounds.still_open) == ([], [])


# ──────────────────────────────────────────────────────────────────────────────
# Through the tools
# ──────────────────────────────────────────────────────────────────────────────


def test_every_tool_answer_carries_a_link_to_its_own_report():
    answer = tools.review_tests(TestsIn.model_validate(SUITE), HOST)
    assert answer.report_link.startswith(f"https://{HOST}/report#")
    found = unpack(answer.report_link)
    assert found["tool"] == "review_tests"
    assert found["summary"] == answer.summary
    assert [one["id"] for one in found["problems"]] == [
        one.id for one in answer.problems
    ]


def test_the_link_carries_what_the_page_needs_to_show_the_findings():
    answer = tools.review_tests(TestsIn.model_validate(SUITE), HOST)
    found = unpack(answer.report_link)
    assert found["story"] == SUITE["story"]
    assert len(found["criteria"]) == 2
    assert len(found["test_cases"]) == 1


def test_the_link_does_not_carry_a_link_to_itself():
    answer = tools.review_tests(TestsIn.model_validate(SUITE), HOST)
    found = unpack(answer.report_link)
    assert "report_link" not in found


def test_no_host_means_the_answer_simply_has_no_link():
    answer = tools.review_tests(TestsIn.model_validate(SUITE))
    assert answer.report_link == ""
    assert answer.problems


def test_a_second_round_says_what_was_fixed():
    first = tools.review_tests(TestsIn.model_validate(SUITE), HOST)
    assert first.problems

    better = dict(SUITE)
    better["test_cases"] = [
        *SUITE["test_cases"],
        *[one.model_dump() for one in first.add_tests],
        {
            "id": "TC-90",
            "title": "A fourth wrong password does not lock the account",
            "steps": ["Open sign-in", "Enter a wrong password four times", "Sign in"],
            "expected": "The shopper is signed in and no lock message is shown",
            "test_data": "attempts=4",
            "covers": ["AC-1"],
            "kind": "at the limit",
        },
        {
            "id": "TC-91",
            "title": "Still locked after 29 minutes",
            "steps": ["Lock the account", "Wait 29 minutes", "Enter the right password"],
            "expected": "The page shows: Account locked for 30 minutes",
            "test_data": "wait=29 minutes",
            "covers": ["AC-2"],
            "kind": "at the limit",
        },
    ]
    better["previous_report_link"] = first.report_link

    second = tools.review_tests(TestsIn.model_validate(better), HOST)
    was = {one.id for one in first.problems}
    assert set(second.fixed_since_last_check) <= was
    assert second.fixed_since_last_check
    assert set(second.still_open) == was & {one.id for one in second.problems}


def test_a_problem_that_is_still_there_is_listed_as_still_open():
    first = tools.review_tests(TestsIn.model_validate(SUITE), HOST)
    again = dict(SUITE)
    again["previous_report_link"] = first.report_link
    second = tools.review_tests(TestsIn.model_validate(again), HOST)
    # Nothing changed, so nothing is fixed and everything is still open.
    assert second.fixed_since_last_check == []
    assert set(second.still_open) == {one.id for one in first.problems}


def test_the_round_fields_are_empty_without_a_previous_link():
    answer = tools.review_tests(TestsIn.model_validate(SUITE), HOST)
    assert answer.fixed_since_last_check == []
    assert answer.still_open == []


def test_a_previous_link_does_not_change_what_the_tool_finds():
    plain = tools.review_tests(TestsIn.model_validate(SUITE), HOST)
    with_link = dict(SUITE)
    with_link["previous_report_link"] = plain.report_link
    again = tools.review_tests(TestsIn.model_validate(with_link), HOST)
    assert [one.id for one in again.problems] == [one.id for one in plain.problems]
    assert again.summary == plain.summary
