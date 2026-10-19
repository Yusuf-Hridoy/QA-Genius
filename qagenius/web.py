import base64
import html
import json
import logging
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ValidationError, field_validator

import openai
from markupsafe import Markup

from qagenius import (
    automation,
    bug_report,
    duel,
    llm,
    risk_register_exports,
    ship_report_exports,
)
from qagenius.automation_checks import CheckReport, check_project
from qagenius.automation_exports import build_zip, run_steps
from qagenius.bug_report import BugInput, environment_text, reproducibility_text
from qagenius.bug_report_checks import Check, check_report, quality_score
from qagenius.bug_report_exports import to_jira, to_markdown
from qagenius.duel import NOT_STATED_A, NOT_STATED_B, DuelResult, build_highlights
from qagenius.models import (
    AmbiguityAnalysis,
    AutomationScript,
    BugReport,
    DuelComparison,
    DuelSummary,
    FailureMode,
    Interpretation,
    MatrixProposal,
    QualityInsightSummary,
    RiskAnalysis,
    TestCase,
    TestCaseList,
)
from qagenius.insights_summary import clean_summary, facts_text, insights_prompt
from qagenius.numbers import match_numbers
from qagenius.pairwise import (
    MAX_FACTORS,
    MAX_RULES,
    Factor,
    Rule,
    build_matrix,
    validate,
)
from qagenius.test_matrix_exports import (
    manual_only_count,
    projects,
    to_playwright_config,
)
from qagenius.test_matrix_exports import to_csv as matrix_to_csv
from qagenius.test_matrix_proposal import (
    clean_proposal,
    reasons_for,
    standard_set,
)
from qagenius.prompts import (
    automation_prompt,
    bug_report_prompt,
    risk_radar_prompt,
    story_check_prompt,
    test_cases_prompt,
    test_matrix_prompt,
    with_plain_words,
)
from qagenius.providers import PROVIDERS, get_provider, pick_default
from qagenius.report_parsers import ReportError, RunReport, parse_report
from qagenius.shadow_qa.review import (
    CODING_RULES,
    PRINCIPAL_PREFIX,
    PRINCIPAL_SOURCE,
    CaseReview,
    checklist_block,
    is_principal,
    reason_for,
    limit_conflicts,
    review_automation,
    review_risks,
    review_test_cases,
    risk_titles,
    with_context,
)
from qagenius.shadow_qa.story_rules import StoryNote, review_story
from qagenius.story_text import (
    split_confidence,
    strip_confidence_deep,
    without_criteria_lines,
)
from qagenius.ship_check import (
    CHECK_IDS,
    MAX_DETAILS,
    MatrixRun,
    MAX_REASON,
    MIN_REASON,
    TOOLS,
    VERDICT_LABELS,
    ShipInputs,
    ShipReport,
    compute_ship_report,
)
from qagenius.risk_radar import (
    MAX_RISKS,
    RiskReport,
    ScoredRisk,
    case_lines,
    clean_analysis,
    criteria_lines,
    score_risks,
)
from qagenius.test_case_depth import compute_depth, summary_line
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
ANALYZE_AGAIN_ERROR = "Read the reports again first."
SAMPLE_REPORTS = ("nightly-chromium.xml", "nightly-firefox.json")
# The AI's kind, shown as a pill. Mirrors GroupInsight.kind in models.py.
KIND_PILLS = {
    "product bug": "bad",
    "test issue": "warn",
    "environment": "info",
    "unknown": "neutral",
}
# The test-case kinds, in words a tester says out loud. The keys are the
# category values the code compares and the exports carry, so only the words
# on the screen change.
CATEGORY_WORDS = {
    "Negative": "Wrong input",
    "Boundary": "At the limit",
    "Edge Case": "Unusual case",
}
# The code check result, in words a reader does not have to decode. The report
# itself keeps the QA words, because the ZIP README is read by developers.
SYNTAX_WORDS = {
    "valid": "it parses",
    "basic check passed": "looks OK",
    "error": "error",
    "not checked": "not done yet",
}
# Starlette caps a form field at 1 MB, which a 2 MB screenshot exceeds once it is
# base64 (about 2.7 MB). Raised just for the bug form, still under Vercel's ~4.5 MB body.
FORM_PART_LIMIT = 4 * 1024 * 1024

app = FastAPI(title="QA-Genius v2")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
# Drawer + key panel live in base.html, rendered by every page.
templates.env.globals["providers"] = PROVIDERS
# Every template that shows model text uses this to take the confidence
# tag off the end of a line and show it as a pill instead.
templates.env.filters["confidence"] = split_confidence
# Plain words for values the code compares: the data keeps its spelling, the
# screen gets the words. Globals, so every template that shows a card has them.
templates.env.globals["category_words"] = CATEGORY_WORDS
templates.env.globals["syntax_words"] = SYNTAX_WORDS


@app.get("/health")
def health() -> str:
    return "ok"


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """The overview: what each desk does and where the key lives."""
    return templates.TemplateResponse(request, "home.html", {"active": "home"})


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
        {
            "active": "bugs",
            "devices": bug_report.DEVICE_OPTIONS,
            "page_title": "Turn rough notes into a report worth filing",
            "page_lede": (
                "Say what happened in your own words. QA-Genius writes the title, the "
                "steps and what should have happened instead. It then checks the "
                "report against what a developer will ask you."
            ),
            "eyebrow": "Bug desk",
        },
    )


