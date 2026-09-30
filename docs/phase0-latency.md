---
doc_type: design
hypothesis: null
status: ACCUMULATING
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Finish the RDP codec A/B and the browser-side (L5) numbers with Batt's console tab open; run Batt's glass-to-glass A/B against Windows App.
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

**The toggle.** RO is logged in on a live server, so the trial is a pointer **move** (never a click
or a key) between two points on empty floor: RO draws its own cursor sprite, so the move shows up in
the pixels. That makes L2 the real in-game motion-to-photon of the RDP leg (RDP round trip + RO's own
render cadence).

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

## Results

*(Filled in by the 2026-09-30 runs; see the report in the session log.)*

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
