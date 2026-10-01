---
doc_type: design
hypothesis: null
status: ACCUMULATING
role: null
verdict_date: 2026-10-01
verdict_ticket: null
supersedes: null
related: []
next_action: Arm C -- FreeRDP 3.32.1 (trixie-backports) in one guarded desktop build in an operator-chosen window, then A/B progressive vs AVC420 vs AVC444 with measure_motion + measure_delay. Until then the lab runs RDP_GFX=progressive (the Windows AVC policies stay on).
---

# H.264 for the RDP leg: plan and Arm A result

Status:
- **Arm A done 2026-10-01**: the Windows policies are on, and one reboot happened. With FreeRDP 3.15's
  software decode it brings **no delivery gain and a worse latency tail**.
- The lab therefore runs **`RDP_GFX=progressive`** (client-side; AVC not offered).
- Arm C (a newer FreeRDP) is next.
- ➡️ There will be **no disk split** (Batt, 2026-10-01). Builds go through `scripts/guarded_build.py`
  in an operator-chosen window. Every "after the split" below means that.

## Arm A results (2026-10-01, `poring-lab` session, 800×664, dgVoodoo FPSLimit 30)

The same scenes and tools as before:
- `measure_motion.py rotate 60`: indoor `prt_church` 99,112; outdoor `new_4-1` 53,111;
- `typeperf` over the RemoteFX Graphics counters (rotation windows only);
- `measure_delay.py walks 40` (outdoor).

| Arm | RDP codec (event 162) | Scene | Xvfb frames/s median (p10–p90) | Desktop cores | RDP input fps | RDP output fps | Skipped: client /s | Encode ms |
|---|---|---|---|---|---|---|---|---|
| A: before (autodetect, no policy) | profile 2 (mixed), AVC available 1 | indoor | 6 (3–9) | 6.92 | 29.99 | 7.54 | 22.13 | 7.5 |
| A | " | outdoor | 5 (4–11) | 6.35 | 30.22 | 6.32 | 23.90 | 9.6 |
| B: policies + autodetect | **AVC444, profile 2048; event 170: Intel Quick Sync encoder enabled** | indoor | 5 (3–6) | 6.05 | 6.10 | 6.10 | 0.00 | 19.1 |
| B | " | outdoor | 6 (4–12)¹ | 5.88 | 7.43 | 7.43 | 0.00 | 18.6 |
| **D: policies + `RDP_GFX=progressive`** (kept) | profile 2, AVC available **0** | indoor | **8 (3–17)** | 7.13 | – | – | – | – |
| D | " | outdoor | **12 (7–22)**² | 7.17 | 29.94 | **12.75** | 17.19 | 11.3 |

¹ This run was labelled "B_indoor2": a GM `@warp` was mangled into chat, and `@where` proved the
scene was outdoor (new_4-1 69,137).
² The idle lead-in was not zero (4,4,1,5), so there was some ambient motion.

**Packet → frame delay**
- Method: own `0x0087` → the first lab frame whose 8×8 thumbnail of the scene band differs by
  >10 % from the last frame before the packet.
- Non-detections within 1.5 s count as ">1.5 s".

| Codec | Matched | p50 | p75 | p90 | p95 |
|---|---|---|---|---|---|
| AVC444 (policies, autodetect) | 29/40 | **740** | >1500 | >1500 | >1500 |
| progressive (kept) | 35/40 | **195** | 981 | >1500 | >1500 |

- Click sent → server walk reply: p50 ~180 ms throughout.
- The earlier frame-to-frame metric (A 154 / B 200 ms, ≥50 ms rule) is **superseded**: it detects
  later at higher frame rates and made the faster codec look slower (`measure_delay.py`).

**Reading.**
- **The policies work as designed.** Windows encodes full-screen AVC444 on Quick Sync at ~19 ms
  per frame, and stops capturing frames the client can't take (input = output, 0 skips).
- **xfreerdp 3.15 decodes AVC444 (two 4:2:0 streams) in software at ~6 cores and acknowledges
  only 6–7 fps.** Delivery doesn't improve and the latency tail gets worse.
- **Explicit `progressive` beats autodetect even without the policies.** In mixed mode, Windows
  also pushed AVC regions that the client decoded in software. With AVC not offered, output
  doubles outdoors (12.75 vs 6.32 fps).
- **Kept:**
  - `RDP_GFX=progressive` (.env, plus the RAM override until the next desktop recreate);
  - the policies stay on for Arm C.
  - Revert of the policies: `rathena-client.md` settings table.

**Next (Arm C):**
- FreeRDP 3.32.1, one guarded desktop build;
- then progressive vs `/gfx:AVC444` vs AVC420, the latter only via autodetect-with-AVC420 (the
  plain `/gfx:AVC420` flag disables RDP10 caps).
- NVDEC remains last.

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

## Windows side (applied 2026-10-01: two policies and one reboot)

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

## Lab side (one guarded desktop image build, operator-chosen window)

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

## Disk needs (what this adds; no split -- guarded build on the shared disk)

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
