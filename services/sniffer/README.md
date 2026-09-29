# sniffer (placeholder)

**Nothing is implemented.** This service exists so the wiring is in place: profile `sniffer`,
`network_mode: "service:rathena"` (it shares the game server's network namespace), `cap_add: [NET_RAW]`.

## Intent

Passive capture of rAthena traffic, used **only offline as ground truth** for evaluating perception —
for example, "the model detected 3 Porings on frame 1234; the server says 4 were on screen at that time".

## Rules (from the project's core principle)

- The agent perceives **pixels only** and acts **mouse/keyboard only**. Packet data must never reach
  the agent at decision time — no live feed from here into `vision`.
- Passive only: no injection, no modification, no replay against the server.
- Captures go to `data/captures/` (gitignored). **RO login packets carry credentials** — treat
  `*.pcap*` as secrets; `.gitignore` already excludes them everywhere.

## TODO (not in the scaffold)

- `tcpdump`/`dumpcap` ring buffer on ports 6900/6121/5121 → `data/captures/`.
- Offline decoder keyed by `PACKETVER`, aligned to frames via timestamps (host `CLOCK_MONOTONIC` vs
  capture timestamps needs a documented offset procedure).
