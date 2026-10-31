"""Key rotation + JSON calls.

Keys arrive per request (never stored). They are tried in the user's order:
- 429 or 5xx/timeout -> try the next key.
- 401/403 -> mark the key invalid, try the next key.
- 404 model retired, or 402 no credit -> try the next key.
- anything else -> stop with a friendly error.

Model ids come from each provider's live /models list (picked per key);
hard-coded names are never trusted.

Keys are NEVER printed, logged, or put in an error message.
Logs mention only the provider name and the key position.
"""

import json
import logging
import re
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

import openai
from pydantic import BaseModel, ValidationError

from qagenius import json_repair_utils
from qagenius.providers import get_provider, pick_default

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 45.0
MODELS_TIMEOUT = 20.0

# Model ids containing any of these are not chat models.
CHAT_DROP = (
    "embed",
    "whisper",
    "tts",
    "audio",
    "image",
    "vision-preview",
    "guard",
    "moderation",
    "rerank",
    "transcribe",
    "dall-e",
    "imagen",
    "veo",
    "aqa",
)

MODEL_RE = re.compile(r"[A-Za-z0-9\-_./:]+")
KEYLIKE_RE = re.compile(r"[A-Za-z0-9\-_]{20,}")

# A 400/404/422 mentioning one of these means the model cannot read the image,
# so the same key is worth one more try with the text alone.
IMAGE_MARKERS = ("image", "vision", "multimodal", "content type", "image_url")


class NoKeysError(Exception):
    """Raised when the request carries no keys."""


class AiError(Exception):
    """Something went wrong talking to the AI, with one plain note per key.

    Every desk shows these the same way, so they share a base: the desk
    supplies its own title and this carries the words.

    `kind` is which of the four things went wrong, in the words the page
    uses: "key" a key was refused, "busy" every key is rate limited,
    "server" the other end broke, "model" the model is gone, "output" no
    key could answer in the shape the desk needs. `provider` is the short
    name of the provider whose key was refused, when one key is to blame.
    A page never shows a status code or a line of JSON, so both of these
    carry the meaning instead.
    """

    kind = ""

    def __init__(
        self,
        message: str,
        notes: list[str] | None = None,
        kind: str = "",
        provider: str = "",
    ) -> None:
        super().__init__(message)
        self.notes = list(notes or [])
        if kind:
            self.kind = kind
        self.provider = provider


class AllKeysBusyError(AiError):
    """Raised when every key failed with a retryable (busy/down) error."""

    kind = "busy"

    def __init__(self, notes: list[str]) -> None:
        super().__init__("All keys busy", notes)


class InvalidKeyError(AiError):
    """Raised when every key tried was rejected as invalid (401/403)."""

    kind = "key"

    def __init__(self, notes: list[str], provider: str = "") -> None:
        super().__init__("Invalid key", notes, provider=provider)


class ModelUnavailableError(AiError):
    """Raised when every key failed only because the model is gone (404)."""

    kind = "model"

    def __init__(self, notes: list[str]) -> None:
        super().__init__("Model unavailable", notes)


class ProviderError(AiError):
    """Raised for non-retryable provider errors (we stop, no further keys tried)."""


class BadOutputError(AiError):
    """Raised when no key could give an answer in the shape the desk needs."""

    kind = "output"


UNREADABLE = "The AI returned something unreadable. Try again."

# What this request's AI calls did to each key, so the key panel can say
# "working · just now" or "failed · too many requests" from a real run and
# not only from the Test button. Positions only: a key never goes in here.
_KEY_RESULTS: ContextVar[list[dict] | None] = ContextVar("key_results", default=None)


def start_recording() -> list[dict]:
    """Begin collecting this request's key results, and return the list."""
    found: list[dict] = []
    _KEY_RESULTS.set(found)
    return found


def record_key(index: int, ok: bool, reason: str = "") -> None:
    """Note what one key did. Silent when nothing is recording."""
    found = _KEY_RESULTS.get()
    if found is None:
        return
    found.append({"index": index, "ok": ok, "reason": reason[:REASON_LIMIT]})


def _short_model(model: str, limit: int = 22) -> str:
    return model if len(model) <= limit else model[:limit] + "…"


def _label(index: int, short: str, model: str | None = None) -> str:
    if model:
        return f"Key {index + 1} ({short}, {_short_model(model)})"
    return f"Key {index + 1} ({short})"


