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


class NoKeysError(Exception):
    """Raised when the request carries no keys."""


class AllKeysBusyError(Exception):
    """Raised when every key failed with a retryable (busy/down) error."""

    def __init__(self, notes: list[str]) -> None:
        super().__init__("All keys busy")
        self.notes = notes


class InvalidKeyError(Exception):
    """Raised when every key tried was rejected as invalid (401/403)."""

    def __init__(self, notes: list[str]) -> None:
        super().__init__("Invalid key")
        self.notes = notes


class ModelUnavailableError(Exception):
    """Raised when every key failed only because the model is gone (404)."""

    def __init__(self, notes: list[str]) -> None:
        super().__init__("Model unavailable")
        self.notes = notes


class ProviderError(Exception):
    """Raised for non-retryable provider errors (we stop, no further keys tried)."""


class BadOutputError(Exception):
    """Raised when the AI answer could not be parsed/validated (we stop)."""


def _short_model(model: str, limit: int = 22) -> str:
    return model if len(model) <= limit else model[:limit] + "…"


def _label(index: int, short: str, model: str | None = None) -> str:
    if model:
        return f"Key {index + 1} ({short}, {_short_model(model)})"
    return f"Key {index + 1} ({short})"


def clean_reason(text: str, key: str) -> str:
    """Shorten a provider error for display and hide anything key-like."""
    short = text[:160]
    if key:
        short = short.replace(key, "[hidden]")
    return KEYLIKE_RE.sub("[hidden]", short)


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
    client: Any, model: str, system: str, user: str, use_json_mode: bool
) -> str:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if use_json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    completion = client.chat.completions.create(**kwargs)
    content = completion.choices[0].message.content
    return content or ""


def generate_json(
    keys: list[dict[str, str]],
    system: str,
    user: str,
    schema: type[BaseModel],
    client_factory: Callable[[str, str], Any] | None = None,
    models_fetcher: Callable[[str, str], list[str]] | None = None,
) -> tuple[BaseModel, int, list[str]]:
    """Call the first working key and return (result, used_key_index, notes).

    `used_key_index` is the 0-based position in `keys`. `notes` describes
    skipped keys plus who answered, e.g.
    ["Key 1 (Gemini, gemini-…) was busy, trying the next key",
     "Used Key 2 (Groq, llama-…)"].
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

    notes: list[str] = []
    invalid_count = 0
    notfound_count = 0
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
                    notes.append(
                        f"{_label(index, short)} looked invalid, trying the next key"
                    )
                    invalid_count += 1
                    attempted += 1
                    continue
                except openai.PermissionDeniedError:
                    logger.warning("key %d rejected (forbidden)", index + 1)
                    notes.append(
                        f"{_label(index, short)} looked invalid, trying the next key"
                    )
                    invalid_count += 1
                    attempted += 1
                    continue
                except openai.OpenAIError:
                    logger.warning("key %d could not list models", index + 1)
                    notes.append(
                        f"{_label(index, short)} could not list models, "
                        "trying the next key"
                    )
                    attempted += 1
                    continue
            model = pick_default(provider, listed[provider["base_url"]])
            if not model:
                logger.warning("key %d has no chat models", index + 1)
                notes.append(
                    f"{_label(index, short)} has no chat models, trying the next key"
                )
                attempted += 1
                continue
        label = _label(index, short, model)
        attempted += 1
        client = client_factory(provider["base_url"], api_key)
        try:
            try:
                content = _call_once(
                    client, model, system, user, use_json_mode=True
                )
            except openai.BadRequestError as e:
                if "response_format" not in str(e).lower():
                    raise
                logger.info("%s rejected JSON mode, retrying without it", label)
                content = _call_once(
                    client, model, system, user, use_json_mode=False
                )
        except openai.AuthenticationError:
            logger.warning("%s rejected (invalid key)", label)
            notes.append(f"{label} looked invalid, trying the next key")
            invalid_count += 1
            continue
        except openai.PermissionDeniedError:
            logger.warning("%s rejected (forbidden)", label)
            notes.append(f"{label} looked invalid, trying the next key")
            invalid_count += 1
            continue
        except openai.RateLimitError:
            logger.warning("%s rate limited", label)
            notes.append(f"{label} was busy, trying the next key")
            continue
        except openai.NotFoundError:
            logger.warning("%s model not available (404)", label)
            notes.append(f"{label} is not available — try updating QA-Genius")
            notfound_count += 1
            continue
        except (openai.APITimeoutError, openai.APIConnectionError):
            logger.warning("%s timed out or unreachable", label)
            notes.append(f"{label} was busy, trying the next key")
            continue
        except openai.APIStatusError as e:
            status = e.status_code or 0
            if status >= 500:
                logger.warning("%s server error (%d)", label, status)
                notes.append(f"{label} was busy, trying the next key")
                continue
            if status == 402:
                logger.warning("%s no credit (402)", label)
                notes.append(
                    f"{label} has no credit for this model, trying the next key"
                )
                continue
            logger.warning("%s failed (%d)", label, status)
            reason = clean_reason(str(e), api_key)
            raise ProviderError(
                f"{label} failed ({status}): {reason}"
            ) from None
        except openai.OpenAIError as e:
            logger.warning("%s failed", label)
            reason = clean_reason(str(e), api_key)
            raise ProviderError(f"{label} failed: {reason}") from None

        data = json_repair_utils.parse_json_resilient(content)
        if data is None:
            logger.warning("%s returned unparseable output", label)
            raise BadOutputError(
                "The AI returned something unreadable. Try again."
            )
        try:
            result = schema.model_validate(data)
        except ValidationError:
            logger.warning("%s returned output that failed validation", label)
            raise BadOutputError(
                "The AI returned something unreadable. Try again."
            )
        logger.info("%s answered", label)
        if notes:
            notes.append(f"Used {label}")
        return result, index, notes

    if attempted > 0 and invalid_count == attempted:
        raise InvalidKeyError(notes)
    if attempted > 0 and notfound_count == attempted:
        raise ModelUnavailableError(notes)
    raise AllKeysBusyError(notes)
