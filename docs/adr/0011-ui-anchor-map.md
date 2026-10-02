---
doc_type: decision
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Templates + stable masks cut and element offsets measured at 1280x720 (2026-10-02); amended the same day by ADR-0012 (the map stores keys, label_key, locale-invariant N-way masks). Remaining for ACCEPT -- a live drag test (move a window, re-locate), the console backend (S1), and the en<->th acceptance test (ADR-0012).
---

# ADR-0011: A UI anchor map and an action-resolution seam -- the policy never speaks pixels

- **Status:** PROPOSED (2026-10-02). Batt's idea, from WRO mat-relative positioning.
  ➡️ **Amended 2026-10-02 by [ADR-0012](0012-locale-agnostic-ui.md): the map stores KEYS, never
  text** (see "Amendment" at the end).
- **Code:** `packages/poring_env/src/poring_env/ui_anchors.py` (the registry, matching and
  `Resolver`), tested in `packages/poring_env/tests/test_ui_anchors.py`;
  `scripts/ui_anchors_tool.py capture|check` cuts and checks the templates.
- **Related:**
  - [ADR-0003](0003-env-abstraction.md): Env is pixels in, input out; this is the layer between
    policy and Env input;
  - [ADR-0010](0010-dataset-format.md) and docs/phase2-plan.md: the world projection;
  - [ADR-0009](0009-console-session-capture.md): capture backends must not touch policy.

## Context

Today the tools address the RO UI by absolute pixels: `ro_agent` layouts, chat-input clicks and
crop boxes. Each of them breaks the day a window moves, the resolution changes (it is changing now,
800×664 → 1280×720) or the hotbar is rearranged.

The world side already has the right shape. A walk target is a **cell**, turned into a pixel by
the calibrated camera projection. The UI deserves the same: an element is a position **inside its
window**, turned into a pixel by finding the window on the frame.

## Decision (proposed)

1. **Two coordinate systems, one pixel space, both behind one seam.**
   - **World** (mobs, NPCs, players, walk targets): cell offset from the player → pixel, through the
     calibrated default camera (a 3×3 homography; a calibration constant like a camera intrinsic,
     not world state).
   - **UI** (HP/SP bars, chat input, hotbar slots, window buttons): window-relative → pixel, through
     the anchor map.
   - Predictable layout → anchor map. Positions that move every frame → projection. Never mixed.
2. **The anchor map has two layers** (`ui_anchors.UiAnchors`):
   - **Layer 1, windows.** RO windows are drag-movable and **fixed-size**, not scaled by the
     resolution. Each registered window is found anywhere in the client area by template-matching a
     distinctive strip (its title bar), with FFT-based SSD in numpy and a distance threshold. The
     match gives the window's origin.
   - **Layer 2, elements.** A fixed box relative to the window origin (`hotbar_slot_3` = origin +
     (73, 3)), **or** an icon template searched inside the window for things that move between
     slots.
3. **The seam (`ui_anchors.Resolver`).**
   - Policy asks for `ui("chat_input", frame)` or `cell(dx, dy)` and gets a pixel, or None when the
     window isn't on screen.
   - Turning that pixel into input events stays in Env / the mux. A window move, a resolution
     change or another capture backend changes anchors and calibration, **never policy**.
4. **Scope now: what is actually used.** HP/SP (bars and text), the chat input, the hotbar slots and
   the Game option window. Full coverage comes when the policy needs it; projection work is not
   blocked on it.
5. **Pixels in only.**
   - The registry reads frames and nothing else. Templates are cut from the lab's own frames and
     stored with the lab's data (gitignored, like ro_agent's signatures); the element geometry is
     code.
   - `poring_env` stays free of packets and datasets (`test_guards.py`).

## Consequences

- One re-measure per layout change: re-cut the templates, re-check the offsets. Everything above
  the seam is untouched.
- **A shared vocabulary.** The UI crops used by the benchmark (fidelity) and the OCR track can be
  defined as anchor elements rather than absolute boxes, so they follow their windows.
- **Template matching costs a few ms per window per frame.** The agent locates windows when they
  may have moved (after a drag, a map change or a reconnect), not on every frame.
- **The camera constant reaches the agent side.** It is derived offline from packets, but it is
  geometry, not world state; ADR-0007's line (no packet data at decision time) is kept.
  **Batt to confirm.**

## Measured on the frozen layout (2026-10-02, 1:1 1280×720 client)

| Window | Found by (strip, window-relative) | Size | Elements (window-relative box) |
|---|---|---|---|
| `basic_info` | title bar (0,0) 200×15 | 220×140 (+ the menu when expanded, to 327) | `hp_bar` (35,53,135,9), `sp_bar` (35,68,135,9), `hp_sp_text` (30,51,190,27) |
| `hotbar` | the row-number column (0,30) 16×100 | 290×131 (4 rows) | `hotbar_slot_1..9` (15+29i, 3, 26, 26) |
| `chat` | the tab strip (0,0) 240×15 | 597×93 | `chat_input` (80,72,400,14) |
| `game_option` | title bar (0,0) 260×15 | 280×138 (open after Escape) | `game_option_close` (30,113,220,20) |

- **RO windows are translucent, the chat window almost entirely.** Only 0.6 % of its pixels are
  identical over two scenes. So each template carries a **stable mask**: the pixels within 4 grey
  levels when the same strip is cut over another scene (`capture --mask-png`). Matching is masked
  SSD, still FFT-only (`match_template(..., mask)`). Stable fractions: `basic_info` 0.98, `hotbar`
  0.87, `chat` 0.17.
- **Checked offline on saved frames:**
  - Each window is found at distance 0.0 on its own frame and ≤ 1.65 on the other scene.
  - On a third frame, from the old 1280×800 session, the UI sits 168,22 away; those windows are
    found at their moved origin. `basic_info` scores 0.34, `hotbar` 1.84 and `chat` 8.37: the
    thinnest margin under the acceptance of 12, so more scenes in the mask would tighten it.
  - A closed `game_option` is rejected at 31–41.
- The templates and masks live in `data/ui_anchors/` (gitignored, lab frames); the geometry above
  is code.

## Amendment (2026-10-02): keys, never text ([ADR-0012](0012-locale-agnostic-ui.md))

The map was already free of pixels at the policy side. Batt's language-agnostic amendment makes it
free of **text** as well, so one map serves every locale pack.

- **Canonical names.** Window and element names must be canonical identifiers
  (`[a-z][a-z0-9_]*`), checked when a spec is built; `validate_registry` checks the shipped
  registry at import.
- **`ElementSpec.label_key`.** An element whose meaning is a piece of UI text carries its key:
  - a message key, `msg.k` + 8 hex;
  - or a curated alias, `ui.*`, listed in `ALIASES` and pointing at a message key.
  Display text is refused. None of today's elements has one yet: the keys come from the kRO
  reference once it is on the NAS.
- **`UiAnchors.labelled_boxes(origins)`.** Each visible keyed element's client-pixel box and key.
  With a locale pack this auto-labels OCR crops (docs/locale-packs.md §7).
- **Locale-invariant templates.** `stable_masks(templates, others)` accepts one variant (the
  original two-frame call, unchanged) or a list of variants: other scenes AND other locales. A pixel
  stays in the mask only if it agrees in every variant, so title text drops out.
  `ui_anchors_tool.py capture --mask-png` is repeatable.
- **Unchanged:** the templates already saved in `data/ui_anchors/`, the measured geometry above,
  and `Resolver`.

