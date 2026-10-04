import html
import json
import logging
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import openai

from qagenius import llm
from qagenius.models import AmbiguityAnalysis
from qagenius.prompts import story_check_prompt
from qagenius.providers import PROVIDERS, get_provider, pick_default

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
SAMPLES_DIR = BASE_DIR / "samples"

STORY_LIMIT = 3000
CONTEXT_LIMIT = 1000

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
        "notes": notes,
        "provider_name": provider_name,
    }


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
    return HTMLResponse(story_field + type_field + context_field + body)


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


# Served from the site root (e.g. /style.css). On Vercel the CDN serves
# public/ first; locally this mount serves the same files. It must stay
# last so it never shadows the routes above. check_dir=False keeps
# startup working even if the folder is missing from the bundle.
app.mount(
    "/",
    StaticFiles(directory=BASE_DIR.parent / "public", check_dir=False),
    name="public",
)
