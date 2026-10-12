import base64
import html
import json
import logging
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ValidationError, field_validator

import openai
from markupsafe import Markup

from qagenius import automation, bug_report, duel, llm, risk_register_exports
from qagenius.automation_checks import CheckReport, check_project
from qagenius.automation_exports import build_zip
from qagenius.bug_report import BugInput, environment_text, reproducibility_text
from qagenius.bug_report_checks import Check, check_report, quality_score
from qagenius.bug_report_exports import to_jira, to_markdown
from qagenius.duel import NOT_STATED_A, NOT_STATED_B, DuelResult, build_highlights
from qagenius.models import (
    AmbiguityAnalysis,
    AutomationScript,
    BugReport,
    DuelComparison,
    FailureMode,
    Interpretation,
    QualityInsightSummary,
    RiskAnalysis,
    TestCase,
    TestCaseList,
)
from qagenius.insights_summary import clean_summary, facts_text, insights_prompt
from qagenius.numbers import match_numbers
from qagenius.prompts import (
    automation_prompt,
    bug_report_prompt,
    risk_radar_prompt,
    story_check_prompt,
    test_cases_prompt,
)
from qagenius.providers import PROVIDERS, get_provider, pick_default
from qagenius.report_parsers import ReportError, RunReport, parse_report
from qagenius.risk_radar import (
    MAX_RISKS,
    RiskReport,
    ScoredRisk,
    case_lines,
    clean_analysis,
    criteria_lines,
    score_risks,
)
from qagenius.test_case_depth import compute_depth
from qagenius.test_case_diff import diff_cases
from qagenius.test_case_exports import to_csv, to_xlsx
from qagenius.test_case_refine import (
    INSTRUCTION_LIMIT,
    MAX_CASES,
    add_risk_tags,
    merge_strengthened,
    refine_user_text,
    risk_instruction,
    strengthen_instruction,
)
from qagenius.test_cases import (
    COVERAGE_FOCUS_OPTIONS,
    Criterion,
    build_user_text,
    compute_counts,
    compute_coverage,
    number_criteria,
    traced_ids,
)
from qagenius.test_run_metrics import (
    Insights,
    compute_insights,
    insights_from_dict,
    insights_markdown,
    insights_to_dict,
)

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
SAMPLES_DIR = BASE_DIR / "samples"

STORY_LIMIT = 3000
CONTEXT_LIMIT = 1000
CRITERIA_LIMIT = 40
CRITERION_LIMIT = 1000
CURRENT_JSON_LIMIT = 200000
REFINE_MODES = ("strengthen", "instruction", "risks")
RISKS_JSON_LIMIT = 50000
SELECTED_JSON_LIMIT = 100000
EXPORT_BODY_LIMIT = 500000
BASE_URL_LIMIT = 200
SCREENSHOT_TYPES = ("image/png", "image/jpeg", "image/webp")
SCREENSHOT_LIMIT = 2 * 1024 * 1024
SCREENSHOT_ERROR = "Screenshot must be a PNG, JPG or WebP under 2 MB."
MAX_REPORTS = 5
REPORT_SIZE_LIMIT = 2 * 1024 * 1024
# Vercel's request body limit is about 4.5 MB, so the upload has to stay under it.
REPORT_TOTAL_LIMIT = 4 * 1024 * 1024
REPORT_LIMIT_ERROR = "Upload up to 5 files, 2 MB each, 4 MB in total."
FACTS_JSON_LIMIT = 300000
ANALYZE_AGAIN_ERROR = "Please analyze the reports again."
SAMPLE_REPORTS = ("nightly-chromium.xml", "nightly-firefox.json")
# The AI's kind, shown as a pill. Mirrors GroupInsight.kind in models.py.
KIND_PILLS = {
    "product bug": "bad",
    "test issue": "warn",
    "environment": "info",
    "unknown": "neutral",
}
# Starlette caps a form field at 1 MB, which a 2 MB screenshot exceeds once it is
# base64 (about 2.7 MB). Raised just for the bug form, still under Vercel's ~4.5 MB body.
FORM_PART_LIMIT = 4 * 1024 * 1024

app = FastAPI(title="QA-Genius v2")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
# Drawer + key panel live in base.html, rendered by every page.
templates.env.globals["providers"] = PROVIDERS


@app.get("/health")
def health() -> str:
    return "ok"


@app.get("/", include_in_schema=False)
def index() -> RedirectResponse:
    return RedirectResponse(url="/requirements/story")


@app.get("/requirements/story", response_class=HTMLResponse)
def story_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "story.html", {"active": "requirements"}
    )


@app.get("/keys", include_in_schema=False)
def keys_page() -> RedirectResponse:
    return RedirectResponse(url="/requirements/story?keys=open")


@app.get("/bugs", response_class=HTMLResponse)
def bugs_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "bug_desk.html",
        {"active": "bugs", "devices": bug_report.DEVICE_OPTIONS},
    )


@app.get("/insights", response_class=HTMLResponse)
def insights_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "insights.html", {"active": "insights"})


@app.get("/performance", response_class=HTMLResponse)
def performance_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "coming_soon.html", {"active": "performance", "page": "Performance"}
    )


class KeyTestRequest(BaseModel):
    provider: str = ""
    key: str = ""
    model: str = ""


class KeyTestSchema(BaseModel):
    ok: bool


@app.post("/api/keys/test")
def test_key(body: KeyTestRequest) -> dict:
    """Ask the model for {"ok": true} with one key. Never echoes the key."""
    provider = get_provider(body.provider)
    if provider is None or not body.key.strip():
        return {"ok": False, "error": "Pick a provider and paste a key."}
    try:
        key_entry: dict[str, str] = {
            "provider": body.provider,
            "key": body.key,
            "label": "test",
        }
        if llm.valid_model(body.model):
            key_entry["model"] = body.model
        result, _, _ = llm.generate_json(
            [key_entry],
            'Reply with exactly {"ok": true}.',
            'Reply with exactly {"ok": true}.',
            KeyTestSchema,
        )
    except llm.InvalidKeyError:
        return {
            "ok": False,
            "error": "That key was rejected. Check it and try again.",
        }
    except llm.AllKeysBusyError:
        return {"ok": False, "error": "The provider is busy. Try again in a minute."}
    except llm.ModelUnavailableError:
        return {
            "ok": False,
            "error": "That model isn't available right now. "
            "QA-Genius needs a model update.",
        }
    except (llm.ProviderError, llm.BadOutputError, llm.NoKeysError) as e:
        return {"ok": False, "error": str(e)}
    if not result.ok:
        return {"ok": False, "error": "Unexpected answer. Try again."}
    return {"ok": True}


class KeyModelsRequest(BaseModel):
    provider: str = ""
    key: str = ""


@app.post("/api/keys/models")
def key_models(body: KeyModelsRequest) -> dict:
    """List chat models one key can call. Never echoes or logs the key."""
    provider = get_provider(body.provider)
    if provider is None or not body.key.strip():
        return {"ok": False, "error": "Pick a provider and paste a key."}
    try:
        models = llm.list_chat_models(provider, body.key)
    except openai.OpenAIError as e:
        logger.warning(
            "%s model list failed (%s)", provider["short"], type(e).__name__
        )
        return {"ok": False, "error": llm.clean_reason(str(e), body.key)}
    except Exception:  # never leak unexpected details (or the key)
        logger.warning("%s model list failed", provider["short"])
        return {"ok": False, "error": "Could not list models. Try again."}
    return {
        "ok": True,
        "models": models,
        "suggested": pick_default(provider, models),
    }


