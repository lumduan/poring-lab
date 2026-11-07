---
doc_type: decision
hypothesis: null
status: GO
role: null
verdict_date: 2026-10-04
verdict_ticket: null
supersedes: null
related: []
next_action: Keep the import boundary (test_guards) green (GREEN again since d436cc6, route A). The repository IS PUBLIC; the publication checklist was re-run 2026-11-07 (section at the end). The removed GPL port stays in history, labelled (Batt 2026-11-07).
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
  ➡️ **SUPERSEDED: the repository is PUBLIC** (GitHub reports `PUBLIC`, checked 2026-11-07; it
  became public for the teaching kit, Batt 2026-11-06). The obligations now apply; the checklist
  was re-run 2026-11-07 (the section at the end).
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

## Publication checklist re-run (2026-11-07, Batt: "ok"; read-only)
Run on an anonymous `git clone --mirror` of the PUBLIC repository into RAM (26 MB: 5 branches, 2,029
commits, 1,229 paths ever committed): what anyone can download, with no read of the shared disk.

1. **Client-derived or RO-copyrighted files: none outside the approved exception.** No GRF / GPF /
   GAT / RSW / GND / SPR / ACT / PAL / BMP / LUB file, no client exe or dll, no packet capture, no
   `.env`, nothing under `data/` but its README, in any commit. Images: 4 Blockly UI images (the
   Blockly package, Apache-2.0, already in THIRD_PARTY.md) and the teaching kit's 20 sample frames
   (Batt's scoped exception, 2026-11-06). The largest blob ever is the kit's `v1.onnx` (10.8 MB).
2. **GPL (rAthena) material: two pieces, now labelled GPL-3.0 in THIRD_PARTY.md.**
   - `services/rathena/patches/0001-thai-trim-chars.patch` (19 lines): a change to rAthena, the same
     as upstream PR #9990.
   - `packages/poring_dataset/src/poring_dataset/paths.py`, in history only (added 2a0404a
     2026-10-02, removed d384d1e 2026-10-04): the literal port of rAthena's `path.cpp`. Public
     history distributes it, so it is GPL-3.0 there.
   - No rAthena db, knowledge base or table copy in any commit. `tables.lock.json` (packet ids and
     lengths where rAthena and OpenKore disagree) and `mapcache.lock.json` (rAthena file names,
     sizes, sha256) are protocol facts and checksums.
   - Not done, Batt's decision: rewriting history to drop `paths.py` (`git filter-repo` + a force
     push). It would change every commit SHA from 2026-10-02 on, and every document that cites one.
     ➡️ **DECIDED 2026-11-07 (Batt: "do as recommended"): keep the history, labelled GPL-3.0.**
3. **Attributions:** every port the code names (nostalro-client, korangar, RagLite) has its row; the
   licensed dependencies' versions in THIRD_PARTY.md equal the pins (ultralytics 8.4.165, -thop
   2.2.1, -platform 0.1.70, torch 2.14.0+cu130 / torchvision 0.29.0+cu130 in `uv.lock`; blockly
   13.3.0, @xyflow/react 12.12.0 in `package.json`).
4. **Secrets:** `.env` was never committed on any branch. No private key, GitHub / AWS / Slack /
   OpenAI-style token in any diff (one fake key, body `AAA`, in a test fixture). The
   password-like lines are code: the secret generators of `rotate_secrets.py`, test values.
- **The teaching kit** (`teaching-kit` 8377220) now states its licences in `NOTICE.md` with both
  licence texts: `simple_bot.py` Apache-2.0, `v1.onnx` AGPL-3.0 (its source: `services/vision` at
  05b8cff), the sample frames not ours to license. `teaching/simple-bot/make_kit.py` carries them
  into every kit it builds.
- **The import boundary:** GREEN again since d436cc6 (route A: `gold_eval.py` reads frame-cache
  shards with its own reader; the parity with the trainer's reader is tested on the vision side).