@app.get("/insights", response_class=HTMLResponse)
def insights_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "insights.html",
        {
            "active": "insights",
            "page_title": "What your last test run is telling you",
            "page_lede": (
                "Drop in JUnit XML or Playwright JSON. Code groups the failures, finds "
                "the flaky tests and puts the slow ones in order. No API key needed, "
                "and nothing is sent to an AI unless you ask."
            ),
            "eyebrow": "Quality insights",
        },
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
        return {"ok": False, "error": "That answer made no sense. Try again."}
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
    request: Request,
    message: str,
    notes: list[str] | None = None,
    heading: str | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "_error.html",
        {"message": message, "notes": notes or [], "heading": heading},
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


SAVED_EXAMPLE = "saved example"


def _score_tone(score: int) -> str:
    """Reserved status scale: a score always ships with its word, never a hue alone."""
    if score >= 75:
        return "ok"
    return "warn" if score >= 45 else "bad"


def _shadow_story(story: str, criteria: list[str]) -> tuple[StoryNote | None, list[StoryNote]]:
    """The Principal QA read of the story: the epic warning, then the rest."""
    found = review_story(story, criteria)
    epic = next((note for note in found if note.epic), None)
    return epic, [note for note in found if not note.epic]


def _story_result_context(
    request: Request,
    story: str,
    result: AmbiguityAnalysis,
    notes: list[str],
    provider_name: str,
    context: str = "",
) -> dict:
    rows, passes = _invest_rows(result)
    clarity = max(0, 100 - result.ambiguity_score)
    # Same click: the rules run on the result that just came back, no AI.
    epic, shadow_notes = _shadow_story(story, result.generated_acceptance_criteria)
    return {
        "epic": epic,
        "shadow_notes": shadow_notes,
        # A limit two criteria disagree about, or none of them decides, is
        # worth saying here: it is cheaper to fix a criterion than a suite.
        "limit_notes": limit_conflicts(
            with_context(
                number_criteria(result.generated_acceptance_criteria), context
            ),
            [],
        ),
        "result": result,
        "clarity_score": clarity,
        "score_tone": _score_tone(clarity),
        "is_example": provider_name == SAVED_EXAMPLE,
        "invest_rows": rows,
        "invest_passes": passes,
        "highlighted_story": _highlight_story(
            story, [vp.phrase for vp in result.vague_phrases]
        ),
        "acceptance_criteria": "\n\n".join(result.generated_acceptance_criteria),
        "criteria_list": result.generated_acceptance_criteria,
        # Ship check and Risk radar read this back and have nowhere to put
        # a confidence pill, so the tags come off before it is stored.
        "analysis_data": strip_confidence_deep(result.model_dump()),
        # Criteria were drafted, so "no acceptance criteria" is no longer
        # true. Ship check drops the same lines.
        "missing_elements": without_criteria_lines(
            result.missing_elements, bool(result.generated_acceptance_criteria)
        ),
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
        # What the browser keeps for Ship check: the gap, not the whole duel.
        "duel_data": {
            "agreement_pct": result.agreement_pct,
            "forks": [
                {"topic": fork.topic, "severity": fork.severity} for fork in forks
            ],
        },
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
    user = with_plain_words(user)
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
        _story_result_context(
            request, user_story, result, notes, provider_name, context
        ),
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


class _CriteriaBody(BaseModel):
    """The run's criteria on their own, before step 3 has written any cases.

    Story clarity is judged against them, so they have to reach the server
    even when there is no test case list to carry them.
    """

    criteria: list[str] = []

    @field_validator("criteria")
    @classmethod
    def _within_limits(cls, value: list[str]) -> list[str]:
        if len(value) > CRITERIA_LIMIT:
            raise ValueError(f"Send at most {CRITERIA_LIMIT} criteria.")
        if any(len(text) > CRITERION_LIMIT for text in value):
            raise ValueError(f"Keep each criterion under {CRITERION_LIMIT} characters.")
        return value


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


def _nothing_to_add_line(review: CaseReview) -> str:
    """What the box says when the AI left the senior tester nothing to do.

    The box used to disappear in that case, which reads as "the rules did
    not run" rather than "the rules ran and found nothing".
    """
    checked = len(review.covered)
    if not checked:
        return (
            "A senior tester has nothing to add for this kind of story. "
            "Nothing to add."
        )
    things = "thing" if checked == 1 else "things"
    return (
        f"The AI already covered all {checked} {things} a senior tester "
        "checks for this story. Nothing to add."
    )


def _review_line(review: CaseReview) -> str:
    """The one line on the Principal QA review card, before it is opened."""
    if not review.added and not review.conflicts:
        return _nothing_to_add_line(review)
    parts = []
    # A test that argues with a criterion is the most valuable thing here,
    # so it is said before anything that was added.
    if review.conflicts:
        count = len(review.conflicts)
        parts.append(
            f"{count} disagreement{'' if count == 1 else 's'} about a limit"
        )
    if review.added:
        parts.append(
            f"Added {len(review.added)} case{'' if len(review.added) == 1 else 's'} "
            "the AI missed"
        )
    if review.more:
        parts.append(f"{len(review.more)} more idea{'' if len(review.more) == 1 else 's'}")
    if review.quality:
        parts.append(
            f"{len(review.quality)} note{'' if len(review.quality) == 1 else 's'} "
            "on weak cases"
        )
    return " · ".join(parts)


def _test_cases_result_context(
    result: TestCaseList,
    criteria: list[Criterion],
    notes: list[str],
    provider_name: str,
    is_example: bool = False,
    review: CaseReview | None = None,
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
        "depth_line": summary_line(depth),
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
        "review": review,
        "review_line": _review_line(review) if review else "",
        "is_principal": is_principal,
        "pq_reason": reason_for,
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
    context: str = Form(default=""),
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
    # The checklist rides along with the request the user already made. The v1
    # prompt text is untouched; this is appended to the user text.
    user = with_plain_words(user + checklist_block(user_story, criteria, context)[0])
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
    merged, review = _with_principal_cases(
        user_story, criteria, result, context
    )
    return templates.TemplateResponse(
        request,
        "_test_cases_result.html",
        _test_cases_result_context(
            merged,
            criteria,
            notes,
            provider["name"] if provider else "unknown provider",
            review=review,
        ),
    )


def _with_principal_cases(
    story: str, criteria: list[Criterion], result: TestCaseList, context: str = ""
) -> tuple[TestCaseList, CaseReview]:
    """The AI's cases plus the ones it missed. Every count is then taken from this."""
    review = review_test_cases(story, criteria, result, context)
    merged = TestCaseList(
        test_cases=list(result.test_cases) + list(review.added),
        summary=result.summary,
    )
    return merged, review


def _test_cases_sample() -> tuple[TestCaseList, list[Criterion], str]:
    with open(SAMPLES_DIR / "test_cases.json", encoding="utf-8") as f:
        sample = json.load(f)
    return (
        TestCaseList.model_validate(sample["result"]),
        number_criteria(sample["criteria"]),
        str(sample.get("story") or ""),
    )


def _example_suite() -> tuple[TestCaseList, list[Criterion], CaseReview, str]:
    """The saved suite with Principal QA's additions, exactly as a run shows it."""
    result, criteria, story = _test_cases_sample()
    merged, review = _with_principal_cases(story, criteria, result)
    return merged, criteria, review, story


@app.get("/requirements/test-cases/example", response_class=HTMLResponse)
def test_cases_example(request: Request) -> HTMLResponse:
    """Load example: a saved suite, reviewed. No key needed, no AI call."""
    merged, criteria, review, _ = _example_suite()
    return templates.TemplateResponse(
        request,
        "_test_cases_result.html",
        _test_cases_result_context(
            merged, criteria, [], "saved example", is_example=True, review=review
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
            "Criteria tested",
            compute_coverage(current, criteria).percent,
            compute_coverage(proposed, criteria).percent,
            "up",
            "%",
        ),
        (
            "Criteria needing more tests",
            len(before_depth.thin_ids),
            len(after_depth.thin_ids),
            "down",
            "",
        ),
        (
            "Wrong input",
            before_counts.by_category.get("Negative", 0),
            after_counts.by_category.get("Negative", 0),
            "up",
            "",
        ),
        (
            "At the limit",
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
        "is_principal": is_principal,
        "pq_reason": reason_for,
        "proposal": {
            "result": proposed.model_dump(),
            "criteria": [criterion.text for criterion in criteria],
        },
        "notes": notes,
        "provider_name": provider_name,
    }


FIELD_LABELS = {
    "title": "Title",
    "category": "Kind",
    "priority": "Priority",
    "pre_conditions": "Before you start",
    "steps": "Steps",
    "expected_result": "What should happen",
    "test_data": "Data to use",
    "bdd_scenario": "Given / When / Then version",
    "traceability": "Linked to",
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
    context: str = Form(default=""),
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
    user = with_plain_words(user + checklist_block(user_story, criteria, context)[0])
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
    # Principal QA cases join the proposal, so they show as added in the diff.
    proposed, _ = _with_principal_cases(user_story, criteria, proposed, context)
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
    # The page already shows the reviewed suite, so the diff is against that
    # one; otherwise every Principal QA case would read as "removed".
    current, criteria, _, _ = _example_suite()
    saved, _, _ = _test_cases_sample()
    known = {case.id for case in saved.test_cases}
    with open(SAMPLES_DIR / "test_cases_strengthened.json", encoding="utf-8") as f:
        sample = json.load(f)
    stronger = TestCaseList.model_validate(sample["result"])
    # The saved proposal numbers its new cases from where the saved suite
    # ended; the Principal QA cases now sit there, so the ids come off and
    # merge_strengthened gives them the next free ones.
    fresh = TestCaseList(
        test_cases=[
            case.model_copy(update={"id": ""})
            for case in stronger.test_cases
            if case.id not in known
        ],
        summary=stronger.summary,
    )
    proposed = merge_strengthened(current, fresh)
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


def _checked_project(script: AutomationScript, selected_ids: list[str]) -> CheckReport:
    """The existing checks plus what a principal QA would send back. No AI."""
    report = check_project(script, selected_ids)
    extra = review_automation(script, report.files)
    if not extra:
        return report
    return replace(report, findings=list(report.findings) + extra)


def _is_pq_finding(finding) -> bool:
    return str(finding.message or "").startswith(PRINCIPAL_PREFIX)


def _finding_text(finding) -> str:
    """The message without the label, which the card draws as a pill instead."""
    message = str(finding.message or "")
    return message[len(PRINCIPAL_PREFIX):] if _is_pq_finding(finding) else message


def _automation_result_context(
    script: AutomationScript,
    report: CheckReport,
    selected_ids: list[str],
    notes: list[str],
    provider_name: str,
    is_example: bool = False,
) -> dict:
    # The two stats mean one thing each: Syntax is about the code parsing,
    # Principal QA is about what a reviewer would send back. No finding is
    # counted in both.
    checked = [one for one in report.findings if not _is_pq_finding(one)]
    principal = [one for one in report.findings if _is_pq_finding(one)]
    warnings = [finding for finding in checked if finding.level == "warning"]
    errors = [finding for finding in checked if finding.level == "error"]
    return {
        "script": script,
        "report": report,
        "selected_ids": selected_ids,
        "traced_total": len(report.traced) + len(report.missing),
        "warnings": warnings,
        "errors": errors,
        "principal_findings": principal,
        "syntax_label": "all fine" if not errors else f"{len(errors)} error"
        + ("s" if len(errors) != 1 else ""),
        "notes": notes,
        "provider_name": provider_name,
        "is_example": is_example,
        "is_pq_finding": _is_pq_finding,
        "finding_text": _finding_text,
        # Worked out from the files in the ZIP, not from the AI's instructions.
        "run_it": run_steps(script, report.files),
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
    user = with_plain_words(
        automation.build_user_text(base_user, cases, base_url) + CODING_RULES
    )
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
    report = _checked_project(script, selected_ids)
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
    report = _checked_project(script, selected_ids)
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

RISK_BAD_INPUT = "Check the story, the criteria and the test cases, then try again."
RISK_NO_STORY = "Start from a story in Requirements first."
RISK_NO_KEY = '<p class="muted">Add an API key to find risks.</p>'
LEVEL_PILLS = {"high": "bad", "medium": "warn", "low": "ok"}
COVERAGE_TONES = {"verified": "ok", "covered": "ok", "weak": "warn", "none": "bad"}
# A cell of the heat map, coloured by severity x likelihood.
HEAT_BAD, HEAT_WARN = 15, 8
# The heat map encodes one magnitude - severity x likelihood, 1..25 - so it
# takes one sequential ramp, light to dark, not a traffic-light mix. Every
# cell that holds a risk also prints its id, so colour is never the only cue.
HEAT_STEPS = ((2, "s1"), (5, "s2"), (9, "s3"), (14, "s4"), (19, "s5"))


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
            tone = "s6"
            for ceiling, step in HEAT_STEPS:
                if product <= ceiling:
                    tone = step
                    break
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
    answered_line: str = "",
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
        "answered_line": answered_line,
        "principal_source": PRINCIPAL_SOURCE,
    }


TYPICAL_RISKS_HEAD = "Typical risks for this kind of feature (consider them too):"


def _typical_risks_block(story: str, criteria: list[str]) -> str:
    """What a principal QA would hand the AI before it starts. No AI, no key."""
    titles = risk_titles(story, criteria)
    if not titles:
        return ""
    lines = [TYPICAL_RISKS_HEAD] + [f"- {one}" for one in titles]
    return "\n\n" + "\n".join(lines)


def _risk_result(request: Request, **context) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "_risk_radar_result.html", _risk_result_context(**context)
    )


@app.get("/risks", response_class=HTMLResponse)
def risks_page(request: Request) -> HTMLResponse:
    """The page is empty; the browser fills it from sessionStorage."""
    return templates.TemplateResponse(
        request,
        "risk_radar.html",
        {
            "active": "risks",
            "page_title": "Where this feature is most likely to break",
            "page_lede": (
                "Risk radar reads your story, criteria and tests. It lists the ways "
                "this feature can break, gives each one a risk score, and checks if "
                "a test already covers it."
            ),
            "eyebrow": "Risk radar",
        },
    )


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
    user = with_plain_words(user + _typical_risks_block(user_story, texts))
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

    known_ids = ({criterion.id for criterion in criteria}, {case.id for case in cases})
    analysis, guard_notes = clean_analysis(result, *known_ids)
    # The classics the AI left out, numbered and scored like everything else.
    extra = review_risks(user_story, texts, analysis)
    if extra:
        analysis, _ = clean_analysis(
            RiskAnalysis(failure_modes=list(analysis.failure_modes) + extra), *known_ids
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


RECHECKED_BY_CODE = "Rechecked by code — no AI."
ADJUSTED_SCORES = "Updated with your adjusted scores."


@app.post("/risks/rescore", response_class=HTMLResponse)
def risks_rescore(
    request: Request, payload: RiskBody, by: str = Query(default="scores")
) -> HTMLResponse:
    """Re-draw the card. No AI call either way, but say which way it was.

    `by=code` is the automatic recheck when new test cases arrive;
    anything else is someone having moved a score by hand.
    """
    automatic = by == "code"
    return _risk_result(
        request,
        analysis=payload.analysis,
        cases=payload.cases,
        criteria=number_criteria(payload.criteria),
        notes=[],
        provider_name="code" if automatic else "your adjusted scores",
        answered_line=RECHECKED_BY_CODE if automatic else ADJUSTED_SCORES,
    )


def _risk_sample() -> tuple[RiskAnalysis, list[TestCase], list[Criterion]]:
    with open(SAMPLES_DIR / "risk_radar.json", encoding="utf-8") as f:
        sample = json.load(f)
    analysis = RiskAnalysis.model_validate(sample["analysis"])
    cases = [TestCase.model_validate(case) for case in sample["cases"]]
    criteria = number_criteria(sample["criteria"])
    story = str(sample.get("story") or "")
    # The example runs the reviewer too, so Load example shows what a real run
    # shows. Still no key and still no AI call.
    extra = review_risks(story, [item.text for item in criteria], analysis)
    if extra:
        analysis, _ = clean_analysis(
            RiskAnalysis(failure_modes=list(analysis.failure_modes) + extra),
            {item.id for item in criteria},
            {case.id for case in cases},
        )
    return analysis, cases, criteria


@app.get("/risks/example", response_class=HTMLResponse)
def risks_example(request: Request) -> HTMLResponse:
    """Load example: a saved FMEA, reviewed. No key needed, no AI call."""
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


# ──────────────────────────────────────────────────────────────────────────────
# Ship check: the release verdict. No AI, no key, nothing stored.
# ──────────────────────────────────────────────────────────────────────────────

SHIP_BODY_LIMIT = 2_000_000
SHIP_BAD_BODY = "Could not read your results. Open Ship check again."
SHIP_TOO_BIG = "That run is too large to check. Trim the test cases and try again."
# Each part of the body is validated on its own: one tool's bad data must not
# hide the other six.
SHIP_PART_LABELS = {
    "story_analysis": "story analysis",
    "duel_summary": "ambiguity duel",
    "test_cases": "test cases",
    "criteria": "acceptance criteria",
    "risk_analysis": "risk analysis",
    "automation": "automation",
    "insights": "test run",
    "matrix": "test matrix",
    "acceptances": "acceptances",
}
SHIP_VERDICT_TONES = {"ship": "ok", "ship_with_risks": "warn", "dont_ship": "bad"}
SHIP_STATUS_TONES = {
    "pass": "ok",
    "warn": "warn",
    "fail": "bad",
    "accepted": "warn",
    "not_checked": "neutral",
}
SHIP_STATUS_LABELS = {
    "pass": "fine",
    "warn": "check this",
    "fail": "needs fixing",
    "accepted": "accepted",
    "not_checked": "not done yet",
}
STORY_IN_BANNER = 160


def matrix_from_dict(raw) -> MatrixRun:
    """The matrix a browser saved, as Ship check reads it.

    Only the counts matter here; the rows themselves live on the matrix page.
    Anything misshapen raises, and _ship_part turns that into "not checked".
    """
    if not isinstance(raw, dict):
        raise ValueError("matrix must be an object")
    runs = raw.get("runs")
    if not isinstance(runs, int) or isinstance(runs, bool) or runs < 0:
        raise ValueError("matrix.runs must be a whole number")

    def whole(name: str) -> int:
        value = raw.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return 0
        return value

    names = [
        str(one.get("name") or "")
        for one in (raw.get("factors") or [])
        if isinstance(one, dict) and one.get("name")
    ]
    return MatrixRun(
        runs=runs,
        valid_pairs=whole("valid_pairs"),
        covered_pairs=whole("covered_pairs"),
        manual_only=whole("manual_only"),
        factors=names[:MAX_DETAILS],
    )


def _ship_part(raw: dict, key: str, build, ignored: list[str]):
    """One part of the body, or None. Bad data is missing data, never an error."""
    value = raw.get(key)
    if value is None:
        return None
    try:
        return build(value)
    except (ValidationError, ValueError, TypeError, KeyError, AttributeError):
        ignored.append(SHIP_PART_LABELS[key])
        return None


def _ship_stale(raw: dict) -> list[str]:
    """Check ids the browser says were built from older work.

    Anything that is not a known check id is dropped without comment:
    this is a hint from the page, not data worth an error card.
    """
    value = raw.get("stale_inputs")
    if not isinstance(value, list):
        return []
    return [one for one in value if isinstance(one, str) and one in CHECK_IDS]


def _ship_acceptances(raw: dict, ignored: list[str]) -> dict[str, str]:
    """check id -> written reason. Unknown ids and non-text drop out."""
    value = raw.get("acceptances")
    if value is None:
        return {}
    if not isinstance(value, dict):
        ignored.append(SHIP_PART_LABELS["acceptances"])
        return {}
    return {
        key: value[key]
        for key in CHECK_IDS
        if isinstance(value.get(key), str) and value[key].strip()
    }


def _ship_inputs(raw: dict) -> tuple[ShipInputs, list[str]]:
    ignored: list[str] = []
    # Ship check quotes the same sentences the story page shows, and a model
    # writes its confidence in every shape it can think of. The story page and
    # this share one helper, so a tag never reaches a detail line here either.
    raw = strip_confidence_deep(raw)

    suite = _ship_part(
        raw, "test_cases", lambda part: _SuiteBody.model_validate(part), ignored
    )
    risks = _ship_part(raw, "risk_analysis", RiskBody.model_validate, ignored)
    auto = _ship_part(raw, "automation", AutomationExportRequest.model_validate, ignored)
    # The suite carries the criteria once step 3 has run; before that they
    # arrive on their own, and story clarity is judged against them either way.
    loose = _ship_part(raw, "criteria", lambda part: _CriteriaBody(criteria=part), ignored)

    return (
        ShipInputs(
            story=_ship_story(raw),
            context=str(raw.get("context") or "")[:CONTEXT_LIMIT],
            story_analysis=_ship_part(
                raw, "story_analysis", AmbiguityAnalysis.model_validate, ignored
            ),
            duel=_ship_part(raw, "duel_summary", DuelSummary.model_validate, ignored),
            test_cases=suite.result if suite else None,
            criteria=list(suite.criteria) if suite else (list(loose.criteria) if loose else []),
            risk_analysis=risks.analysis if risks else None,
            risk_cases=list(risks.cases) if risks else [],
            automation_script=auto.script if auto else None,
            automation_selected_ids=list(auto.selected_ids) if auto else [],
            insights=_ship_part(raw, "insights", insights_from_dict, ignored),
            matrix=_ship_part(raw, "matrix", matrix_from_dict, ignored),
            acceptances=_ship_acceptances(raw, ignored),
            stale_inputs=_ship_stale(raw),
        ),
        ignored,
    )


def _ship_story(raw: dict) -> str:
    story = raw.get("story")
    return story.strip() if isinstance(story, str) else ""


def _ship_result(
    request: Request, report: ShipReport, story: str, ignored: list[str]
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "_ship_check_result.html",
        {
            "report": report,
            "story": story,
            "story_short": story[:STORY_IN_BANNER],
            "total_checks": len(report.items),
            "verdict_label": VERDICT_LABELS[report.verdict],
            "verdict_tone": SHIP_VERDICT_TONES[report.verdict],
            "status_tones": SHIP_STATUS_TONES,
            "status_labels": SHIP_STATUS_LABELS,
            "tools": TOOLS,
            "ignored": ignored,
            # Copy as Markdown reads this; the browser never builds it.
            "markdown": ship_report_exports.to_markdown(report, story),
            "min_reason": MIN_REASON,
            "max_reason": MAX_REASON,
        },
    )


@app.get("/ship", response_class=HTMLResponse)
def ship_page(request: Request) -> HTMLResponse:
    """The page is empty; the browser fills it from sessionStorage."""
    return templates.TemplateResponse(
        request,
        "ship_check.html",
        {
            "active": "ship",
            "page_title": "Can we release this feature?",
            "page_lede": (
                "Ship check reads what the other desks already worked out and turns "
                "it into one decision you can defend. Nothing is sent to an AI."
            ),
            "eyebrow": "Ship check",
        },
    )


RING_VALUES = (0, 7, 44, 100)
RING_TONES = {0: "bad", 7: "bad", 44: "warn", 100: "ok"}


@app.get("/dev/rings", response_class=HTMLResponse)
def dev_rings(request: Request) -> HTMLResponse:
    """A check page: every round score at the values that used to overflow.

    Not a desk and not in the rail. It exists so the number inside the circle
    can be seen at 1366px and at 390px without running a desk first.
    """
    return templates.TemplateResponse(
        request,
        "dev_rings.html",
        {
            "rings": [
                {
                    "pct": value,
                    "tone": RING_TONES[value],
                    "label": "tested",
                    "title": f"{value} percent of this is tested",
                }
                for value in RING_VALUES
            ],
        },
    )


@app.get("/dev/next-row", response_class=HTMLResponse)
def dev_next_row(request: Request) -> HTMLResponse:
    """A check page: the "Next:" row in all three states, marks and all.

    Not a desk and not in the rail. The real row fills its marks in from the
    run, so this is the only way to see all three at once in a screenshot.
    """
    return templates.TemplateResponse(request, "dev_next_row.html", {})


@app.post("/ship/report", response_class=HTMLResponse)
async def ship_report_route(request: Request) -> HTMLResponse:
    """Every status is computed here, from the browser's own results. No AI call."""
    body = await request.body()
    if len(body) > SHIP_BODY_LIMIT:
        return HTMLResponse(
            templates.get_template("_error.html").render(
                {"message": SHIP_TOO_BIG, "notes": []}
            ),
            status_code=413,
        )
    try:
        raw = json.loads(body or b"{}")
    except json.JSONDecodeError:
        return _error_card(request, SHIP_BAD_BODY)
    if not isinstance(raw, dict):
        return _error_card(request, SHIP_BAD_BODY)

    inputs, ignored = _ship_inputs(raw)
    return _ship_result(request, compute_ship_report(inputs), _ship_story(raw), ignored)


@app.get("/ship/example", response_class=HTMLResponse)
def ship_example(request: Request) -> HTMLResponse:
    """Load example: a saved run that cannot ship. No key needed, no AI call."""
    with open(SAMPLES_DIR / "ship_check.json", encoding="utf-8") as f:
        sample = json.load(f)
    inputs, ignored = _ship_inputs(sample)
    return _ship_result(
        request, compute_ship_report(inputs), _ship_story(sample), ignored
    )

# ──────────────────────────────────────────────────────────────────────────────
# Smart test matrix: the AI proposes the factors, code computes the runs.
# ──────────────────────────────────────────────────────────────────────────────

MATRIX_NO_KEY_NOTE = (
    "These are the usual things to vary. Add an AI key and QA-Genius will "
    "pick them from your own story."
)
MAX_PINNED = 20
MATRIX_BAD_INPUT = "Some of that run did not reach the server. Reload the page and try again."


class MatrixFactorBody(BaseModel):
    name: str
    values: list[str] = []
    reason: str = ""


class MatrixRuleBody(BaseModel):
    if_factor: str
    if_value: str
    then_factor: str
    then_value: str
    reason: str = ""
    source: str = "standard"


class MatrixBody(BaseModel):
    """The factors, rules and pinned runs the editor currently holds."""

    factors: list[MatrixFactorBody] = []
    rules: list[MatrixRuleBody] = []
    pinned: list[dict[str, str]] = []
    # Whether a model proposed these factors, so the footer stays honest
    # when the page is reopened from what the browser saved.
    from_ai: bool = False

    @field_validator("factors")
    @classmethod
    def _not_too_many(cls, value: list[MatrixFactorBody]) -> list[MatrixFactorBody]:
        if len(value) > MAX_FACTORS:
            raise ValueError(f"Send at most {MAX_FACTORS} factors.")
        return value

    @field_validator("rules")
    @classmethod
    def _not_too_many_rules(cls, value: list[MatrixRuleBody]) -> list[MatrixRuleBody]:
        if len(value) > MAX_RULES:
            raise ValueError(f"Send at most {MAX_RULES} rules.")
        return value

    @field_validator("pinned")
    @classmethod
    def _not_too_many_pins(cls, value: list[dict[str, str]]) -> list[dict[str, str]]:
        if len(value) > MAX_PINNED:
            raise ValueError(f"Pin at most {MAX_PINNED} runs.")
        return value

    def as_engine(self) -> tuple[list[Factor], list[Rule]]:
        factors = [
            Factor(name=one.name, values=tuple(one.values)) for one in self.factors
        ]
        rules = [
            Rule(
                if_factor=one.if_factor,
                if_value=one.if_value,
                then_factor=one.then_factor,
                then_value=one.then_value,
                reason=one.reason,
                source="ai" if one.source == "ai" else "standard",
            )
            for one in self.rules
        ]
        return factors, rules


def _saved_matrix(raw: str) -> tuple[list[Factor], list[Rule], bool] | None:
    """The factors the browser already has, or None to suggest fresh ones."""
    if not (raw or '').strip():
        return None
    try:
        body = MatrixBody.model_validate_json(raw)
    except (ValidationError, ValueError):
        return None
    factors, rules = body.as_engine()
    if validate(factors, rules):
        return None
    return factors, rules, body.from_ai


def _matrix_context(
    factors: list[Factor],
    rules: list[Rule],
    matrix,
    notes: list[str],
    reasons: dict[str, str] | None = None,
    from_ai: bool = False,
) -> dict:
    manual = manual_only_count(matrix)
    return {
        "factors": factors,
        "rules": rules,
        "matrix": matrix,
        "notes": notes,
        "reasons": reasons or {},
        "manual_only": manual,
        "automated": len(matrix.rows) - manual,
        "from_ai": from_ai,
        "run_ids": [f"M{index:02d}" for index in range(1, len(matrix.rows) + 1)],
        "row_is_manual": [
            bool(project.get("manual_only")) for project in projects(matrix)
        ],
        # What test_matrix.js stores in the run for Ship check.
        "matrix_data": {
            "factors": [
                {"name": one.name, "values": list(one.values)} for one in factors
            ],
            "rules": [
                {
                    "if_factor": one.if_factor,
                    "if_value": one.if_value,
                    "then_factor": one.then_factor,
                    "then_value": one.then_value,
                    "reason": one.reason,
                }
                for one in rules
            ],
            "pinned": [
                dict(zip([factor.name for factor in matrix.factors], row))
                for row in matrix.rows[: matrix.pinned_rows]
            ],
            "runs": len(matrix.rows),
            "valid_pairs": matrix.valid_pairs,
            "covered_pairs": matrix.covered_pairs,
            "manual_only": manual,
            "from_ai": from_ai,
        },
    }


@app.get("/requirements/matrix", response_class=HTMLResponse)
def matrix_page(request: Request) -> HTMLResponse:
    """Step 3½: which browsers, devices and users to run the cases on."""
    return templates.TemplateResponse(
        request,
        "test_matrix.html",
        {
            "active": "matrix",
            "page_title": "Which runs actually need testing?",
            "page_lede": (
                "Browsers times devices times roles times languages is hundreds of "
                "runs. Code works out the fewest runs where every two options are "
                "still tested together, and proves it."
            ),
            "eyebrow": "Test matrix",
        },
    )


@app.post("/requirements/matrix/suggest", response_class=HTMLResponse)
def matrix_suggest(
    request: Request,
    user_story: str = Form(default=""),
    criteria_json: str = Form(default="[]"),
    cases_json: str = Form(default="[]"),
    saved_json: str = Form(default=""),
) -> HTMLResponse:
    """Factors worth varying for this story. Without a key, the standard set."""
    story = user_story.strip()
    if len(story) > STORY_LIMIT:
        return _error_card(request, MATRIX_BAD_INPUT)
    texts = _parse_criteria_json(criteria_json)
    cases = _parse_cases_json(cases_json)
    if texts is None or cases is None:
        return _error_card(request, MATRIX_BAD_INPUT)

    # Factors the browser already holds come back as they are. Reopening a
    # page must never spend the user's key, and must never quietly replace
    # factors they edited by hand.
    saved = _saved_matrix(saved_json)
    if saved is not None:
        factors, rules, from_ai = saved
        matrix = build_matrix(factors, rules)
        return templates.TemplateResponse(
            request,
            "_test_matrix_editor.html",
            _matrix_context(factors, rules, matrix, [], from_ai=from_ai),
        )

    keys = _request_keys(request)
    reasons: dict[str, str] = {}
    notes: list[str] = []
    from_ai = False
    if not keys or not story:
        factors, rules = standard_set()
        notes.append(MATRIX_NO_KEY_NOTE)
    else:
        criteria = number_criteria(texts)
        system, user = test_matrix_prompt(
            story, criteria_lines(criteria), case_lines(cases)
        )
        user = with_plain_words(user)
        try:
            result, _used, call_notes = llm.generate_json(
                keys, system, user, MatrixProposal
            )
        except (llm.NoKeysError, llm.AllKeysBusyError, llm.InvalidKeyError,
                llm.ModelUnavailableError, llm.ProviderError, llm.BadOutputError):
            # The matrix is too useful to lose to a key problem.
            factors, rules = standard_set()
            notes.append(MATRIX_NO_KEY_NOTE)
        else:
            factors, rules, guard_notes = clean_proposal(
                result, "\n".join([story, *texts])
            )
            from_ai = True
            reasons = reasons_for(result)
            notes = call_notes + guard_notes

    matrix = build_matrix(factors, rules)
    return templates.TemplateResponse(
        request,
        "_test_matrix_editor.html",
        _matrix_context(factors, rules, matrix, notes, reasons, from_ai),
    )


@app.post("/requirements/matrix/build", response_class=HTMLResponse)
def matrix_build(request: Request, payload: MatrixBody) -> HTMLResponse:
    """Recompute the matrix after an edit. No AI, no key."""
    factors, rules = payload.as_engine()
    problems = validate(factors, rules)
    if problems:
        return _error_card(request, problems[0], problems[1:])
    try:
        matrix = build_matrix(factors, rules, payload.pinned)
    except ValueError as error:
        return _error_card(request, str(error))
    return templates.TemplateResponse(
        request,
        "_test_matrix_result.html",
        _matrix_context(factors, rules, matrix, []),
    )


def _matrix_or_422(payload: MatrixBody):
    factors, rules = payload.as_engine()
    if validate(factors, rules):
        raise HTTPException(status_code=422, detail="Those factors do not make a matrix.")
    try:
        return build_matrix(factors, rules, payload.pinned)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/requirements/matrix/export/playwright")
def matrix_export_playwright(payload: MatrixBody) -> Response:
    return Response(
        content=to_playwright_config(_matrix_or_422(payload)),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="playwright.matrix.config.ts"'
        },
    )


@app.post("/requirements/matrix/export/csv")
def matrix_export_csv(payload: MatrixBody) -> Response:
    return Response(
        content=matrix_to_csv(_matrix_or_422(payload)),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="test-matrix.csv"'},
    )


@app.get("/requirements/matrix/example", response_class=HTMLResponse)
def matrix_example(request: Request) -> HTMLResponse:
    """Load example: the Aurora Storefront login story. No AI call."""
    with open(SAMPLES_DIR / "test_matrix.json", encoding="utf-8") as f:
        sample = json.load(f)
    factors = [
        Factor(name=one["name"], values=tuple(one["values"]))
        for one in sample["factors"]
    ]
    rules = [Rule(**one) for one in sample.get("rules", [])]
    matrix = build_matrix(factors, rules)
    context = _matrix_context(
        factors, rules, matrix, [], sample.get("reasons", {})
    )
    context["is_example"] = True
    return templates.TemplateResponse(request, "_test_matrix_editor.html", context)


# Served from the site root (e.g. /style.css). On Vercel the CDN serves
# public/ first; locally this mount serves the same files. It must stay
# last so it never shadows the routes above. check_dir=False keeps
# startup working even if the folder is missing from the bundle.
app.mount(
    "/",
    StaticFiles(directory=BASE_DIR.parent / "public", check_dir=False),
    name="public",
)
