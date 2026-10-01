---
doc_type: design
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: After the weekend disk split, Batt approves (1) the two Windows policies + one reboot and (2) one desktop image build with FreeRDP 3.32.1 from trixie-backports; then run the A/B below.
---

# H.264 for the RDP leg: plan (not implemented)

Status: PROPOSED, 2026-10-01. Plan only; nothing in this document has been applied.

## Why: the client decode is the ceiling, and Windows chose the codec that costs the most

Measured twice: Phase 0 on 2026-09-30, and the window A/B on 2026-10-01 (`phase0-latency.md`).
During full-scene motion:
- Windows captures **~32 fps** of game frames.
- It sends **~5–8 fps**.
- It skips **21–26/s** with the counter "Frames Skipped/Second – **Insufficient Client Resources**".
- Server-side and network skips are 0. Encode takes ~10 ms. RTT is 1–5 ms.
- xfreerdp3 runs at 6.7–7.0 of its 8 allowed cores, and every CPU cap lowered delivery in step.

So the client's software decode, plus GDI into Xvfb, sets the rate. The GFX frame
acknowledgement makes the server wait for it.

**Why profile 2 (RemoteFX progressive) and not H.264.** RdpCoreTS event 162 shows:
- the client advertises GFX 0xA0701 with "AVC available: 1";
- the server still picks **Initial profile 2**;
- there is no event 170 (no AVC hardware encoder in use).

That is Windows' **default "mixed" mode**:
- without the H.264/AVC policies, Windows 11 encodes the desktop with RemoteFX progressive;
- it uses AVC only for regions it classifies as video.

A game window rotating its camera is not classified as video, so every frame goes out as
progressive RFX tiles. FreeRDP decodes those in software on the CPU (the 7 cores). It is
**not a client misconfiguration**. The 800×664 window did not change it either:
- output was 5.6–6.4 fps vs 5.5–6.0 at 1024×768;
- the area is ~40 % smaller, but decode stays the bottleneck.

## Windows side (needs Batt: two policies and one reboot)

Computer policies, under `HKLM\SOFTWARE\Policies\Microsoft\Windows NT\Terminal Services`:

| Policy (gpedit name) | Value | Effect |
|---|---|---|
| Prioritize H.264/AVC 444 graphics mode for Remote Desktop connections | `AVC444ModePreferred` = 1 (DWORD) | full-screen AVC (444 when the client offers it) instead of mixed mode |
| Configure H.264/AVC hardware encoding for Remote Desktop connections | `AVCHardwareEncodePreferred` = 1 (DWORD) | encode on the GPU (Quick Sync), not the CPU |

- Windows 11 Pro supports both (21H2 and later). They take effect after a **reboot** (one RDP
  outage, ~1.5 min, as on 2026-09-30).
- **Verify** (read-only, event log `Microsoft-Windows-RemoteDesktopServices-RdpCoreTS/Operational`):
  - event **162** shows `Avc444FullScreenProfile` (profile 2048), not "Initial profile 2";
  - event **170** shows "AVC hardware encoder enabled: **1**";
  - `\GPU Engine(*engtype_VideoEncode)` becomes non-zero during motion.
- **Intel UHD 630 (Coffee Lake) Quick Sync encodes 4:2:0 only.** AVC444 is two 4:2:0 streams (luma
  plus a chroma auxiliary view), so the hardware still serves it.
  - If 444 turns out to cost too much, AVC420 is the fallback. Text is slightly softer, which is
    acceptable for a game.
- **Revert:** delete both values and reboot.
- **Never** via the Run dialog: Defender's ClickFix detection flagged our Run-dialog PowerShell on
  2026-10-01 (see `client/rathena-client.md`). Use `gpedit.msc` or an elevated console Batt opens
  himself.

## Lab side (one desktop image build, after the disk split)

- **Today:** Debian trixie's `freerdp3` **3.15** can already decode H.264 in software via FFmpeg. So
  the Windows half alone may help, and it is worth trying first:
  - no build;
  - the image is unchanged.
- **Then:** `freerdp3` **3.32.1** from **trixie-backports** (`apt -t trixie-backports`) in
  `services/desktop/Dockerfile`:
  - a larger thread pool (capped at 16 threads; we cap the container at 8 cores anyway);
  - AVC paths that render via 512 YUV tiles;
  - many GFX fixes since 3.15.
- **Flags:**
  - keep `/gfx` on auto-negotiation, or use `/gfx:AVC444`;
  - `/gfx:AVC420` **alone disables the RDP 10 capabilities**, a known trap: the server then falls
    back to older GFX caps;
  - `RDP_GFX` in `rdp-loop.sh` already takes these keywords through the override file, without a
    rebuild.
- **NVDEC (CUDA) decode:** possible with the RTX 5060 Ti, but it is experimental in FreeRDP. It
  also costs VRAM next to Frigate and Ollama. **Not first.**

## Measurement (the same procedure as the 2026-10-01 window A/B)

`scripts/measure_motion.py rotate 60`, in two scenes:
- indoor: `prt_church`;
- outdoor: `new_4-1` (53,111), with GM `@warp`.

Windows `typeperf` runs over the three RemoteFX Graphics counters, typed into a PowerShell console.

| Arm | Change |
|---|---|
| A | today (profile 2, 3.15, FPSLimit 30) |
| B | the Windows policies only (3.15 software H.264) |
| C | B + FreeRDP 3.32.1 |

- **Goal:** output ≈ input ≈ 30 fps (the dgVoodoo cap), skips for client resources → 0, desktop
  CPU well under 8 cores.
- **Also:** key-to-paint latency with `scripts/latency_probe.py` (Phase 0 method). AVC must not add
  latency: there are no B-frames in RDP AVC, but encode happens on a GPU queue.
- **Only after** delivery reaches ~30 fps: consider `DWMFRAMEINTERVAL` = 15 (60 fps desktop
  composition) together with `FPSLimit` = 60. Before then, more frames only means more skips.

## Expected gain

- H.264 at 784×625 is ~0.5 MP per frame. Software H.264 decode of 1080p30 fits in about one core,
  so the decode cost should drop by an order of magnitude compared with progressive RFX tiles at
  the same motion.
- If decode stops being the ceiling, the next limit is the GDI blit into Xvfb plus our capture. In
  Phase 0 both stayed under 5 ms per frame at this size.
- The **expectation** is 25–30 fps delivered during camera motion, against 6–8 today. This is
  unmeasured until arm B runs.

## Disk needs after the split (what this adds)

- **Desktop image:** FreeRDP 3.32.1 plus its FFmpeg-backed codecs. Expect on the order of 10–30 MB
  of extra layers, plus one rebuild of ~5 GB of build writes, through `scripts/guarded_build.py` in
  an operator-chosen window.
- **No change to captures:**
  - pcapng grows **~0.4–0.5 MB/hour** at today's light activity, and events **~10 KB/hour**
    (`/captures`, 2026-10-01 04:20–06:41 UTC);
  - a busy map multiplies that, and the 20 GB / 7-day retention in `sniffer.py` bounds it.
- **Datasets (Phase 2):** frames at 30 fps × 784×625 would be the dominant writer, so they are what
  the split must size for:
  - ~10–20 GB/hour as JPEG q80;
  - much less if sampled.
  - Measure on the first recording run, not here.
