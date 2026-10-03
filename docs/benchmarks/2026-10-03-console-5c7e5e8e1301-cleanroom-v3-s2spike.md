# Benchmark run 2026-10-03-console-5c7e5e8e1301-cleanroom-v3-s2spike

- SPEC v2, backend **console**, client {'name': 'moonlight-qt', 'version': 'moonlight-qt 6.1.0', 'codec': 'H.264'}, config hash `5c7e5e8e1301`
- 2026-10-03T13:54:19+0700 → 2026-10-03T14:05:42+0700; preflight {'lock_seq': 51, 'viewers': 1, 'mode': 'ASSIST'}

## Delivery and cost

| scene | fps median | p10 | p90 | lab cores (motion) | idle cores |
|---|---|---|---|---|---|
| outdoor | 33 | 29 | 39 | 1.5 | 1.24 |
| indoor | 5 | 1 | 35 | 1.46 | 1.19 |

## Latency (outdoor)

| metric | matched | p50 | p75 | p90 | p95 | p99 |
|---|---|---|---|---|---|---|
| packet_to_frame_ms | 39/40 | 118.9 | 157.2 | 259.3 | 302.2 | >1500 |
| key_to_paint_ms | 40/40 | 137.6 | 166.9 | 307.8 | 350.3 | 435.7 |

## Fidelity vs the lossless reference (outdoor)

| crop | PSNR dB | SSIM |
|---|---|---|
| hp_sp_panel | 37.9 | 0.9964 |
| skill_bar | 38.3 | 0.9889 |
| chat | 27.5 | 0.937 |
