"""Performance budget built by code from criteria and risks. No AI.

A chat model guesses performance numbers. This reads the ones the team already
wrote down -- "routes within 200ms", "below 768 pixels" -- and fills the rest
with the published Core Web Vitals thresholds, labelling every line with where
its number came from. Nothing here calls a model.
"""

import re
from dataclasses import dataclass, field

from qagenius.models import RiskAnalysis, TestCase
from qagenius.test_cases import number_criteria, traced_ids

METRICS = {  # id -> (label, unit, default limit, PSI-measurable)
    "lcp": ("Largest contentful paint (LCP)", "ms", 2500, True),
    "inp": ("Interaction to next paint (INP)", "ms", 200, True),
    "cls": ("Cumulative layout shift (CLS)", "", 0.1, True),
    "fcp": ("First contentful paint (FCP)", "ms", 1800, True),
    "ttfb": ("Server response time (TTFB)", "ms", 800, True),
    "weight": ("Page weight", "KB", 1600, True),
}
DEFAULT_SOURCE = "Core Web Vitals 'good' threshold"
# Page weight is not a Core Web Vital, so it does not get to claim one.
WEIGHT_SOURCE = "Common web budget"

# A label long enough to recognise, short enough for a table cell.
MAX_CUSTOM_LABEL = 60


@dataclass(frozen=True)
class BudgetLine:
    id: str  # "lcp" … or "custom-1" for non-measurable lines
    label: str
    limit: float | None  # in the metric's unit; None for custom lines with no number
    unit: str  # "ms" | "KB" | "" | "px" | "s" for custom
    source: str  # "AC-2" | "Risk R4" | DEFAULT_SOURCE
    source_text: str  # the phrase that produced it ("" for defaults)
    measurable: bool  # False for custom lines (e.g. "no clipping at 768 px")
    covered_by: list[str] = field(default_factory=list)  # TC ids, for custom lines


@dataclass(frozen=True)
class Budget:
    lines: list[BudgetLine]
    gaps: list[str]


# ──────────────────────────────────────────────────────────────────────────────
# Reading numbers out of a requirement
# ──────────────────────────────────────────────────────────────────────────────

# A sentence ends at . ; or a newline. Gherkin's Given/When/Then arrive as
# separate lines, so each step is judged on its own words. A dot between two
# digits is a decimal point, not a full stop - "1.2 MB" is one number.
_SENTENCE = re.compile(r"(?<!\d)[.;](?!\d)|\n+")

# "within 200ms", "in under 2 seconds", "smaller than 1.2 MB", "below 768 pixels".
# The qualifier is part of the phrase, because "within 200ms" is what the
# requirement actually says and what the budget table quotes back.
_QUALIFIER = (
    r"in under|no larger than|no more than|no bigger than|less than|faster than|"
    r"smaller than|at most|within|under|below|in"
)
_UNITS = (
    r"milliseconds?|ms|seconds?|secs?|s|kilobytes?|kb|megabytes?|mb|pixels?|px"
)
_TARGET = re.compile(
    rf"(?:\b(?:{_QUALIFIER})\s+)?"
    rf"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>{_UNITS})(?![a-z])",
    re.IGNORECASE,
)

# CLS has no unit, so it is written bare: "CLS below 0.1", "layout shift under 0.1".
_CLS_WORDS = re.compile(r"cumulative layout shift|layout shift|\bcls\b", re.IGNORECASE)
_BARE_NUMBER = re.compile(r"\d*\.\d+|\d+")

_MS_UNITS = {"ms", "millisecond", "milliseconds"}
_S_UNITS = {"s", "sec", "secs", "second", "seconds"}
_KB_UNITS = {"kb", "kilobyte", "kilobytes"}
_MB_UNITS = {"mb", "megabyte", "megabytes"}
_PX_UNITS = {"px", "pixel", "pixels"}


def _word(*words: str) -> re.Pattern:
    """Whole words only: "reload" must not count as "load"."""
    return re.compile(r"\b(?:" + "|".join(words) + r")\b", re.IGNORECASE)


# Order matters. "routes … without a full page reload" is an interaction, and
# would read as a load if LCP were asked first.
_WEIGHT_WORDS = _word("size", "weight", "bundle", "download", "payload")
_FCP_WORDS = re.compile(r"first paint|first content", re.IGNORECASE)
_INP_WORDS = re.compile(
    r"respond to input|\b(?:click|clicks|tap|taps|route|routes|navigate|navigates|"
    r"switch|switches|interaction|press|presses|type|types)\b",
    re.IGNORECASE,
)
_TTFB_WORDS = re.compile(
    r"response time|\b(?:server|api|backend|ttfb|request|requests|endpoint)\b",
    re.IGNORECASE,
)
_LCP_WORDS = _word(
    "load", "loads", "loaded", "render", "renders", "display", "displays",
    "appear", "appears", "paint", "paints", "visible",
)


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE.split(str(text or "")) if part.strip()]


def _to_metric_unit(value: float, unit: str) -> tuple[float, str]:
    """The number in the unit the metric is budgeted in."""
    unit = unit.lower()
    if unit in _S_UNITS:
        return value * 1000, "ms"
    if unit in _MB_UNITS:
        return value * 1024, "KB"
    if unit in _KB_UNITS:
        return value, "KB"
    if unit in _PX_UNITS:
        return value, "px"
    return value, "ms"


def _metric_for(sentence: str, metric_unit: str) -> str:
    """Which budget line a number in this sentence belongs to."""
    if metric_unit == "KB" or _WEIGHT_WORDS.search(sentence):
        return "weight"
    if metric_unit == "px":
        return "custom"
    if _FCP_WORDS.search(sentence):
        return "fcp"
    if _CLS_WORDS.search(sentence):
        return "cls"
    if _INP_WORDS.search(sentence):
        return "inp"
    if _TTFB_WORDS.search(sentence):
        return "ttfb"
    if _LCP_WORDS.search(sentence):
        return "lcp"
    return "custom"