# How much of a provider's own words a reader can use. Past this it is the
# provider talking to itself.
REASON_LIMIT = 120
# The one readable line inside a provider's JSON error body.
_JSON_MESSAGE = re.compile(r'"(?:message|error|detail)"\s*:\s*"([^"]{3,})"')
_BRACES = re.compile(r"[{}\[\]]+")
_SPACES = re.compile(r"\s+")
# "Error code: 400" and "400 - " tell a reader nothing, so they go.
_STATUS_ONLY = re.compile(r"^(?:error code:?\s*)?\d{3}\s*[-:]?\s*", re.IGNORECASE)


def _cut(text: str, limit: int) -> str:
    """At most `limit` characters, ending on a whole word."""
    if len(text) <= limit:
        return text
    kept = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return (kept or text[:limit].rstrip()) + "…"


def clean_reason(text: str, key: str) -> str:
    """A provider error a person can read: no JSON, no key, 120 characters.

    Providers answer a bad request with their whole error body. Pasting it
    on the page tells a reader nothing and shows them a wall of braces, so
    the one human sentence in it is pulled out and the rest is dropped.
    """
    said = str(text or "")
    found = _JSON_MESSAGE.search(said)
    if found:
        said = found.group(1)
    said = _SPACES.sub(" ", _BRACES.sub(" ", said)).strip()
    said = _STATUS_ONLY.sub("", said).strip(" -:")
    if key:
        said = said.replace(key, "[hidden]")
    said = KEYLIKE_RE.sub("[hidden]", said)
    return _cut(said, REASON_LIMIT)


def valid_model(value: Any) -> bool:
    """True for safe model ids: short and limited to a plain charset."""
    return (
        isinstance(value, str)
        and 0 < len(value) <= 100
        and MODEL_RE.fullmatch(value) is not None
    )


def default_client_factory(base_url: str, api_key: str) -> Any:
    """Build the production client: no SDK retries (rotation handles that)."""
    return openai.OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=REQUEST_TIMEOUT,
        max_retries=0,
    )


def fetch_model_ids(base_url: str, api_key: str) -> list[str]:
    """Raw model ids from a provider's OpenAI-compatible /models endpoint."""
    client = openai.OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=MODELS_TIMEOUT,
        max_retries=0,
    )
    return [m.id for m in client.models.list().data]


def filter_chat_models(provider_id: str, model_ids: list[str]) -> list[str]:
    """Keep chat models only, sorted. Strips Gemini's leading `models/`."""
    kept = []
    for model_id in model_ids:
        if provider_id == "gemini" and model_id.startswith("models/"):
            model_id = model_id[len("models/") :]
        if any(fragment in model_id.lower() for fragment in CHAT_DROP):
            continue
        kept.append(model_id)
    return sorted(kept)


def list_chat_models(
    provider: dict,
    api_key: str,
    fetcher: Callable[[str, str], list[str]] | None = None,
) -> list[str]:
    """Live chat model ids for one key. Never logs the key."""
    raw = (fetcher or fetch_model_ids)(provider["base_url"], api_key)
    models = filter_chat_models(provider["id"], raw)
    logger.info("%s listed %d chat models", provider["short"], len(models))
    return models


def _call_once(
    client: Any,
    model: str,
    system: str,
    user: str,
    use_json_mode: bool,
    image: tuple[str, str] | None = None,
) -> str:
    """One chat call. With an image the user content becomes a text + image_url list."""
    content: Any = user
    if image is not None:
        mime, data = image
        content = [
            {"type": "text", "text": user},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{data}"},
            },
        ]
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
    }
    if use_json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    completion = client.chat.completions.create(**kwargs)
    answer = completion.choices[0].message.content
    return answer or ""


# A 400 saying any of these is the provider refusing the way we asked for
# JSON, not refusing the request. A real run had Groq's gpt-oss-20b answer
# "400 Failed to validate JSON" to every structured call, and the same key
# answers fine when asked in plain text.
JSON_MODE_MARKERS = ("response_format", "json", "schema", "validate")


def _rejects_json_mode(error: openai.BadRequestError) -> bool:
    said = str(error).lower()
    return any(marker in said for marker in JSON_MODE_MARKERS)


