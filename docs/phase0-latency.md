---
doc_type: design
hypothesis: null
status: ACCUMULATING
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: The RDP delivery ceiling is client-side (FreeRDP decode; server skips 'insufficient client resources'). After the disk split, A/B AVC/H.264 hardware encode + a newer FreeRDP; then the console A/B (q70, paint=raf) and Batt's Windows App glass-to-glass.
---

# Phase 0: web-console latency, measured and reduced

Target: feel close to Microsoft's Windows App (the native RDP client on the Mac). Status and history:
[ROADMAP](ROADMAP.md) Phase 0. Results table: [Results](#results) (filled in per run).

## The pipeline and its segments

```
 browser event --L1--> XTest --L2--> pixels in Xvfb --L3--> grab --L4--> sent --net--> browser
                 WS+mux         RDP round trip            capture      encode      recv -> decode -> paint
                                (xfreerdp -> Windows -> app -> RDP update -> xfreerdp)         (L5)
```

| Segment | What it is | How it is measured |
|---|---|---|
| L1 | browser/script event → mux decision → XTest synced | `t_mono_ns` of the input (the event's own time) vs `t_injected` (after the injector's XSync), `/debug/latency` |
| L2 | XTest → first changed pixel in Xvfb | the probe's own XDamage (raw rectangles) on the target box + a pixel diff |
| L3 | change in Xvfb → the grab that contains it | XDamage receipt time vs the frame's `t_capture_ns` |
| L4 | capture → JPEG encoded → sent; sent → received | frame metadata; the probe's loopback receive; the browser's receive via the ping offset |
| L5 | browser receive → decoded → painted | the console's `ViewerTiming` reports (tab clock) |

**Clocks.** The probe, the backend and Xvfb share the host's `CLOCK_MONOTONIC`. A browser tab has its
own clock; it maps onto ours with Cristian's algorithm on the input socket's ping/pong (the sample
with the smallest round trip), so every browser→backend number carries an uncertainty of half that
round trip (shown next to it). Segments within the tab (decode, paint) are exact.

**The toggle.** The plan was a pointer **move** (never a click or a key) between two points on empty
floor in RO. RO draws its own cursor sprite, so the move would show up in the pixels as the real
in-game motion-to-photon.

At the time, the RO client was logged in to the community server. Under
[ADR-0006](adr/0006-sanctioned-test-environments.md) no agent automation runs there; Batt permitted
only these moves, while watching. He closed RO before the runs, so **the measured toggle is `Ctrl+A`
/ `→` in Notepad on the Windows desktop**. `latency_probe.py cursor --a … --b …` remains available
for the RO-cursor variant on rAthena.

## Tools (no restart needed between changes)

- `scripts/latency_probe.py` (runs inside the backend container):
  - `passive`: L3/L4/L5 and the RO render rate, no input at all;
  - `cursor`: pointer moves A↔B, L1–L5 per trial;
  - `jpeg-bench`;
  - `tune`: switch knobs.
- Runtime knobs, `POST /debug/stream-tuning` (loopback only):

  | Knob | Values | Original |
  |---|---|---|
  | `capture` | `fixed` / `damage` | `fixed` |
  | `fps` | number | 30 |
  | `max_fps` | number | – |
  | `jpeg_quality` | number | 80 |
  | `move_interval_ms` | a number, or `"raf"` | `"raf"` |
  | `paint` | `decode` / `raf` | `decode` |

  The console knobs reach open tabs through Status within a second.
- RDP leg A/B: the desktop reads `/dev/shm/rdp-override` (whitelisted `RDP_GFX`, `RDP_NETWORK`,
  `RDP_FRAME_ACK`, `RDP_GDI`) before each connect. A variant = write it, then TERM xfreerdp3; the
  loop reconnects in ~2 s.

## Results (2026-09-30)

**Setup.** Windows desktop, a maximised Notepad with 28 lines. The toggle is `Ctrl+A` (select all)
then `→` (deselect); the watch box is inside the text; N = 60 per configuration (40 for RDP variants).
p50/p95 in ms, host clock. RO had been closed by Batt (13:17), so the in-game cursor test and the RO
render rate were not run.

### Per change (one at a time; each row keeps the best so far)

| # | Configuration | L1 inject | L2 RDP leg | L3 capture wait | encode | send | **key → frame sent** | Verdict |
|---|---|---|---|---|---|---|---|---|
| 0 | fixed 30 fps, q80, paint on decode (**before**) | 4.0 / 8.7 | 72.4 / 86.7 | 23.5 / 31.3 | 12.5 / 17.3 | 1.4 / 2.0 | **109.4 / 135.4** | baseline |
| 1 | **damage capture, max 60 fps** | 3.2 / 5.7 | 69.5 / 88.8 | **4.8 / 22.0** | 12.8 / 16.7 | 0.7 / 0.9 | **96.9 / 114.2** | **kept**: −12.5 / −21.2 |
| 1′ | same, after R2 (the new defaults) | 3.4 / 5.2 | 66.5 / 86.4 | 5.0 / 18.3 | 12.5 / 18.6 | 1.4 / 2.8 | **91.3 / 110.1** | confirms |
| 2 | + JPEG q70 | 3.3 / 5.5 | 65.9 / 88.0 | 5.1 / 19.5 | 12.1 / 18.8 | – | 89.1 / 121.7 | not kept |
| 3 | + JPEG q60 | 3.1 / 4.5 | 69.6 / 93.0 | 5.0 / 19.9 | 12.4 / 17.1 | – | 92.8 / 126.9 | not kept |
| 4 | q70 + paint on rAF | – | 66.6 / 95.5 | 5.0 / 20.0 | 12.4 / 15.8 | – | 91.4 / 119.1 | not kept |
| 5 | move interval 8 / 4 ms | – | – | – | – | – | – | **not measured** |

Notes on the rows:
- **Rows 2–4 did not change the server side** beyond the RDP leg's noise. Their benefit is on the
  network and in the browser, which could not be measured then: Safari was a background tab, and
  hidden tabs stop decoding.
- **Row 5** needs real mouse use in a visible tab.

**Browser side, in one run with Safari visible** (row 1′ settings; offset uncertainty 2–9.5 ms in
those minutes):

| Browser segment | p50 | p95 |
|---|---|---|
| sent → received (Wi-Fi/LAN) | 14.9 | **100.1** |
| Safari decode | 13.5 | 47.5 |
| decode → painted | 0.0 | 1.0 |
| **key → painted in Safari** | **123.1** | **246.5** |

Browser L1, from Batt's own mouse moves (n = 5, indicative only): **30.8 / 73.4 ms**. That
includes the one-per-frame coalescing that the `move_interval_ms` knob removes.

### RDP leg (L2) per variant

N = 40. All runs were on fixed capture, so the capture mode doesn't differ between them.

| Variant | L2 p50 / p95 |
|---|---|
| autodetect (default, N = 60) | 73.8 / 88.9 |
| `/network:lan` | 70.7 / 88.9 |
| `/gfx:progressive` | 73.8 / 86.4 |
| `/gfx:RFX` | 75.7 / 92.9 |
| `/gfx:AVC420` | 74.6 / 89.3 |
| `/gfx:AVC444` | 74.5 / 95.3 |
| legacy `-gfx /bpp:32` | 72.8 / 89.2 |
| `frame-ack:off` | 71.5 / 84.3 |
| `/gdi:hw` | 68.0 / 86.0 |
| default again | 75.3 / 98.6 |

- **Caveat:** the progressive through legacy variants also carried `network=lan`, because the first
  version of the override loader let it stick (fixed since).
- **Run-to-run noise is about ±4 ms**; the same default measured 73.8 and then 75.3. No variant is
  meaningfully better, so the defaults stay.
- The distribution is a **~58 ms floor plus 0–33 ms of jitter** (58–90 ms). That is the Windows side:
  input → app redraw → DWM → the RDP server's ~30 fps graphics pacing. Windows App pays the same
  cost.

**JPEG at 1280×720, live frames** (encode is noisy on a loaded host):

| Quality | Frame size | Encode p50 |
|---|---|---|
| q60 | 173 KiB | 7.7 ms |
| q70 | 204 KiB | 8.1 ms |
| q80 | 252 KiB | 11.1 ms |
| q90 | 360 KiB | 9.0 ms |

At 30 fps, q80 is about **60 Mbit/s**. That makes the network tail above (p95 100 ms) the next
thing to attack.

### Where the time goes now (p50, key → Safari paint ≈ 123 ms)

```
L1 3 | L2 RDP leg (Windows side) 66 | L3 5 | encode 12 | send 1 | net 15 | decode 14 | paint 0
```

Windows App pays the ~66 ms L2 too, since it is the server's. Our extra is roughly
**L3 + encode + net + decode ≈ 45 ms at p50**, and far more at p95 (net and decode tails). So the
next steps are **smaller frames** and **no queueing**:
- q70, measured with a visible tab;
- frame-ack flow control (rank 1 below);
- H.264 (rank 3).

Not measured this run, with how to measure it:

| Item | How |
|---|---|
| RO render rate | `latency_probe.py passive` while RO runs |
| Browser-side effect of q70 / rAF paint / move interval | the knobs + `/health` `latency` with a visible tab |

## Game render vs RDP delivery, and CPU protection (2026-09-30, 1280×800)

**The game is not the bottleneck; RDP delivery to our FreeRDP client is.**
- The rAthena client renders at 60 fps (PresentMon) on the Intel UHD 630. Details are in
  [client/rathena-client.md](client/rathena-client.md), "Render performance".

**Method.** A 200 s camera rotation (a bot right-drag: full-scene motion, no game-state change).
- Host: frames reaching Xvfb (a passive counter on the game region, a change being >1 % of pixels
  differing by >24 levels), and the lab and quant cgroups every 1 s (`cpu.stat`, `cpu.pressure`,
  `io.pressure`).
- Windows: `typeperf` at 1 s over `\RemoteFX Graphics(*)\*`, `\RemoteFX Network(*)\*`, per-process
  CPU and GPU-engine counters. Nothing on Windows was changed.
- The CPU caps were applied live with `docker update --cpus` (no reconnect).
- Medians per arm.

| Desktop CPU arm | Frames reaching Xvfb (p10–p90) | Desktop cores used | RDP input fps | RDP output fps | Skipped: client | Skipped: server / network | Avg encode | Quant cpu.pressure (some, sum) | quant-postgres io full |
|---|---|---|---|---|---|---|---|---|---|
| idle (no motion) | 0 | 0.17 | 32.0 | 9.8 | 0 | 0 / 0 | 1 ms | 0.88 % | 4.58 % |
| unlimited | 7 (4–11) | 7.25 | 31.7 | 6.0 | 24.8/s | 0 / 0 | 10 ms | 0.47 % | 3.43 % |
| `cpus 8` | 8 (4–12) | 6.86 | 32.6 | 6.9 | 24.8/s | 0 / 0 | 10 ms | 0.67 % | 4.16 % |
| `cpus 6` | 5 (3–10) | 5.77 | 32.6 | 4.0 | 26.8/s | 0 / 0 | 12 ms | 0.74 % | 4.70 % |
| `cpus 4` | 3 (1–4) | 4.00 | 31.6 | 2.0 | 28.2/s | 0 / 0 | 9 ms | 0.44 % | 3.45 % |

**Where the ~6–17 fps ceiling comes from: the client (FreeRDP decode).**
- The server captures ~32 fps. It skips 25–28 of them per second with the counter "Frames Skipped/Second
  - **Insufficient Client Resources**". Server and network skips are 0.
- Encoding takes ~10 ms, well under the 33 ms budget. Windows uses ~4 % total CPU (TermService ~11 %
  of one core, dwm ~0). RTT is 1–5 ms.
- Capping xfreerdp's CPU lowers the output fps in step: 6.9, then 4.0, then 2.0. So the client's
  software decode, plus GDI into Xvfb, sets the rate through GFX frame acknowledgement.
- RdpCoreTS event 162: the client supports GFX 0xA0701 with "AVC available: 1", but the server picked
  **Initial profile 2** (RemoteFX progressive, not H.264).
- There is no event 170 (no AVC hardware encoder) and no VideoEncode GPU engine use.
- Transport is TCP only (event 135: "No UDP Packets Received").
- The earlier outdoor run (17 fps) vs this indoor run (7 fps) shows the decode cost depends on content.
- Next levers (Batt: deferred until after the disk split): H.264/AVC hardware encode on Windows plus
  AVC decode in a newer FreeRDP, or UDP transport.

**CPU protection (applied 2026-09-30 22:08, one desktop + backend recreate).**
- **desktop:** `cpu_shares: 64` (cgroup v2 `cpu.weight` = 12 with runc 1.3.5's quadratic mapping,
  vs 100 for every quant container) and `cpus: 8` (`cpu.max 800000 100000`).
  - 8 is the tightest cap with no measured fps loss.
  - 6 cores cost ~35 %.
  - 4 cores cost ~60 %, and they also throttle Xvfb, whose grab rate fell from ~95/s to 58/s.
- **backend:** `cpu_shares: 256` (weight 35), no ceiling. It uses ~1 core in motion (stream JPEG encode).
- **frontend-dev:** unchanged. It used ~0 CPU in motion.
- The quant containers' CPU pressure stayed below 1 % in every arm: 64 cores, so no real contention
  today. The weight is the protection for when there is contention.
- `test_guards.py::test_cpu_heavy_lab_services_yield_to_the_quant_stack` pins both.

## Rebuild-dependent options (not implemented), ranked

| Rank | Option | Expected gain | Effort | Disk / GPU cost |
|---|---|---|---|---|
| 1 | **Frame-ack flow control** (the console acks each painted frame; ≤ 1–2 frames in flight) | removes Wi-Fi/TCP queueing when frames are large (q80 ≈ 250 KiB) | small–medium, **no rebuild** | none |
| 2 | **Dirty tiles** (encode and send only changed 64×64 tiles) | big for desktop apps (a cursor move = a few tiles); small for full-screen RO animation | medium, **no rebuild** | none |
| 3 | **H.264 via NVENC** (backend) + browser hardware decode, low-latency: no B-frames, intra-refresh, small GOP | ~5–10× less bandwidth than JPEG at similar quality. Encode 2–4 ms. Browser hardware decode. Latency gain comes mostly from smaller frames on Wi-Fi | high: an image rebuild (FFmpeg/NVENC or PyNvVideoCodec, after the disk split), GPU passthrough into backend. **WebCodecs requires HTTPS** (secure context); over plain HTTP use MSE low-latency (Chrome/Safari) or WebRTC | NVENC is its own engine: Frigate (NVDEC decode + detector) and Ollama (CUDA) are not slowed beyond ~150 MB VRAM. Consumer drivers allow several concurrent NVENC sessions |
| 4 | PyTurboJPEG instead of simplejpeg | **none**: simplejpeg already is libjpeg-turbo (SIMD, `fastdct`, 4:2:0) | – | – |

**Not ours to change:** Windows limits the RDP graphics pipeline to about 30 fps by default (a
registry setting on the Windows side). Both Windows App and this console see that same cap. Changing
it means changing Windows, which is out of scope.

## A/B against Windows App (for Batt, glass-to-glass)

There is only one RDP session: the two clients can never be connected at once. **Always stop our
desktop first.** Otherwise Windows App kicks our session, `rdp-loop` backs off 10 minutes, and then it
kicks Windows App back.

1. **Prepare the content.**
   - In the Windows session, open Notepad with a few lines of text, maximised. The RO client works too
     (move the pointer over empty floor).
   - Set the console view to **1:1**.
   - In Windows App, set the display to **1280×720, no scaling** (PC settings → Display), so both show
     the same pixels.
2. **Our console first.**
   - Open `http://192.168.1.13:3000` and click the screen.
   - Film the Mac's keyboard and screen together with the phone in **slow motion (240 fps)**, both in
     frame.
   - Do 10 toggles: `Ctrl+A` (select all), then `→` (deselect). With RO: 10 fast pointer moves.
3. **Hand the session to Windows App.**

       cd ~/docker/poring-lab && scripts/dev.sh stop desktop

   Then connect Windows App to `192.168.1.169` as `batt` and repeat the same 10 toggles on camera.
4. **Hand it back.** Close the Windows App window (the Windows session stays), then:

       cd ~/docker/poring-lab && scripts/dev.sh start desktop
       curl -s http://192.168.1.13:8000/health | python3 -m json.tool | grep rdp_window_present

   It should read `true` within ~10 s.
5. **Count.** For each toggle, count the video frames from the key bottoming out, or the finger
   moving, to the first changed pixel on screen. Latency = frames × 4.17 ms. Compare the medians of
   the 10 trials, console vs Windows App.
6. **Keep the recordings.** They are the ground truth the measured segments should add up to (the
   display scan-out, ~8–16 ms, is visible only here).