def _request_keys(request: Request) -> list[dict[str, str]]:
    """Read the X-QAG-Keys header. Returns [] when missing or malformed."""
    try:
        data = json.loads(request.headers.get("x-qag-keys", ""))
    except (ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    keys = []
    for entry in data:
        if (
            isinstance(entry, dict)
            and entry.get("provider")
            and entry.get("key")
            and get_provider(str(entry["provider"])) is not None
        ):
            parsed: dict[str, str] = {
                "provider": str(entry["provider"]),
                "key": str(entry["key"]),
                "label": "",
            }
            if llm.valid_model(entry.get("model")):
                parsed["model"] = str(entry["model"])
            keys.append(parsed)
    return keys


def _error_card(
    request: Request, message: str, notes: list[str] | None = None
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "_error.html", {"message": message, "notes": notes or []}
    )


def _highlight_story(story: str, phrases: list[str]) -> str:
    """Escape the story, then wrap each vague phrase in <mark> in place.

    Case-insensitive; phrases not found are skipped; never nests marks.
    """
    marked: str = html.escape(story)
    for phrase in sorted(set(phrases), key=len, reverse=True):
        needle = html.escape(phrase)
        if not needle.strip():
            continue
        lower = marked.lower()
        start = lower.find(needle.lower())
        while start != -1:
            # skip matches already inside a <mark> region
            before = marked[:start]
            if before.count("<mark>") > before.count("</mark>"):
                start = lower.find(needle.lower(), start + 1)
                continue
            match = marked[start : start + len(needle)]
            marked = marked[:start] + "<mark>" + match + "</mark>" + marked[start + len(needle) :]
            break
    return marked


def _invest_rows(result: AmbiguityAnalysis) -> tuple[list[dict[str, str]], int]:
    dims = [
        ("Independent", result.invest_independent),
        ("Negotiable", result.invest_negotiable),
        ("Valuable", result.invest_valuable),
        ("Estimable", result.invest_estimable),
        ("Small", result.invest_small),
        ("Testable", result.invest_testable),
    ]
    rows = []
    passes = 0
    for name, value in dims:
        verdict = value.strip().upper()
        if verdict.startswith("PASS"):
            pill = "ok"
            short = "PASS"
            passes += 1
        elif verdict.startswith("PARTIAL"):
            pill = "warn"
            short = "PARTIAL"
        else:
            pill = "bad"
            short = "FAIL"
        rows.append({"name": name, "value": short, "pill": pill})
    return rows, passes


def _story_result_context(
    request: Request,
    story: str,
    result: AmbiguityAnalysis,
    notes: list[str],
    provider_name: str,
) -> dict:
    rows, passes = _invest_rows(result)
    return {
        "result": result,
        "clarity_score": max(0, 100 - result.ambiguity_score),
        "invest_rows": rows,
        "invest_passes": passes,
        "highlighted_story": _highlight_story(
            story, [vp.phrase for vp in result.vague_phrases]
        ),
        "acceptance_criteria": "\n\n".join(result.generated_acceptance_criteria),
        "criteria_list": result.generated_acceptance_criteria,
        "notes": notes,
        "provider_name": provider_name,
    }


def _highlight_duel_story(
    story: str, highlights: list[tuple[int, int, int]], forks: list
) -> Markup:
    """Escape the story, then wrap each highlight with a CSS-only tooltip."""
    valid = [
        (s, e, i)
        for s, e, i in highlights
        if isinstance(s, int)
        and isinstance(e, int)
        and 0 <= s < e <= len(story)
        and 0 <= i < len(forks)
    ]
    valid.sort(key=lambda item: item[0])
    deduped: list[tuple[int, int, int]] = []
    for item in valid:
        if deduped and item[0] < deduped[-1][1]:
            continue
        deduped.append(item)
    parts: list[str] = []
    last = 0
    for start, end, idx in deduped:
        fork = forks[idx]
        parts.append(html.escape(story[last:start]))
        parts.append(
            '<span class="fork-wrap">'
            + f'<mark class="fork-mark" tabindex="0" data-fork="{idx}">'
            + html.escape(story[start:end])
            + "</mark>"
            + '<span class="tip" role="tooltip">'
            + "<strong>Reader A — strict:</strong> "
            + html.escape(fork.reading_a)
            + "<br><strong>Reader B — relaxed:</strong> "
            + html.escape(fork.reading_b)
            + "<br><strong>Suggested rewrite:</strong> "
            + html.escape(fork.suggested_rewrite)
            + "</span></span>"
        )
        last = end
    parts.append(html.escape(story[last:]))
    return Markup("".join(parts))


def _agreement_pill(pct: int) -> str:
    if pct >= 70:
        return "ok"
    if pct >= 40:
        return "warn"
    return "bad"


def _severity_pill(severity: str) -> str:
    if severity == "high":
        return "bad"
    if severity == "medium":
        return "warn"
    return "info"


def _match_pill(status: str) -> str:
    if status == "same":
        return "ok"
    if status == "different":
        return "bad"
    return "warn"


def _match_label(status: str) -> str:
    if status == "only_a":
        return "only Reader A"
    if status == "only_b":
        return "only Reader B"
    return status


def _duel_result_context(story: str, result: DuelResult) -> dict:
    forks = result.comparison.forks
    has_high = any(f.severity == "high" for f in forks)
    return {
        "result": result,
        "comparison": result.comparison,
        "forks": forks,
        "forks_pill": "bad" if has_high else "warn",
        "vague_count": len(result.highlights),
        "agreement_pct": result.agreement_pct,
        "agreement_pill": _agreement_pill(result.agreement_pct),
        "highlighted_story": _highlight_duel_story(
            story, result.highlights, forks
        ),
        "severity_pill": _severity_pill,
        "match_pill": _match_pill,
        "match_label": _match_label,
        "vague_rewrites": result.vague_rewrites,
        "not_stated_values": {NOT_STATED_A, NOT_STATED_B},
        "notes": result.notes,
        "provider_name": result.provider_name,
    }


def _duel_from_sample(story: str) -> dict:
    with open(SAMPLES_DIR / "duel.json", encoding="utf-8") as f:
        sample = json.load(f)
    reading_a = Interpretation.model_validate(sample["reading_a"])
    reading_b = Interpretation.model_validate(sample["reading_b"])
    comparison = DuelComparison.model_validate(sample["comparison"])
    matches = match_numbers(reading_a, reading_b)
    n_forks = len(comparison.forks)
    n_agree = len(comparison.agreements)
    pct = 100 if n_forks + n_agree == 0 else round(100 * n_agree / (n_forks + n_agree))
    result = DuelResult(
        reading_a=reading_a,
        reading_b=reading_b,
        comparison=comparison,
        agreement_pct=pct,
        highlights=build_highlights(story, comparison.forks),
        notes=[],
        provider_name="saved example",
        used_index=0,
        number_matches=matches,
    )
    return _duel_result_context(story, result)


@app.get("/requirements/story/example", response_class=HTMLResponse)
def story_example(request: Request) -> HTMLResponse:
    """Load example: fills the form and shows a saved result. No key needed."""
    with open(SAMPLES_DIR / "story_check.json", encoding="utf-8") as f:
        sample = json.load(f)
    result = AmbiguityAnalysis.model_validate(sample["result"])
    form = sample["form"]
    context = _story_result_context(
        request,
        form["user_story"],
        result,
        notes=[],
        provider_name="saved example",
    )
    story_field = (
        '<textarea id="story-user-story" name="user_story" hx-swap-oob="true">'
        + html.escape(form["user_story"])
        + "</textarea>"
    )
    type_field = (
        '<select id="story-type" name="story_type" hx-swap-oob="true">'
        + "".join(
            f'<option value="{html.escape(t)}"'
            + (" selected" if t == form["story_type"] else "")
            + f">{html.escape(t)}</option>"
            for t in ("User story", "Technical story", "Bug fix story", "Spike/Research")
        )
        + "</select>"
    )
    context_field = (
        '<textarea id="story-context" name="context" hx-swap-oob="true">'
        + html.escape(form["context"])
        + "</textarea>"
    )
    body = templates.get_template("_story_result.html").render(context)
    duel_body = templates.get_template("_duel_result.html").render(
        _duel_from_sample(form["user_story"])
    )
    return HTMLResponse(story_field + type_field + context_field + body + duel_body)


@app.post("/requirements/story/run", response_class=HTMLResponse)
def story_run(
    request: Request,
    user_story: str = Form(default=""),
    story_type: str = Form(default="User story"),
    context: str = Form(default=""),
) -> HTMLResponse:
    user_story = user_story.strip()
    context = context.strip()
    if not user_story:
        return _error_card(request, "Please paste a user story first.")
    if len(user_story) > STORY_LIMIT or len(context) > CONTEXT_LIMIT:
        return _error_card(
            request,
            "That input is too long. Keep the story under "
            f"{STORY_LIMIT} characters and context under {CONTEXT_LIMIT}.",
        )
    keys = _request_keys(request)
    if not keys:
        # The browser opens the keys drawer (HX-Trigger: open-keys).
        return HTMLResponse(
            '<p class="muted">Add an API key to run the check.</p>',
            headers={"HX-Trigger": "open-keys"},
        )
    system, user = story_check_prompt(
        user_story, story_type=story_type, context=context
    )
    try:
        result, used_index, notes = llm.generate_json(
            keys, system, user, AmbiguityAnalysis
        )
    except llm.NoKeysError:
        return HTMLResponse(
            '<p class="muted">Add an API key to run the check.</p>',
            headers={"HX-Trigger": "open-keys"},
        )
    except llm.AllKeysBusyError as e:
        return _error_card(
            request,
            "All your keys are busy. Try again in a minute or add another key.",
            e.notes,
        )
    except llm.InvalidKeyError as e:
        return _error_card(
            request,
            "Your key was rejected. Check it on the Your API keys page "
            "and try again.",
            e.notes,
        )
    except llm.ModelUnavailableError as e:
        return _error_card(
            request,
            "The AI model isn't available right now. Your keys are fine — "
            "QA-Genius needs a model update.",
            e.notes,
        )
    except llm.ProviderError as e:
        return _error_card(request, str(e))
    except llm.BadOutputError as e:
        return _error_card(request, str(e))
    provider = get_provider(keys[used_index]["provider"])
    provider_name = provider["name"] if provider else "unknown provider"
    return templates.TemplateResponse(
        request,
        "_story_result.html",
        _story_result_context(request, user_story, result, notes, provider_name),
    )


@app.post("/requirements/story/duel", response_class=HTMLResponse)
def story_duel(
    request: Request,
    user_story: str = Form(default=""),
    story_type: str = Form(default="User story"),
    context: str = Form(default=""),
) -> HTMLResponse:
    user_story = user_story.strip()
    context = context.strip()
    if not user_story:
        return _error_card(request, "Please paste a user story first.")
    if len(user_story) > STORY_LIMIT or len(context) > CONTEXT_LIMIT:
        return _error_card(
            request,
            "That input is too long. Keep the story under "
            f"{STORY_LIMIT} characters and context under {CONTEXT_LIMIT}.",
        )
    keys = _request_keys(request)
    if not keys:
        return HTMLResponse(
            '<p class="muted">Add an API key to run the check.</p>',
            headers={"HX-Trigger": "open-keys"},
        )
    try:
        result = duel.run_duel(keys, user_story, story_type, context)
    except llm.NoKeysError:
        return HTMLResponse(
            '<p class="muted">Add an API key to run the check.</p>',
            headers={"HX-Trigger": "open-keys"},
        )
    except llm.AllKeysBusyError as e:
        return _error_card(
            request,
            "All your keys are busy. Try again in a minute or add another key.",
            e.notes,
        )
    except llm.InvalidKeyError as e:
        return _error_card(
            request,
            "Your key was rejected. Check it on the Your API keys page "
            "and try again.",
            e.notes,
        )
    except llm.ModelUnavailableError as e:
        return _error_card(
            request,
            "The AI model isn't available right now. Your keys are fine — "
            "QA-Genius needs a model update.",
            e.notes,
        )
    except llm.ProviderError as e:
        return _error_card(request, str(e))
    except llm.BadOutputError as e:
        return _error_card(request, str(e))
    return templates.TemplateResponse(
        request,
        "_duel_result.html",
        _duel_result_context(user_story, result),
    )



CATEGORY_PILLS = {
    "Functional": "info",
    "Negative": "warn",
    "Boundary": "ok",
    "Edge Case": "neutral",
}
PRIORITY_PILLS = {"High": "bad", "Medium": "warn", "Low": "ok"}


class _SuiteBody(BaseModel):
    """A test case list plus its criteria, as the browser hands it back."""

    result: TestCaseList
    criteria: list[str] = []

    @field_validator("criteria")
    @classmethod
    def _within_limits(cls, value: list[str]) -> list[str]:
        if len(value) > CRITERIA_LIMIT:
            raise ValueError(f"Send at most {CRITERIA_LIMIT} criteria.")
        if any(len(text) > CRITERION_LIMIT for text in value):
            raise ValueError(f"Keep each criterion under {CRITERION_LIMIT} characters.")
        return value

    @field_validator("result")
    @classmethod
    def _not_too_many_cases(cls, value: TestCaseList) -> TestCaseList:
        if len(value.test_cases) > MAX_CASES:
            raise ValueError(f"Send at most {MAX_CASES} test cases.")
        return value


class ExportRequest(_SuiteBody):
    """Body of the export routes."""


class RenderRequest(_SuiteBody):
    """Body of the re-render route, used after accept and undo."""


def _parse_criteria_json(raw: str) -> list[str] | None:
    """The posted criteria, or None when the payload is not a short list of short strings."""
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(value, list) or len(value) > CRITERIA_LIMIT:
        return None
    if not all(isinstance(item, str) for item in value):
        return None
    if any(len(item) > CRITERION_LIMIT for item in value):
        return None
    return value


def _category_pill(category: str) -> str:
    return CATEGORY_PILLS.get(category.strip().title(), "neutral")


def _priority_pill(priority: str) -> str:
    return PRIORITY_PILLS.get(priority.strip().title(), "neutral")


def _coverage_pill(percent: int) -> str:
    if percent >= 100:
        return "ok"
    if percent >= 60:
        return "warn"
    return "bad"


def _test_cases_result_context(
    result: TestCaseList,
    criteria: list[Criterion],
    notes: list[str],
    provider_name: str,
    is_example: bool = False,
) -> dict:
    """Everything the result card shows is computed here, never read from result.summary."""
    coverage = compute_coverage(result, criteria)
    counts = compute_counts(result)
    depth = compute_depth(result, criteria)
    valid_ids = {criterion.id for criterion in criteria}
    cases = [
        {"case": test_case, "ac_ids": traced_ids(test_case, valid_ids)}
        for test_case in result.test_cases
    ]
    return {
        "cases": cases,
        "criteria": criteria,
        "coverage": coverage,
        "counts": counts,
        "depth": depth,
        "categories": list(counts.by_category),
        "ac_text": {criterion.id: criterion.text for criterion in criteria},
        "category_pill": _category_pill,
        "priority_pill": _priority_pill,
        "coverage_pill": _coverage_pill(coverage.percent),
        "tc_data": {
            "result": result.model_dump(),
            "criteria": [criterion.text for criterion in criteria],
        },
        "is_example": is_example,
        "notes": notes,
        "provider_name": provider_name,
    }


@app.get("/requirements/criteria", response_class=HTMLResponse)
def criteria_page(request: Request) -> HTMLResponse:
    """Step 2. The page is empty; the browser fills it from sessionStorage."""
    return templates.TemplateResponse(
        request, "criteria.html", {"active": "requirements"}
    )


@app.get("/requirements/test-cases", response_class=HTMLResponse)
def test_cases_page(request: Request) -> HTMLResponse:
    """Step 3. The page is empty; the browser fills it from sessionStorage."""
    return templates.TemplateResponse(
        request, "test_cases.html", {"active": "requirements"}
    )


@app.post("/requirements/test-cases/run", response_class=HTMLResponse)
def test_cases_run(
    request: Request,
    user_story: str = Form(default=""),
    criteria_json: str = Form(default="[]"),
    coverage_focus: list[str] = Form(default=[]),
) -> HTMLResponse:
    user_story = user_story.strip()
    if not user_story:
        return _error_card(request, "Please paste a user story first.")
    if len(user_story) > STORY_LIMIT:
        return _error_card(
            request,
            f"That story is too long. Keep it under {STORY_LIMIT} characters.",
        )
    texts = _parse_criteria_json(criteria_json)
    if texts is None:
        return _error_card(request, "Please check the story and criteria.")
    if any(focus not in COVERAGE_FOCUS_OPTIONS for focus in coverage_focus):
        return _error_card(request, "Please check the story and criteria.")
    keys = _request_keys(request)
    if not keys:
        # The browser opens the keys drawer (HX-Trigger: open-keys).
        return HTMLResponse(
            '<p class="muted">Add an API key to write test cases.</p>',
            headers={"HX-Trigger": "open-keys"},
        )
    criteria = number_criteria(texts)
    system, base_user = test_cases_prompt(user_story)
    user = build_user_text(base_user, list(coverage_focus), criteria)
    try:
        result, used_index, notes = llm.generate_json(keys, system, user, TestCaseList)
    except llm.NoKeysError:
        return HTMLResponse(
            '<p class="muted">Add an API key to write test cases.</p>',
            headers={"HX-Trigger": "open-keys"},
        )
    except llm.AllKeysBusyError as e:
        return _error_card(
            request,
            "All your keys are busy. Try again in a minute or add another key.",
            e.notes,
        )
    except llm.InvalidKeyError as e:
        return _error_card(
            request,
            "Your key was rejected. Check it on the Your API keys page "
            "and try again.",
            e.notes,
        )
    except llm.ModelUnavailableError as e:
        return _error_card(
            request,
            "The AI model isn't available right now. Your keys are fine -- "
            "QA-Genius needs a model update.",
            e.notes,
        )
    except llm.ProviderError as e:
        return _error_card(request, str(e))
    except llm.BadOutputError as e:
        return _error_card(request, str(e))
    provider = get_provider(keys[used_index]["provider"])
    return templates.TemplateResponse(
        request,
        "_test_cases_result.html",
        _test_cases_result_context(
            result,
            criteria,
            notes,
            provider["name"] if provider else "unknown provider",
        ),
    )


def _test_cases_sample() -> tuple[TestCaseList, list[Criterion]]:
    with open(SAMPLES_DIR / "test_cases.json", encoding="utf-8") as f:
        sample = json.load(f)
    return (
        TestCaseList.model_validate(sample["result"]),
        number_criteria(sample["criteria"]),
    )


@app.get("/requirements/test-cases/example", response_class=HTMLResponse)
def test_cases_example(request: Request) -> HTMLResponse:
    """Load example: a saved suite. No key needed, no AI call."""
    result, criteria = _test_cases_sample()
    return templates.TemplateResponse(
        request,
        "_test_cases_result.html",
        _test_cases_result_context(
            result, criteria, [], "saved example", is_example=True
        ),
    )


@app.post("/requirements/test-cases/export.csv")
def test_cases_export_csv(payload: ExportRequest) -> Response:
    data = to_csv(payload.result, number_criteria(payload.criteria))
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="qa-genius-test-cases.csv"'
        },
    )


