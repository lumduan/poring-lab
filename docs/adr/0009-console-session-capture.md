---
doc_type: decision
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: S1 trial (Batt approved Sunshine, 2026-10-02) -- firewall/config, pairing, the to-console handover (stop point before tscon), A4 functional checks, then bench.py run --backend console vs the RDP v1 baseline. RDP stays the default until Batt decides.
---

# ADR-0009: Console-session capture as a second display mode (Sunshine first, VNC fallback)

- **Status:** PROPOSED (2026-10-01). ➡️ **2026-10-02: Batt approved the Sunshine install and the S1
  trial** ("Sunshine research gets the weight"); RDP stays the default until he decides otherwise.
  - Sunshine v2026.914.233613 is installed on the Dell by Batt (UAC). The MSI was checked first:
    SHA-256 = GitHub's digest, Authenticode Valid, signer CN=David Lane = LizardByte's maintainer.
  - Revisions below (2026-10-02): the S1 client is **moonlight-qt**, not moonlight-embedded; the
    **capture-backend lock** replaces the proposed `RDP_MODE` override.
- **Deciders:** Batt.
- **Plan and evidence:** [console-capture-plan.md](../console-capture-plan.md). Every fact there
  carries its source URL, or is marked UNVERIFIED.
- **Related:**
  - [ADR-0001](0001-single-rdp-session.md): one RDP session. This ADR would **amend** it.
  - [ADR-0002](0002-input-mux.md): input mux, unchanged.
  - [ADR-0003](0003-env-abstraction.md): Env contract, gains a transport.
  - [ADR-0004](0004-human-only-clipboard-and-file-transfer.md): clipboard and files, RDP-mode only.
  - [ADR-0005](0005-vision-x-access.md): S2 helps close it.
  - [ADR-0006](0006-sanctioned-test-environments.md): unchanged; the interlock is still required.

## Context

- **The RDP leg caps what reaches the lab.** It delivers 6–12 fps of the 784×625 game for ~6.5
  desktop cores of FreeRDP software decode, whatever the codec ([h264-plan.md](../h264-plan.md)).
  Arm C tests FreeRDP 3.32.1.
- **The game itself renders at 60 fps** on the PC's Intel UHD 630 (i5-10500T).
- **The Windows console session** can be captured on the GPU with Desktop Duplication and encoded
  with Quick Sync. The lab would then decode one hardware-encoded H.264 stream instead of RDP's
  surface commands.
- **Batt's order (2026-10-01):** Arm C first, then VNC if needed. Sunshine is built regardless,
  after Arm C.

Three facts shape the decision:

1. **Windows 11 Pro has one interactive session.**
   - RDP owns it today.
   - A console capture tool sees only the session attached to the physical console. Sunshine's
     service starts in `WTSGetActiveConsoleSessionId()` [S].
   - The session must therefore be **moved** to the console (`tscon <id> /dest:console`), not
     duplicated.
2. **Sunshine or VNC is a new path into Windows that accepts any authenticated client.**
   - CLAUDE.md hard rule 2 forbids "a second RDP or VNC path into Windows".
   - Hard rule 3 requires every input to pass the mux.
3. **Without RDP, ADR-0004's cliprdr paste and `\\tsclient` files do not exist.**
   - Sunshine has neither: no clipboard sync and no file transfer in its docs.
   - Apollo and the VNC servers have bidirectional clipboards.

## Decision (proposed)

