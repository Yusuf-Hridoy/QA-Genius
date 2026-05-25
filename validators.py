"""Centralized input validation for all tabs."""
import json
import re
from typing import Tuple


class ValidationError(Exception):
    """User-facing validation error with a clear message."""
    pass


def validate_text_input(
    text: str,
    field_name: str,
    min_chars: int = 10,
    max_chars: int = 10000,
    required: bool = True,
) -> str:
    """Validate a free-text input field."""
    if not text or not text.strip():
        if required:
            raise ValidationError(f"{field_name} cannot be empty.")
        return ""

    text = text.strip()

    if len(text) < min_chars:
        raise ValidationError(
            f"{field_name} is too short (minimum {min_chars} characters). "
            f"Please provide more detail."
        )

    if len(text) > max_chars:
        raise ValidationError(
            f"{field_name} is too long ({len(text)} characters; maximum {max_chars}). "
            f"Please shorten your input."
        )

    return text


def validate_json_input(text: str, field_name: str, max_chars: int = 50000) -> dict:
    """Validate that a field contains parseable JSON."""
    text = validate_text_input(text, field_name, min_chars=2, max_chars=max_chars)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValidationError(
            f"{field_name} contains invalid JSON: {e.msg} at line {e.lineno}, column {e.colno}. "
            f"Please verify your JSON is well-formed."
        )

    if not isinstance(parsed, (dict, list)):
        raise ValidationError(
            f"{field_name} must be a JSON object or array, not {type(parsed).__name__}."
        )

    return parsed


def detect_suspicious_content(text: str) -> Tuple[bool, str]:
    """Detect likely prompt injection or off-topic content."""
    text_lower = text.lower()

    injection_patterns = [
        r"ignore (previous|all|prior) instructions",
        r"disregard (the |your )?(system|previous) prompt",
        r"reveal (your |the )?(system prompt|instructions)",
        r"output (your |the )?(system prompt|instructions)",
        r"you are now (a |an )?(different|new)",
        r"forget everything",
        r"jailbreak",
        r"DAN mode",
    ]

    for pattern in injection_patterns:
        if re.search(pattern, text_lower):
            return True, "Input contains patterns that may not produce useful output."

    return False, ""


def validate_total_input_size(input_dict: dict, max_total_chars: int = 50000) -> None:
    """Defense-in-depth: cap total combined input size across all fields."""
    total = sum(len(str(v)) for v in input_dict.values() if v is not None)
    if total > max_total_chars:
        raise ValidationError(
            f"Total input is too large ({total} characters; maximum {max_total_chars}). "
            f"Please reduce the input size."
        )