def _call_json_then_plain(
    client: Any,
    model: str,
    system: str,
    user: str,
    image: tuple[str, str] | None,
    label: str,
) -> str:
    """The call, falling back to no JSON mode for providers that reject it.

    The schema stays in the system message either way, so the answer still
    has a shape to aim at; only the provider-side JSON mode is dropped.
    """
    try:
        return _call_once(client, model, system, user, True, image)
    except openai.BadRequestError as e:
        if not _rejects_json_mode(e):
            raise
        logger.info("%s rejected JSON mode, retrying without it", label)
        return _call_once(client, model, system, user, False, image)


def _cannot_read_images(error: openai.APIStatusError, api_key: str) -> bool:
    """True when the provider refused the call because of the image, not the key."""
    if (error.status_code or 0) not in (400, 404, 422):
        return False
    reason = clean_reason(str(error), api_key).lower()
    return any(marker in reason for marker in IMAGE_MARKERS)


def generate_json(
    keys: list[dict[str, str]],
    system: str,
    user: str,
    schema: type[BaseModel],
    client_factory: Callable[[str, str], Any] | None = None,
    models_fetcher: Callable[[str, str], list[str]] | None = None,
    image: tuple[str, str] | None = None,
) -> tuple[BaseModel, int, list[str]]:
    """Call the first working key and return (result, used_key_index, notes).

    `used_key_index` is the 0-based position in `keys`. On a success `notes`
    is one sentence naming the keys that were skipped and the one that
    answered, e.g. ["Key 1 (Gemini) was busy, so Key 2 (Groq) answered."].
    When every key failed it is one short clause per key.
    Keys without a (valid) model get one from the provider's live list.
    """
    if not keys:
        raise NoKeysError("No API keys were sent with this request.")

    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    if "{json_schema}" in system:
        system = system.replace("{json_schema}", schema_json)
    else:
        system += (
            "\n\nRespond with ONLY a JSON object that matches this JSON Schema. "
            "Use these exact field names.\n" + schema_json
        )

    if client_factory is None:
        client_factory = default_client_factory

    # Clauses about keys that were skipped; they become one sentence at the end.
    notes: list[str] = []
    # Anything else worth saying, which is not part of that sentence.
    asides: list[str] = []
    invalid_count = 0
    # Which providers refused a key. One name here means the page can say
    # "Your Gemini key was refused" instead of "Your key was refused".
    invalid_shorts: list[str] = []
    notfound_count = 0
    unreadable_count = 0
    attempted = 0
    listed: dict[str, list[str]] = {}

    for index, entry in enumerate(keys):
        provider_id = entry.get("provider", "")
        provider = get_provider(provider_id)
        if provider is None:
            logger.warning("key %d uses unknown provider id", index + 1)
            raise ProviderError(
                f"Key {index + 1} names an unknown provider. "
                "Check the provider and try again."
            )
        short = provider["short"]
        api_key = entry.get("key", "")
        model = entry.get("model", "") if valid_model(entry.get("model")) else ""
        if not model:
            if provider["base_url"] not in listed:
                try:
                    listed[provider["base_url"]] = list_chat_models(
                        provider, api_key, fetcher=models_fetcher
                    )
                except openai.AuthenticationError:
                    logger.warning("key %d rejected (invalid key)", index + 1)
                    notes.append(f"{_label(index, short)} looked invalid")
                    record_key(index, False, "the key was rejected")
                    invalid_count += 1
                    invalid_shorts.append(short)
                    attempted += 1
                    continue
                except openai.PermissionDeniedError:
                    logger.warning("key %d rejected (forbidden)", index + 1)
                    notes.append(f"{_label(index, short)} looked invalid")
                    record_key(index, False, "the key was not allowed")
                    invalid_count += 1
                    invalid_shorts.append(short)
                    attempted += 1
                    continue
                except openai.OpenAIError:
                    logger.warning("key %d could not list models", index + 1)
                    notes.append(f"{_label(index, short)} could not list its models")
                    record_key(index, False, "could not list its models")
                    attempted += 1
                    continue
            model = pick_default(provider, listed[provider["base_url"]])
            if not model:
                logger.warning("key %d has no chat models", index + 1)
                notes.append(f"{_label(index, short)} has no chat models")
                record_key(index, False, "has no chat models")
                attempted += 1
                continue
        label = _label(index, short, model)
        attempted += 1
        client = client_factory(provider["base_url"], api_key)
        logger.info("%s called, image attached: %s", label, "yes" if image else "no")
        try:
            try:
                content = _call_json_then_plain(
                    client, model, system, user, image, label
                )
            except openai.APIStatusError as e:
                if image is None or not _cannot_read_images(e, api_key):
                    raise
                logger.info("%s cannot read images, retrying without it", label)
                asides.append(
                    f"{label} can't read images — the screenshot was not used."
                )
                content = _call_json_then_plain(
                    client, model, system, user, None, label
                )
        except openai.AuthenticationError:
            logger.warning("%s rejected (invalid key)", label)
            notes.append(f"{label} looked invalid")
            record_key(index, False, "the key was rejected")
            invalid_count += 1
            invalid_shorts.append(short)
            continue
        except openai.PermissionDeniedError:
            logger.warning("%s rejected (forbidden)", label)
            notes.append(f"{label} looked invalid")
            record_key(index, False, "the key was not allowed")
            invalid_count += 1
            invalid_shorts.append(short)
            continue
        except openai.RateLimitError:
            logger.warning("%s rate limited", label)
            notes.append(f"{label} was busy (too many requests)")
            record_key(index, False, "busy (too many requests)")
            continue
        except openai.NotFoundError:
            logger.warning("%s model not available (404)", label)
            notes.append(f"{label} is not available — try updating QA-Genius")
            record_key(index, False, "that model is gone")
            notfound_count += 1
            continue
        except (openai.APITimeoutError, openai.APIConnectionError):
            logger.warning("%s timed out or unreachable", label)
            notes.append(f"{label} did not answer in time")
            record_key(index, False, "did not answer in time")
            continue
        except openai.APIStatusError as e:
            status = e.status_code or 0
            if status >= 500:
                logger.warning("%s server error (%d)", label, status)
                notes.append(f"{label} had a server problem")
                record_key(index, False, "the provider had a server problem")
                continue
            if status == 402:
                logger.warning("%s no credit (402)", label)
                notes.append(f"{label} has no credit for this model")
                record_key(index, False, "no credit for this model")
                continue
            logger.warning("%s failed (%d)", label, status)
            reason = clean_reason(str(e), api_key)
            record_key(index, False, reason or "the request was refused")
            # A 400 from a provider is almost always the key: the page says
            # so in plain words rather than printing the number back.
            raise ProviderError(
                f"{label} failed ({status}): {reason}" if reason else f"{label} failed",
                notes=[f"{label}: {reason}"] if reason else [],
                kind="key" if status in (400, 401, 403) else "server",
                provider=short,
            ) from None
        except openai.OpenAIError as e:
            logger.warning("%s failed", label)
            reason = clean_reason(str(e), api_key)
            record_key(index, False, reason or "the request was refused")
            raise ProviderError(
                f"{label} failed: {reason}" if reason else f"{label} failed",
                notes=[f"{label}: {reason}"] if reason else [],
                kind="server",
                provider=short,
            ) from None

        data = json_repair_utils.parse_json_resilient(content)
        result = None
        if data is not None:
            try:
                result = schema.model_validate(data)
            except ValidationError:
                result = None
        if result is None:
            # One key that cannot hold a shape is not the end of the run:
            # the next key is tried, exactly as for a busy one.
            logger.warning("%s gave an answer of the wrong shape", label)
            notes.append(f"{label} couldn't give a structured answer")
            record_key(index, False, "could not give a structured answer")
            unreadable_count += 1
            continue
        logger.info("%s answered", label)
        record_key(index, True)
        if notes:
            # One sentence, not a log: "Key 1 (Gemini) was busy, so Key 2
            # (Groq) answered." The model id is left off — it is in the key
            # panel, and it is not what this line is telling anyone.
            answered = f"{_label(index, short)} answered."
            notes = [", ".join(notes) + f", so {answered}"]
        return result, index, asides + notes

    if attempted > 0 and invalid_count == attempted:
        only = set(invalid_shorts)
        raise InvalidKeyError(notes, provider=only.pop() if len(only) == 1 else "")
    if attempted > 0 and notfound_count == attempted:
        raise ModelUnavailableError(notes)
    if attempted > 0 and unreadable_count == attempted:
        raise BadOutputError(UNREADABLE, notes)
    raise AllKeysBusyError(notes)
