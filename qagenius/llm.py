"""Key rotation + JSON calls.

Keys arrive per request (never stored). They are tried in the user's order:
- 429 or 5xx/timeout -> try the next key.
- 401/403 -> mark the key invalid, try the next key.
- anything else -> stop with a friendly error.

Keys are NEVER printed, logged, or put in an error message.
Logs mention only the provider name and the key position.
"""

import json
import logging
from collections.abc import Callable
from typing import Any

import openai
from pydantic import BaseModel, ValidationError

from qagenius import json_repair_utils
from qagenius.providers import get_provider

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 45.0


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


class ProviderError(Exception):
    """Raised for non-retryable provider errors (we stop, no further keys tried)."""


class BadOutputError(Exception):
    """Raised when the AI answer could not be parsed/validated (we stop)."""


def _label(index: int, short: str) -> str:
    return f"Key {index + 1} ({short})"


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
) -> tuple[BaseModel, int, list[str]]:
    """Call the first working key and return (result, used_key_index, notes).

    `used_key_index` is the 0-based position in `keys`. `notes` describes
    skipped keys plus who answered, e.g.
    ["Key 1 (Gemini) was busy, trying the next key", "Used Key 2 (Groq)"].
    """
    if not keys:
        raise NoKeysError("No API keys were sent with this request.")

    if "{json_schema}" in system:
        system = system.replace(
            "{json_schema}", json.dumps(schema.model_json_schema())
        )

    if client_factory is None:
        def client_factory(base_url: str, api_key: str) -> Any:
            return openai.OpenAI(
                base_url=base_url,
                api_key=api_key,
                timeout=REQUEST_TIMEOUT,
                max_retries=0,
            )

    notes: list[str] = []
    invalid_count = 0
    attempted = 0

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
        label = _label(index, short)
        attempted += 1
        client = client_factory(provider["base_url"], entry.get("key", ""))
        try:
            try:
                content = _call_once(
                    client, provider["model"], system, user, use_json_mode=True
                )
            except openai.BadRequestError as e:
                if "response_format" not in str(e).lower():
                    raise
                logger.info("%s rejected JSON mode, retrying without it", label)
                content = _call_once(
                    client, provider["model"], system, user, use_json_mode=False
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
            logger.warning("%s failed (%d)", label, status)
            raise ProviderError(
                f"{label} failed with an unexpected error. "
                "Check the provider status and try again."
            ) from None
        except openai.OpenAIError:
            logger.warning("%s failed", label)
            raise ProviderError(
                f"{label} failed with an unexpected error. "
                "Check the provider status and try again."
            ) from None

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
    raise AllKeysBusyError(notes)
