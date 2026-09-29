---
doc_type: decision
hypothesis: null
status: GO
role: null
verdict_date: 2026-09-29
verdict_ticket: null
supersedes: null
related: []
next_action: Phase 0 - measure capture FPS, fidelity and end-to-end latency per RDP codec (autodetect/AVC444 vs progressive vs lossless legacy); live-verify against the Windows host once WIN_HOST and credentials are set.
---

# ADR-0001: One RDP session serves the web UI and the agent

- **Status:** accepted and implemented in the scaffold (2026-09-29)
- **Related:** [ADR-0002 input mux](0002-input-mux.md), [ADR-0003 env abstraction](0003-env-abstraction.md)

## Context

The Ragnarok Online client runs on a Windows host (Dell OptiPlex 3080 Micro). It is controlled from the
Ubuntu Docker host over RDP. Windows **client** editions allow a single interactive session:

- connecting over RDP locks the console and takes over any logged-in session;
- a second RDP connection (for example `mstsc` from a laptop) kicks the first one off.

Several parties need the same screen and the same input path at once: a human in the browser (live
view plus control), the vision agent (pixels in, mouse and keyboard out), and occasional debugging.

## Decision

1. **Exactly one RDP client.** The `desktop` container runs `xfreerdp3` (FreeRDP **3.15**, Debian
   trixie). It runs fullscreen (`/f`) inside **Xvfb `:99`** at `XVFB_RESOLUTION` (default 1280x720x24),
   with no window manager.
2. **Everyone else reads the Xvfb framebuffer; nobody opens another session.**
   - The X socket is shared through the named volume `x11-unix` (`/tmp/.X11-unix`).
   - Xvfb runs with `-nolisten tcp -ac`, so the volume mount *is* the access boundary.
   - backend and vision mount it read-only (`connect()` on a socket needs no filesystem write).
   - Capture uses mss 10.2: XCB + XShmGetImage, with the segment passed as a memfd. It works across
     containers without IPC-namespace sharing.
3. **All input enters through XTest, and only from the backend's input mux** (ADR-0002).
   - x11vnc/noVNC is a **view-only** debugging window (`NOVNC_VIEW_ONLY=true`).
   - Interactive VNC would be a third input source that is unlogged and bypasses the mux.
4. **Credentials only from the environment, never in argv.**
   - `rdp-loop.sh` feeds xfreerdp3 through `/args-from:stdin`, one argument per line, written by the
     bash builtin `printf`.
   - It runs under `env -u RDP_PASSWORD`, so the password is not even in xfreerdp's environment.
   - `RDP_CERT_SHA256` pins the server certificate (`/cert:deny,fingerprint:sha256:…`). When unset,
     the loop falls back to `/cert:ignore` with a warning.
5. **Reconnect policy keyed on xfreerdp3's exit code.** It never fights a human and never feeds a
   lockout policy.

   | Exit | Meaning | Action |
   |---|---|---|
   | 0 1 2 3 4 11 12 | clean end, logoff, timeouts, user disconnect | reconnect after 2 s |
   | 5 | `DISCONNECTED_BY_OTHER_CONNECTION` (someone took the session) | back off 10 min |
   | 132 134 135 148–159 | authentication or account failure | **stop** (Windows lockout risk) |
   | 16–26 | licensing, or CLI parse error | **stop** |
   | other | network, DNS, TLS, target booting | backoff 2 s → 60 s |

   Empty `WIN_HOST`/`RDP_*` means no connection is attempted. The stack runs Xvfb-only, which is how CI
   and the smoke test run.
6. **FreeRDP major 3 is pinned.**
   - Pin: apt glob `freerdp3-x11=3.15.0+dfsg-2.1+deb13u*`, plus a build-time `xfreerdp3 --version`
     assertion.
   - 2.x is end-of-life upstream, and its spellings (`/cert-ignore`, `/gfx-h264`, `/kbd:0x409`) are not
     even compiled into 3.x distro builds.
   - Ubuntu's FreeRDP 3 has no H.264 (`/gfx:AVC444` fails to parse there), so the base image is
     Debian.
   - The codec is a knob: `RDP_GFX` empty means FreeRDP autodetect (GFX + AVC444 + RFX); the
     alternatives are `progressive`, `AVC444`, `AVC420`, `RFX`, or `off` (legacy lossless bitmaps).

## Consequences

**Positive**

- One session serves every consumer, and nothing extra runs on Windows.
- Frames reach the agent without an encode/decode hop (see ADR-0003).
- The stack is fully testable without Windows (Xvfb-only mode).

**Negative / constraints**

- The Windows console is locked while the stack is connected. The RO client must run *inside* the RDP
  session, at the Xvfb resolution.
- **H.264 is lossy** (AVC420 halves chroma). Pixel-level perception may prefer `progressive` or legacy
  lossless mode; Phase 0 measures it.
- The remote cursor is an X cursor, not framebuffer pixels, so grabs are cursor-free. Set
  `CAPTURE_WITH_CURSOR=true` if Phase 0 wants it composited.
- xfreerdp client hotkeys act on the session itself:
  - Ctrl+Alt+Enter is disabled with `-toggle-fullscreen`.
  - The mux refuses Ctrl+Alt+D and Ctrl+Alt+Enter.
- Debian trixie's 3.15 carries a backlog of FreeRDP CVEs that are fixed upstream. Accepted for now,
  because the only server it ever connects to is our own LAN host. trixie-backports 3.32.x fixes them,
  but from 3.32.1 draws a "Reconnecting" window at (0,0) into the framebuffer. Revisit with Phase 0.
- `/prevent-session-lock` is deliberately **not** used: it injects input outside the mux. Disable
  lock, sleep and the screensaver on the Windows host instead.

## Alternatives considered

- **A second session per consumer.** Impossible on a client SKU; one session is the constraint itself.
- **An agent and capture on Windows (DXGI + SendInput).** Needs Windows-side software and breaks
  "controlled via ONE RDP connection from the Ubuntu stack".
- **A VNC server on Windows.** Shares the console session and needs no RDP, but it is Windows-side
  software with its own codec path. Not chosen.
- **TigerVNC `Xvnc`** (X server and VNC server in one process). Leaner, but the spec asked for
  Xvfb + x11vnc; possible later.
- **FreeRDP 2.x, or an Ubuntu base image.** Rejected: end-of-life, and no H.264, respectively.
