---
doc_type: design
hypothesis: null
status: GO
role: null
verdict_date: 2026-10-01
verdict_ticket: null
supersedes: null
related: []
next_action: Arm C DONE -- FreeRDP 3.32.1 kept with RDP_GFX=progressive (30 fps outdoor, 0 skips, p95 157 ms). Open -- Batt's live paste check on 3.32 (ADR-0004 amendment b); optional DWMFRAMEINTERVAL/FPSLimit 60 now that delivery sits at the 30 fps cap; console capture is planned separately (ADR-0009).
---

# H.264 for the RDP leg: plan and Arm A result

Status:
- ✅ **Arm C done 2026-10-01 (evening): FreeRDP 3.32.1 lifted the ceiling.** Outdoor delivery went
  from 9 to **30 fps** (the dgVoodoo cap), there are 0 client-resource skips, desktop cores fell
  6.8 → 4.8, and packet→frame p95 went from >1.5 s to **157 ms**. The lab keeps 3.32.1 with
  **`RDP_GFX=progressive`**. See "Arm C results" below; it supersedes the Arm A and AVC420
  conclusions about delivery.
- Arm A, 2026-10-01 (history): the Windows policies are on, and one reboot happened. With FreeRDP
  3.15's software decode it brought **no delivery gain and a worse latency tail**.
- ➡️ There will be **no disk split** (Batt, 2026-10-01). Builds go through `scripts/guarded_build.py`
  in an operator-chosen window. Every "after the split" below means that.

## Arm A results (2026-10-01, `poring-lab` session, 800×664, dgVoodoo FPSLimit 30)

➡️ **History, FreeRDP 3.15.** The delivery numbers here are superseded by "Arm C results" (3.32.1: 30 fps outdoor, 0 skips).

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

➡️ **The "Next (Arm C)" list that stood here is SUPERSEDED by the AVC420 experiment below
(2026-10-01 evening):** there is no client-side way to get plain AVC420 from Windows with
FreeRDP 3.15.

## AVC420 experiment (2026-10-01, 19:49–20:45 ICT, poring-lab session, policies ON, 800×664, FPSLimit 30)

**How FreeRDP 3.15 asks for codecs** (source of `parse_gfx_options` and
`rdpgfx_send_supported_caps` at the 3.15.0 tag):
- Naming any codec in `/gfx:` sets `GfxH264` from `AVC420` only, and `GfxAVC444` from `AVC444` only.
- The 10.x capability sets are sent only if `!GfxH264 || GfxAVC444`, and AVC is disabled in 10.x
  unless `GfxAVC444` is set. So "AVC420, not AVC444" means **8.1 caps only**.
- `thin-client` adds `AVC_THINCLIENT` to every 10.3+ set. `mask:` is a **filter** (bit set =
  version NOT offered; bit order 8, 8.1, 10, 10.1, …, 10.6, 10.6err, 10.7).

**What Windows chose** (RdpCoreTS event 162, read by `poring-lab`):

| Client args | Caps Windows picked | AVC available | Initial profile |
|---|---|---|---|
| `/gfx:AVC420:on,AVC444:off,progressive:off,RFX:off` | 8.1 (0x80105) | 0 | 2 (progressive) |
| `/gfx:AVC420` (bare) | 8.1 (0x80105) | 0 | 2 |
| `/gfx:thin-client` | 10.7 | 0 | 2 |
| `/gfx:AVC444` | 10.7 | 1 | 2048 (+ event 170: Quick Sync) |
| **`/gfx:AVC444:on,thin-client:on,mask:2015`** = `RDP_GFX=AVCthin` | **10.3 (0xA0301)** | 1 | 2048 (+ event 170) |
| `progressive` (kept) | 10.7 | 0 | 2 |

**Windows 11 never uses AVC for an 8.1-only client.** AVC420 cannot be forced client-side.
`AVCthin` gets full-screen AVC with the 10.3 thin-client flag. Neither the protocol semantics of
that flag nor the per-frame codec (AVC420 vs AVC444) were verified; the client's debug logging
for rdpgfx isn't compiled in.

