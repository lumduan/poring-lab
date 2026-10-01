---
doc_type: review
hypothesis: null
status: GO
role: null
verdict_date: 2026-10-01
verdict_ticket: null
supersedes: null
related: []
next_action: Phase 2 builds on these events (GAT for exact paths). After any decoder change, re-run the entity check and re-decode the banked pcapng (python -m poring_packets.replay).
---

# Phase 1 validation: packet ground truth against the server's own truth

Status: **GO for the first slice**, 2026-10-01. Scope: ADR-0007, as planned in
[phase1-plan.md](phase1-plan.md).
- Everything below was measured live on our rAthena (PACKETVER 20211103 RE, pre-renewal).
- Sources: the sniffer (`poring_packets`, dev overlay) and the agent's own accounts.
- Every GM action came from the validation account (group 20), so its events carry
  `validation_account`, and the commands plus their replies carry `gm_command`.

## Summary

| Check | Method | Result |
|---|---|---|
| Clock: `gettick()` vs host CLOCK_MONOTONIC | capture mono ms mod 2³² − server tick in ZC_NOTIFY_TIME, ZC_NOTIFY_PLAYERMOVE, ZC_ACCEPT_ENTER | **n = 406: 0 ms in 388, 1 ms in 18**; nothing else. `time_sync` arrives every 12.0 s |
| Decode health | the whole capture, 04:20–06:50 UTC, five accounts' sessions | **1,078 events, 0 unknown packet ids, 0 desyncs**. 46 walk requests, 46 walk replies |
| Position | `@where <self>` reply vs the decoded `char_selected` + `map_enter` vs `char.last_map/x/y` | **new_1-1 (53,111) in all three**; prt_fild08 (170,375) decoded = `char` after logout |
| Chat, ASCII | CZ_GLOBAL_MESSAGE bytes vs `chatlog.message` | **byte-exact** (`506F72…31333330`) |
| Chat, Thai | the same, typed via Kedmanee | **byte-exact** (`CAC7D1CAB4D5`, decoded "สวัสดี", cp874) |
| HP | the last decoded `stat_change hp/max_hp` vs `char.hp/max_hp` after logout | **40/40 = 40/40** (no damage taken: a static check) |
| Entities | `@monster 1002 5` on prt_fild08, then `@mobsearch 1002` vs the packet world state at the search time | **count 5 = 5** in view (of 75 on the map); **5/5 within 1 cell** (4 exact) after walk interpolation; 5 distinct ids |
| Tags | every validation-session event | `validation_account` on all of them; `gm_command` on each command and its replies (2 s window) |
| Packet → frame delay | 40 click-to-walks; own 0x0087 capture time → first lab frame where >10 % of a scene band moved | **p50 150 / p95 585 / p99 999 ms** (39 matched, 1 unmatched); **p50 179** without the 6 implausible < 50 ms matches; click-sent → packet p50 171 ms (p95 177) |
| ➡️ Delay method SUPERSEDED 2026-10-01 | the row above used a frame-to-frame >10 % change, which detects later at higher delivered fps | re-measured with the post-hoc reference method in [h264-plan.md](h264-plan.md) "Arm A results": progressive p50 195 ms (non-detections counted as >1.5 s); the Phase 1 figures stay as history |

## Method notes and caveats

**Clock.**
- Every packet carrying a server tick was used:
  - `time_sync` (353 samples);
  - `self_move` (46);
  - `map_enter` (7).
- The difference is the time from `gettick()` in rAthena to the kernel's receive timestamp on the
  same host, in whole milliseconds. 0–1 ms confirms ADR-0007's premise: the server tick **is** the
  host's monotonic clock, so server ticks can be placed on the frame timeline with no fitting.

**Entities.**
- First run: `@mobsearch poring` printed only its header. In this rAthena build the name lookup
  resolves to a different mob id, so **use numeric ids** (`@mobsearch 1002`).
- The same run exposed a decoder bug: entities were keyed by the entry packet's GID field, which is
  the **char_id** (0 for every monster). All five Porings collapsed into one.
  - Fixed in `42e2d4d`: the identity is now the block id (AID @5), the id ZC_NOTIFY_VANISH uses.
  - A regression test pins it.
  - The raw pcapng from before the fix is intact, and `python -m poring_packets.replay` re-decodes
    it. Replaying the day's captures through the fixed decoder gave 1,227 events: the 5 Porings of
    the first run now have distinct ids (0 at gid 0), with 0 unknown and 0 desyncs. Validation
    sessions are tagged by account id, because the pcapng's login payloads are redacted.
- Comparing walk *destinations* matched 2/5. Interpolating each walk to the server tick at which
  `@mobsearch` ran gave 4 exact and 1 off by one.
  - The tick comes from the capture time, per the clock result.
  - The interpolation is `world.Walk.position_at`: diagonal first, step = speed, ×1.4 on the
    diagonal.
  - Paths around obstacles need GAT (Phase 2).

**Packet → frame delay.** What it measures:
- **Start:** our own ZC_NOTIFY_PLAYERMOVE leaving rathena (kernel timestamp, host clock).
- **End:** the first grab, inside the backend container (same clock), where >10 % of a scene band
  above the character changed by >24 levels. The camera follows the character, so a walk scrolls
  the whole band.

It therefore includes:
- the client receiving the packet and rendering (FPSLimit 30);
- RDP capture and encode on Windows (RemoteFX progressive, ~10 ms);
- the network;
- xfreerdp's decode, which is the bottleneck (21–26 skipped frames per second during motion);
- Xvfb and our grab.

Caveats:
- **Six matches arrived < 50 ms after the packet.** That is below the RDP leg alone (66–75 ms in
  Phase 0), so they are not responses to the walk. They are most likely late frames from the decode
  backlog, so they are reported both with and without them.
- **The long tail (p95 585, p99 999 ms) is the backlog itself.** Frames reach the lab at 4–8 fps
  during motion (`phase0-latency.md`); H.264 is the planned fix ([h264-plan.md](h264-plan.md)).
- **Improvement:** match on the scroll direction, not just the change magnitude.
- **Click → packet** (agent click sent → server reply leaving rathena; mux, XTest, RDP input,
  client, server): **p50 171 ms**, tightly bounded (159–212 ms).

**HP** is a static check: no damage was taken. A damage case (aggressive mob, or `@damage`, which is
not in group 20) is left for Phase 2's combat slice.

## Limitations found

1. **A sniffer restart loses session identity** for connections that are already open. Validation
   tagging binds at CA_LOGIN / CH_ENTER / CZ_ENTER2, so a mid-session restart leaves the open map
   connection untagged.
   - Mitigation today: relog the validation account after a sniffer restart.
   - Proper fix (later): persist the AID → session binding.
2. **`@mobsearch <name>` is unreliable here**; use numeric mob ids.
3. **Achievement and some system strings are Korean (EUC-KR) shown under code page 874**, so they
   render as Thai mojibake. This is client UI only; packets carry bytes, and the decoder reports
   cp874 plus `raw_hex`.

## Accounts used (variable names only)

- **`RATHENA_AGENT_USER` / `_PASSWORD` / `_CHAR`:** player, group 0. Recovery and measurement moves.
- **`RATHENA_GM_USER` / `_PASSWORD` / `_CHAR`:** group 20 "Validation" (`conf/import/groups.yml`).
  Every command is logged in `atcommandlog`, and every session is tagged `validation_account` by
  the sniffer.
- Batt's own test account (`RATHENA_TEST_*`) was not used by the agent.
