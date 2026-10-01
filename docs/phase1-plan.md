---
doc_type: design
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Batt approves (or amends) this plan and ADR-0007, and decides the open questions at the end (OpenKore table license, GM test account, sniffer image timing). Nothing is built until then.
---

# Phase 1 plan: packet ground truth from rAthena, on the host clock

**Goal.** Passive ground truth from our own rAthena traffic, aligned to screen frames on one host clock:
- who and what is where;
- movement;
- HP, SP and weight;
- chat.

It feeds Phase 2 (projection and auto-labeling) and evaluation.

**Principle 2 holds throughout.** Packet data never reaches the live decision loop:
- vision can't read it;
- the agent channel can't carry it;
- nothing in the agent path imports it.

Sources, all read on 2026-09-30:
- rAthena at the pinned `e985006171d2eb320ee512a653f4c83aea3d81b6` (paths relative to `src/`);
- OpenKore master `51de1ddfc4449ae5217f6886de702f87ca934030`;
- Linux, libpcap and PSI documentation.

Line numbers refer to those revisions.

## 1. Capture

**Where.**
- The `sniffer` service (already in `compose.yaml`, profile `sniffer`) runs in rathena's network
  namespace (`network_mode: service:rathena`).
- Capabilities: **CAP_NET_RAW only**. Opening an AF_PACKET socket, promiscuous mode included, checks
  only that capability; NET_ADMIN is not needed.
- It sees the client ↔ server TCP from inside the server's namespace.
- Passive only: it never sends, and never injects.

**Filter.** A kernel BPF filter on the socket:

    host 192.168.1.169 and tcp and (port 6900 or port 6121 or port 5121)

- The client IP is required. The same ports also carry inter-server traffic: char→login 0x2710 on
  6900, map→char 0x2af8 on 6121. Filtering by client IP drops it.
- The filter bytecode is generated with `tcpdump -dd` and committed as a constant (with a test).
- Python doesn't expose `SO_ATTACH_FILTER`/`SO_TIMESTAMPNS`; the constants are 26 and 35 on x86-64.

**Timestamps: kernel stamp + a realtime↔monotonic mapping** (chosen).
- Kernel packet timestamps (`SO_TIMESTAMPNS`, pcap `host`) are **CLOCK_REALTIME**. No libpcap timestamp
  type is monotonic on Linux, and no socket option selects a monotonic software clock.
- The capture keeps the kernel stamp: taken at receive, it doesn't suffer userspace scheduling. Once a
  second it records a paired sample `m1 = mono, r = real, m2 = mono`, giving
  `offset = r − (m1 + m2)/2`.
- `realtime − monotonic` only changes when the clock is **stepped**: NTP slewing adjusts both clocks'
  rate together. So between samples the mapping error is the pairing read time, which is sub-µs. A
  jump in `offset` between consecutive samples marks a step, and packets are mapped with the segment
  they fall in.
- Rejected: stamping in userspace with `clock_gettime(CLOCK_MONOTONIC)` after `recv`. The error is the
  network-stack and scheduling latency: tens of µs when idle, **milliseconds under load**, and up to a
  whole 100 ms CFS period if the container is ever CPU-capped.
- Containers share the host's CLOCK_MONOTONIC (no time namespace), so packet `t_mono_ns` is directly
  comparable with frame `t_mono_ns` from the backend.

**Bonus: the server tick is the same clock.**
- rAthena's `gettick()` is `clock_gettime(CLOCK_MONOTONIC)` in ms when `HAVE_MONOTONIC_CLOCK` is defined
  (`common/timer.cpp:147-167`). `configure.ac:1183-1206` defines it on Linux.
- Tick fields on the wire (`moveStartTime`, `ZC_NOTIFY_TIME`) are that value truncated to `uint32`
  (`map/clif.cpp:64-66`).
- So the server's movement start times map onto host monotonic ms exactly, modulo 2³². **To confirm
  live** in step 1 of the build: compare a `ZC_NOTIFY_TIME` (0x007f) tick with the capture's
  monotonic stamp.

## 2. Storage (disk rules: few large files, never one file per packet)

