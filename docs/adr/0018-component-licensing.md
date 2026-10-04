---
doc_type: decision
hypothesis: null
status: GO
role: null
verdict_date: 2026-10-04
verdict_ticket: null
supersedes: null
related: []
next_action: Keep the import boundary (test_guards) green; before the repository is published, re-run the publication checklist below.
---

# ADR-0018: Component licensing (AGPL-3.0 where ultralytics is imported, Apache-2.0 elsewhere)

- **Status:** ACCEPTED (Batt, 2026-10-04).
- **Context:**
  - Phase 3 trains and runs YOLO with ultralytics ([phase3-plan.md](../phase3-plan.md) M9).
    ultralytics, its two companion packages and the pretrained weights are all AGPL-3.0
    ([THIRD_PARTY.md](../../THIRD_PARTY.md), "Runtime dependencies with licence obligations").
  - The project will be public. It is private today only to keep Ragnarok Online's copyrighted
    material out of a public repository.
  - Until this ADR, the repository declared no licence at all.

## Decision
1. **`services/vision` is AGPL-3.0-only.** It imports ultralytics (the detector, and training).
   - `services/vision/LICENSE` holds the AGPL-3.0 text;
   - `services/vision/pyproject.toml` says `license = "AGPL-3.0-only"`.
   - `scripts/check_gpu.py` belongs to it too: it imports ultralytics, is copied into the vision
     image only, and runs there. Its header says so, and the guard allowlists exactly that file.
2. **Everything else is Apache-2.0.** That covers:
   - `poring_env` (the Env contract, the protocol, input);
   - the backend (mux, injector, capture hub);
   - the frontend;
   - `poring_packets`;
   - `poring_dataset`;
   - `scripts/` and the service images other than vision.

   The root `LICENSE` holds the Apache-2.0 text, and each of these `pyproject.toml` files says
   `license = "Apache-2.0"`.
3. **The boundary is enforced, not documented only** (`services/backend/tests/test_guards.py`):
   - no Python file outside `services/vision` imports `ultralytics`;
   - no Python file outside `services/vision` imports `poring_vision`.

   The existing guards already keep the other direction clean (vision never imports
   `poring_dataset`, `poring_packets` or `poring_backend`). Vision talks to the rest of the lab
   only over the wire protocol (`/internal/agent`) and the frame bus.

## Consequences
- **When the AGPL obligations bite.** They apply when the vision component is distributed, or
  when users interact with it over a network (AGPL §13). Then its complete corresponding source must
  be offered under AGPL-3.0. Today the repository is private and nothing is distributed, so there
  is no obligation yet. The licence files are in place now, so publication does not need a
  relicensing step.
- **Trained weights.** Models trained with ultralytics or from its weights are treated as
  AGPL-3.0, following Ultralytics' stated terms. They live in `data/` (gitignored) and are not
  published with the repository.
- **Mixing is one-way.** Apache-2.0 code may be used inside the AGPL-3.0 component; AGPL-3.0 code
  must never flow into the Apache-2.0 components. That is what the import guard protects.
- **An alternative stays open.** Ultralytics sells an enterprise licence. If the vision component
  ever needs a non-AGPL release, it can be bought, or the detector replaced. Because of the
  boundary, only `services/vision` is affected.

## Publication checklist (before the repository goes public)
1. Nothing client-derived or RO-copyrighted is in the history: no GRF content, sprites, GAT, client
   binaries, screenshots of other players, chat or packet captures. `.gitignore` and
   `.githooks/pre-commit` already refuse them; re-scan the history anyway.
2. No rAthena-derived (GPL) data is in the repository: the knowledge base is generated locally
   (ADR-0015).
3. Every port in THIRD_PARTY.md has its attribution, and the licences in this ADR still match the
   pinned dependency versions.
4. No secrets: `.env` is never committed, and the credentials were rotated (2026-10-01).
