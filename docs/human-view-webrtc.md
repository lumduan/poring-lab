---
doc_type: design
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Batt reviews with ADR-0017 (R2). Nothing is built. The first step is the TCP-vs-UDP measurement below, on the same clocks, with a VISIBLE viewer; the TCP sysctl decision waits for it.
---

# The human view over WebRTC (H.264 passthrough), and a TCP-vs-UDP measurement plan

**Status:** PROPOSED (2026-10-04, Post-S2 round Part F2). Design only; **nothing is built**.
**Why now:** R2 (S2 at rest, [ADR-0017](adr/0017-r2-s2-at-rest.md)) makes the console's human
view a permanent path, not a clean-room tool. Batt's decision 9 asks two things:
- measure and compare a UDP path;
- make the TCP sysctl call only after a measurement with a visible viewer.

## Today's human view (S2)
Sunshine H.264 → the S2 client decodes once (the frame bus) → the backend re-encodes JPEG at
`CONSOLE_FPS` (15) → `/ws/stream` (TCP) → the browser.

It costs three things:
- **a JPEG encode per shown frame:** ~0.1 core at 15 fps (s2-plan §6);
- **the encode's latency**, plus TCP's head-of-line blocking on a lossy hop (the LAN's ~1 lost
  frame/10 s shows up upstream already; s2-plan "packet loss");
- **a frame-rate cap (15)** that is below what the stream carries (30).

## The proposal: forward the H.264 Sunshine already sent, over WebRTC
```
Sunshine ──H.264/UDP──▶ s2spike (decode once → bus, unchanged; the bot's path is untouched)
                          └─ the SAME access units ─▶ a WebRTC sender (RTP, H.264 packetization)
                                                       └─▶ the browser's <video> (hardware decode)
```
- **No re-encode:** the access units the client already has (`h264rec`'s tap point) are packetized
  as RTP. Expected saving: the JPEG encode (~0.1 core) and its latency (~10-40 ms, measured below).
- **The browser decodes in hardware**, at the stream's full rate (30 fps), with a jitter buffer
  that drops late frames instead of stalling behind them (UDP: no head-of-line blocking).
- **Keyframes on demand:** a viewer joining mid-stream (or after loss) needs an IDR. WebRTC's PLI
  (picture loss indication) maps onto the client's `LiRequestIdrFrame()`, the same call the
  recorder uses.
- **Input is unchanged:** it stays on `/ws/input` and the mux. WebRTC carries video only; a data
  channel is NOT a new input path (ADR-0002: new input paths go through the mux, never around it).
- **Security posture (unchanged rules):**
  - LAN viewers only (VIEWER_NETWORKS);
  - signaling through the backend with the allowlisted Origin;
  - no TURN or STUN to the internet (host candidates only);
  - the agent network refused (c2);
  - one more listening socket (UDP, an ephemeral range pinned in compose), so compose and the
    guards change with it.
- **Library options** (none chosen; a probe decides):
  - `aiortc` in the backend: pure Python. It can forward pre-encoded H.264 through a custom
    `MediaStreamTrack` (the frames are passed as `Packet`s, not re-encoded).
  - A small native sender in the gamestream image (GStreamer `webrtcbin`, or `pion` behind a unix
    socket): more CPU-efficient, but a new image dependency.
- **Where it runs:**
  - in **gamestream**: the access units are there, and no bitstream crosses containers;
  - or in the backend, fed over a socket.

  The backend already owns viewers, Origins and the banner, so signaling stays there in both cases.

## What could go wrong (the probe's checklist)
1. **Profile and level:** Sunshine's H.264 (high profile, possibly 4:4:4 off) must be one the
   browser's WebRTC stack negotiates. Safari and Chrome both decode High profile over WebRTC, but
   the `profile-level-id` must match.
2. **SPS/PPS cadence:** Sunshine repeats them with each IDR (the recorder checks NAL 7/8 on the
   first IDR), so a late joiner is fine after the next IDR or a PLI.
3. **Timing:** `presentationTimeMs` from the decode unit gives the RTP timestamps (90 kHz).
4. **Safari hidden tabs stop decoding** (Phase 0 finding): unchanged with WebRTC, so a measurement
   needs a visible viewer.
5. **CPU in gamestream** (cpus 4): packetization is cheap, but a Python sender at 30 fps × ~80 KB
   must be measured, not assumed.

## The TCP-vs-UDP measurement plan (same clocks, one variable at a time, A/A first)
**Question:** for a VISIBLE human viewer on the LAN, does a UDP path (WebRTC) beat the current
TCP path (`/ws/stream` JPEG), and does a TCP tuning (the sysctl Batt deferred) change the TCP
side?

**Clocks:**
- key → photon is measured the way Phase 0 measured key → paint;
- the backend's `t_mono_ns` stamps the input;
- the viewer's displayed frame is detected by a marker in the frame (the existing
  `measure_delay.py` patch), with the ping/pong offset between the browser and the backend
  (separate clock domains: never subtracted directly).

**Arms** (each a 3-min run, the same scene and seed, a visible Chrome viewer on the MacBook):

| Arm | Path | Variable |
|---|---|---|
| T0 | `/ws/stream` JPEG at 15 fps (today) | — |
| T0' | T0 again | the A/A (spread = noise) |
| T1 | `/ws/stream` at 30 fps | the rate (the cap's own cost) |
| T2 | T1 + the TCP knob (per-container `sysctls` on the backend only, never host-wide; e.g. `net.ipv4.tcp_notsent_lowat`) | one sysctl |
| U1 | WebRTC H.264 passthrough at 30 fps | the transport + no re-encode |
| U1' | U1 again | the A/A |

**Measured per arm:**
- key→photon p50/p95/p99;
- displayed fps (the browser's `getVideoPlaybackQuality` / requestVideoFrameCallback counts);
- dropped/late frames;
- backend + gamestream cores (cgroup usage);
- LAN bytes/s;
- the behaviour across a loss burst: the LAN's own ~1 frame/10 s, plus one induced 2-s stall by
  pausing the sender (never by touching the network);
- recovery time to a fresh picture.

**Pre-registered expectations** (to be refined before any run):
- U1's key→photon p50 is ≥ 20 ms below T1's (no JPEG encode, a hardware decode);
- its p95 tail is shorter under loss (no head-of-line blocking);
- cores drop by ≥ 0.08;
- T2 changes T1's p95 by < 10 ms. If so, the sysctl is NOT worth adopting, and the deferred
  decision closes as "no".

**Decision rule:**
- WebRTC replaces the JPEG view only if U1 wins on p95 AND cores AND the A/A spreads are smaller
  than the differences;
- otherwise `/ws/stream` stays.
- The sysctl is adopted only if T2 beats T1 by more than the T0/T0' spread.

**Order:**
1. The probe: can a browser show Sunshine's access units at all? (aiortc, one session, no lab
   wiring.)
2. T0/T0' and T1.
3. U1/U1'.
4. T2 last, because it changes a kernel setting, however narrowly.

Everything is measured in an S2 session with a visible viewer (Batt's MacBook), never on a hidden
tab.

## Out of scope
- Audio.
- Any Moonlight-protocol client other than the lab's (ADR-0009: one lab client at a time).
- WebRTC for the BOT. The bot reads the frame bus: lossless, in-process, and with no reason to
  move.