- **Raw:** pcapng, rotated hourly or at 256 MB.
  - Each file holds a custom block (PEN option, copyable) with the mapping samples, plus a small
    sidecar `*.map.jsonl`.
- **Credentials:** CA_LOGIN (0x0064) carries the password in plain text (24 bytes at offset 30,
  `common/packets.hpp:119-126`). **The capture zeroes those bytes before anything is written.**
  - The char server's auth codes and the map login's auth code are session tokens. They are kept (they
    expire) but never shown in the console.
- **Where:** a NEW named volume `captures`, mounted read-write only by `sniffer` and read-only by
  `backend`. **Not `./data`**, because `vision` mounts `./data` (`compose.yaml:204`). `.gitignore`
  already covers `*.pcap*`.
- **Size:** one client is a few to a few hundred packets/s, mostly small.
  - Worst case at 300 packets/s with full payloads: ~170 MB/h of pcapng.
  - Typical play is far less (to be measured in step 1).
  - Decoded events: hourly `events-*.jsonl.zst` shards, a few MB/h.
- **Retention:** 7 days or 20 GB, whichever comes first. The oldest files are deleted by the sniffer
  itself (one deletion per rotated hour, not a sweep).
- No pyarrow and no Parquet in the images. Parquet can come later, offline on the host.

## 3. Decoder: `packages/poring_packets`

A new uv-workspace package: mypy `--strict`, pure Python, pydantic only. Wiring: workspace members,
sources, ruff `known-first-party`, mypy `files`, pytest `testpaths`, and the dev-overlay mount.

**TCP reassembly** per 4-tuple:
- sequence-number ordering, retransmit de-dup, a bounded out-of-order window, FIN/RST;
- one stream per direction.

**RO framing:** a `u16` packet ID, then either a fixed length or `-1` (variable: a `u16` length at
offset 2, 4..32768; `map/clif.cpp:25757-25772`).

**Length tables (generated, never hand-edited).**
- **Client→server:** from rAthena's own `packet_db`.
  - `map/clif_packetdb.hpp` + `map/clif_shuffle.hpp:4723-4761`, replayed by `packetdb_readdb()`,
    last write wins.
  - A cpp pass alone leaves 130 IDs and 112 lengths symbolic (`HEADER_*`, `sizeof`). So the table is
    dumped from a build: a tiny dumper compiled in the rathena build tmpfs with
    `--enable-packetver=20211103`.
  - It becomes a JSON artifact with the rAthena SHA recorded.
  - Char and login are `PacketDatabase<T>` (`common/packets.hpp:665-752`), dumped the same way.
- **Server→client:** rAthena has no S→C length table; its S→C packets are structs sent with
  `sizeof`.
  - The table comes from the client's own lengths: OpenKore `tables/kRO/Ragexe_2021_11_03/recvpackets.txt`
    (1584 entries), pinned to a commit.
  - It's cross-checked against rAthena's struct sizes for every packet the decoder interprets. All
    first-slice packets agree.
  - **License:** OpenKore is GPL. The table is facts (ID→length), but see the open questions.
- A test regenerates both tables and fails on drift, like `test_committed_schema_matches_models`.

**Obfuscation: confirmed no-op.**
- For PACKETVER > 20180307 the keys are `0,0,0` (`map/clif_obfuscation.hpp:421-422`).
- The C→S decryption `cmd ^ ((key >> 16) & 0x7FFF)` with key updates `(0*0+0)` stays 0
  (`map/clif.cpp:25713-25725, 25785`).
- S→C and the char and login servers never obfuscate.
- The decoder asserts that `src/custom/defines_pre.hpp` sets no `PACKET_OBFUSCATION_KEY*` (build-time
  check).

**Never silent.**
- Unknown IDs are counted per stream and ID.
- A stream whose framing breaks is marked **desynced** and counted. Resync: scan for an offset where N
  consecutive packets frame correctly.
- The bytes skipped are counted.
- Counters appear in the timeline panel and in each shard's footer.

**Traps found in the source.**
- The char server sends **4 raw header-less bytes** (the account ID) right after CH_ENTER
  (`char/char_clif.cpp:850-853`).