def _short(sentence: str) -> str:
    cleaned = " ".join(sentence.split())
    if len(cleaned) <= MAX_CUSTOM_LABEL:
        return cleaned
    return cleaned[: MAX_CUSTOM_LABEL - 1].rstrip() + "…"


def extract_targets(text: str) -> list[tuple[str, float, str, str]]:
    """Every performance number in the text.

    Returns (metric id or "custom", value in the metric's unit, the unit as
    written, the phrase that produced it). A number without a unit and without
    a CLS word is a count, not a target, and never appears here.
    """
    found: list[tuple[str, float, str, str]] = []
    for sentence in _sentences(text):
        consumed: list[tuple[int, int]] = []
        for match in _TARGET.finditer(sentence):
            consumed.append(match.span("value"))
            written = match.group("unit")
            value, metric_unit = _to_metric_unit(float(match.group("value")), written)
            metric = _metric_for(sentence, metric_unit)
            found.append((metric, value, written, match.group(0).strip()))
        # CLS is written without a unit, so it is read only from the numbers
        # the unit pass did not already claim.
        if not _CLS_WORDS.search(sentence):
            continue
        for match in _BARE_NUMBER.finditer(sentence):
            if any(start <= match.start() < end for start, end in consumed):
                continue
            found.append(("cls", float(match.group(0)), "", match.group(0)))
            break
    return found


# ──────────────────────────────────────────────────────────────────────────────
# Turning those numbers into a budget
# ──────────────────────────────────────────────────────────────────────────────


def human_value(value: float, unit: str) -> str:
    """How a reader would say the number: 4000 ms is "4 s"."""
    if unit == "ms" and value >= 1000:
        return f"{value / 1000:g} s"
    return f"{value:g} {unit}".strip()


def _default_source(metric_id: str) -> str:
    return WEIGHT_SOURCE if metric_id == "weight" else DEFAULT_SOURCE


def _sources(
    criteria: list[str], risk_analysis: RiskAnalysis | None
) -> list[tuple[str, str]]:
    """(source label, text to read) for every criterion and every risk."""
    rows = [(item.id, item.text) for item in number_criteria(criteria)]
    for risk in (risk_analysis.failure_modes if risk_analysis else []):
        text = " ".join([risk.title or "", risk.effect or "", risk.cause or ""])
        rows.append((f"Risk {risk.id}", text))
    return rows


def build_budget(
    criteria: list[str],
    risk_analysis: RiskAnalysis | None,
    cases: list[TestCase],
) -> Budget:
    """Every line of the budget, and every requirement that asked for nothing."""
    criteria = list(criteria or [])
    cases = list(cases or [])
    ac_ids = {item.id for item in number_criteria(criteria)}

    # metric id -> list of (value, source, phrase); custom targets keep their own list.
    claimed: dict[str, list[tuple[float, str, str]]] = {key: [] for key in METRICS}
    customs: list[tuple[float | None, str, str, str, str]] = []  # value, unit, label, source, phrase
    produced: set[str] = set()

    for source, text in _sources(criteria, risk_analysis):
        for metric, value, written, phrase in extract_targets(text):
            produced.add(source)
            if metric == "custom":
                sentence = next(
                    (one for one in _sentences(text) if phrase in one), phrase
                )
                unit = "px" if written.lower() in _PX_UNITS else "ms"
                label = (
                    f"Layout at {value:g} px"
                    if unit == "px"
                    else _short(sentence)
                )
                customs.append((value, unit, label, source, phrase))
            else:
                claimed[metric].append((value, source, phrase))

    lines: list[BudgetLine] = []
    gaps: list[str] = []

    for metric_id, (label, unit, default, measurable) in METRICS.items():
        targets = claimed[metric_id]
        if not targets:
            lines.append(
                BudgetLine(
                    id=metric_id,
                    label=label,
                    limit=default,
                    unit=unit,
                    source=_default_source(metric_id),
                    source_text="",
                    measurable=measurable,
                )
            )
            continue
        # The strictest number the team wrote down wins.
        value, source, phrase = min(targets, key=lambda row: row[0])
        lines.append(
            BudgetLine(
                id=metric_id,
                label=label,
                limit=value,
                unit=unit,
                source=source,
                source_text=phrase,
                measurable=measurable,
            )
        )
        # A looser number is still the agreement, so it stands - but it is not
        # what "good" means, and the page says so.
        if value > default:
            gaps.append(
                f"{source} allows {metric_id.upper()} {human_value(value, unit)} — looser "
                f'than the {human_value(default, unit)} "good" threshold.'
            )

    seen: set[tuple[str, float | None]] = set()
    for value, unit, label, source, phrase in customs:
        if (label, value) in seen:
            continue
        seen.add((label, value))
        covered = [
            case.id
            for case in cases
            if source in ac_ids and source in traced_ids(case, ac_ids)
        ]
        lines.append(
            BudgetLine(
                id=f"custom-{len(seen)}",
                label=label,
                limit=value,
                unit=unit,
                source=source,
                source_text=phrase,
                measurable=False,
                covered_by=covered,
            )
        )

    for risk in (risk_analysis.failure_modes if risk_analysis else []):
        if risk.category != "performance" or f"Risk {risk.id}" in produced:
            continue
        gaps.append(
            f'Risk {risk.id} "{risk.title}" is a performance risk with no target.'
        )

    return Budget(lines=lines, gaps=gaps)