**Measured** (the same tools as Arm A; rotations 60 s; delay = 40 walks, post-hoc reference,
non-detections counted as >1.5 s; delay runs alternate spots because a wandering NPC blocked
new_4-1 53,111 later):

| Arm | Scene | Xvfb frames/s median (p10–p90) | Desktop cores | RDP in | RDP out | Skips: client /s | Encode ms |
|---|---|---|---|---|---|---|---|
| progressive | indoor | 7 (3–14) | 6.70 | 30.11 | **12.01** | 17.64 | 9.6 |
| progressive | outdoor | **9 (5–20)** | 6.80 | 29.93 | **10.15** | 19.75 | 11.4 |
| AVCthin | indoor | 6 (3–9) | 6.47 | 7.20 | 7.20 | 0.00 | 18.7 |
| AVCthin | outdoor | 6 (4–9); repeat 8 (5–16) | 6.39; 6.66 | 6.71 | 6.71 | 0.00 | 18.7 |

| Codec | Spot | Matched | p50 | p75 | p90 | p95 |
|---|---|---|---|---|---|---|
| progressive | new_4-1 53,111 (18:31) | 35/40 | 195 | 981 | >1500 | >1500 |
| progressive | new_4-1 53,111 (19:52) | 35/40 | 204 | 972 | >1500 | >1500 |
| progressive | prt_fild08 170,375 (20:44; a human lease touched 2 trials) | 35/40 | 242 | 1007 | >1500 | >1500 |
| AVCthin | new_4-1 53,111 (20:18) | 39/40 | 169 | 269 | 439 | 1370 |
| AVCthin | prt_fild08 170,375 (20:41) | 35/40 | 195 | 778 | >1500 | >1500 |
| AVC444 (10.7, Arm A) | new_4-1 53,111 (18:33) | 29/40 | 740 | >1500 | >1500 | >1500 |

**Decision: keep `progressive`.** ➡️ On 3.32.1 (Arm C below) both codecs deliver 30 fps; progressive is still kept, now for fidelity and idle cost, not delivery.
- It delivers ~50 % more frames (Windows output 10–12 vs 6–7 fps; Xvfb 7–9 vs 6–8), consistently.
- AVCthin's fresher-frame advantage was dramatic once (p75 269 ms) and modest on the repeat
  (778 vs 1007 ms). Not enough to give up a third of the frames.
- `AVCthin` stays as a keyword for later A/Bs. Reverted client-side; event 162 confirmed 10.7,
  AVC 0, profile 2.

**What this says about Arm C.** Every codec lands at **~6.4–6.8 desktop cores** for 6–12 delivered
fps of a 784×625 game: progressive, AVC444 and AVCthin alike.
- A single-stream H.264 decode of this size costs a fraction of one core, so the ceiling is **not
  the codec** but FreeRDP 3.15's surface/GDI path into Xvfb (the client also runs ~390 threads).
- That is exactly what 3.32 reworked: the thread pool capped at 16, and YUV work in 512 tiles. So
  **Arm C is still worth one guarded desktop build**, measured with the same two tables.
- If 3.32 doesn't move the ~6.5-core ceiling, the next suspect is the X11 GDI path (`RDP_GDI=hw`
  was tried in Phase 0) rather than any codec.

**GPU decode, research only.**
- The Debian 3.15 package is built `WITH_VAAPI=OFF` and has no CUDA/NVDEC path.
- The desktop container has no GPU device: compose gives the RTX 5060 Ti only to vision.
- GPU decode would therefore need a custom FreeRDP build (VAAPI, or an FFmpeg hwaccel), a render
  device passed to the desktop container, and VRAM next to Frigate, Ollama and vision.
- Not worth it before Arm C shows whether decode is even the limit.

## Arm C results (2026-10-01, 21:49–22:31 ICT, FreeRDP 3.32.1, poring-lab session, policies ON, 800×664, FPSLimit 30)

**Build.** `services/desktop/Dockerfile` installs `freerdp-x11` + `freerdp3-x11` **3.32.1+dfsg-1~bpo13**
from trixie-backports, in a layer of its own on top of the unchanged 3.15 layer.
- The build asserts `xfreerdp3 --version` = 3.32 and `/buildconfig` has `WITH_GFX_H264=ON` and FFmpeg.
  Measured in the container: `WITH_FFMPEG=ON WITH_VIDEO_FFMPEG=ON WITH_DSP_FFMPEG=ON WITH_SWSCALE=ON
  WITH_VAAPI=OFF WITH_OPENH264=OFF`.
