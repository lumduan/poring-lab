---
doc_type: decision
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Capture the window templates and measure the element offsets on the frozen 1280x720 layout; then ACCEPT once the resolver finds them after a window move and across both capture backends.
---

# ADR-0011: A UI anchor map and an action-resolution seam -- the policy never speaks pixels

- **Status:** PROPOSED (2026-10-02). Batt's idea, from WRO mat-relative positioning.
- **Code:** `packages/poring_env/src/poring_env/ui_anchors.py` (the registry, matching and
  `Resolver`), tested in `packages/poring_env/tests/test_ui_anchors.py`.
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
