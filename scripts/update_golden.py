"""Rewrite the saved answers in tests/mcp_golden/.

Run this only when a change to what the tools say is meant:

    python scripts/update_golden.py

Then read the diff. These files are the five reference runs the whole MCP
door is judged against, and a change in one of them is a change in what an
agent is told about a real story.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qagenius.mcp_server.transport import call_tool  # noqa: E402
from tests.golden_inputs import GOLDEN  # noqa: E402

OUT = ROOT / "tests" / "mcp_golden"


def written() -> list[str]:
    OUT.mkdir(parents=True, exist_ok=True)
    names = []
    for name, case in GOLDEN.items():
        result = call_tool(case["tool"], case["input"])
        body = {
            "tool": case["tool"],
            "input": case["input"],
            "output": result.structured_content,
        }
        path = OUT / f"{name}.json"
        path.write_text(
            json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        names.append(path.name)
    return names


if __name__ == "__main__":
    for name in written():
        print(f"wrote tests/mcp_golden/{name}")