@app.post("/requirements/test-cases/export.xlsx")
def test_cases_export_xlsx(payload: ExportRequest) -> Response:
    data = to_xlsx(payload.result, number_criteria(payload.criteria))
    return Response(
        content=data,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": 'attachment; filename="qa-genius-test-cases.xlsx"'
        },
    )


def _refine_rows(
    current: TestCaseList, proposed: TestCaseList, criteria: list[Criterion]
) -> list[dict]:
    """The before -> after line. Every number is computed, none comes from the AI."""
    before_counts = compute_counts(current)
    after_counts = compute_counts(proposed)
    before_depth = compute_depth(current, criteria)
    after_depth = compute_depth(proposed, criteria)
    rows = [
        ("Test cases", before_counts.total, after_counts.total, "up", ""),
        (
            "Coverage",
            compute_coverage(current, criteria).percent,
            compute_coverage(proposed, criteria).percent,
            "up",
            "%",
        ),
        (
            "Thin criteria",
            len(before_depth.thin_ids),
            len(after_depth.thin_ids),
            "down",
            "",
        ),
        (
            "Negative",
            before_counts.by_category.get("Negative", 0),
            after_counts.by_category.get("Negative", 0),
            "up",
            "",
        ),
        (
            "Boundary",
            before_counts.by_category.get("Boundary", 0),
            after_counts.by_category.get("Boundary", 0),
            "up",
            "",
        ),
    ]
    return [
        {
            "label": label,
            "before": f"{before}{suffix}",
            "after": f"{after}{suffix}",
            "tone": _delta_tone(before, after, good),
        }
        for label, before, after, good, suffix in rows
    ]