- `ZC_NOTIFY_MOVE` 0x0086 exists in the client table but rAthena never sends it.
- CZ_ENTER2 0x0436: rAthena reads the client tick at offset 14 and OpenKore sends it at 18. The decoder
  reads both and reports which one the real client uses.

## 4. The first slice

**Verified for PACKETVER RE 20211103.** Every length matches both rAthena and OpenKore's table.

| Area | Packets (dir: C = client→server, S = server→client) |
|---|---|
| Login | CA_LOGIN 0x0064 (C, 55; password zeroed), AC_ACCEPT_LOGIN 0x0ac4 (S, var: 64 + 160·n), AC_REFUSE_LOGIN 0x083e (S, 26) |
| Char | CH_ENTER 0x0065 (C, 17), 4 raw bytes (S), HC_ACCEPT_ENTER2 0x082d (S, 29), HC_ACCEPT_ENTER 0x006b (S, var 27 + 175·n), HC_ACK_CHARINFO_PER_PAGE 0x0b72 (S, var 4 + 175·n), CH_SELECT_CHAR 0x0066 (C, 3), HC_NOTIFY_ZONESVR **0x0ac5** (S, 156: map name + IP/port) |
| Map entry | CZ_ENTER2 0x0436 (C, 23), ZC_AID 0x0283 (S, 6), ZC_ACCEPT_ENTER **0x02eb** (S, 13: start tick + position), CZ_NOTIFY_ACTORINIT 0x007d (C, 2) |
| Time | CZ_REQUEST_TIME2 **0x0360** (C, 6), ZC_NOTIFY_TIME 0x007f (S, 6) |
| Own movement | CZ_REQUEST_MOVE2 **0x035f** (C, 5: 3-byte position), ZC_NOTIFY_PLAYERMOVE 0x0087 (S, 12: tick + 6-byte MoveData), ZC_STOPMOVE 0x0088 (S, 10) |
| Entities | ZC_NOTIFY_MOVEENTRY11 0x09fd (S, 114), ZC_NOTIFY_NEWENTRY11 0x09fe (S, 107), ZC_NOTIFY_STANDENTRY11 0x09ff (S, 108): objecttype @4, speed @13, (moveStartTime @37, MoveData @67 in 0x09fd), name @90/…; ZC_NOTIFY_VANISH 0x0080 (S, 7) |
| Map change | ZC_NPCACK_MAPMOVE 0x0091 (S, 22), ZC_NPCACK_SERVERMOVE **0x0ac7** (S, 156) |
| Stats | ZC_PAR_CHANGE 0x00b0 (S, 8), ZC_LONGPAR_CHANGE 0x00b1 (S, 8), ZC_LONGLONGPAR_CHANGE 0x0acb (S, 12); vars SPEED 0, HP 5, MAXHP 6, SP 7, MAXSP 8, WEIGHT 24, MAXWEIGHT 25 (`map/map.hpp:499-502`); party HP 0x080e (S, 14) |
| Chat | CZ_REQUEST_CHAT 0x00f3 (C), ZC_NOTIFY_CHAT 0x008d (S, GID + "Name : msg"), ZC_NOTIFY_PLAYERCHAT 0x008e (S, own echo; also system text without a name), CZ_WHISPER 0x0096 (C), ZC_WHISPER02 **0x09de** (S), ZC_ACK_WHISPER02 **0x09df** (S, 7), ZC_BROADCAST 0x009a / ZC_BROADCAST2 0x01c3 (S), party 0x0108 (C) / 0x0109 (S), guild 0x017e (C) / 0x017f (S), ZC_NPC_CHAT 0x02c1 (S) |

**Chat text.**
- It is raw bytes (cp874 in this lab), never transcoded by the server.
- Server strings end in NUL; the client sends none (PACKETVER ≥ 20151001). The decoder uses the packet
  length and strips trailing NULs.
- "Name : msg" is split on `" : "` only when it's present. Broadcasts may carry a `blue`/`ssss` prefix.
- Client chat must start with `<own name> : ` or rAthena kicks the player (`map/clif.cpp:10487-10511`).
  That is useful as a self-check.

