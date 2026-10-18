"""Load and validate the rule packs in qagenius/shadow_qa/packs/*.toml.

One pack is one kind of feature. The owner adds his own by dropping another
TOML file in that folder, so everything a pack may say is checked here and a
bad file names itself in the error.
"""

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PACKS_DIR = Path(__file__).resolve().parent / "packs"

SEVERITIES = ("high", "medium", "low")
# The four categories the rest of QA-Genius counts by, written their way.
TEST_CATEGORIES = ("Functional", "Negative", "Boundary", "Edge Case")
TEST_PRIORITIES = ("High", "Medium", "Low")
MIN_SCORE, MAX_SCORE = 1, 5

# high first: an uncovered high-severity check is added before a low one.
SEVERITY_RANK = {name: index for index, name in enumerate(SEVERITIES)}


class PackError(ValueError):
    """A rule pack that cannot be trusted. The message always names the file."""


@dataclass(frozen=True)
class CheckTest:
    """The test case a check turns into when the AI did not write one."""

    title: str
    category: str
    priority: str
    pre_conditions: str
    steps: tuple[str, ...]
    expected_result: str
    test_data: str


@dataclass(frozen=True)
class Check:
    """One thing a principal QA would insist on for this kind of feature."""

    id: str  # "login.email_case"
    short_id: str  # "email_case"
    pack_id: str
    title: str
    severity: str
    why: str
    covered_if: tuple[str, ...]
    test: CheckTest


@dataclass(frozen=True)
class PackRisk:
    """A classic failure mode for this kind of feature, ready for Risk radar."""

    pack_id: str
    title: str
    category: str
    severity: int
    likelihood: int
    detectability: int
    effect: str
    cause: str
    covered_if: tuple[str, ...]

    @property
    def rpn(self) -> int:
        return self.severity * self.likelihood * self.detectability


@dataclass(frozen=True)
class Pack:
    id: str
    name: str
    short: str  # two words at most: what the epic banner shows as a pill
    # A strong trigger is a word that only this kind of feature uses, so one
    # is enough. A weak trigger is a word half the stories in the world
    # contain -- "email", "list", "file" -- so it needs company: two different
    # weak triggers, or one in the story itself rather than only in a
    # criterion. See detect.py.
    triggers: tuple[str, ...]
    weak_triggers: tuple[str, ...]
    exclude: tuple[str, ...]
    checks: tuple[Check, ...]
    risks: tuple[PackRisk, ...]


def _fail(file_name: str, message: str) -> None:
    raise PackError(f"{file_name}: {message}")


