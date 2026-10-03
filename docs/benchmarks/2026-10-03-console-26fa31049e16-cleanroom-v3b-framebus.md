# Benchmark run 2026-10-03-console-26fa31049e16-cleanroom-v3b-framebus

- SPEC v2, backend **console**, client {'name': 's2spike', 'version': 'moonlight-common-c 8599b6042a4ba27749b0f94134dd614b4328a9bc', 'codec': 'H.264', 'paint': 'bus', 'version_recorded': 'moonlight-common-c cat: /opt/s2spike/MLCC_SHA: No such file or directory', 'version_note': "corrected 2026-10-03 18:45: bench.run_config read /opt/s2spike/MLCC_SHA; the image keeps it at /opt/s2spike/lib/MLCC_SHA (fixed in bench.py). config_hash was computed over the recorded string and is kept as the run's identifier."}, config hash `26fa31049e16`
- 2026-10-03T17:52:50+0700 → 2026-10-03T18:04:15+0700; preflight {'lock_seq': 68, 'viewers': 0, 'mode': 'ASSIST'}

## Delivery and cost

| scene | fps median | p10 | p90 | lab cores (motion) | idle cores |
|---|---|---|---|---|---|
| outdoor | 30 | 26 | 30 | 1.03 | 0.78 |
| indoor | 16 | 11 | 19 | 0.98 | 0.75 |

## Latency (outdoor)

| metric | matched | p50 | p75 | p90 | p95 | p99 |
|---|---|---|---|---|---|---|
| packet_to_frame_ms | 39/40 | 113.9 | 131.5 | 214.4 | 268.3 | >1500 |
| key_to_paint_ms | 40/40 | 121 | 132.6 | 257.4 | 277.1 | 304.6 |

## Fidelity vs the lossless reference (outdoor)

| crop | PSNR dB | SSIM |
|---|---|---|
| hp_sp_panel | 37.85 | 0.9961 |
| skill_bar | 38.36 | 0.9893 |
| chat | 27.49 | 0.9377 |