## 5. World state

- **Map:** from HC_NOTIFY_ZONESVR, ZC_NPCACK_MAPMOVE and ZC_NPCACK_SERVERMOVE.
- **Own character:** AID/CID (CZ_ENTER2, ZC_AID), name and speed from the character list; position from
  ZC_ACCEPT_ENTER and 0x0087.
- **Entities:** keyed by GID, from 0x09fd/0x09fe/0x09ff (type, class, speed, position/MoveData, name).
  They are removed on 0x0080 and stopped on 0x0088.
- **Movement interpolation:**
  - MoveData unpacks with `RBUFPOS2` (`map/clif.cpp:214-240`):
    - `x0=(p0<<2)|(p1>>6)`, `y0=((p1&0x3f)<<4)|(p2>>4)`;
    - `x1=((p2&0x0f)<<6)|(p3>>2)`, `y1=((p3&0x03)<<8)|p4`;
    - sub-cell nibbles in p5 (always 8 for own movement).
  - Each step takes `speed` ms, ×14/10 when diagonal (`map/unit.cpp:226-238`; `path.hpp:11-12`).
    Default speed is 150.
  - The start is `moveStartTime`, a server tick, and so host monotonic (section 1).
- **Path:** the packet carries only start and end cells.
  - Without GAT map data the decoder uses rAthena's own fallback, "diagonal first, then straight"
    (`map/path.cpp:292-325`). It is exact on open ground; around obstacles the error is bounded by
    the detour.
  - Later: A* with the map's GAT (Manhattan×10 heuristic, `map/path.cpp:337-407`), which needs the GAT
    files from the client data (a separate decision).
- Other units' walks are re-sent every cell for 1 s after they take damage (`map/unit.cpp:241-245`).
  The state machine treats a re-send as an update, not a new walk.

## 6. Events and the live feed

- **Event models** (Pydantic, in `poring_packets.events`), each with `t_mono_ns` (the mapped capture
  time), `stream`, `dir`, `packet_id`, a name, and decoded fields:
  - `LoginOk`, `CharSelected`, `MapEnter`, `MapChange`, `SelfMove`, `EntityAppear`, `EntityMove`,
    `EntityVanish`, `EntityStop`, `StatChange`, `Chat{kind: public/party/guild/whisper/broadcast/npc}`,
    `TimeSync`, `Unknown`, `Desync`.
  - Their JSON Schema is generated like the existing protocol and committed.
- **Sniffer → backend ingest.**
  - A dedicated route, `/ingest/packets`, on the backend's **internal** listener, accepted only from
    rathena's pinned IP. The sniffer shares rathena's namespace, and rathena's IP is pinned in
    `compose.yaml`.
  - It is NOT `/internal/agent`: the sniffer can reach `:8001`, and that route would make it the BOT.
  - One-way: the ingest socket sends nothing back except acks and drop counts.
- **Viewer feed:** `/ws/packets` on the public listener `:8000`, its own socket with its own bounded
  outbox. Not the stream's 64-deep control deque, which would evict Status and ErrorReply.
- **The ADR-0005 gap, and why this plan doesn't widen it** (ADR-0007). Today vision could reach any
  `:8000` socket without an Origin. `/ws/packets` refuses:
  1. any connection that arrived on the internal port (`scope["server"]`);
  2. **any peer inside the compose subnet** `10.210.96.0/24`, where vision lives;
  3. a missing browser Origin (weak on its own, but layered).
  Also:
  - `captures` is not mounted in vision;
  - vision's image doesn't install `poring_packets`;
  - `test_protocol` reachability makes sure no agent-side schema (`agent_to_backend`, `input_event`,
    and now `backend_to_agent`) can reach any `Packet*` model;
  - `test_guards` greps vision's sources for `poring_packets`, `/ws/packets` and `captures`.
- **Console:** a "Packet timeline" `<details>` panel next to Paste/Files, showing:
  - the event list (filters per kind, pause);
  - the world-state summary (map, own position, entity count, HP/SP);
  - the counters (unknown / desync).
  The logic lives in `src/lib/packets.ts` with `node --test` tests. Read-only: it sends nothing.