- The binary is now `/usr/bin/xfreerdp`, and `xfreerdp3` is a link to it. rdp-loop.sh keeps calling
  `xfreerdp3`, so the process's comm stays `xfreerdp3`.
- **Rollback image:** `poring-lab/desktop:freerdp-3.15` (227cd4aac623): re-tag it as `:local`, then
  a guarded `recreate:desktop@90`. The new `:local` is f49703cfee4d (864 MB, +9 MB).
- **Build path and the IO guard** (quant-postgres ±5 min in the 2026-10-01 report):
  1. Try 1 put the upgrade in the big RUN layer. Re-unpacking 135 packages tripped `--spike 25`
     (27.8 %).
  2. Try 2 had the upgrade in its own layer and every layer cached, but the **export** tripped:
     the active buildx builder is `armbuilder` (docker-container driver), which loads the whole
     image into dockerd as a tarball. That was ~5 s at 66–100 % io_full on postgres, ticker,
     orderbook and cron; crypto-engine stayed at 0 %.
  3. Try 3, export only, ran with `--spike 101` (Batt's one-time approval; the 30 s sustain rule
     stayed on): worst 37.8 %, 8 s above 10 %.
  4. The recreate: worst 6.6 %.

**Negotiation is unchanged** (RdpCoreTS event 162 read by `poring-lab`):
- `progressive`: 0xA0701, AVC 0, profile 2.
- `AVCthin`: 0xA0301, AVC 1, profile 2048, plus event 170 (Quick Sync).
- So `mask:` and `thin-client` behave as on 3.15.

**Delivery and cost.** Same tools and spots as the AVC420 experiment. Rotations are 60 s; the Windows
columns are `typeperf` over the same wall-clock windows.

| FreeRDP | Arm | Scene | Xvfb frames/s median (p10–p90) | Desktop cores | RDP in | RDP out | Skips: client /s | Encode ms |
|---|---|---|---|---|---|---|---|---|
| 3.15 | progressive | indoor | 7 (3–14) | 6.70 | 30.11 | 12.01 | 17.64 | 9.6 |
| 3.15 | progressive | outdoor | 9 (5–20) | 6.80 | 29.93 | 10.15 | 19.75 | 11.4 |
| 3.15 | AVCthin | indoor | 6 (3–9) | 6.47 | 7.20 | 7.20 | 0.00 | 18.7 |
| 3.15 | AVCthin | outdoor | 6 (4–9) | 6.39 | 6.71 | 6.71 | 0.00 | 18.7 |
| **3.32.1** | progressive | indoor | **17 (15–23)** | **4.42** | 30.01 | **28.43** | **0.00** | 8.7 |
| **3.32.1** | progressive | outdoor | **30 (29–30)** | **4.78** | 29.99 | **29.96** | **0.00** | 10.5 |
| **3.32.1** | AVCthin | indoor | **17 (9–30)** | **0.94** | 30.00 | **30.00** | **0.00** | 16.0 |
| **3.32.1** | AVCthin | outdoor | **30 (28–31)** | **0.98** | 30.01 | **30.01** | **0.00** | 19.6 |

The AVCthin rows are a clean re-run at 22:22–22:25. The first run (22:16–22:19) was interrupted by
two human leases, which paused the agent and put 0-fps seconds into the samples: 17 (0–28) and
29 (0–31).

**Packet → frame delay.** 40 walks at `prt_fild08 170,375`. Non-detections count as >1.5 s; p50 is
from `measure_delay.py`, and p75+ is nearest-rank over all 40.

| FreeRDP | Codec | Time | Matched | p50 | p75 | p90 | p95 |
|---|---|---|---|---|---|---|---|
| 3.15 | progressive | 20:44 (a human lease touched 2 trials) | 35/40 | 242 | 1007 | >1500 | >1500 |
| 3.15 | AVCthin | 20:41 | 35/40 | 195 | 778 | >1500 | >1500 |
| **3.32.1** | progressive | 22:06 | **39/40** | **119** | **139** | **151** | **157** |
| **3.32.1** | AVCthin | 22:19 | **39/40** | **118** | **125** | **131** | **136** |