def _delta_tone(before: int, after: int, good: str) -> str:
    if after == before:
        return "same"
    improved = after > before if good == "up" else after < before
    return "good" if improved else "bad"


def _diff_context(
    current: TestCaseList,
    proposed: TestCaseList,
    criteria: list[Criterion],
    mode: str,
    notes: list[str],
    provider_name: str,
) -> dict:
    diff = diff_cases(current, proposed)
    valid_ids = {criterion.id for criterion in criteria}
    items = [
        {
            "item": item,
            "case": item.after or item.before,
            "ac_ids": traced_ids(item.after or item.before, valid_ids),
        }
        for item in diff.items
    ]
    return {
        "diff": diff,
        "items": items,
        "rows": _refine_rows(current, proposed, criteria),
        "mode": mode,
        "ac_text": {criterion.id: criterion.text for criterion in criteria},
        "category_pill": _category_pill,
        "priority_pill": _priority_pill,
        "field_labels": FIELD_LABELS,
        "proposal": {
            "result": proposed.model_dump(),
            "criteria": [criterion.text for criterion in criteria],
        },
        "notes": notes,
        "provider_name": provider_name,
    }


FIELD_LABELS = {
    "title": "Title",
    "category": "Category",
    "priority": "Priority",
    "pre_conditions": "Pre-conditions",
    "steps": "Steps",
    "expected_result": "Expected result",
    "test_data": "Test data",
    "bdd_scenario": "BDD scenario",
    "traceability": "Traceability",
}


@app.post("/requirements/test-cases/render", response_class=HTMLResponse)
def test_cases_render(request: Request, payload: RenderRequest) -> HTMLResponse:
    """Re-draw the result card from a list the browser already holds. No AI call."""
    criteria = number_criteria(payload.criteria)
    return templates.TemplateResponse(
        request,
        "_test_cases_result.html",
        _test_cases_result_context(payload.result, criteria, [], "your saved list"),
    )


def _parse_current(raw: str) -> TestCaseList | None:
    """The posted test case list, or None when it is missing, huge or malformed."""
    if not raw or len(raw) > CURRENT_JSON_LIMIT:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    try:
        current = TestCaseList.model_validate(value)
    except ValueError:
        return None
    if not current.test_cases or len(current.test_cases) > MAX_CASES:
        return None
    return current


def _parse_risks_json(raw: str) -> list[ScoredRisk] | None:
    """The risks the Risk radar page asked for tests for, or None when malformed.

    Only the id, category, title and test idea travel; the scores stay on the
    risk page, so the objects here carry no RPN or level to be mistaken for one.
    """
    if len(raw or "") > RISKS_JSON_LIMIT:
        return None
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(value, list) or not value or len(value) > MAX_RISKS:
        return None
    asked = []
    for item in value:
        if not isinstance(item, dict):
            return None
        fields = {
            name: str(item.get(name) or "").strip()
            for name in ("id", "category", "title", "test_idea")
        }
        if not fields["id"] or not fields["title"]:
            return None
        if any(len(text) > CRITERION_LIMIT for text in fields.values()):
            return None
        asked.append(
            ScoredRisk(
                risk=FailureMode(
                    id=fields["id"],
                    title=fields["title"],
                    category=fields["category"],
                    effect="",
                    cause="",
                    severity=3,
                    likelihood=3,
                    detectability=3,
                    test_idea=fields["test_idea"],
                ),
                rpn=0,
                level="high",
                coverage="none",
                covered_tests=[],
            )
        )
    return asked