## 7. Validation against ground truth

| Check | Method | Pass |
|---|---|---|
| Chat | Decoded `Chat` bytes vs `chatlog` `HEX(message)` (VARBINARY, cp874) for the same line | byte-identical, 100 % of lines in a session |
| Own position | Interpolated position at a save vs `char.last_x/last_y` (saved on map change and logout); plus `@where` with a **GM test account** (needs Batt's OK) | exact cell at rest |
| HP/SP | `StatChange` vs the `char.hp`/`sp` rows after a save | equal |
| Entities | Entity count and positions on a quiet test map vs GM `@mobsearch` / `@who` output | counts equal; cells equal at rest |
| Clocks | `ZC_NOTIFY_TIME` tick vs capture monotonic ms (section 1) | difference within a few ms and stable (confirms `gettick` = CLOCK_MONOTONIC) |
| Packet → frame offset | Own 0x0087 capture time vs the first frame where the character sprite starts moving (XDamage timestamps, as in `latency_probe.py`) | reported as a **distribution** (expected ≈ the RDP leg of ~60–100 ms plus render and jitter), and used as the label-alignment prior for Phase 2 |

## 8. Build, images and tests

- **No image build is needed to start.** A dev-overlay `sniffer` runs the existing
  `poring-lab/backend:local` image (Python 3.12, pydantic, websockets) with:
  - `packages/poring_packets/src` mounted read-only;
  - `network_mode: service:rathena`, `cap_add: [NET_RAW]`;
  - the `captures` volume.
  Caveat: after rathena is recreated, the sniffer must be `--force-recreate`d, because it stays
  attached to the old namespace.
- **Later:** a dedicated slim `poring-lab/sniffer` image (debian slim + python + the package, a few
  hundred files), built through `guarded_build.py` with the tolerant guard. Batt picks the window.
- **The C→S table dump** needs one extra compile step inside the existing rathena build tmpfs (no new
  image). Alternatively, gdb on a running server.
- **Tests** (pytest, mypy strict):
  - framing on synthetic streams (split, merged and interleaved segments, retransmits, out of order);
  - RBUFPOS2/RBUFPOS vectors from rAthena's macros;
  - cp874 chat;
  - unknown-ID and desync counters;
  - the credential-zeroing test on a synthetic 0x0064;
  - clock mapping with a simulated step;
  - table-drift tests;
  - backend: `/ws/packets` refused from `:8001`, from the compose subnet, and without an Origin;
    `/ingest/packets` refused from any IP but rathena's;
  - protocol reachability;
  - guard greps;
  - frontend `packets.test.ts`.

## 9. ADR

[ADR-0007](adr/0007-packet-ground-truth-channel.md) (PROPOSED) records:
- the new viewer channel and ingest route;
- the `captures` volume;
- the principle-2 enforcement.

## Order of work (after approval)

1. The `poring_packets` skeleton, the tables and the framing, all tested offline on synthetic streams.
2. The sniffer (dev overlay).
   - First capture of a real session (Batt plays).
   - Confirm the clocks.
   - Measure the real packet rate and size.
3. World state and interpolation. Validate against the DB, chatlog and GM queries.
4. Ingest + `/ws/packets` + the console panel, with the guards and tests.
5. The packet → frame offset distribution. That completes Phase 1's exit gate ("decoded state matches
   the server on N sessions").

## Open questions for Batt

1. **The OpenKore table license.** Commit a generated ID→length JSON derived from OpenKore's GPL
   `recvpackets.txt`, with provenance? Or fetch it at build time from a pinned commit and never commit
   it?
2. **A GM test account** (group 99) for `@where` / `@mobsearch` / `@who` validation, with credentials
   in `.env` only.
3. **When to build the slim sniffer image:** now with the tolerant guard, or after the disk split? ➡️ Decided:
   dev-overlay sniffer; there is no disk split (Batt, 2026-10-01), so the slim image waits for a guarded build window. The
   dev-overlay path needs no build.
4. **The map GAT files** for exact pathing (A*): read from the client's GRF (data only, local, never
   committed). Now or later?