def _text(raw: object, file_name: str, where: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        _fail(file_name, f"{where} must be a non-empty string")
    return str(raw).strip()


def _words(raw: object, file_name: str, where: str, required: bool = True) -> tuple[str, ...]:
    if raw is None and not required:
        return ()
    if not isinstance(raw, list) or any(not isinstance(one, str) for one in raw):
        _fail(file_name, f"{where} must be a list of strings")
    items = tuple(one.strip() for one in raw if str(one).strip())
    if required and not items:
        _fail(file_name, f"{where} must not be empty")
    return items


def _score(raw: object, file_name: str, where: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        _fail(file_name, f"{where} must be a whole number {MIN_SCORE}-{MAX_SCORE}")
    if not MIN_SCORE <= int(raw) <= MAX_SCORE:
        _fail(file_name, f"{where} must be {MIN_SCORE}-{MAX_SCORE}, not {raw}")
    return int(raw)


def _check_test(raw: object, file_name: str, where: str) -> CheckTest:
    if not isinstance(raw, dict):
        _fail(file_name, f"{where} needs a [checks.test] table")
    steps = _words(raw.get("steps"), file_name, f"{where}.steps")
    if len(steps) < 2:
        _fail(file_name, f"{where}.steps needs at least 2 steps")
    category = _text(raw.get("category"), file_name, f"{where}.category")
    if category not in TEST_CATEGORIES:
        _fail(
            file_name,
            f"{where}.category must be one of {' | '.join(TEST_CATEGORIES)}, "
            f"not {category!r}",
        )
    priority = _text(raw.get("priority"), file_name, f"{where}.priority")
    if priority not in TEST_PRIORITIES:
        _fail(
            file_name,
            f"{where}.priority must be one of {' | '.join(TEST_PRIORITIES)}, "
            f"not {priority!r}",
        )
    return CheckTest(
        title=_text(raw.get("title"), file_name, f"{where}.title"),
        category=category,
        priority=priority,
        pre_conditions=_text(raw.get("pre_conditions"), file_name, f"{where}.pre_conditions"),
        steps=steps,
        expected_result=_text(raw.get("expected_result"), file_name, f"{where}.expected_result"),
        test_data=_text(raw.get("test_data"), file_name, f"{where}.test_data"),
    )


def _check(raw: object, pack_id: str, file_name: str, index: int) -> Check:
    where = f"checks[{index}]"
    if not isinstance(raw, dict):
        _fail(file_name, f"{where} must be a table")
    short_id = _text(raw.get("id"), file_name, f"{where}.id")
    where = f"check {short_id!r}"
    severity = _text(raw.get("severity"), file_name, f"{where}.severity").lower()
    if severity not in SEVERITIES:
        _fail(
            file_name,
            f"{where}.severity must be one of {' | '.join(SEVERITIES)}, not {severity!r}",
        )
    return Check(
        id=f"{pack_id}.{short_id}",
        short_id=short_id,
        pack_id=pack_id,
        title=_text(raw.get("title"), file_name, f"{where}.title"),
        severity=severity,
        why=_text(raw.get("why"), file_name, f"{where}.why"),
        covered_if=_words(raw.get("covered_if"), file_name, f"{where}.covered_if"),
        test=_check_test(raw.get("test"), file_name, where),
    )


def _risk(raw: object, pack_id: str, file_name: str, index: int) -> PackRisk:
    where = f"risks[{index}]"
    if not isinstance(raw, dict):
        _fail(file_name, f"{where} must be a table")
    title = _text(raw.get("title"), file_name, f"{where}.title")
    where = f"risk {title!r}"
    return PackRisk(
        pack_id=pack_id,
        title=title,
        category=_text(raw.get("category"), file_name, f"{where}.category"),
        severity=_score(raw.get("severity"), file_name, f"{where}.severity"),
        likelihood=_score(raw.get("likelihood"), file_name, f"{where}.likelihood"),
        detectability=_score(raw.get("detectability"), file_name, f"{where}.detectability"),
        effect=_text(raw.get("effect"), file_name, f"{where}.effect"),
        cause=_text(raw.get("cause"), file_name, f"{where}.cause"),
        covered_if=_words(raw.get("covered_if"), file_name, f"{where}.covered_if"),
    )


def _pack(data: dict, file_name: str) -> Pack:
    pack_id = _text(data.get("id"), file_name, "id")
    raw_checks = data.get("checks")
    if not isinstance(raw_checks, list) or not raw_checks:
        _fail(file_name, "a pack needs at least one [[checks]] entry")
    checks: list[Check] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_checks):
        check = _check(raw, pack_id, file_name, index)
        if check.short_id in seen:
            _fail(file_name, f"check id {check.short_id!r} is used twice")
        seen.add(check.short_id)
        checks.append(check)

    raw_risks = data.get("risks") or []
    if not isinstance(raw_risks, list):
        _fail(file_name, "risks must be a list of [[risks]] tables")
    risks = [_risk(raw, pack_id, file_name, index) for index, raw in enumerate(raw_risks)]

    name = _text(data.get("name"), file_name, "name")
    strong = _words(data.get("triggers"), file_name, "triggers", required=False)
    weak = _words(data.get("weak_triggers"), file_name, "weak_triggers", required=False)
    if not strong and not weak:
        _fail(file_name, "a pack needs at least one trigger or weak_trigger")
    shared = {one.lower() for one in strong} & {one.lower() for one in weak}
    if shared:
        _fail(file_name, f"{sorted(shared)[0]!r} is both a trigger and a weak_trigger")
    return Pack(
        id=pack_id,
        name=name,
        short=_text(data.get("short"), file_name, "short") if data.get("short") else name,
        triggers=strong,
        weak_triggers=weak,
        exclude=_words(data.get("exclude"), file_name, "exclude", required=False),
        checks=tuple(checks),
        risks=tuple(risks),
    )


def read_pack(path: Path) -> Pack:
    """One pack from one file. Raises PackError naming the file when it is wrong."""
    file_name = path.name
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        raise PackError(f"{file_name}: not valid TOML — {error}") from error
    return _pack(data, file_name)


@lru_cache(maxsize=1)
def load_packs() -> list[Pack]:
    """Every pack in the packs folder, by id. Cached: the files never change at runtime.

    The returned list is shared, so treat it as read-only.
    """
    packs: list[Pack] = []
    by_id: dict[str, str] = {}
    for path in sorted(PACKS_DIR.glob("*.toml")):
        pack = read_pack(path)
        if pack.id in by_id:
            raise PackError(
                f"{path.name}: pack id {pack.id!r} is already used by {by_id[pack.id]}"
            )
        by_id[pack.id] = path.name
        packs.append(pack)
    packs.sort(key=lambda pack: pack.id)
    return packs


def all_checks() -> list[Check]:
    """Every check of every pack, in pack order."""
    return [check for pack in load_packs() for check in pack.checks]


def check_by_id(check_id: str) -> Check | None:
    wanted = str(check_id or "").strip().lower()
    for check in all_checks():
        if check.id.lower() == wanted:
            return check
    return None