@app.post("/requirements/test-cases/refine", response_class=HTMLResponse)
def test_cases_refine(
    request: Request,
    user_story: str = Form(default=""),
    criteria_json: str = Form(default="[]"),
    current_json: str = Form(default=""),
    mode: str = Form(default="strengthen"),
    instruction: str = Form(default=""),
    risks_json: str = Form(default="[]"),
    coverage_focus: list[str] = Form(default=[]),
) -> HTMLResponse:
    bad_input = "Please check the test cases and instruction."
    user_story = user_story.strip()
    instruction = instruction.strip()
    if not user_story or len(user_story) > STORY_LIMIT:
        return _error_card(request, bad_input)
    if mode not in REFINE_MODES:
        return _error_card(request, bad_input)
    if len(instruction) > INSTRUCTION_LIMIT:
        return _error_card(request, bad_input)
    if mode == "instruction" and not instruction:
        return _error_card(
            request, "Type what you want changed, then press Propose changes."
        )
    texts = _parse_criteria_json(criteria_json)
    if texts is None:
        return _error_card(request, bad_input)
    if any(focus not in COVERAGE_FOCUS_OPTIONS for focus in coverage_focus):
        return _error_card(request, bad_input)
    current = _parse_current(current_json)
    if current is None:
        return _error_card(request, bad_input)
    asked_risks = _parse_risks_json(risks_json) if mode == "risks" else []
    if asked_risks is None:
        return _error_card(request, bad_input)

    criteria = number_criteria(texts)
    depth = compute_depth(current, criteria)
    if mode == "strengthen" and not depth.thin_ids:
        return HTMLResponse(
            '<div class="card"><p class="muted">Every criterion already has '
            "enough cases.</p></div>"
        )

    keys = _request_keys(request)
    if not keys:
        # The browser opens the keys drawer (HX-Trigger: open-keys).
        return HTMLResponse(
            '<p class="muted">Add an API key to ask for changes.</p>',
            headers={"HX-Trigger": "open-keys"},
        )

    system, base_user = test_cases_prompt(user_story)
    base = build_user_text(base_user, list(coverage_focus), criteria)
    if mode == "instruction":
        asked = instruction
    elif mode == "risks":
        asked = risk_instruction(asked_risks)
    else:
        asked = strengthen_instruction(depth)
    user = refine_user_text(base, current, criteria, asked)
    try:
        ai_result, used_index, notes = llm.generate_json(
            keys, system, user, TestCaseList
        )
    except llm.NoKeysError:
        return HTMLResponse(
            '<p class="muted">Add an API key to ask for changes.</p>',
            headers={"HX-Trigger": "open-keys"},
        )
    except llm.AllKeysBusyError as e:
        return _error_card(
            request,
            "All your keys are busy. Try again in a minute or add another key.",
            e.notes,
        )
    except llm.InvalidKeyError as e:
        return _error_card(
            request,
            "Your key was rejected. Check it on the Your API keys page "
            "and try again.",
            e.notes,
        )
    except llm.ModelUnavailableError as e:
        return _error_card(
            request,
            "The AI model isn't available right now. Your keys are fine -- "
            "QA-Genius needs a model update.",
            e.notes,
        )
    except llm.ProviderError as e:
        return _error_card(request, str(e))
    except llm.BadOutputError as e:
        return _error_card(request, str(e))

    # Strengthen and the risk run are additive: code drops any edit or
    # deletion the AI tried.
    if mode == "instruction":
        proposed = ai_result
    else:
        proposed = merge_strengthened(current, ai_result)
    if mode == "risks":
        # The AI was asked for the risk:Rn tag; code puts it on when it forgot.
        proposed = add_risk_tags(
            current, proposed, [item.risk.id for item in asked_risks]
        )
    provider = get_provider(keys[used_index]["provider"])
    return templates.TemplateResponse(
        request,
        "_test_cases_diff.html",
        _diff_context(
            current,
            proposed,
            criteria,
            mode,
            notes,
            provider["name"] if provider else "unknown provider",
        ),
    )


@app.get("/requirements/test-cases/example-strengthen", response_class=HTMLResponse)
def test_cases_example_strengthen(request: Request) -> HTMLResponse:
    """What Strengthen does to the saved example. No key needed, no AI call."""
    current, criteria = _test_cases_sample()
    with open(SAMPLES_DIR / "test_cases_strengthened.json", encoding="utf-8") as f:
        sample = json.load(f)
    proposed = TestCaseList.model_validate(sample["result"])
    return templates.TemplateResponse(
        request,
        "_test_cases_diff.html",
        _diff_context(
            current, proposed, criteria, "strengthen", [], "saved example"
        ),
    )

def _parse_selected(raw: str) -> list[TestCase] | None:
    """The posted test cases, or None when the payload is not 1..12 valid cases."""
    if len(raw or "") > SELECTED_JSON_LIMIT:
        return None
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(value, list):
        return None
    if not 1 <= len(value) <= automation.MAX_SELECTED:
        return None
    try:
        return [TestCase.model_validate(item) for item in value]
    except ValidationError:
        return None


def _valid_base_url(base_url: str) -> bool:
    """Empty is fine. Anything else must be a short http(s) URL."""
    text = (base_url or "").strip()
    if not text:
        return True
    if len(text) > BASE_URL_LIMIT:
        return False
    return text.startswith("http://") or text.startswith("https://")


def _browsers_text(framework: str, browsers: list[str]) -> str:
    """The browsers line for the prompt. Only Playwright runs more than one."""
    if not framework.startswith("Playwright"):
        return "chromium"
    picked = [name for name in automation.BROWSER_OPTIONS if name in browsers]
    return ", ".join(picked) or "chromium"


def _automation_result_context(
    script: AutomationScript,
    report: CheckReport,
    selected_ids: list[str],
    notes: list[str],
    provider_name: str,
    is_example: bool = False,
) -> dict:
    warnings = [finding for finding in report.findings if finding.level == "warning"]
    errors = [finding for finding in report.findings if finding.level == "error"]
    return {
        "script": script,
        "report": report,
        "selected_ids": selected_ids,
        "traced_total": len(report.traced) + len(report.missing),
        "warnings": warnings,
        "errors": errors,
        "syntax_label": "all valid" if not errors else f"{len(errors)} error"
        + ("s" if len(errors) != 1 else ""),
        "notes": notes,
        "provider_name": provider_name,
        "is_example": is_example,
        # What the Download ZIP button posts back to the export route.
        "automation_data": {
            "script": script.model_dump(),
            "selected_ids": selected_ids,
        },
    }


@app.get("/requirements/automation", response_class=HTMLResponse)
def automation_page(request: Request) -> HTMLResponse:
    """Step 4. The page is empty; the browser fills it from sessionStorage."""
    return templates.TemplateResponse(
        request, "automation.html", {"active": "requirements"}
    )


