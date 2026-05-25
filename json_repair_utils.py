"""Utilities for repairing common JSON output issues from LLMs."""
import json
import re
from typing import Optional


def strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` and ``` ... ``` wrappers."""
    text = text.strip()

    # Match opening fence (```json or just ```)
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]

        # Remove closing fence
        if text.endswith("```"):
            text = text[:-3].strip()

    return text


def extract_json_object(text: str) -> Optional[str]:
    """Find the outermost JSON object in text, even if surrounded by prose."""
    # Find the first { and the matching closing }
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape_next:
            escape_next = False
            continue

        if ch == "\\":
            escape_next = True
            continue

        if ch == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    return None


def repair_unescaped_quotes(text: str) -> str:
    """
    Attempt to repair JSON where the LLM forgot to escape quotes inside string values.
    Heuristic: detect string values where an inner unescaped quote breaks parsing.
    NOTE: this is best-effort. Complex cases will still fail.
    """
    # More robust approach: find all string values in the JSON and escape quotes inside them
    result = []
    i = 0
    while i < len(text):
        if text[i] == '"':
            # Found start of a string
            result.append('"')
            i += 1
            # Read until closing quote (not escaped)
            while i < len(text):
                if text[i] == '\\' and i + 1 < len(text):
                    result.append(text[i])
                    result.append(text[i + 1])
                    i += 2
                elif text[i] == '"':
                    result.append('"')
                    i += 1
                    break
                elif text[i] == '\n':
                    # Unescaped newline inside string — replace with \n
                    result.append('\\n')
                    i += 1
                else:
                    result.append(text[i])
                    i += 1
        else:
            result.append(text[i])
            i += 1

    return "".join(result)


def parse_json_resilient(raw_response: str) -> Optional[dict]:
    """
    Multi-stage JSON parsing with progressive repair attempts.
    Returns parsed dict on success, None on irrecoverable failure.
    """
    if not raw_response or not raw_response.strip():
        return None

    # Stage 1: try direct parse
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError:
        pass

    # Stage 2: strip markdown fences
    cleaned = strip_markdown_fences(raw_response)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Stage 3: extract embedded JSON object
    extracted = extract_json_object(cleaned)
    if extracted:
        try:
            return json.loads(extracted)
        except json.JSONDecodeError:
            pass

        # Stage 4: try to repair unescaped quotes in extracted object
        try:
            repaired = repair_unescaped_quotes(extracted)
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        # Stage 5: try aggressive repair — replace all unescaped inner quotes
        try:
            aggressive = _aggressive_quote_repair(extracted)
            return json.loads(aggressive)
        except json.JSONDecodeError:
            pass

    return None


def _aggressive_quote_repair(text: str) -> str:
    """
    Aggressively repair unescaped quotes by tracking JSON state.
    This handles the common LLM pattern of including quoted phrases inside string values.
    """
    result = []
    in_string = False
    escape_next = False

    for ch in text:
        if escape_next:
            result.append(ch)
            escape_next = False
            continue

        if ch == '\\':
            result.append(ch)
            escape_next = True
            continue

        if ch == '"':
            if not in_string:
                in_string = True
                result.append(ch)
            else:
                # We're inside a string. Look ahead to decide if this closes the string.
                # Heuristic: if next non-whitespace char is :, , ] or } at the right nesting,
                # this quote likely closes the string. Otherwise it's an unescaped inner quote.
                # Simpler heuristic: just escape it and let the parser find the real end.
                result.append('\\"')
        else:
            result.append(ch)

    return "".join(result)
