#!/usr/bin/env python3
"""Write the /flows Zones layer's cross-language fixtures (blocks-from-hunt-flow.md B2):

    services/frontend/src/lib/flow/fixtures/zones/prt_fild08.yaml   config/map_zones' file, copied
    services/frontend/src/lib/flow/fixtures/zones/<map>.json        the editor's model of a file as
        the backend reads it (GET /flows/zones/file), its sha256 and the review a person types
    services/frontend/src/lib/flow/fixtures/zones/errors.json       the loader's error corpus as the
        editor receives it (POST /flows/zones/check), every message the CLI's own

`syn_zones.yaml` beside them is HAND-WRITTEN (the twin), never generated. The frontend's
zones.test.ts reproduces the twins click by click; services/backend/tests/test_flows_zones.py fails
when a fixture is stale. Our own synthetic data and our own zones file only.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "services/backend/tests"), str(REPO / "services/backend/src"),
                str(REPO / "scripts")]  # fmt: skip


def main() -> None:
    from test_flows_zones import TS_ZONES, fixture_docs

    TS_ZONES.mkdir(parents=True, exist_ok=True)
    for name, text in fixture_docs().items():
        (TS_ZONES / name).write_text(text, encoding="utf-8")
        print(f"{name}: {len(text)} chars")


if __name__ == "__main__":
    main()
