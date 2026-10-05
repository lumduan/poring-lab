---
doc_type: design
hypothesis: null
status: KILLED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: "DECIDED 2026-10-05 (Batt): do NOT switch. The lab stays on the kRO data + the main rathena; rathena-th stays documented and stopped (db-th stopped, its volume kept). Revisit only if a future need appears that the kRO data cannot meet."
---

# The Thai-data experiment: a separate client AND a separate rAthena

> ➡️ **DECIDED 2026-10-05 (Batt): do NOT switch.** The lab stays on the kRO data and the main
> rathena. The measurements below are why:
> - every KB species' sprites are byte-identical to kRO;
> - the four lab maps are identical;
> - the Thai GRF cannot sit in front of the 2021 exe.
>
> rathena-th and the th client stay as a documented, STOPPED option: db-th is stopped
> (`scripts/dev.sh --profile th stop db-th`) with its volume kept.
>
> What the experiment left that stays in use:
> - the server identity in the interlock (ADR-0016);
> - the AssistAddr override on both clients;
> - the exe-scoped layer-1 allowlist (replacing the IP blocklist below);
> - the durable watcher (ADR-0013 amendment);
> - the Equip-texture placeholders.

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

Run on 2026-10-05 from 14:19 ICT (Batt moved it ahead of 17:00 while he was available).

### 3b. The client copy and its defences

- **The copy:** `C:\RO-rAthena-th` holds 936 files (3,808,348,146 B, verified) from `C:\RO-rAthena`;
  the original is untouched.
  - `client\thdata.grf` came through the temporary NAS drop (sha256 `a3718c74…f537`).
  - DATA.INI started as `0=thdata.grf, 1=rdata.grf, 2=data.grf`.
- **The shortcut:** "Ragnarok Offline TH" at desktop (37,747) runs `C:\RO-rAthena-th\PoringLab.cmd`.
  - In .env: `RO_SHORTCUT_TH`; signature `shortcut_icon@thdata`.
  - `ro_agent.py --profile th` drives it.
- **Our clientinfo** (`data\clientinfo.xml`, `data\sclientinfo.xml`):
  - display "PoringLab LAN (rathena-th)", `192.168.1.13:6900`, version 24, langtype 5;
  - servicetype `thai` at first, `korea` since T1 (table below).
  - The service-select list shows ONLY that line, so the loose file wins over the Thai GRF's
    official one.
  - The kRO `service_select` signature also matches this list (5.2), so the line was read by eye.
- **Layer 1, the firewall:** Batt opened the elevated console; the agent typed only the agreed rule.
  - Read back from the agent's shell: Outbound Block, Enabled, Profile Any.
  - Program: exactly `C:\RO-rAthena-th\client\PoringLab.exe`.
  - RemoteAddress: the five resolved official Thai IPs.
  - It is the only active rule naming any RO exe: the main lab client and the community client
    have none.
- **Layer 2, `thwatch`:** a `Start-Job` in the agent's own shell.
  - Every 500 ms it lists the TCP connections of `PoringLab.exe` processes whose PATH is the th
    exe. Any remote other than 192.168.1.13, loopback or unbound means Stop-Process plus a
    `KILLED` line in `C:\RO-rAthena-th\watch.log`. An `alive` line is written each ~60 s.
  - It lives in that shell window. `ro_agent.py open-terminal` opens a new shell when none is
    visible and then closes the others, so before typing, restore the minimised shell from the
    taskbar instead.
  - It polls, so a sub-500 ms failed attempt could escape it.
- **Layer 3:** sniffer-th's attestation (`server=lab-rathena-th`).

### 3c. Compatibility (RDP mode, rathena-th running, main rathena stopped)

