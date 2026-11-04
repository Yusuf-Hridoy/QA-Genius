"""Rewrite the saved JSON Schemas in tests/contracts/.

Run this only when a change to qagenius/mcp_server/schemas.py is meant:

    python scripts/update_contracts.py

The saved files are what an agent builds its calls from. A field that
changes name or disappears breaks every caller, so the test that compares
them is there to make that change deliberate rather than quiet.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qagenius.mcp_server.schemas import CONTRACTS  # noqa: E402

OUT = ROOT / "tests" / "contracts"


def written() -> list[str]:
    OUT.mkdir(parents=True, exist_ok=True)
    names = []
    for name, model in CONTRACTS.items():
        path = OUT / f"{name}.json"
        text = json.dumps(model.model_json_schema(), indent=2, sort_keys=True)
        path.write_text(text + "\n", encoding="utf-8")
        names.append(path.name)
    return names


if __name__ == "__main__":
    for name in written():
        print(f"wrote tests/contracts/{name}")
