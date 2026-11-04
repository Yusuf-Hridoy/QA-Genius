"""A whole report, carried in the part of a URL the server never sees.

There is no database here and there is not going to be one. A report link
is the answer itself, squeezed and written after a `#`, so the page can
draw it and the server learns nothing: a fragment is never sent in an HTTP
request. Nobody has to be logged in, nothing expires, and deleting the
link deletes the report.

The same packing is what lets an agent be told what it has fixed. It sends
back the link it was given, we unpack the problem ids that were in it, and
compare. No session, no storage, no memory of anyone.
"""

from __future__ import annotations

import base64
import binascii
import json
import zlib
from dataclasses import dataclass

# What goes in front of the data, so a link from a future shape can be
# told apart from a broken one rather than half-read.
PREFIX = "v1."
# Everything real is served over TLS. A developer running the app on their
# own machine is not, and an https link to localhost opens nothing.
SCHEME = "https"
LOCAL_SCHEME = "http"
LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]", "::1", "0.0.0.0")

# Past this, the inputs are dropped and only the findings travel. A link
# nobody can paste into a chat message is not a link.
MAX_PACKED = 60 * 1024
# What we will hand back out of an inflate, however small the input was.
# A few hundred bytes of the right zeros expand forever otherwise.
MAX_UNPACKED = 2 * 1024 * 1024
# The text we are willing to read at all, before any of this starts.
MAX_LINK = 200_000

TOO_BIG_NOTE = (
    "Too big to pack everything into a link — open the desks to see all tests."
)
BROKEN = "That report link is broken or was not made by QA-Genius."


class LinkTrouble(Exception):
    """A link we will not read, said in one sentence."""


def _deflate_raw(data: bytes) -> bytes:
    """Raw deflate: no zlib header, no checksum. The browser inflates it."""
    maker = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    return maker.compress(data) + maker.flush()


def _inflate_raw(data: bytes) -> bytes:
    """Back again, refusing to grow past what a report could ever be."""
    taker = zlib.decompressobj(-zlib.MAX_WBITS)
    out = taker.decompress(data, MAX_UNPACKED)
    if taker.unconsumed_tail:
        raise LinkTrouble(BROKEN)
    return out


