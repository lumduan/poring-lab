---
doc_type: decision
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Batt approves or amends the scope. Then it is built only after S2 is working and shared control is approved (docs/s2-plan.md §11). Nothing is implemented.
---

# ADR-0013: A Windows-side status indicator, display-only

- **Status:** PROPOSED (2026-10-02, from Batt's capture-direction note).
- **Related:**
  - [ADR-0009](0009-console-session-capture.md): the console mode and its 2026-10-02 amendment;
  - [docs/s2-plan.md](../s2-plan.md) §11: shared control;
  - [ADR-0002](0002-input-mux.md): the mux;
  - [ADR-0004](0004-human-only-clipboard-and-file-transfer.md): never log what people type;
  - [ADR-0006](0006-sanctioned-test-environments.md): the sanctioned environments.

## Context

**The lab has been agentless on Windows.** Nothing of ours runs there except:
- Sunshine (a third-party service);
- Batt's one-time SYSTEM task for tscon.

**Shared control changes the need.** A person at the Dell and the bot both drive the same console
session. The person needs to see, at a glance, what the bot is doing, the way a camera LED shows
that a camera is on:

| Colour | Meaning |
|---|---|
| green | the bot is observing only |
| orange | the bot is acting (clicking/typing): don't touch the mouse |
| blue | a human is in control; the bot is paused |

**No agentless channel can draw on the Windows screen.**
- The video goes one way only: out of Windows.
- Input injection could type or click, but it can't paint a persistent overlay. Doing that would
  mean the bot acting in the UI just to signal its state, which defeats the purpose.

So it takes a small program that runs on Windows.

## Decision (proposed)

**A display-only helper, limited to exactly this scope.**

| It MAY | It MUST NOT |
|---|---|
| receive the bot state (`observing` / `acting` / `human`) from the backend | capture, hook, or read ANY input (no keyboard or mouse hooks, no raw input, no clipboard) |
| draw a small always-on-top, **click-through** (WS_EX_TRANSPARENT + WS_EX_LAYERED), transparent overlay in one screen corner | read the screen (no capture, no GDI or DXGI reads) |
| show a stale state as **grey** when no update arrived within N seconds (fail visible, never fail green) | send anything to the backend except its own liveness (an ack carrying the state it is showing) |
| run as the **logged-in user** at logon (a per-user scheduled task or Startup) | run as admin or SYSTEM, install a service or driver, or need UAC |
| | write logs containing anything but its own state changes |

**Transport.**
- A read-only WebSocket `/ws/indicator` on the backend's public port:
  - it accepts only the Windows host's address (`WIN_HOST`);
  - it carries state messages only, never frames;
  - it gets the same never-silent drop handling as every other channel.
- The helper connects out to the backend. Nothing listens on Windows.

**Placement and perception.**
- The overlay sits **inside the session but outside GAME_REGION** (e.g. the top-right corner of the
  1440×900 session: x ≥ 1360 or y < 77).
- It appears in every captured frame, so its rectangle is a **fixed perception mask**. The bot
  never reads its own indicator.
- The recorder (ADR-0010) stores the mask with each session.

**Implementation options** (the choice is in the build step, not now):

| Option | For | Against |
|---|---|---|
| **(1) PowerShell + WPF script** | no binary; auditable source; nothing to sign | PowerShell at logon; Defender heuristics around script launches. Launched by the scheduled task, never the Run dialog (CLAUDE.md) |
| **(2) a tiny .NET app built from this repo** | a clean click-through window; small | an unsigned binary (SmartScreen); a build toolchain |
| (3) AutoHotkey | quick | a third-party runtime; AHK carries a "bot tool" reputation |

**Recommendation: (1)**, the smallest trust surface; (2) if WPF click-through proves unreliable.

## Consequences

- **"Agentless" stops being literally true.** It is replaced by "agentless for capture and input".
  The only lab code on Windows displays state. Re-review this ADR if anyone proposes widening the
  helper.
- **The helper's state comes from the mux:**
  - `acting` = the bot sent input within the last ~500 ms;
  - `human` = a lease held by `human` or `human_local`;
  - otherwise `observing`.
- **Human-presence detection stays agentless** (pixels only, docs/s2-plan.md §11b). The helper is
  NOT a sensor, by design.
- **No keystroke logging, ever.** Control episodes are audited, keystrokes are not (§11c).

## Alternatives considered

- **Use the helper to detect local input too** (a low-level hook). **Rejected:** that is a
  keylogger in all but name; detection uses pixels instead.
- **Signal the state in the RO client** (e.g. a chat message). **Rejected:** it is invisible
  outside the game, and it pollutes server-side data.
- **No indicator; rely on the web console.** **Rejected for shared control:** the person at the Dell
  doesn't watch the console.
