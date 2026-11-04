"""Rewrite the tool reference inside docs/mcp.md from the schemas.

The prose around it is written by hand; the table of every field is not,
because a hand-written field list is a field list that is wrong by the
third release. Run this whenever a schema changes:

    python scripts/update_mcp_docs.py

The generated part lives between the two markers below and nothing else in
the file is touched.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qagenius.mcp_server import server  # noqa: E402

DOCS = ROOT / "docs" / "mcp.md"
START = "<!-- tools:start -->"
END = "<!-- tools:end -->"
NOTE = (
    "*This section is generated from the schemas by "
    "`python scripts/update_mcp_docs.py`. Do not edit it by hand.*"
)


def _type(body: dict) -> str:
    """One field's type, said the way somebody writing JSON would say it."""
    if "const" in body:
        return f"`{body['const']}`"
    if body.get("enum"):
        return " \\| ".join(f"`{one}`" for one in body["enum"])
    if "$ref" in body:
        return _name(body["$ref"])
    kind = body.get("type")
    if kind == "array":
        inner = body.get("items") or {}
        return f"list of {_type(inner)}" if inner else "list"
    if kind == "object":
        return "object"
    if isinstance(body.get("anyOf"), list):
        parts = [_type(one) for one in body["anyOf"] if one.get("type") != "null"]
        return " \\| ".join(parts) + " (optional)" if parts else "optional"
    return f"`{kind}`" if kind else "any"


def _name(ref: str) -> str:
    return f"`{str(ref).rsplit('/', 1)[-1]}`"


def _limits(body: dict) -> str:
    parts = []
    for key, word in (
        ("maxLength", "at most {} characters"),
        ("minLength", "at least {} characters"),
        ("maxItems", "at most {}"),
        ("minItems", "at least {}"),
        ("minimum", "{} or more"),
        ("maximum", "{} or less"),
    ):
        if key in body:
            parts.append(word.format(body[key]))
    return "; ".join(parts)


def _rows(schema: dict) -> list[str]:
    required = set(schema.get("required") or [])
    lines = [
        "| field | type | required | what it is |",
        "| --- | --- | --- | --- |",
    ]
    for name, body in (schema.get("properties") or {}).items():
        said = str(body.get("description") or "").replace("|", "\\|")
        limit = _limits(body)
        if limit:
            said = f"{said} ({limit})"
        lines.append(
            f"| `{name}` | {_type(body)} | "
            f"{'yes' if name in required else 'no'} | {said} |"
        )
    return lines


def _nested(schema: dict) -> list[str]:
    """The shapes a tool's own fields refer to, each written out once."""
    out: list[str] = []
    for name, body in (schema.get("$defs") or {}).items():
        out.append("")
        out.append(f"**`{name}`**")
        out.append("")
        out.extend(_rows(body))
    return out


def built() -> str:
    lines = [START, "", NOTE, ""]
    for spec in server.SPECS:
        lines.append(f"### `{spec.name}`")
        lines.append("")
        lines.append(" ".join(spec.description.split()))
        lines.append("")
        lines.append("**Sends**")
        lines.append("")
        lines.extend(_rows(spec.input_model.model_json_schema()))
        lines.extend(_nested(spec.input_model.model_json_schema()))
        lines.append("")
        lines.append("**Answers**")
        lines.append("")
        lines.extend(_rows(spec.output_model.model_json_schema()))
        lines.extend(_nested(spec.output_model.model_json_schema()))
        lines.append("")
    lines.append(END)
    return "\n".join(lines)


def write() -> bool:
    text = DOCS.read_text(encoding="utf-8")
    head, _, rest = text.partition(START)
    _, _, tail = rest.partition(END)
    updated = head + built() + tail
    if updated == text:
        return False
    DOCS.write_text(updated, encoding="utf-8")
    return True


if __name__ == "__main__":
    print("rewrote docs/mcp.md" if write() else "docs/mcp.md was already current")
