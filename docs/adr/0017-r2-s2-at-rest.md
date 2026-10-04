---
doc_type: decision
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Batt reviews. Nothing switches; R1 stays the resting state. The open verifications (UTF-8 text in RO and Notepad, UAC/secure desktop through Sunshine, a multi-day S2 soak) run in later S2 sessions before any switch.
---

# ADR-0017: R2 — S2 at rest (the long-term target, designed, NOT switched)

- **Status:** PROPOSED (2026-10-04, Post-S2 round Part F1). Design only.
- **Decided context (Batt, 2026-10-04):** R1 now (RDP at rest, S2 on demand). The LONG-TERM
  TARGET is R2. Design it, don't switch, and first fix what R2 means exactly (in
  [ADR-0014](0014-s2-primary-bot-path.md), "Resting state").
- **Builds on:** ADR-0001/0009 (one Windows session, one display path, the capture-backend lock),
  ADR-0002 (one input writer), ADR-0004 (human-only clipboard and files), ADR-0014 (S2 is the bot's
  path), ADR-0016 (the environment interlock), [human-view-webrtc.md](../human-view-webrtc.md).

## What R2 means (the definition ADR-0014 records)
**The Windows session lives on the console, with the lab's S2 client continuously connected (the
lock `console/steady`, REASON `s2-rest`). RDP is used only by an explicit, logged handover
(`capture_backend.py to-rdp`) for the human's admin work, and the session returns to the console
afterwards.**

R2 is therefore NOT:
- two display paths at once. It is still one session and one path, and the lock decides;
- a second client. It is the same lab client and identity;
- an unattended bot. The mux still boots HUMAN, and BOT needs the interlock (ADR-0016).

## What has to exist before R2 can be the resting state
### 1. Paste without RDP: `LiSendUtf8TextEvent` (verify first)
`LiSendUtf8TextEvent` (Limelight.h:700, present at mlcc 8599b60) types Unicode text into the host
through Sunshine.
- **The design:** a human-only `ClipboardPaste` (the console already sends one) is routed by the
  backend in console mode to a new `text` message on the S2 input socket.
  - The mux refuses it for BOT; ADR-0004's bot rule is unchanged.
  - Text is never logged (no length, no digest: ADR-0004 amendment c).
  - The CLIPBOARD scrub is not needed: no X clipboard is involved.
- **To verify:** that the text arrives intact in RO's chat (Thai, tis620) and in Notepad, with
  `Flags` and IME state noted. Until then console mode keeps refusing paste (`console_backend`),
  as today.

### 2. Files without RDP
`\\tsclient\transfer` exists only over RDP. Options, each human-only:
- **(a)** an authenticated SMB share on the NAS, the `nas_drop.py` pattern: a temporary Dell-only
  drop, opened and closed per use and read back;
- **(b)** an upload route into a Dell-side folder via a small Windows-side agent. That is a new
  path into Windows, so it is NOT preferred.

**Proposed: (a)**, because it already exists for the NAS and adds nothing to Windows.

### 3. UAC and the secure desktop
Sunshine runs as SYSTEM, so it can capture the secure desktop and accept input there, unlike a
user-mode capturer. That is exactly why it needs a rule.
- **To verify on the Dell:** does a UAC prompt appear on the stream, and does input reach it?
- **The rule either way:** the agent NEVER answers UAC (unchanged), and the mux refuses BOT input
  while a UAC/secure-desktop frame is detected. That needs a template, `uac_prompt`: a new
  interlock-style refusal, `secure_desktop`.
- Batt's elevated work stays a handover to RDP, or Batt at the rack.

### 4. The security of an unlocked console
At rest the console session is unlocked and visible on the Dell's (VDD-only) display. There is no
physical monitor showing it: the console is VDD-only by decision. The table covers the
threats and controls:

| Threat | Control |
|---|---|
| someone at the rack | a VDD-only layout, so no physical display shows the session; the rack is physically Batt's |
| a second streaming client | Sunshine pairs only the lab client; its firewall admits only this host; its web UI is `pc`-only (CLAUDE.md rule 2) |
| a process reaching the input socket | `s2-input` is mounted only in backend + gamestream (`test_guards`); every event passes the mux |
| the session idling unlocked for days | a lock policy: the S2 client's supervisor locks the session (Win+L through the mux, as HUMAN-equivalent `backend` source) after N hours without a lab job, or keeps R1 for the night |
| audit | the input log (every event, sources, refusals), the lock history, the interlock log |

### 5. Supervision replaces clean rooms
At rest there is no time box. A **supervisor** (`s2session.py`, as ADR-0014 sketched it) runs
under systemd `--user`. It does health checks and auto-recovery, and shows a status indicator.

**Health checks:**
- the frame age (A2's `StallMonitor`: `stalled_now`, the freeze rate);
- the S2 client's process and stats (fps, decode errors);
- the input socket's peers;
- `/health.alarms`. The supervisor is itself watched, A3-style: a guard timer raises `watchdog_down`
  RED if the supervisor's unit dies;
- the sink: is the frame bus writer alive?
- presence: the presence marker, and no Moonlight-qt window;
- the interlock state, shown, never forced.

**Auto-recovery rules:**
- a client crash → restart with backoff (never faster than gamestream-loop's rule; ADR-0009
  "never retry fast");
- 3 failures in 30 min → `to-rdp` (R1 fallback) plus an alarm;
- a frozen stream > 60 s → request an IDR, then restart the client, then fall back to R1;
- never touch Windows elevation; never pair or unpair.

**The status indicator:** the console banner, plus ADR-0013's Windows status indicator.

### 6. CPU at rest
| | R1 (RDP at rest) | R2 (S2 at rest) |
|---|---|---|
| lab cores, idle | 0.47 (RDP v2) | ~0.78 (V3b) → measured anew for `S2` (60 fps) before any switch |
| Windows | idle RDP | Sunshine encodes continuously (the Dell's GPU/CPU: to measure) |
| shared-host pressure | known | a multi-day soak with the quant sampler (io_full, cpu_full) is a precondition |

The ~+0.3 lab core is affordable on this host only if the soak shows no quant pressure. The WebRTC
human view (F2) would remove the JPEG re-encode (~0.1 core).

## Migration R1 → R2, and rollback
1. The prerequisites above, verified in S2 sessions: text input, UAC, a 72-h soak, the supervisor's
   failure drills (kill the client, freeze it, drop the sink).
2. `s2session.py start --rest`: to-console, then the supervisor with no box. Lock REASON `s2-rest`.
3. The console banner shows "R2 (S2 at rest)"; the handover to RDP is a single command or button
   (it already exists: `capture_backend.py to-rdp`).
4. **Rollback is the R1 default:** `s2session.py end` → to-rdp, then the exit checks (one session,
   `ensure_only_display` restored). Any supervisor fallback lands there too. Rollback needs no new
   code, because R1 is today's state.

## Open (to verify before Batt decides)
- `LiSendUtf8TextEvent` in RO's chat (Thai) and Notepad.
- UAC/secure desktop through Sunshine: is it visible, does it take input; and the `uac_prompt`
  template.
- A 72-h S2 soak: memory growth, decode errors, freezes per hour, Windows-side encode cost.
- The supervisor's drills.
- Whether the WebRTC view (F2) is adopted, since it changes R2's human-view cost.