| Run (ICT) | DATA.INI | servicetype | Result |
|---|---|---|---|
| T0 14:38 | Thai first | thai | **Crash at start**, ~5 s after launch, before any window or connection: `ucrtbase.dll` access violation `0xc0000005` at `0x61cc6` (event 1000) |
| T1 14:51 | Thai first | korea | The same crash: servicetype is not the cause |
| T2 14:55 | **Thai last** | korea | Starts. The GM logs in (account 2000001). At CHARACTER SELECT the exe opened `kro-assit.ragnarok.co.kr:3000`: **killed by layer 2** at 14:58:33 |
| T3 15:19 | Thai last | korea + AssistAddr override | Holds at character select (no PIN or web step). ThGm01 created (db-th char 150000). In game on `new_4-1`; interlock GREEN as `lab-rathena-th`. `@warp prt_fild08 170 375` and the four `@monster` spawns work. **Froze** ~5 s after clicking the Basic-Info menu buttons (Equip/Item/Skill): game loop stopped, window still responding, map session timed out at 60 s, no crash event, no outbound connection; stopped by PID |
| T4 15:37 | the same | the same | In game. **10 min idle with no input: PASS**: 11 samples from 15:38:19 to 15:48:50, all green as `lab-rathena-th`, session live, 0 map timeouts; the picture stays live (10 % of game-area bytes change in 2 s). **Walking: PASS** (minimap 170,375 → 179,361). A clean Alt+F4 logs off. `thwatch` silent |
| T5 15:52 | the same | the same | The agent account (2000000, group 0) logs in; ThAgent01 created (db-th char 150001); closed at character select. `thwatch` silent |

**Where the character-select call comes from.** It is data, not code:
- `AssistAddr` in `data\luafiles514\lua files\service_<svc>\externalsettings_<svc>.lub`;
- kRO `data.grf`/`rdata.grf` hold `_kr`, `_kr_qm`, `_kr_sak`, `_kr_sak_qm`;
- the Thai GRF holds `service_thailand\externalsettings_th(_stage).lub`.