@app.post("/requirements/automation/run", response_class=HTMLResponse)
def automation_run(
    request: Request,
    selected_json: str = Form(default="[]"),
    framework_choice: str = Form(default=""),
    structure_choice: str = Form(default=""),
    browsers: list[str] = Form(default=[]),
    base_url: str = Form(default=""),
) -> HTMLResponse:
    cases = _parse_selected(selected_json)
    settings_ok = (
        cases is not None
        and framework_choice in automation.FRAMEWORK_OPTIONS
        and structure_choice in automation.STRUCTURE_OPTIONS
        and all(name in automation.BROWSER_OPTIONS for name in browsers)
        and _valid_base_url(base_url)
    )
    if not settings_ok or cases is None:
        return _error_card(
            request, "Please check the selected test cases and settings."
        )
    keys = _request_keys(request)
    if not keys:
        # The browser opens the keys drawer (HX-Trigger: open-keys).
        return HTMLResponse(
            '<p class="muted">Add an API key to write automation.</p>',
            headers={"HX-Trigger": "open-keys"},
        )

    framework, language = automation.FRAMEWORK_OPTIONS[framework_choice]
    structure = automation.STRUCTURE_OPTIONS[structure_choice]
    site_type = f"Custom web app at {automation.effective_base_url(base_url)}"
    scenario = automation.build_scenario(cases)
    system, base_user = automation_prompt(
        scenario,
        framework,
        language,
        structure,
        _browsers_text(framework, list(browsers)),
        site_type,
    )
    user = automation.build_user_text(base_user, cases, base_url)
    try:
        script, used_index, notes = llm.generate_json(
            keys, system, user, AutomationScript
        )
    except llm.NoKeysError:
        return HTMLResponse(
            '<p class="muted">Add an API key to write automation.</p>',
            headers={"HX-Trigger": "open-keys"},
        )
    except llm.AllKeysBusyError as e:
        return _error_card(
            request,
            "All your keys are busy. Try again in a minute or add another key.",
            e.notes,
        )
    except llm.InvalidKeyError as e:
        return _error_card(
            request,
            "Your key was rejected. Check it on the Your API keys page "
            "and try again.",
            e.notes,
        )
    except llm.ModelUnavailableError as e:
        return _error_card(
            request,
            "The AI model isn't available right now. Your keys are fine -- "
            "QA-Genius needs a model update.",
            e.notes,
        )
    except llm.ProviderError as e:
        return _error_card(request, str(e))
    except llm.BadOutputError as e:
        return _error_card(request, str(e))

    selected_ids = [case.id for case in cases]
    report = check_project(script, selected_ids)
    provider = get_provider(keys[used_index]["provider"])
    return templates.TemplateResponse(
        request,
        "_automation_result.html",
        _automation_result_context(
            script,
            report,
            selected_ids,
            notes,
            provider["name"] if provider else "unknown provider",
        ),
    )


def _automation_sample() -> tuple[AutomationScript, list[str]]:
    with open(SAMPLES_DIR / "automation.json", encoding="utf-8") as f:
        sample = json.load(f)
    return (
        AutomationScript.model_validate(sample["script"]),
        [str(one) for one in sample["selected_ids"]],
    )


@app.get("/requirements/automation/example", response_class=HTMLResponse)
def automation_example(request: Request) -> HTMLResponse:
    """Load example: a saved project. No key needed, no AI call."""
    script, selected_ids = _automation_sample()
    report = check_project(script, selected_ids)
    return templates.TemplateResponse(
        request,
        "_automation_result.html",
        _automation_result_context(
            script, report, selected_ids, [], "saved example", is_example=True
        ),
    )


class AutomationExportRequest(BaseModel):
    """Body of the ZIP route, as the browser hands it back."""

    script: AutomationScript
    selected_ids: list[str] = []

    @field_validator("selected_ids")
    @classmethod
    def _within_limits(cls, value: list[str]) -> list[str]:
        if len(value) > automation.MAX_SELECTED:
            raise ValueError(f"Send at most {automation.MAX_SELECTED} test case ids.")
        return value


@app.post("/requirements/automation/export.zip")
async def automation_export_zip(request: Request) -> Response:
    raw = await request.body()
    if len(raw) > EXPORT_BODY_LIMIT:
        return Response(
            content='{"detail":"That project is too large to pack."}',
            media_type="application/json",
            status_code=422,
        )
    try:
        payload = AutomationExportRequest.model_validate_json(raw)
    except ValidationError:
        return Response(
            content='{"detail":"Could not read the project."}',
            media_type="application/json",
            status_code=422,
        )
    report = check_project(payload.script, payload.selected_ids)
    return Response(
        content=build_zip(payload.script, report),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="qa-genius-automation.zip"'
        },
    )


def _as_int(raw: str, fallback: int) -> int | None:
    """The number the form sent, or None when it is not a plain integer."""
    text = (raw or "").strip()
    if not text:
        return fallback
    try:
        return int(text)
    except ValueError:
        return None


def _bug_severity_pill(severity: str) -> str:
    name = (severity or "").strip().title()
    if name in ("Critical", "High"):
        return "bad"
    if name == "Medium":
        return "warn"
    if name == "Low":
        return "ok"
    return "neutral"


def _bug_result_context(
    report: BugReport,
    bug: BugInput,
    checks: list[Check],
    notes: list[str],
    provider_name: str,
    is_example: bool = False,
) -> dict:
    return {
        "report": report,
        "bug": bug,
        "checks": checks,
        "score": quality_score(checks),
        "ok_count": len([check for check in checks if check.ok]),
        "severity_pill": _bug_severity_pill(report.severity),
        # Code works these two out; the AI's own wording is not used here.
        "reproducibility": reproducibility_text(
            bug.total_attempts, bug.successful_attempts
        ),
        "environment": environment_text(bug),
        "notes": notes,
        "provider_name": provider_name,
        "is_example": is_example,
        # Copy buttons read these; the page never rebuilds the text itself.
        "bug_export": {
            "markdown": to_markdown(report, checks),
            "jira": to_jira(report),
        },
        # True when a key refused the screenshot, so the card can say so.
        "image_note": any("can't read images" in note for note in notes),
    }


def _screenshot_or_error(mime: str, data: str) -> tuple[str, str] | str | None:
    """(mime, base64) to send, None when there is no screenshot, or an error message."""
    if not data:
        return None
    if mime not in SCREENSHOT_TYPES:
        return SCREENSHOT_ERROR
    try:
        raw = base64.b64decode(data, validate=True)
    except ValueError:
        return SCREENSHOT_ERROR
    if not raw or len(raw) > SCREENSHOT_LIMIT:
        return SCREENSHOT_ERROR
    return (mime, data)


@app.post("/bugs/run", response_class=HTMLResponse)
async def bugs_run(request: Request) -> HTMLResponse:
    # Parsed by hand so the screenshot field may exceed Starlette's 1 MB default.
    form = await request.form(max_part_size=FORM_PART_LIMIT)

    def field(name: str, default: str = "") -> str:
        value = form.get(name, default)
        return value if isinstance(value, str) else default

    notes = field("notes")
    device = field("device", "Not specified")
    os = field("os")
    browser = field("browser")
    build = field("build")
    url = field("url")
    screenshot_mime = field("screenshot_mime")
    screenshot_data = field("screenshot_data")

    total = _as_int(field("total_attempts", "1"), 1)
    if total is None:
        return _error_card(request, bug_report.TOTAL_ERROR)
    happened = _as_int(field("successful_attempts", "0"), 0)
    if happened is None:
        return _error_card(request, bug_report.HAPPENED_ERROR)

    bug = bug_report.validate_bug_input(
        notes=notes,
        device=device,
        os=os,
        browser=browser,
        build=build,
        url=url,
        total_attempts=total,
        successful_attempts=happened,
    )
    if isinstance(bug, str):
        return _error_card(request, bug)

    image = _screenshot_or_error(screenshot_mime, screenshot_data)
    if isinstance(image, str):
        return _error_card(request, image)
    if image is not None:
        bug = replace(bug, has_screenshot=True)

    keys = _request_keys(request)
    if not keys:
        # The browser opens the keys drawer (HX-Trigger: open-keys).
        return HTMLResponse(
            '<p class="muted">Add an API key to write a bug report.</p>',
            headers={"HX-Trigger": "open-keys"},
        )

    system, base_user = bug_report_prompt(bug.notes)
    user = bug_report.build_user_text(base_user, bug)
    try:
        report, used_index, run_notes = llm.generate_json(
            keys, system, user, BugReport, image=image
        )
    except llm.NoKeysError:
        return HTMLResponse(
            '<p class="muted">Add an API key to write a bug report.</p>',
            headers={"HX-Trigger": "open-keys"},
        )
    except llm.AllKeysBusyError as e:
        return _error_card(
            request,
            "All your keys are busy. Try again in a minute or add another key.",
            e.notes,
        )
    except llm.InvalidKeyError as e:
        return _error_card(
            request,
            "Your key was rejected. Check it on the Your API keys page "
            "and try again.",
            e.notes,
        )
    except llm.ModelUnavailableError as e:
        return _error_card(
            request,
            "The AI model isn't available right now. Your keys are fine -- "
            "QA-Genius needs a model update.",
            e.notes,
        )
    except llm.ProviderError as e:
        return _error_card(request, str(e))
    except llm.BadOutputError as e:
        return _error_card(request, str(e))

    provider = get_provider(keys[used_index]["provider"])
    return templates.TemplateResponse(
        request,
        "_bug_report_result.html",
        _bug_result_context(
            report,
            bug,
            check_report(report, bug),
            run_notes,
            provider["name"] if provider else "unknown provider",
        ),
    )


