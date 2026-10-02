# Benchmark run 2026-10-02-rdp-d16fcc9cff64-v2-baseline

- SPEC v2, backend **rdp**, client {'name': 'xfreerdp', 'version': 'This is FreeRDP version 3.32.1 (3.32.1)', 'codec': 'progressive'}, config hash `d16fcc9cff64`
- 2026-10-02T13:23:02+0700 → 2026-10-02T13:34:25+0700; preflight {'lock_seq': 1, 'viewers': 1, 'mode': 'ASSIST'}

## Delivery and cost

| scene | fps median | p10 | p90 | lab cores (motion) | idle cores |
|---|---|---|---|---|---|
| outdoor | 23 | 20 | 27 | 5.41 | 0.47 |
| indoor | 13 | 5 | 19 | 4.96 | 0.04 |

## Latency (outdoor)

| metric | matched | p50 | p75 | p90 | p95 | p99 |
|---|---|---|---|---|---|---|
| packet_to_frame_ms | 39/40 | 375.9 | 488.3 | 513.7 | 521.2 | >1500 |
| key_to_paint_ms | 40/40 | 101.1 | 108.5 | 110 | 114.1 | 119.3 |

## Fidelity vs the lossless reference (outdoor)

| crop | PSNR dB | SSIM |
|---|---|---|
| hp_sp_panel | inf | 1 |
| skill_bar | inf | 1 |
| chat | 40.18 | 0.9839 |