def _b64(data: bytes) -> str:
    """base64url with the padding taken off: it is going in a URL."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode(text + padding)
    except (binascii.Error, ValueError) as bad:
        raise LinkTrouble(BROKEN) from bad


def pack(data: dict) -> str:
    """One report as the text that goes after the `#`."""
    raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return PREFIX + _b64(_deflate_raw(raw.encode("utf-8")))


def unpack(text: str) -> dict:
    """The report back out of that text, or LinkTrouble.

    Everything that comes out of here is data somebody else wrote. It is
    read, never run, and the page that draws it puts every string on the
    screen as text.
    """
    said = str(text or "").strip()
    if len(said) > MAX_LINK:
        raise LinkTrouble("That report link is too long to read.")
    # A whole URL, a fragment, or just the data: all three are what people
    # paste, so all three are read.
    if "#" in said:
        said = said.partition("#")[2]
    if not said.startswith(PREFIX):
        raise LinkTrouble(BROKEN)
    try:
        raw = _inflate_raw(_unb64(said[len(PREFIX) :]))
    except zlib.error as bad:
        raise LinkTrouble(BROKEN) from bad
    if len(raw) >= MAX_UNPACKED:
        raise LinkTrouble("That report link holds more than a report should.")
    try:
        found = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as bad:
        raise LinkTrouble(BROKEN) from bad
    if not isinstance(found, dict):
        raise LinkTrouble(BROKEN)
    return found


# ──────────────────────────────────────────────────────────────────────────────
# Where the link points
# ──────────────────────────────────────────────────────────────────────────────

# A host we will put in a link. Anything else and we use the configured
# site instead: a link is something a person clicks, and a host somebody
# else chose is how a tool result becomes a phishing page.
_SAFE_HOST = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-:[]"
)


def safe_host(host: str) -> str:
    """The host, if it is one we would put in a link. Otherwise nothing."""
    said = str(host or "").strip()
    # Only the first, when a proxy chain has left several.
    said = said.split(",")[0].strip()
    if not said or len(said) > 253:
        return ""
    if not set(said) <= _SAFE_HOST:
        return ""
    return said


def link_for(host: str, data: dict) -> tuple[str, str]:
    """The report link for this answer, and the note when it had to be cut.

    Over the size limit the inputs are dropped and the findings go on
    their own, because a report with no tests in it still tells the reader
    what is wrong — and a link too long to send tells them nothing.
    """
    where = safe_host(host)
    if not where:
        return "", ""
    packed = pack(data)
    note = ""
    if len(packed) > MAX_PACKED:
        packed = pack(_findings_only(data))
        note = TOO_BIG_NOTE
    return f"{scheme_for(where)}://{where}/report#{packed}", note


def scheme_for(host: str) -> str:
    """http for a machine you are sitting at, https for everything else.

    An IPv6 host wears brackets — "[::1]:8000" — so the port is cut off
    after the closing bracket rather than at the first colon, which in
    that spelling is part of the address.
    """
    said = str(host or "").strip().lower()
    if said.startswith("["):
        name = said.partition("]")[0] + "]"
    else:
        name = said.partition(":")[0]
    return LOCAL_SCHEME if name in LOCAL_HOSTS else SCHEME


# What a report keeps when it will not all fit: who it is about and what
# is wrong with it, and none of the material those findings came from.
_FINDINGS_KEYS = (
    "schema_version",
    "tool",
    "summary",
    "problems",
    "ask_the_po",
    "notes",
    "decision",
    "grade",
    "checks",
    "path_to_ready",
    "fixed_since_last_check",
    "fixed_said",
    "still_open",
    "story_label",
)


def _findings_only(data: dict) -> dict:
    kept = {name: data[name] for name in _FINDINGS_KEYS if name in data}
    kept["report_note"] = TOO_BIG_NOTE
    return kept


# ──────────────────────────────────────────────────────────────────────────────
# What changed since last time
# ──────────────────────────────────────────────────────────────────────────────


def problem_ids(report: dict) -> list[str]:
    """Every problem id in an unpacked report, in the order it listed them."""
    return list(said_by_id(report))


def said_by_id(report: dict) -> dict[str, str]:
    """id -> what that problem said, out of an unpacked report.

    The ids alone are enough to count a round. They are not enough to show
    one: "L-ff63 · Fixed" tells a reader nothing they can check. The
    sentence travels so the report page can say what was fixed.
    """
    found: dict[str, str] = {}
    for problem in report.get("problems") or []:
        if not isinstance(problem, dict):
            continue
        name = str(problem.get("id") or "").strip()
        if name and name not in found:
            found[name] = str(problem.get("says") or "")
    return found


@dataclass(frozen=True)
class Rounds:
    """What changed between the last report and this one."""

    fixed: list[str]
    still_open: list[str]
    # id -> what the problem said last time, for the ones now fixed.
    fixed_said: dict[str, str]


def compare(previous_link: str, now: list[str]) -> Rounds:
    """What is gone since the last report, and what is still here.

    A link we cannot read is not an error: the agent gets an answer about
    this round either way, and a round it cannot be told about is better
    than a refusal it cannot act on.
    """
    if not str(previous_link or "").strip():
        return Rounds([], [], {})
    try:
        before = said_by_id(unpack(previous_link))
    except LinkTrouble:
        return Rounds([], [], {})
    here = set(now)
    fixed = [one for one in before if one not in here]
    return Rounds(
        fixed=fixed,
        still_open=[one for one in before if one in here],
        fixed_said={one: before[one] for one in fixed},
    )