The values are all official (ADR-0016's known-forbidden list). The string is not in the exe.

**The fix, client config only** (Batt: never patch the exe; rAthena's web auth stays off):
- the four kRO files are extracted from the th copy's own GRFs on the Dell;
- only the `AssistAddr` constant is changed, to `127.0.0.1:3000`;
- they are placed as loose files in `C:\RO-rAthena-th\client\data\luafiles514\lua files\service_korea\`
  and read back.

Nothing listens on the Dell's port 3000. After the fix:
- `thwatch` stays silent;
- the client's only TCP is `192.168.1.13:5121`;
- the DNS cache holds no ragnarok, gnjoy or gravity name.

The main lab client has no such override (Batt decides).

**What it means for the experiment:**
- With the Thai GRF in FRONT, the 2021 exe crashes at start. The exe can index the Thai GRF
  (with it last, it starts), so the crash comes from a Thai file read at startup that replaces a
  kRO one.
- With the Thai GRF LAST, the client is the kRO client plus the files only Thai has. The sprite
  question (3d) cannot be answered in that configuration.
- The open option is a selective overlay: only the Thai sprites/textures/maps in front, kRO tables
  and Lua behind. It is Batt's decision.

Sizes for a selective overlay, from our reader over the Thai GRF:

| Overlay | Entries | Bytes |
|---|---|---|
| the four M4 species (`.spr` 0x03 MIXCRYPT, `.act` 0x05 DES) | 8 | ~73 KB |
| all monster sprites (`data\sprite\몬스터\`) | 2,476 | 108.5 MB |
| all other sprites | 124,057 | 900 MB |
| textures | 40,514 | 1.44 GB |
| maps (gat/gnd/rsw) | 2,436 | 655 MB |

A raw copy keeps each entry's encryption, so an overlay needs no decryption. Which overlay, and
how it reaches the Dell, is Batt's decision.

Offline facts about the Thai GRF (our reader):
- 185,765 entries; the longest name is 126 bytes;
- 84,450 entries lie past 2 GiB, but the kRO `data.grf` is 2.97 GB and works, so that is not the
  cause;
- 245 directory entries carry flag 0x02.

### 3d. Sprite fidelity: the sprites are IDENTICAL (measured 2026-10-05 16:25-17:05)

**The Thai data is not needed for sprites.** For every species in the KB (poring, lunatic, pupa,
drops, creamy, plankton, marina, hydra, kukre, vadon, black_mushroom, cornutus), the SPR and ACT
files in the lab client's kRO `data.grf` and in the Thai GRF decode to the same bytes. That is 24
of 24 files.

How it was proven, with no file moved and the study decoder kept on the host:
1. **Declared sizes.** In both GRFs, every file has the same compressed, aligned and uncompressed
   sizes and the same flags (`.spr` 0x03 MIXCRYPT, `.act` 0x05 header-DES). The kRO copies live in
   `data.grf` (plus copies under `npc\`); `rdata.grf` has none.
2. **Raw diff on the Dell.** Both GRFs are on the Dell: `thdata.grf` is the Thai one. PowerShell
   compared the stored (encrypted) bytes:
   - poring, hydra.act, vadon.act and cornutus: 0 differing bytes;
   - every other file differs ONLY at or past `zsize`, which is the 8-byte alignment padding;
   - the one exception is `kukre.spr`, below.
3. **Padding invariance on the host.** Decoding the Thai blob with its padding replaced (zeros,
   0xFF, random) gives the same output for 23 files, so their kRO twins decode to the same bytes.
4. **`kukre.spr`.** Its last block is DES-encrypted, so the padding changes all 8 bytes of that
   block.
   - Its kRO bytes were read off the Dell's screen (16 hex digits).
   - The Thai bytes were read the same way and matched the host read.
   - With the kRO bytes spliced into the Thai blob, it decodes to the same 18,998 bytes.

The M4 render mismatches (phase3-plan.md §5a) therefore do not come from different art. The
on-screen comparison planned for 3d is moot for these species.

### 3e. Adoption cost (preliminary)

| Item | Thai LAST (works today) | Selective overlay (sprites only, proposed) |
|---|---|---|
| Login and UI signatures | unchanged: the kRO UI; every login step matched the existing signatures (`service_select` 5.2 matches either list text, so the line is read by eye) | the same as Thai LAST |
| Map geometry, camera fits, map cache | prt_fild08, prt_church, iz_dun00/01 identical (0 cells); prontera 46 flips; izlude a different map (avoid on rathena-th) | the same |
| Sprites, KB, datasets, v0 labels | the kRO art, so nothing changes, and nothing is gained | **no change: the 12 KB species are byte-identical**, so an overlay buys nothing for them |
| Server | rathena-th works end to end (accounts, characters, interlock, idle, walk, spawns) | the same |
| Safety | the AssistAddr override is required on any client copy | the same |
| Rollback | today's setup (`rm:sniffer-th,rathena-th`, `start:rathena`, `start:sniffer`); nothing deleted | the same, plus removing one overlay file |

**Verdict input for Batt:**
- For vision, the Thai data changes nothing measurable today: the 12 species' sprites and the
  four lab maps are identical.
- Its GRF cannot sit in front of the 2021 exe (it crashes at start).
- What the experiment did produce, and what remains useful either way:
  - a working separate server (rathena-th);
  - the server identity in the interlock;
  - the assist-call discovery and its config-only fix;
  - the Equip-window texture finding below.

### Found on the way (2026-10-05)

- **Both lab clients now carry the AssistAddr override.**
  - The main client (`C:\RO-rAthena`) got the same four loose files at 16:23, hashes equal to the
    th copy (Batt: override first; no unprotected login to "prove" the call).
  - Existing traces cannot show past calls: the DNS cache was empty, the DNS-Client operational
    log is off, and firewall logging is off on all profiles.
  - The watched main-client login (16:47) reached in game with the interlock green as
    `lab-rathena` and `mainwatch` silent.
  - A path-scoped `mainwatch` job like `thwatch` (log `C:\RO-rAthena-th\watch-main.log`) runs in
    the agent's shell.
- **The T3 "freeze" was the Equip window.** Reproduced on the MAIN client at 16:48.
  - Alt+Q (or the Equip button) raises modal "Resource File Loading fail" boxes for
    `texture\유저인터페이스\basic_interface\btn_e_change_a/b.bmp` (later ones, such as
    `btn_e_off_c.bmp`, go to chat).
  - The lab's kRO data lacks these textures. While a box is open the game loop stops. Past 60 s
    the map session times out ("Disconnected from Server"), and the interlock goes red as it
    should.
  - It is not caused by the Thai data. Avoid the Equip window until the textures are supplied.
- **Chords are paced now** (`ro_agent` d55d149). One instantaneous batch was ignored.
  - Live check on the main client: Alt+E opened the inventory, Alt+Q opened Equip (with the
    errors above), and Alt+F4 closed the client at once.