1. **Two display modes, never at once: RDP mode (today's default) and console mode.**
   - There is still exactly **one Windows session**: the same session ID, moved between RDP and the
     console.
   - ➡️ **Implemented (2026-10-02) as the capture-backend lock**, not an `RDP_MODE` override:
     `state/capture-backend` (`BACKEND=rdp|console`), mounted read-only in desktop, backend and
     gamestream; its only writer is `scripts/capture_backend.py`, and `/health` reports it.
     rdp-loop connects only under `rdp`, gamestream streams only under `console`, and each refuses
     while the other's window is on the display. The handover writes the lock first; only then
     does tscon run (`to-console --yes-tscon`).
   - Leaving console mode clears the hold, and RDP takes the session back.
   - Each switch is explicit and logged.
2. **Sunshine is the console-mode server; VNC is the fallback.**
   - Sunshine: the upstream LizardByte build, service install, `capture=ddx`, `encoder=quicksync`,
     H.264 only, gamepad off, `origin_web_ui_allowed=pc`, stream encryption on the LAN.
   - The fallback: TightVNC 2.8.88 or UltraVNC 1.8.3.0, with the clipboard and file transfer off.
     TigerVNC winvnc is unmaintained and excluded.
   - Apollo is rejected: it diverges from upstream and syncs the clipboard.
3. **One client, through the mux.**
   - Sunshine is paired with **exactly one client: the lab's**. Pairing any other Moonlight is
     forbidden, because it would be an input writer outside the mux.
   - The firewall admits only 192.168.1.13.
   - The agent never holds the Sunshine web-UI credentials; pairing PINs are Batt's.
4. **The lab-side client comes in two stages:**
   - **S1:** ➡️ **moonlight-qt** (6.1.0, the official AppImage) rendering into Xvfb `:99`, in the
     `gamestream` service. Nothing downstream changes. Why not moonlight-embedded: its X11 mouse is
     relative-only and warps the pointer to a fixed point on every move (`src/input/x11.c`), while
     moonlight-qt takes X events through SDL and has `--absolute-mouse`
     (`LiSendMousePositionEvent`), so the mux's XTest positions arrive as positions. The live proof
     is the A4 input check.
   - **S2:** our own `poring_env` transport on moonlight-common-c (ctypes) and PyAV.
     - Frames come from a `FrameSource` stamped on the host `CLOCK_MONOTONIC`.
     - Input goes through an `XInput`-compatible sink behind the unchanged `Injector`/`InputMux`.
     - The backend then owns the frames, and vision reads them from it (ADR-0005 option a).
5. **ADR-0004 in console mode:**
   - no clipboard channel exists;
   - ⌘V becomes **typed paste** (`LiSendUtf8TextEvent` in S2), with the same guarantees:
     human-only, never in `AgentToBackend`, digest-only audit, refused for BOT;
   - nothing reaches the Windows clipboard, so there is nothing to scrub;
   - file transfer stays an RDP-mode activity (hybrid).
6. **Amend CLAUDE.md hard rule 2 and ADR-0001 when this is accepted.** Proposed text: *"One Windows
   session and one display path at a time: the RDP session, or the console-mode server of ADR-0009
   with the RDP loop held. Never both, never a second client."*

## Gate: what ACCEPTED requires

➡️ **Reworded 2026-10-02:** "2× the best RDP arm" can no longer hold -- FreeRDP 3.32.1 already
delivers the game's full 30 fps outdoors (h264-plan.md, Arm C). The comparison is now the fixed
benchmark (docs/benchmarks/SPEC.md v1) against the RDP v1 baseline:
- delivery at the 30 fps cap, outdoor and indoor (no worse than RDP);
- packet → frame p75 and key → paint p75 ≤ RDP's, or a lab-side CPU saving worth a small loss;
- fidelity of the UI crops vs the lossless reference: no worse than RDP's;
- the RO client accepts Sunshine's SendInput keyboard and mouse. This is **UNVERIFIED**, and is the
  first thing tested;
- the console switch works with **no** second session ever appearing (`qwinsta` before and after).

If S1 fails on input but passes on video, S2 is the next step. If video fails, VNC V1 is.

## Consequences

**Positive**
- Hardware encode at the source, and one H.264 decode in the lab.
- No RemoteFX "insufficient client resources" skips.
- S2 also gives vision frames without X access.

**Negative / risks**
- **A new authenticated network service on the PC.** The firewall, single pairing and web-UI
  exposure must be audited after every Sunshine update.
- **Sunshine runs as SYSTEM** and can capture the secure desktop. The lab could see UAC prompts.
  Typed passwords stay masked, and "the agent never approves UAC" stays policy.
- **Console mode leaves the screen unlocked** on the PC. Physical access to the Dell is not a lab
  threat today; Batt's call.
- **Paste and files are weaker in console mode** (typed paste only, no file transfer).
- **Smart App Control is ON** on the PC. Unsigned installers (possibly the VNC servers) are blocked,
  and switching SAC off is irreversible, so it is not planned for.
- The Phase 0 baselines are RDP-path numbers. Console mode needs its own.

## Alternatives considered

| Alternative | Why not (now) |
|---|---|
| Stay on RDP (Arm C, then the GDI path) | Still running. This ADR only proceeds if Batt wants it regardless (he does) or Arm C falls short |
| VNC first | Weaker auth (8-character DES) and CPU encode on the PC; kept as the fallback |
| Apollo (Sunshine fork) | Bidirectional clipboard sync (ADR-0004); divergence from upstream |
| Parsec and other cloud-brokered tools | Account and cloud dependency; not open source |
| Hyper-V VM | A separate, queued track (Batt, 2026-10-01) |