def _bug_sample() -> tuple[BugReport, BugInput]:
    with open(SAMPLES_DIR / "bug_report.json", encoding="utf-8") as f:
        sample = json.load(f)
    return BugReport.model_validate(sample["report"]), BugInput(**sample["input"])


@app.get("/bugs/example", response_class=HTMLResponse)
def bugs_example(request: Request) -> HTMLResponse:
    """Load example: a saved bug report. No key needed, no AI call."""
    report, bug = _bug_sample()
    return templates.TemplateResponse(
        request,
        "_bug_report_result.html",
        _bug_result_context(
            report, bug, check_report(report, bug), [], "saved example", is_example=True
        ),
    )


def _pass_rate_pill(percent: int) -> str:
    if percent >= 95:
        return "ok"
    if percent >= 80:
        return "warn"
    return "bad"


def _insights_result_context(insights: Insights, is_example: bool = False) -> dict:
    return {
        "ins": insights,
        # The page posts this back to Explain; the AI only ever sees facts_text of it.
        "facts": insights_to_dict(insights),
        "pass_rate_pill": _pass_rate_pill(insights.overall.pass_rate),
        "summary_markdown": insights_markdown(insights),
        "is_example": is_example,
    }


def _explanation_context(
    summary: QualityInsightSummary,
    notes: list[str],
    provider_name: str,
    is_example: bool = False,
) -> dict:
    return {
        "summary": summary,
        "notes": notes,
        "provider_name": provider_name,
        "is_example": is_example,
        "kind_pill": KIND_PILLS,
    }


def _unique_label(label: str, taken: list[str]) -> str:
    """Two files called report.xml become "report" and "report (2)"."""
    if label not in taken:
        return label
    number = 2
    while f"{label} ({number})" in taken:
        number += 1
    return f"{label} ({number})"


@app.post("/insights/analyze", response_class=HTMLResponse)
async def insights_analyze(request: Request) -> HTMLResponse:
    """Read the uploaded reports with code. No key, no AI call, nothing stored."""
    form = await request.form()
    uploads = [
        item
        for item in form.getlist("reports")
        if not isinstance(item, str) and getattr(item, "filename", "")
    ]
    if not uploads:
        return _error_card(request, "Choose a JUnit XML or Playwright JSON file first.")
    if len(uploads) > MAX_REPORTS:
        return _error_card(request, REPORT_LIMIT_ERROR)

    reports: list[RunReport] = []
    labels: list[str] = []
    total_bytes = 0
    for upload in uploads:
        # Checked before the read so an oversized file is never pulled into memory.
        declared = getattr(upload, "size", None)
        if isinstance(declared, int) and declared > REPORT_SIZE_LIMIT:
            return _error_card(request, REPORT_LIMIT_ERROR)
        content = await upload.read()
        total_bytes += len(content)
        if len(content) > REPORT_SIZE_LIMIT or total_bytes > REPORT_TOTAL_LIMIT:
            return _error_card(request, REPORT_LIMIT_ERROR)
        try:
            report = parse_report(upload.filename or "report", content)
        except ReportError as e:
            return _error_card(request, str(e))
        label = _unique_label(report.label, labels)
        labels.append(label)
        reports.append(replace(report, label=label))

    return templates.TemplateResponse(
        request,
        "_insights_result.html",
        _insights_result_context(compute_insights(reports)),
    )


def _sample_insights() -> Insights:
    reports = []
    for name in SAMPLE_REPORTS:
        path = SAMPLES_DIR / "reports" / name
        reports.append(parse_report(name, path.read_bytes()))
    return compute_insights(reports)


@app.get("/insights/example", response_class=HTMLResponse)
def insights_example(request: Request) -> HTMLResponse:
    """Load example: two saved runs of the Aurora Storefront suite. No key, no AI."""
    return templates.TemplateResponse(
        request,
        "_insights_result.html",
        _insights_result_context(_sample_insights(), is_example=True),
    )


@app.get("/insights/example-explained", response_class=HTMLResponse)
def insights_example_explained(request: Request) -> HTMLResponse:
    """The saved explanation for the example runs. No key, no AI call."""
    with open(SAMPLES_DIR / "insights_summary.json", encoding="utf-8") as f:
        summary = QualityInsightSummary.model_validate(json.load(f))
    cleaned, notes = clean_summary(summary, _sample_insights())
    return templates.TemplateResponse(
        request,
        "_insights_explanation.html",
        _explanation_context(cleaned, notes, "saved example", is_example=True),
    )


@app.post("/insights/explain", response_class=HTMLResponse)
async def insights_explain(request: Request) -> HTMLResponse:
    """Send only the computed facts to the AI. The uploaded files are long gone."""
    form = await request.form()
    raw = form.get("facts_json", "")
    if not isinstance(raw, str) or not raw or len(raw) > FACTS_JSON_LIMIT:
        return _error_card(request, ANALYZE_AGAIN_ERROR)
    try:
        insights = insights_from_dict(json.loads(raw))
    except (ValueError, TypeError):
        return _error_card(request, ANALYZE_AGAIN_ERROR)

    keys = _request_keys(request)
    if not keys:
        return HTMLResponse(
            '<p class="muted">Add an API key to explain these results.</p>',
            headers={"HX-Trigger": "open-keys"},
        )

    system, user = insights_prompt(facts_text(insights))
    try:
        summary, used_index, run_notes = llm.generate_json(
            keys, system, user, QualityInsightSummary
        )
    except llm.NoKeysError:
        return HTMLResponse(
            '<p class="muted">Add an API key to explain these results.</p>',
            headers={"HX-Trigger": "open-keys"},
        )
    except llm.AllKeysBusyError as e:
        return _error_card(
            request,
            "All your keys are busy. Try again in a minute or add another key.",
            e.notes,
        )
    except llm.InvalidKeyError as e:
        return _error_card(
            request,
            "Your key was rejected. Check it on the Your API keys page and try again.",
            e.notes,
        )
    except llm.ModelUnavailableError as e:
        return _error_card(
            request,
            "The AI model isn't available right now. Your keys are fine -- "
            "QA-Genius needs a model update.",
            e.notes,
        )
    except (llm.ProviderError, llm.BadOutputError) as e:
        return _error_card(request, str(e))

    cleaned, guard_notes = clean_summary(summary, insights)
    provider = get_provider(keys[used_index]["provider"])
    return templates.TemplateResponse(
        request,
        "_insights_explanation.html",
        _explanation_context(
            cleaned,
            run_notes + guard_notes,
            provider["name"] if provider else "unknown provider",
        ),
    )


# ══════════════════════════════════════════════════════════════════════════════
# RISK RADAR
# ══════════════════════════════════════════════════════════════════════════════

RISK_BAD_INPUT = "Please check the story, criteria and test cases."
RISK_NO_STORY = "Start from a story in Requirements first."
RISK_NO_KEY = '<p class="muted">Add an API key to find risks.</p>'
LEVEL_PILLS = {"high": "bad", "medium": "warn", "low": "ok"}
COVERAGE_TONES = {"verified": "ok", "covered": "ok", "weak": "warn", "none": "bad"}
# A cell of the heat map, coloured by severity x likelihood.
HEAT_BAD, HEAT_WARN = 15, 8