Click-sent → server-packet p50 is 178 ms (progressive) and 180 ms (AVCthin). That leg is not the
display path.

**Client threads and idle cost.** The GM is standing, the game visible, and only the idle animation
moves.

| FreeRDP / codec | xfreerdp threads | Idle cores, prt_fild08 (180 s) | Idle cores, new_4-1 53,111 (120 s) | Windows idle in/out fps, encode ms |
|---|---|---|---|---|
| 3.15 progressive | **329** | 0.08 | 1.35 | not measured |
| 3.32.1 progressive | **26** | 0.43 | 0.29 | 30.0/30.0, 1.3 ms; 30.0/30.0, 2.0 ms |
| 3.32.1 AVCthin | 26 | 0.79 | 0.77 | 30.0/30.0, 18.0 ms; 30.0/30.0, 17.8 ms |

**The quant stack does not notice the codec.** From the pressure sampler over the rotation windows:
- quant-postgres `cpu_some` is 0.37–0.49 % (progressive) vs 0.16–0.17 % (AVCthin), against
  0.27–0.31 % idle;
- crypto-engine (the live capture tonight) sits at 0.22–0.29 % in every window.

**Fidelity**, a quick check only: the same static scene, AVCthin frame vs progressive frame.
- The Basic Information panel (HP/SP text) is PSNR **37.8 dB**, and the skill bar 39.5 dB. The text is
  legible in both.
- Chat and minimap come out at 28.9 and 30.4 dB, but their content may have changed between the two
  shots (unverified).
- This is not a fidelity study. Progressive refines static content toward lossless; AVC does not.

**Decision: keep FreeRDP 3.32.1, and keep `RDP_GFX=progressive`** (`.env` unchanged).
- Delivery ties at the 30 fps cap with zero skips. The 3.15 ceiling (6–12 fps at ~6.5 cores, 17–20
  skips/s) was FreeRDP 3.15's client path, as suspected: 329 threads vs 26.
- Progressive keeps near-lossless static fidelity for the perception work, and costs less when
  idle, which is most of the time.
- Its motion cost (~4.6 cores, under the 8-core cap) is invisible to the quant stack.
- **`AVCthin` is the alternative, one keyword away** (`scripts/rdp_reconnect.sh AVCthin`): ~5× cheaper
  in motion (0.95 cores) with a slightly tighter tail (p95 136 vs 157 ms). Prefer it for long
  motion-heavy sessions or if the CPU budget tightens.

**Regression checks on 3.32.1**
- One client process. The certificate pin holds: it connected under `/cert:deny,fingerprint`.
- The same Windows session (ID 2) came back with the game still running.
- **Keyboard:** GM commands were typed and answered by the server.
- **Clicks:** 39/40 walks moved the character, twice.
- **`\\tsclient\transfer`:** visible from the session (`Test-Path` True).
- **Auto-reconnect after TERM:** exit 145, then reconnect in 2 s, twice.
- **Exit-code enum:** identical to 3.15 up to 159. 3.32 adds 160 `CONNECT_TARGET_BOOTING` and 161
  `HYBRID_REQUIRED_BY_SERVER`, which fall into rdp-loop's backoff branch.
- **⚠ The clipboard direction filter changed.** It is recorded as ADR-0004 amendment (b):
  - A Windows-side copy now makes xfreerdp **claim** the X CLIPBOARD, with no data targets.
  - The backend watchdog cleared it 3 times for one copy.
  - Content still cannot flow Windows → X: 3.32.1 refuses the data request client-side.
- **Not verified:** a live ⌘V paste through the console (ADR-0004 T1) on 3.32. It needs Batt.

**What it unlocks.** Delivery now sits at dgVoodoo's FPSLimit 30 outdoors. The "only after delivery
reaches ~30 fps" item below (DWMFRAMEINTERVAL 15 + FPSLimit 60) is now actionable. It is not done.

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
