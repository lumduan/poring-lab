---
doc_type: design
hypothesis: null
status: ACCUMULATING
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: "After 17:00 ICT: the separate client (3b), the compatibility test (3c), sprite fidelity (3d), then the adoption cost (3e) and Batt's decision whether to switch."
---

# The Thai-data experiment: a separate client AND a separate rAthena

Batt, 2026-10-05: GO as an experiment, with BOTH the client and rAthena separated from the
current setup. Nothing of today's setup is modified; the rollback is today's setup. M4's re-run,
M5 and v1 training follow on whichever setup Batt chooses.

**Rule:** the Thai client's own exe is never used (WinLicense-protected, `requireAdministrator`, a
hardware-id DLL, a 2026 packet set beyond the pinned rAthena; static findings below). The same
2021-11-03 exe with its WARP patches runs the Thai DATA, against our own server only.

## 1. The separate rAthena: `rathena-th` (built 2026-10-05)

| Piece | What | Where |
|---|---|---|
| Server | the same image, SHA (e985006) and pre-renewal mode as `rathena`; its own database `db-th` (`db-th-data`) | compose profile `th` |
| One at a time | the same pinned IP 10.210.96.6 (the backend's only ingest peer) and LAN ports 6900/6121/5121: Docker refuses to run both. Concurrent instances would need a second LAN IP or new ports, which the sniffer's compiled BPF, the image HEALTHCHECK and smoke_test all assume | `test_guards.py` |
| Map cache | rAthena's own `mapcache` tool over the Thai maps, installed as `db/import/map_cache.dat` (read first; other maps fall back to the stock caches) | `scripts/gen_mapcache_th.py` → `data/mapcache-th/` (never committed) |
| Sniffer | `sniffer-th` in rathena-th's network namespace, its own `captures-th`; attests `server=lab-rathena-th` | ADR-0016 amendment |
| Interlock | `lab-rathena-th` in `config/environments.yaml`; the session signal requires the attested server to equal the environment id | `interlock.py` |
| Accounts | lab-only agent (group 0) and GM (group 20: @heal/@alive) in db-th; credentials in `.env` only (`RATHENA_TH_*`) | `rotate_secrets.py` |

**The map cache could not come from the GRF directly.** rAthena's grfio refuses this 2026 GRF
outright: a stored file name exceeds its buffer
(`...new_dragonbreath_water_11_clock.str is too long`). So our own reader extracts only the lab's
maps (`.gat` + `.rsw`) into `/dev/shm`. Three RSWs are MIXCRYPT and go through the host-local study
decoder. The tool then reads them as a `data_dir`. A second quirk of the pinned tool: in rebuild
mode it resets its header at the start of each list directory, so the list goes in `db/import/`.

### Walkability: the Thai maps vs today's (kRO data, the stock caches)

`scripts/mapcache_diff.py`, 2026-10-05 (cache sha256 `0a2c5726…b5c1`, reproducible):

| Map | Size | Walkable cells | Changed cells |
|---|---|---|---|
| prt_fild08 | 400×400 = | 89,999 = | **0** |
| prt_church | 200×200 = | 2,837 = | **0** |
| iz_dun00 | 400×400 = | 57,986 = | **0** |
| iz_dun01 | 300×300 = | 27,498 = | **0** |
| prontera | 312×392 = | 60,819 → 60,773 | 46 (all flip walkability) |
| izlude | **268×268 → 268×300** | 10,448 → 13,962 | a different (redesigned) map; 461 water cells |

The lab's four maps are identical, so walk paths, the Timeline and the v0 labels carry over
unchanged. Izlude is another map in the Thai data: rathena-th's pre-renewal NPC scripts and warps
assume the old layout, so izlude on rathena-th is suspect. It is only the route to iz_dun.

## 2. The official Thai endpoints: known-forbidden

The Thai GRF's own `data\clientinfo.xml` (recorded, never used): `thro-acc3.gnjoy.in.th:50001`
(49.229.28.13 on 2026-10-05), servicetype `thai`, servertype `primary`, version 24, langtype 5,
registration `http://roc.gnjoy.in.th`. They are in `config/environments.yaml` as
`official-ro-thai` (forbidden).

Defence for the th client, scoped to its EXE only and **never OS-wide** (Batt: a future user may
play official Thai RO normally on the Dell):
1. an outbound Windows Firewall rule bound to `C:\RO-rAthena-th\client\PoringLab.exe` (Batt
   creates it: admin);
2. a live watch of that exe's TCP connections (any non-lab address kills it);
3. the sniffer attestation (`server=lab-rathena-th`).

Our th `clientinfo.xml` keeps the Thai values (version 24, langtype 5, servicetype thai) and
points only at `192.168.1.13:6900`. Before the first online launch: the loose files are in place
and name the lab address only; the three defences are up; the service-select screen must read
"PoringLab LAN (rathena-th)" (anything else: kill, never select). `servicetype thai` differs from
today's `korea`; if login fails, `korea` is the measured fallback.

## 3. The Thai exe: static findings only (never run, never unpacked)

| Question | Finding |
|---|---|
| GameGuard in the exe | hidden by the protector (WinLicense/Themida class: five unnamed sections at entropy 8.0, `.vm_sec`, `.winlice`, `.boot`); the visible import stub names no GameGuard DLL; no GameGuard/npgg/XIGNCODE string in the Thai GRF names or `System\` |
| Launcher / login | hidden; no `1rag1` or `/account:` visible (the 2021 lab exe shows both). Indirect signs: `pcmac.dll!GetEncryptMACAddress`, WININET, bcrypt, IPHLPAPI. Manifest: `requireAdministrator` |
| clientinfo | in the GRF (plain); whether it honours a loose data folder is hidden |
| Build / packets | PE timestamp and Gravity's Authenticode signature: 2026-09-21; PDB "Release Overseas V142 C++20" (`Ragexe_up.exe`); its packet version is hidden but newer than the pinned rAthena's packet DB (newest 20250122); obfuscation keys hidden |

## 4. The separate client, compatibility, sprite fidelity, adoption cost

To be filled after 17:00 ICT (3b–3e).
