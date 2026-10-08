#!/usr/bin/env python3
"""Write the canonical IR JSON of the committed SYNTHETIC flows (MW2, mw2-block-editor.md s. 7):

    services/frontend/src/lib/flow/fixtures/<name>.json   the frontend's round-trip test fixtures
    packages/poring_flow/src/poring_flow/examples/town_warp_farm.json   the sample's JSON export

Each is `ir.to_json` of a flow parsed from its Python view (MW1's fixtures and the MW2 sample).
`packages/poring_flow/tests/test_editor.py` fails when one is stale. Synthetic data only.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "packages/poring_flow/tests")]


def main() -> None:
    from test_editor import EXAMPLES, TS_FIXTURES, committed_json

    from poring_flow import ir

    TS_FIXTURES.mkdir(parents=True, exist_ok=True)
    for name, flow in committed_json().items():
        text = ir.to_json(flow) + "\n"
        (TS_FIXTURES / f"{name}.json").write_text(text, encoding="utf-8")
        if name == "town_warp_farm":
            (EXAMPLES / f"{name}.json").write_text(text, encoding="utf-8")
        print(f"{name}: {ir.flow_hash(flow)}")


if __name__ == "__main__":
    main()
