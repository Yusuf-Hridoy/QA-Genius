import html
import json
import logging
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator

import openai
from markupsafe import Markup

from qagenius import duel, llm
from qagenius.duel import NOT_STATED_A, NOT_STATED_B, DuelResult, build_highlights
from qagenius.models import (
    AmbiguityAnalysis,
    DuelComparison,
    Interpretation,
    TestCaseList,
)
from qagenius.numbers import match_numbers
from qagenius.prompts import story_check_prompt, test_cases_prompt
from qagenius.providers import PROVIDERS, get_provider, pick_default
from qagenius.test_case_exports import to_csv, to_xlsx
from qagenius.test_cases import (
    COVERAGE_FOCUS_OPTIONS,
    Criterion,
    build_user_text,
    compute_counts,
    compute_coverage,
    number_criteria,
    traced_ids,
)

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
SAMPLES_DIR = BASE_DIR / "samples"

STORY_LIMIT = 3000
CONTEXT_LIMIT = 1000
CRITERIA_LIMIT = 40
CRITERION_LIMIT = 1000

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
        request, "coming_soon.html", {"active": "bugs", "page": "Bug desk"}
    )


@app.get("/insights", response_class=HTMLResponse)
def insights_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "coming_soon.html", {"active": "insights", "page": "Quality insights"}
    )


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


class ExportRequest(BaseModel):
    """Body of the export routes. The browser sends back what it was given."""

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
) -> dict:
    """Everything the result card shows is computed here, never read from result.summary."""
    coverage = compute_coverage(result, criteria)
    counts = compute_counts(result)
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
        "categories": list(counts.by_category),
        "ac_text": {criterion.id: criterion.text for criterion in criteria},
        "category_pill": _category_pill,
        "priority_pill": _priority_pill,
        "coverage_pill": _coverage_pill(coverage.percent),
        "tc_data": {
            "result": result.model_dump(),
            "criteria": [criterion.text for criterion in criteria],
        },
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
        _test_cases_result_context(result, criteria, [], "saved example"),
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

# Served from the site root (e.g. /style.css). On Vercel the CDN serves
# public/ first; locally this mount serves the same files. It must stay
# last so it never shadows the routes above. check_dir=False keeps
# startup working even if the folder is missing from the bundle.
app.mount(
    "/",
    StaticFiles(directory=BASE_DIR.parent / "public", check_dir=False),
    name="public",
)