class RiskBody(BaseModel):
    """A risk analysis plus the run it was made for, as the browser hands it back."""

    analysis: RiskAnalysis
    cases: list[TestCase] = []
    criteria: list[str] = []

    @field_validator("criteria")
    @classmethod
    def _within_limits(cls, value: list[str]) -> list[str]:
        if len(value) > CRITERIA_LIMIT:
            raise ValueError(f"Send at most {CRITERIA_LIMIT} criteria.")
        if any(len(text) > CRITERION_LIMIT for text in value):
            raise ValueError(f"Keep each criterion under {CRITERION_LIMIT} characters.")
        return value

    @field_validator("cases")
    @classmethod
    def _not_too_many_cases(cls, value: list[TestCase]) -> list[TestCase]:
        if len(value) > MAX_CASES:
            raise ValueError(f"Send at most {MAX_CASES} test cases.")
        return value

    @field_validator("analysis")
    @classmethod
    def _not_too_many_risks(cls, value: RiskAnalysis) -> RiskAnalysis:
        if len(value.failure_modes) > MAX_RISKS:
            raise ValueError(f"Send at most {MAX_RISKS} failure modes.")
        return value


def _parse_cases_json(raw: str) -> list[TestCase] | None:
    """The posted test cases, or None when the payload is huge or malformed."""
    if len(raw or "") > CURRENT_JSON_LIMIT:
        return None
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(value, list) or len(value) > MAX_CASES:
        return None
    try:
        return [TestCase.model_validate(item) for item in value]
    except ValidationError:
        return None


def _heat_rows(report: RiskReport) -> list[dict]:
    """The grid the template draws: severity 5 at the top, likelihood 1 on the left."""
    rows = []
    for severity in range(5, 0, -1):
        cells = []
        for likelihood in range(1, 6):
            product = severity * likelihood
            tone = "ok"
            if product >= HEAT_BAD:
                tone = "bad"
            elif product >= HEAT_WARN:
                tone = "warn"
            cells.append(
                {
                    "severity": severity,
                    "likelihood": likelihood,
                    "ids": report.heatmap[(severity, likelihood)],
                    "tone": tone,
                }
            )
        rows.append({"severity": severity, "cells": cells})
    return rows


def _untested_high(report: RiskReport) -> list[dict[str, str]]:
    """What the Write tests button sends to step 3."""
    return [
        {
            "id": item.risk.id,
            "category": item.risk.category,
            "title": item.risk.title,
            "test_idea": item.risk.test_idea,
        }
        for item in report.risks
        if item.level == "high" and item.coverage in ("none", "weak")
    ]


def _risk_result_context(
    analysis: RiskAnalysis,
    cases: list[TestCase],
    criteria: list[Criterion],
    notes: list[str],
    provider_name: str,
    is_example: bool = False,
) -> dict:
    """Every number here is computed from the analysis, never read back from it."""
    report = score_risks(analysis, cases)
    # A weak claim is not coverage: the test the AI named is about something else.
    covered = sum(
        1 for item in report.risks if item.coverage in ("verified", "covered")
    )
    return {
        "report": report,
        "covered": covered,
        "heat_rows": _heat_rows(report),
        "untested": _untested_high(report),
        "level_pill": LEVEL_PILLS,
        "coverage_tone": COVERAGE_TONES,
        "ac_text": {criterion.id: criterion.text for criterion in criteria},
        "risk_data": {
            "analysis": analysis.model_dump(),
            "cases": [case.model_dump() for case in cases],
            "criteria": [criterion.text for criterion in criteria],
        },
        "is_example": is_example,
        "notes": notes,
        "provider_name": provider_name,
    }


def _risk_result(request: Request, **context) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "_risk_radar_result.html", _risk_result_context(**context)
    )


@app.get("/risks", response_class=HTMLResponse)
def risks_page(request: Request) -> HTMLResponse:
    """The page is empty; the browser fills it from sessionStorage."""
    return templates.TemplateResponse(request, "risk_radar.html", {"active": "risks"})


@app.post("/risks/run", response_class=HTMLResponse)
def risks_run(
    request: Request,
    user_story: str = Form(default=""),
    criteria_json: str = Form(default="[]"),
    cases_json: str = Form(default="[]"),
) -> HTMLResponse:
    user_story = user_story.strip()
    if not user_story:
        return _error_card(request, RISK_NO_STORY)
    if len(user_story) > STORY_LIMIT:
        return _error_card(request, RISK_BAD_INPUT)
    texts = _parse_criteria_json(criteria_json)
    if texts is None:
        return _error_card(request, RISK_BAD_INPUT)
    cases = _parse_cases_json(cases_json)
    if cases is None:
        return _error_card(request, RISK_BAD_INPUT)
    keys = _request_keys(request)
    if not keys:
        # The browser opens the keys drawer (HX-Trigger: open-keys).
        return HTMLResponse(RISK_NO_KEY, headers={"HX-Trigger": "open-keys"})

    criteria = number_criteria(texts)
    system, user = risk_radar_prompt(
        user_story, criteria_lines(criteria), case_lines(cases)
    )
    try:
        result, used_index, notes = llm.generate_json(keys, system, user, RiskAnalysis)
    except llm.NoKeysError:
        return HTMLResponse(RISK_NO_KEY, headers={"HX-Trigger": "open-keys"})
    except llm.AllKeysBusyError as e:
        return _error_card(
            request,
            "All your keys are busy. Try again in a minute or add another key.",
            e.notes,
        )
    except llm.InvalidKeyError as e:
        return _error_card(
            request,
            "Your key was rejected. Check it on the Your API keys page and try again.",
            e.notes,
        )
    except llm.ModelUnavailableError as e:
        return _error_card(
            request,
            "The AI model isn't available right now. Your keys are fine -- "
            "QA-Genius needs a model update.",
            e.notes,
        )
    except llm.ProviderError as e:
        return _error_card(request, str(e))
    except llm.BadOutputError as e:
        return _error_card(request, str(e))

    analysis, guard_notes = clean_analysis(
        result,
        {criterion.id for criterion in criteria},
        {case.id for case in cases},
    )
    provider = get_provider(keys[used_index]["provider"])
    return _risk_result(
        request,
        analysis=analysis,
        cases=cases,
        criteria=criteria,
        notes=notes + guard_notes,
        provider_name=provider["name"] if provider else "unknown provider",
    )


@app.post("/risks/rescore", response_class=HTMLResponse)
def risks_rescore(request: Request, payload: RiskBody) -> HTMLResponse:
    """Re-draw the card after someone adjusted a score. No AI call."""
    return _risk_result(
        request,
        analysis=payload.analysis,
        cases=payload.cases,
        criteria=number_criteria(payload.criteria),
        notes=[],
        provider_name="your adjusted scores",
    )


def _risk_sample() -> tuple[RiskAnalysis, list[TestCase], list[Criterion]]:
    with open(SAMPLES_DIR / "risk_radar.json", encoding="utf-8") as f:
        sample = json.load(f)
    return (
        RiskAnalysis.model_validate(sample["analysis"]),
        [TestCase.model_validate(case) for case in sample["cases"]],
        number_criteria(sample["criteria"]),
    )


@app.get("/risks/example", response_class=HTMLResponse)
def risks_example(request: Request) -> HTMLResponse:
    """Load example: a saved FMEA. No key needed, no AI call."""
    analysis, cases, criteria = _risk_sample()
    return _risk_result(
        request,
        analysis=analysis,
        cases=cases,
        criteria=criteria,
        notes=[],
        provider_name="saved example",
        is_example=True,
    )


@app.post("/risks/export.csv")
def risks_export_csv(payload: RiskBody) -> Response:
    report = score_risks(payload.analysis, payload.cases)
    return Response(
        content=risk_register_exports.to_csv(report),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="qa-genius-risk-register.csv"'
        },
    )


@app.post("/risks/export.xlsx")
def risks_export_xlsx(payload: RiskBody) -> Response:
    report = score_risks(payload.analysis, payload.cases)
    return Response(
        content=risk_register_exports.to_xlsx(report),
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": 'attachment; filename="qa-genius-risk-register.xlsx"'
        },
    )


# Served from the site root (e.g. /style.css). On Vercel the CDN serves
# public/ first; locally this mount serves the same files. It must stay
# last so it never shadows the routes above. check_dir=False keeps
# startup working even if the folder is missing from the bundle.
app.mount(
    "/",
    StaticFiles(directory=BASE_DIR.parent / "public", check_dir=False),
    name="public",
)
