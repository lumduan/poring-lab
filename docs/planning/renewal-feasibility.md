---
doc_type: design
hypothesis: "The lab's rAthena (pinned e985006) and its 2021-11-03 kRO client can run in RENEWAL mode, with the third classes, by a server rebuild alone: the same exe, the same client data and no Windows change; and a separate renewal server beside the pre-renewal one (one at a time, as rathena-th was) can be stood up without putting the pre-renewal work, its data or its rollback at risk."
status: "PARKED by Batt 2026-10-24 ~16:0x ICT ('park it; use ours as before'). It was PROPOSED 2026-10-24 12:14 ICT (offline study only: no build, no docker, no client input, no live query; the server facts are read from the pinned tree, the client facts from the repo's records and one read-only table listing of the Thai GRF). Batt decides: whether to migrate, option A or B (section 7), and the community server's facts (section 4)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [thief-payon.md, payf07-prep.md, crusader-build.md, ../thai-data-experiment.md, ../client/rathena-client.md, ../environments/community-server.md, ../adr/0006-sanctioned-test-environments.md, ../adr/0019-windows-stays-clean.md]
next_action: "PARKED (Batt ~16:0x): nothing to do until he reopens it. When reopened: Batt: (1) the community server's mode, episode, job set and client date (section 4: without them 'our data matches the group's' cannot be checked); (2) migrate or not, and option A (a second renewal rAthena, recommended) or B (switch in place); (3) a build window; (4) the renewal Thief's base level and map (section 6). Nothing is built before his go."
title: "Renewal (third classes) for the lab: server, client, community server, code impact, the map question, and a migration plan"
date: 2026-10-24
owner: Batt
---

# Renewal (third classes) for the lab: a feasibility study and a migration plan

Batt, 2026-10-24: "investigate whether our server and client can be updated to RENEWAL (3rd
classes). I think they can, because the community group still uses it; look into it so our data
matches the group's." He decides; this doc only studies and proposes.

**Sources.** Server facts are pinned to rAthena `e985006171d2eb320ee512a653f4c83aea3d81b6`
(committed 2026-08-21 17:10 UTC, GitHub API). `conf/`, `db/` and `npc/` are read from the
read-only mirror `/dev/shm/poring-lab-rathena-src`. Single `src/` files were fetched from
`raw.githubusercontent.com/rathena/rathena/<ref>/...` into `/dev/shm`. `src/config/packets.hpp`
and `src/config/renewal.hpp` are byte-identical at rAthena master `d4b8e7b` (2026-10-06), so
nothing below depends on a newer ref. Small facts are quoted as `file:line`; no rAthena table is
copied here.

## 0. The answers in short

| # | Question | Answer |
|---|---|---|
| 1 | The server | **Feasible by a rebuild with one build argument changed** (`PRERE=no`). The image already carries both data trees, and `main.sql` is one schema for both modes. The existing characters load unchanged: same stat points, stat costs, job bonuses, HP/SP tables and skill trees for our three jobs. Their derived numbers, the gear's DEF and every monster change. The rebuild gets a NEW image tag, so the pre-renewal image stays as the rollback. |
| 2 | Third classes | **Renewal at this ref has all of them.** That is the 12 third jobs (Base 200 / Job 70), the expanded classes and the fourth jobs (Base 275 / Job 60). The pre-renewal tables have none of them. GM group 20 already holds `jobchange`, so no conf change is needed. |
| 3 | The client | **Very likely yes, with no Windows change.** PACKETVER 20211103 is compiled as a RagexeRE packet set in BOTH modes, and the packet tables do not depend on the mode. The lab's data is kRO 2021-06, i.e. renewal-era data: the client maps already agree better with the RENEWAL map cache. The Thai GRF has every third-job body sprite. The lab's own kRO GRF (on the Dell) is NOT verified: one read-only check is needed. |
| 4 | The community server | **Our docs record nothing about its mode, episode or job set.** They record: evidence pending, FORBIDDEN for automation, a client installed as RagnarokClassic (Gravity Game Tech), and a Cash Shop / RODEX / gacha seen in its frames. Batt's statement is the only source that it is renewal. |
| 5 | Our code and data | **About 45 code sites in 14 areas pin pre-renewal** (section 5): the KB, first workflow and route; econ; the steal comment; 17 mapcache `prere=True` calls; the L2 build name; packet tables; start points; EXP needs; the closed species lists. Nothing checks that the code's mode equals the running server's. |
| 6 | The map | **Renewal splits Batt's two steal targets.** Bigfoot is on pay_fild07 (174) and Elder Willow on prt_fild10 (157) / mjolnir_02 (154). Kill drops are about halved, and a level penalty halves them again for a Base 50 Thief. Steal is NOT level-penalised. Dead Branch and Rough Elunium go with Elder Willow; Honey and Rough Oridecon with Bigfoot. |
| 7 | The plan | **Recommended: option A.** That is a second, separate renewal rAthena (`rathena-re` + `db-re` + `sniffer-re`), one at a time with today's server, the rathena-th way. It uses the same Windows client and has its own environment id. Rollback is a stop and a start. Option B (switch in place) is cheaper in compose but invalidates every pre-renewal number at once, and its DB rollback needs a new guarded dump step. |

## 1. The server

### 1a. How pre-renewal is selected today

- `.env` holds `RATHENA_PRERE=yes`. The live `.env` was read for this key only. `.env.example:69-70` records it as Batt's 2026-09-30 choice.
- `compose.yaml:63` passes `PRERE: ${RATHENA_PRERE:-no}` as a build argument.
- `compose.yaml:66` names the image `poring-lab/rathena:pv${PACKETVER}-prere-${RATHENA_PRERE}`, so today's image is `pv20211103-prere-yes`.
- `services/rathena/Dockerfile:33` has `ARG PRERE=no`, and `:51` runs `./configure --enable-packetver=... --enable-prere="${PRERE}"`.
  - rAthena's `configure.ac:1078-1085` turns `yes` into `-DPRERE`.
  - `src/config/renewal.hpp:9-76`: `#ifndef PRERE` defines `RENEWAL`, `RENEWAL_CAST`, `RENEWAL_DROP`, `RENEWAL_EXP`, `RENEWAL_LVDMG`, `RENEWAL_ASPD` and `RENEWAL_STAT`.
  - `Dockerfile:57` writes `prere=` into BUILD_INFO, and `entrypoint.sh:80` logs it.
- ⚠️ **Both defaults are RENEWAL**: the compose fallback `:-no` and the Dockerfile `ARG PRERE=no`. Only the `.env` line keeps the lab on pre-renewal. A lost `.env` key would build renewal silently.
  - The image tag would differ (`-prere-no`), so it would not overwrite today's image.
  - Recorded, not acted on: a guard (`test_guards.py`) could pin it.
- **PACKETVER is independent of the mode.**
  - `compose.yaml:62` and `Dockerfile:32` set 20211103.
  - `src/config/packets.hpp:19-25` defines `PACKETVER_RE` for 20200902 ≤ PACKETVER ≤ 20211118, whatever PRERE is.
  - So the server ALREADY speaks the RagexeRE packet set to our client.

### 1b. What a renewal build changes, by itself (no file edits)

| What | Pre-renewal (today) | Renewal | Source |
|---|---|---|---|
| db tree | `db/pre-re/` | `db/re/` | `src/config/const.hpp:37-41` (`DBPATH`) |
| npc tree | `npc/pre-re/scripts_main.conf` | `npc/re/scripts_main.conf` | `src/map/map.cpp:4263-4267` |
| map cache order | import → `db/pre-re/map_cache.dat` → `db/map_cache.dat` | import → `db/re/map_cache.dat` → base | `map.cpp:3921-3925` |
| new characters start at | `new_1-1 … new_5-1` (53,111) | `iz_int … iz_int04` (18,26) | `src/char/char.cpp:3007-3012`; `conf/char_athena.conf:115-116` |
| start items | `start_items_pre` | `start_items` (one more item, 23484) | `char.cpp:3021-3026`; `char_athena.conf:124-125` |
| guild skills / weapon levels | 15 / 4 | 20 / 5 (enchant grades on) | `src/common/mmo.hpp:104-108, 132-140` |
| `renewal-`-prefixed inter config keys | ignored | applied | `map.cpp:4287-4297` |

- **No data has to be added to the image.** `Dockerfile:60-61` already tars the whole `conf db npc` trees, both modes, and the entrypoint extracts them into the tmpfs. Only the four server binaries change.
- **SQL.** There is one `sql-files/main.sql` for both modes. `entrypoint.sh:103-108` imports it once, into an EMPTY database. The fourth-job trait columns (`pow` … `trait_point`) are in it in both modes (`main.sql:226-240`). So `db-data` needs no migration, and a renewal server reads today's rows as they are.
- **Battle-conf defaults that differ by mode** (`src/map/battle.cpp`; our `conf/import` has no battle override):
  - `natural_heal_weight_rate` 70 vs 50 (`:8391` / `:8394`): regen stops at 70 % weight, not 50 %;
  - `item_enabled_npc` 0 vs 1 (`:8686` / `:8688`): no item use while an NPC dialog is open;
  - `traps_setting` 2 vs 0 (`:8275` / `:8277`);
  - also the guild relog type, instance reconnect, homunculus delays and alchemist summons.
- **The formulas switch with the defines:**
  - HIT and FLEE get +175 / +100 and LUK terms (`status.cpp:2641`, `:2646`);
  - the hit chance's base is 0 instead of 80 (`battle.cpp:3259-3263`), still capped to 5-100 % (`:3312`);
  - DEF / MDEF / ATK / MATK change, and ASPD (`db/re/job_aspd.yml`, with a shield penalty);
  - cast times, drops (a level penalty, section 6c) and EXP (a level penalty);
  - the stat cost (identical below 100, below).

### 1c. Do the existing characters survive? What happens to each?

**They load.** The schema is the same, every item id they hold exists in the renewal item db, and
their maps exist in both caches. What is STORED is valid under renewal:

| Stored fact | Pre-re vs renewal at this ref | Source |
|---|---|---|
| Status points per base level | identical through Base 105 (first difference at Level 106: 1433 vs 1434) | `db/re/statpoint.yml:245-246` vs `db/pre-re/statpoint.yml:245-246` |
| Cost to raise a stat below 100 | identical. Renewal `2 + ⌊(x-1)/10⌋` equals pre-re `1 + ⌊(x+9)/10⌋` for every x (`⌊(x+9)/10⌋ = ⌊(x-1)/10⌋ + 1`) | `src/map/pc.cpp:8800`, `:8803` |
| Job bonuses (Thief Job 40, Crusader Job 50, Rogue Job 50, Novice) | identical (Thief: STR +3, AGI +3, VIT +1, INT +1, DEX +2, LUK +2) | `db/{re,pre-re}/job_stats.yml` (parsed, compared) |
| Base HP / SP tables | identical for these (Thief Lv 50: 934 / 110; Crusader Lv 60: 2470 / 292; Novice Lv 1: 40 / 11) | `db/{re,pre-re}/job_basepoints.yml` |
| Skill trees (Novice, Swordman, Thief, Crusader, Rogue) | identical: same skills, max levels, prerequisites | `db/{re,pre-re}/skill_tree.yml` (parsed, compared; Thief `re:276`, Rogue `re:1142`) |
| Gear | same ids and weapon ATK (Damascus 118, Flamberge 150). Armour DEF is on the renewal scale: Buckler 4 → 40, Thief Clothes 6 → 40, Manteau 4 → 13, Boots 4 → 16; the Crusader's Shield 6 → 60, Full Plate 10 → 70, Helm 6 → 13. Every piece of the Thief's gear is still sold by an NPC; Fly Wing costs 250 (60 in pre-re) | `db/{re,pre-re}/item_db_equip.yml`; `npc/merchants/shops.txt` + `npc/re/merchants/shops.txt` |

**What changes for each character:**

- **The Novice GM (Lv 1, immune).**
  - Base Lv 1 → 2 needs **548** EXP in renewal, not 9 (`db/re/job_exp.yml` vs `db/pre-re/job_exp.yml`). The fixed state "Lv 1" is easier to keep.
  - `farm0.BASE_NEED_PRE_RE` (`scripts/farm0.py:530`) is wrong under renewal.
  - Its save point and maps (prt_fild08, new_4-1) exist in both modes. prt_fild08's cell grid is identical in both caches (section 3c).
- **The Crusader (Base 60 / Job 50).**
  - Stats, skills and gear rows stay as they are. Its numbers change: DEF on the renewal scale, renewal Heal / cast times / ASPD with the shield penalty.
  - **orcsdun01 roughly doubles in level** (`npc/re/mobs/dungeons/orcsdun.txt`, parsed):
    - Orc Zombie L51 (pre-re L24), Orc Skeleton L53 (L28), Steel Chonchon L48 (L17);
    - Familiar becomes passive (renewal AI 1).
  - Every orcsdun01 result (186 kills/h etc.) is a pre-renewal number.
- **The Thief (Base 50 / Job 40, AGI 62 + 4, DEX 40 + 2, LUK 1 + 6).**
  - Renewal HIT = 50 + 42 + ⌊7/3⌋ + 175 = **269** (pre-re 92).
  - Renewal FLEE = 50 + 66 + ⌊7/5⌋ + 100 + 30 (Increase Dodge, `status.cpp:4518`, both modes) = **247** (pre-re 146).
  - Renewal monster HIT = level + DEX + 150: Elder Willow 34 + 29 + 150 = 213, Bigfoot 29 + 12 + 150 = 191.
  - Renewal hit chance = HIT − FLEE, which is below zero for both, so the **5 % minimum** applies (`battle.cpp:3312`; `min_hitrate` 5 at `:8421`). That is the same 5 % as on pre-re pay_fild07 (thief-payon.md §3).
  - The flee-per-extra-attacker penalty is the same config (`agi_penalty_*`, `battle.cpp:8424-8426`).
  - The Thief's own hit rate is 100 % in both modes (renewal monster FLEE = level + AGI + 100: Elder Willow 148, Bigfoot 133).
  - **Not computed here:** ATK, damage per hit, ASPD and kills/h. Renewal Bigfoot has HP 506 (pre-re 1619) but DEF 55 on the renewal scale. The status window after a switch is the measurement.

### 1d. Build cost and rollback (nothing is built by this study)

- **The build.** One full compile of the pinned tree, as on 2026-09-30.
  - It runs inside the build tmpfs (`Dockerfile:45-61`), at `MAKE_JOBS` 4 and ~1-1.5 GB of RAM per translation unit.
  - It writes ONE ~79 MB runtime tar layer plus BuildKit cache records to the shared disk.
  - It goes through `scripts/guarded_build.py` in an operator-chosen window, with the tolerant guard as rathena had (`--sustain 30 --spike 25 build:rathena`, README.md:331).
  - The base and apt layers are cached, so the build re-downloads only the source tarball, into tmpfs.
  - Its duration is not recorded in our docs: measure it in the window.
- **The new tag.** It is `poring-lab/rathena:pv20211103-prere-no`. **`pv20211103-prere-yes` is not touched**, so going back to pre-renewal needs no rebuild.
- **The database.** Under renewal a character gains renewal-era state: levels, items, positions. Going back keeps that state, so a COLD dump of `db-data` comes first. `guarded_build.py voldump:` allows only `db-th-data` today (`VOLUME_ALLOWED`, `scripts/guarded_build.py:249`). Option B therefore needs that list extended: a code change and a guarded step, with db + rathena stopped. `db-data` is 0.17 GB (`docs/operations/disk-audit.md:47`).

## 2. Third classes: what renewal offers at this ref, and what the server needs

- **The jobs** (`db/re/job_exp.yml`, parsed; `db/pre-re/job_exp.yml` and `skill_tree.yml` have none of them):
  - the 12 third jobs: Base 200 / Job 70 (`job_exp.yml:574-639`);
  - the expanded classes: Kagerou / Oboro, Rebellion, Summoner (Doram), Star Emperor / Soul Reaper, Super Novice expanded (Base 200, Job 60-70);
  - the fourth jobs and their expanded twins: Base 275 / Job 60 (`job_exp.yml:1042-1067`), with trait points (`db/re/statpoint.yml`, `TraitPoints` from Level 200 on).
  - The renewal skill tree defines 175 jobs; the pre-renewal one defines 77.
- **Job ids for `@job`** (`src/common/mmo.hpp:978-1091`):
  - third jobs: Rune Knight 4054, Guillotine Cross 4059, Royal Guard 4066, **Shadow Chaser 4072** (Rogue's third);
  - expanded classes: Super Novice expanded 4190, Kagerou 4211, Oboro 4212, Rebellion 4215, Summoner 4218, Star Emperor 4239, Soul Reaper 4240;
  - fourth jobs: Dragon Knight 4252, Shadow Cross 4254, Imperial Guard 4258, **Abyss Chaser 4260**; the expanded fourths are 4302-4308.
- **Stat caps:** `max_third_parameter: 130` (`conf/battle/player.conf:116`) and `max_fourth_parameter` 130.
- **What the server needs: nothing beyond the renewal build.**
  - The GM group 20 already has `jobchange`, `baselevelup`, `joblevelup` and `questskill` (`services/rathena/conf/import/groups.yml`).
  - Batt's path is Thief → Rogue (job 17, from Thief Job 40) → Shadow Chaser. In the game that change needs Base 99 / Job 50 (the job NPC). In the lab it is `@baselevelup` then `@job 4072`, through `crusader.py gm`'s identity checks.
- **Snatcher (the Rogue).** It calls the same `pc_steal_item` on a melee hit. Its chance is (`RG_SNATCHER` × 15 + 55 + `TF_STEAL` × 10) / 1000, with no mode switch (`src/map/skill.cpp:1381-1388`). So section 6's steal maths applies to the Rogue too.

## 3. The client

### 3a. The exe and the packets

- **The exe needs no change.** The lab exe is `2021-11-03_Ragexe`, PACKETVER 20211103 (`docs/client/rathena-client.md`, Versions), and rAthena compiles it as RagexeRE in both modes (`packets.hpp:22`).
- **The packet tables do not depend on the mode.** `src/map/clif_packetdb.hpp`, `src/map/packets.hpp`, `src/map/packets_struct.hpp` and `src/common/packets.hpp` have no `RENEWAL` / `PRERE` conditional. The lab's tables are generated with `-DPRERE` (`scripts/gen_packet_tables.py:85,190`; `packages/poring_packets/src/poring_packets/tables.lock.json:85` `"prere": true`). Regenerated with `prere: false` they should be identical; prove it once, as a guarded offline step.
- **What the server SENDS does change** (`src/map/clif.cpp`):
  - more status updates in renewal, the trait stats `SP_POW` … (`:4176`, `:9859`, `:10997`);
  - DEF / MDEF sent as sums (`:1854`);
  - a "busy" message on some actions during NPC dialogs (`:12213`, `:12688`).
  - The sniffer's decoders must tolerate those parameter ids. The §2a positive cases are re-run after any switch.

### 3b. The client data

- **The lab's data is kRO's** (`Ragnarok_210607.zip`, rathena-client.md). Korea's main service is a renewal service, so the lab already runs a pre-renewal SERVER on renewal-era CLIENT data.
- **Evidence from the map caches** (computed for this study, counts only; `poring_dataset.walkable.agreement`). The client GATs in `/dev/shm/poring-lab-tmp/gat` were compared with the two server caches for the 8 maps the two trees override. "Client-only" means cells walkable in the client that the server refuses:

  | map | pre-re cache: client-only / server-only | renewal cache: client-only / server-only |
  |---|---|---|
  | alberta | 4,836 / 255 | **168 / 66** |
  | izlude | 8,936 / 5,422 (cache 268×268, client 268×300) | **172 / 0** (268×300, the client's size) |
  | morocc | 4,482 / 2,517 | **1,429 / 351** |
  | prontera | **0 / 46** | 854 / 392 |
  | prt_church, prt_fild08 | 0 / 0 | 0 / 0 (identical) |

  - The other lab maps come from the shared `db/map_cache.dat`: pay_fild07/08/09, orcsdun01, payon and the novice maps. They are the SAME in both modes, so payf07-prep.md's grids and zones stay valid.
  - Caveat: these GATs were extracted from the Thai GRF. The kRO and Thai copies were proven identical only for the four lab maps (thai-data-experiment.md).
- **Third-job sprites: checked offline in the Thai GRF** (`scripts/grf_read.py ls`, header and table only, output in `/dev/shm`, deleted after counting; no names are copied here):
  - 326 human body-sprite entries, 177 base names;
  - **all 12 third jobs**, male and female;
  - the expanded classes (Kagerou / Oboro, Rebellion, Star Emperor, Soul Reaper, Super Novice) and the Doram race (Summoner);
  - **fourth jobs only in part**: bodies for Dragon Knight, Inquisitor and Spirit Handler; garment sprites name the others.
  - The renewal maps that section 6 needs (prt_fild10, mjolnir_02, mjolnir_10, gef_fild05, moc_pryd05, pay_fild07/09) are all in it.
- **The lab's own kRO GRF is on the Dell and is NOT verified.**
  - Expected to pass: kRO added the third jobs long before 2021, and the two copies' 12 KB species were byte-identical (thai-data-experiment.md §3d).
  - The cheapest proof is ONE read-only listing of its file table on the Dell (a live step: Batt's go). An alternative is an in-game look at `@job 4072` on a throwaway character on the renewal server.
- **Item and skill text.** The client draws item and skill descriptions from its own Lua (kRO's: renewal-era). Under a renewal server the descriptions and the server's values should agree better than today (e.g. renewal Buckler DEF 40). Unverified: the lab client's Lua lives on the Dell.

### 3c. Client configuration and the Windows-stays-clean rule

- **No client change is needed for option A or B.** The exe, the data, `clientinfo.xml` (192.168.1.13:6900), the AssistAddr override and the Equip placeholders all stay. One server runs at a time on the same address and ports, so the same client reaches whichever runs. The server-select line shows that server's `RATHENA_SERVER_NAME`.
- **ADR-0019 is not touched.** A NEW client (a newer exe or newer data, e.g. for the fourth jobs) would be a Windows change. It would need its own approval, a fresh AssistAddr override, the placeholders and a new layer-1 rule. It is not needed for third classes.
- **The L2 build `kro-20211103-prere`** (`packages/poring_skills/src/poring_skills/l2/kro-20211103-prere.yaml:5,10`, `renewal: false`) names a CLIENT build but carries a SERVER-mode flag.
  - `resolve.client_for_profile` fails closed when two L2 files claim the profile `kro` (`resolve.py:55-63`). So a renewal copy cannot simply share the profile.
  - Its bindings (shortcuts, windows, the hotbar) are exe-side and carry over. The skill-window geometry that learn_skill@1 uses differs on a third-job tab.
  - Batt's choice: (i) keep the id and move `renewal` to the environment (`config/environments.yaml`); or (ii) a new L2 id plus a new ro_agent profile.

## 4. The community server: what our docs say, and what is unknown

**Recorded** (`docs/environments/community-server.md`, ADR-0006, ADR-0019 audit,
`config/environments.yaml`):
- Name, host and rules: **pending** (Batt to supply).
  - The server is **FORBIDDEN for any automation** until the evidence and the interlock entry exist.
  - Batt may play there manually.
- Its client is the untouched `C:\Program Files (x86)\Gravity Game Tech\RagnarokClassic` (rathena-client.md), launched by a desktop shortcut "RO Dev Serv" (ADR-0019:266).
- Frames on 2026-09-30 showed a Cash Shop, RODEX mail, server-wide gacha broadcasts and a RagnarokClassic installer. These resemble the official Thai Ragnarok Classic service, which is forbidden; its domains, including `roc.gnjoy.in.th`, are in the known-forbidden list (`config/environments.yaml:78`).
- **Nothing about its game mode is recorded:** not renewal or pre-renewal, not the episode, the max level, whether third or fourth jobs are open, the rates, the server software or its version, the client exe date / PACKETVER, or any custom db.

**What Batt must confirm before "our data matches the group's" can be checked** (from the server's
own announcement or rules page, recorded in community-server.md):
1. renewal or pre-renewal, and the episode / content level;
2. the max base / job level, and which classes are open (third? fourth? expanded?);
3. the rates (EXP / drop) and any custom item, monster or spawn changes;
4. the server software (rAthena? Hercules? official?) and, if rAthena, roughly its date;
5. the client's exe date (our exe is fixed at 2021-11-03);
6. the permission evidence ADR-0006 already asks for (unchanged by this study).

"Classic" in the client's product name does not say which mode the server runs. Until 1-4 are
known, a renewal lab at e985006 matches rAthena's renewal (kRO-like) data, not necessarily the
group's.

## 5. Impact on our code and data

The grep: `git grep -P -i "pre-re(?![a-z])|prere|pre_re(?![a-z])|pre-renewal|renewal"`. The
lookahead keeps "pre-registered" out. The sites that change behaviour or a stated fact:

| Area | Site | What is pinned to pre-renewal | Under renewal |
|---|---|---|---|
| Server build | `.env` `RATHENA_PRERE`; `compose.yaml:63,66`; `Dockerfile:33,51,57` | the mode, the image tag | option A: a new service with its own build args and a fixed tag; option B: flip `.env` |
| Thai twin | `compose.yaml:432` (`rathena-th` image follows `RATHENA_PRERE`); `services/backend/tests/test_guards.py:969` asserts the same image | rathena-th = rathena's image | option B would move rathena-th to renewal too: pin its tag to `-prere-yes` first |
| KB | `scripts/kb_build.py:7,52-53,55-75,81-86,400-403` (`mode: "pre-re"`) | mob db, mob skills, spawn files, warp files, item db | a `--mode re` that swaps `db/pre-re` → `db/re` and `npc/pre-re` → `npc/re` and writes a separate KB (`data/kb` is local); the renewal spawn lists differ (section 6) |
| First workflow | `scripts/kb_first_workflow.py:11-24,64,69-71,1586` (`ENTRY` = the pre-re scripts_main, `START_KEY = "start_point_pre"`); `_renewal_only` at `:379-422` | the npc entry, start points (new_1-1 …), job EXP | renewal entry, `start_point` (iz_int), the `checkre(0)` warps become live (already kept apart as `warps_renewal_only`) |
| Route | `scripts/kb_route.py:4,47-98,394,433` | job EXP, skill tree, spawn and warp lists, the novice / merchant job scripts | renewal files (the novice quest differs) |
| Economics | `scripts/econ_items.py:3,14,52-56,242`; `scripts/econ_model.py:50,64,237,493-497,607-630,867` | item prices, mob db, the pre-re damage formula, attr_fix, map caches | renewal db; the renewal DEF formula; **the renewal drop level penalty** (not modelled anywhere today); NPC prices (Fly Wing 250) |
| Weight / regen | `scripts/econ_row.py:29` (regen stops at 50 %, "pre-re default"); `scripts/gm_state.py:329` (weight cap formula); thief-payon.md §3 | 50 % | 70 % (`battle.cpp:8391`) |
| Steal | `scripts/dungeon_hunt.py:181-182` (`STEAL_MAX = 5`, comment "EW 61 % / Bigfoot 83 % a try: >= 99 % within 5") | pre-re success rates | 34.0 % / 51.1 % a try: 87.5 % / 97.2 % within 5 (section 6b) |
| EXP | `scripts/farm0.py:530` `BASE_NEED_PRE_RE = {1: 9, 2: 16}`; `scripts/hunt.py:1062` | Novice EXP needs | 548 / 894 |
| Map caches | `packages/poring_dataset/src/poring_dataset/mapcache.py:11-13,82-105` (`prere=True` default); `walkable.py:109-128`; callers with `prere=True`: `calibrate_projection.py:148`, `camera_validate.py:192`, `item_labels.py:493`, `m4_cells.py:140`, `m4_validate.py:362`, `map_agreement.py:119,126`, `mapcache_diff.py:58`, `npc_click_test.py:360,741`, `orc_dungeon_prep.py:242`, `qa_export.py:382,416`, `selfpos_calibrate.py:394`, `selfpos_eval.py:227`, `walk_check.py:93`; `scripts/gen_mapcache.py:8,36` | the pre-re cache for 8 maps | `prere=False` already works (the lock pins the `re` cache, `mapcache.lock.json`); one mode switch instead of ~17 literals; `data/kb/map_agreement.json` must be rebuilt (alberta / izlude / morocc / prontera change, section 3b) |
| Packets | `scripts/gen_packet_tables.py:85,190,246`; `tables.lock.json:85` | `-DPRERE` | regenerate with `prere: false`, diff (expected identical); decoders tolerate the trait-stat parameters |
| Thai mapcache tool | `scripts/gen_mapcache_th.py:56` (`--enable-prere`) | pre-re | only if the Thai experiment is revived |
| L2 / flows | `l2/kro-20211103-prere.yaml:5,10`; `l1/{char,session,ui}.yaml` (`client: kro-20211103-prere`); every flow `target(client=...)` and its tests and fixtures (`packages/poring_flow/tests/*`, `services/frontend/src/lib/flow/fixtures/*`); `packages/poring_skills/tests/test_resolve.py:16-19` asserts `renewal is False` | the client id carries "prere" | section 3c: Batt's naming choice |
| Species / labels | `scripts/sprite_catalog.py:70-72` (`DEFAULT_AEGIS`, "the pre-renewal spawn tables"); `scripts/battle_log.py:123`, `battle_log_judge.py:50`, `species_check.py:131`, `flow_judge.py:850`, `hit_rate.py:36`, `search_gap.py:82`, `agent_play.py:55`, `vlm_flag.py:55` (closed species lists); `dungeon_hunt.py:181` | the prt_fild08 species set (Poring / Lunatic / Pupa / Drops / Creamy) and pay_fild07's | renewal prt_fild08 adds Fabre 77 and Little Poring 20 plus five one-off variants (Ringleader, Furious, Elusive, Swift, Solid) with their own ids and name tags; renewal pay_fild07 = Bigfoot / Caramel / Stainer / Creamy (+ Bigfoot Ringleader 2). The detector classes are generic (`poring_dataset/labels.py:34`: player / monster / npc) but every trained model saw only pre-re species |
| Zones / spans | `config/map_zones/pay_fild07.yaml:9`; `services/backend/tests/test_map_prep.py:128` (spans from `npc/pre-re/warps/fields/payon_fild.txt`) | the warp spans | re-derive from `npc/re/warps` (pay_fild07's cells are unchanged; its warps may not be) |
| Collect | `scripts/collect_v2.py:75` (`db/pre-re/job_noenter_map.txt`) | noenter zones | `db/re/job_noenter_map.txt` |
| Tests that assume pre-re | `test_mapcache_paths.py:53,218`, `test_walkable.py:95`, `test_map_agreement.py:47-50`, `test_econ.py:271`, `test_farm0.py:132`, `test_kb_first_workflow.py:392-419`, `test_rule_run.py:69,244`, `test_lint_matrix.py:406` | | follow the code |
| Docs | README.md:76,85; ADR-0006 environment 1b; thief-payon.md, crusader-build.md, crusader-orcsdun01-facts.md (every formula is the `#ifndef RENEWAL` branch), docs/econ/economics.md:48 | stated facts | supersede by pointer when a decision lands, never edit history |

**Interlock and environments.**
- `config/environments.yaml` names `lab-rathena` with its accounts and signals. A renewal server is a NEW environment (option A: `lab-rathena-re`, ADR-0006 environment 1c), confirmed by a person on the Settings page, never by the agent.
- Its sniffer attests `server=lab-rathena-re`, as sniffer-th did (ADR-0016 amendment).

## 6. The map question under renewal

### 6a. Where Elder Willow and Bigfoot live, and what they drop

| | Pre-renewal (today) | Renewal |
|---|---|---|
| **Elder Willow** (1033) | Lv 20, HP 693, DEX 38, aggressive (AI 09); pay_fild07 70, moc_fild03 70 | Lv 34, HP 535, DEX 29, aggressive (AI 19); **prt_fild10 157** (`npc/re/mobs/fields/prontera.txt:126`), **mjolnir_02 154** (`mjolnir.txt:33`), pay_fild09 25 (`payon.txt:94`), gef_fild02 24 (`geffen.txt:43`) |
| EW drops: Dead Branch / Rough Elunium | 1 % / 0.4 % | **0.5 % / 0.2 %** (`db/re/mob_db.yml:1603,1609`) |
| **Bigfoot** (1060) | Lv 25, HP 1619, DEX 20, passive; pay_fild09 70, mosk_fild02 40, pay_fild07 30 | Lv 29, HP 506, DEX 12, passive; **pay_fild07 174** (`payon.txt:76`), mjolnir_01 23, ama_fild01 14, small counts in sec_in02 / prt_maze |
| Bigfoot drops: Honey / Rough Oridecon | 4.5 % / 0.43 % | **2.25 % / 0.22 %** (`mob_db.yml:2951,2953`) |
| pay_fild07 | EW 70, Eggyra 40, Bigfoot 30, Poporing 20, Willow 20, Green Plant 8 (`npc/pre-re/mobs/fields/payon.txt:97-102`) | Bigfoot 174, Caramel 40, Stainer 26, Creamy 26, Green Plant 8 (`npc/re/.../payon.txt:76-80`) + Bigfoot Ringleader 2; **0 % aggressive** |

- Renewal halves most drop rates and adds Fly Wing 5 % to many monsters.
- Elder Willow keeps Fire Bolt Lv 3 and Fire Attack (`db/re/mob_skill_db.txt:142-144`). Bigfoot keeps its stun attack and adds Endure (`:316-320`).

### 6b. Steal, as the pinned server computes it in each mode (`pc_steal_item`, `src/map/pc.cpp:6814-6916`)

- **The rate** is the same expression in both modes: rate = (DEX − monster DEX) / 2 (C integer division) + 6 × Steal level + 4 (`:6842`).
- **Pre-renewal:** there is no rate roll. Each drop slot passes, in order, with its rate × rate / 100 (`:6871`).
- **Renewal:** a roll `rnd()%100 < rate` comes first (`:6845-6848`). Then each slot passes, in order, with its RAW drop rate (`:6865`). StealProtected slots (the cards) are skipped in both.
- **Steal is NOT level-penalised.** It uses the slot's rate directly; the level penalty applies only to kill drops (6c).
- Tries are unlimited (`skill_steal_max_tries: 0`, `conf/battle/skill.conf:240`), and each monster can be stolen from once.

With DEX 42 and Steal Lv 10 (the pre-renewal rows reproduce thief-payon.md §6):

| target | mode | rate | success / attempt | P(success within 5 tries) | target items per SUCCESSFUL steal |
|---|---|---|---|---|---|
| Elder Willow | pre-re (DEX 38) | 66 | 61.2 % | 99.1 % | Dead Branch 0.42 %, Rough Elunium 0.17 % |
| Elder Willow | **renewal** (DEX 29) | 70 | **34.0 %** (0.70 × 48.6 %) | 87.5 % | **Dead Branch 0.53 %, Rough Elunium 0.22 %** |
| Bigfoot | pre-re (DEX 20) | 75 | 82.8 % | ~100 % | Honey 0.73 %, Rough Oridecon 0.07 % |
| Bigfoot | **renewal** (DEX 12) | 79 | **51.1 %** (0.79 × 64.7 %) | 97.2 % | **Honey 1.26 %, Rough Oridecon 0.12 %** |

So in renewal a steal success is rarer (2.9 and 2.0 attempts, 10 SP each). But a success more
often yields the target items, because the slots are no longer scaled down by the rate. And since
kill drops are halved and then level-penalised, **Steal carries a larger share of the target
items in renewal than in pre-renewal.**

### 6c. The renewal drop level penalty (it changes which character farms best)

- **The modifier.** `mob.cpp:3259-3261` takes a modifier from `pc_level_penalty_mod` (`pc.cpp:13325-13359`; difference = monster level − player base level, `:13350`). `mob_getdroprate` applies it (`mob.cpp:2874-2876`).
- **The table** is `db/re/level_penalty.yml:78-` (Type Drop), filled outward from 0 by `PenaltyDatabase::loadingFinished` (`pc.cpp:593-619`). By |difference|: 0-3 → 100 %, 4-6 → 90 %, 7-9 → 80 %, 10-12 → 70 %, 13-15 → 60 %, ≥ 16 → **50 %**. It is symmetric, and pre-renewal has no such table.
- **Exempt:** monsters with the `FixedItemDrop` mode (`pc.cpp:13346`) and maps with `MF_NORENEWALDROPPENALTY` (`:13331`). Setting that mapflag is a server customisation, and it would make our data diverge from rAthena's.
- **For our Thief.** At Base 50, Bigfoot (L29, difference −21) and Elder Willow (L34, −16) drop at 50 %. A character at Base 26-32 gets 100 % from Bigfoot; at Base 31-37, 100 % from Elder Willow.

### 6d. Which maps serve the four target items (renewal; per 100 kills, kills in proportion to the spawn counts, plants left out as thief-payon.md did)

| map, character | Dead Branch | Rough Elunium | Rough Oridecon | Honey | note |
|---|---|---|---|---|---|
| **pre-re pay_fild07**, Base 50 (today's plan, thief-payon.md §6) | 0.39 + 0.16 steal | 0.28 + 0.07 | 0.07 + 0.01 | 0.75 + 0.12 | EW + Bigfoot + Eggyra; 37 % aggressive |
| renewal pay_fild07, Base 50 | 0 | 0.01 | 0.08 + 0.08 | 0.87 + 0.80 | no EW; 0 % aggressive |
| **renewal pay_fild07, Base 29** | 0 | 0.01 | **0.15 + 0.08** | **1.72 + 0.80** | Bigfoot at 100 % |
| renewal prt_fild10, Base 50 | 0.19 + 0.32 | 0.08 + 0.13 | 0 | 0 | EW 157; 66 % aggressive (EW) |
| **renewal prt_fild10, Base 34** | **0.38 + 0.32** | **0.15 + 0.13** | 0 | 0 | EW at 100 % |
| renewal mjolnir_02, Base 34 | 0.36 + 0.31 | 0.14 + 0.12 | 0.01 | 0 | EW 154; 58 % aggressive |

At thief-payon.md's ~150 kills/h (its assumption; renewal kill speed is not modelled):
- **renewal pay_fild07 at Base 29:** about 3.8 Honey/h and 0.35 Rough Oridecon/h, and no Dead Branch;
- **renewal prt_fild10 at Base 34:** about 1.05 Dead Branch/h and 0.42 Rough Elunium/h;
- **pre-re pay_fild07 today:** 0.8 Dead Branch, 0.5 Rough Elunium, 0.1 Rough Oridecon and 1.3 Honey per hour.

**Other renewal maps that rank high** (raw rates, monster level ≤ 60, no boss; a Thief must match their level for full drops):

| item | maps |
|---|---|
| Rough Oridecon | the Morroc pyramids moc_pryd05 / 03 / 02 (0.3-0.6 / 100 kills; mummies, 59-86 % aggressive, L30-59); iz_dun03 |
| Rough Elunium | mjolnir_10 (Argos, 0.22, 82 % aggressive), mjolnir_07 (Savage L59, 0.25), iz_dun02 |
| Honey | gef_fild05 (Creamy 143, 1.39, passive), yggdrasil01 (plants, 1.41) |
| Dead Branch | only the Elder Willow maps above, plus gon_dun01 (0.47) |

**Reading.** In renewal no single map serves all four items as pre-re pay_fild07 does. The natural
split is:
- **Honey + Rough Oridecon:** pay_fild07, with Bigfoot steals;
- **Dead Branch + Rough Elunium:** prt_fild10 or mjolnir_02, with Elder Willow steals, on aggressive monsters.

Each wants a character whose base level sits near the map's monsters. That is Batt's call (section
7, decision 5).

## 7. The migration plan

### Option A (recommended): a second, separate renewal rAthena, one at a time with today's

As rathena-th (thai-data-experiment.md §1; `compose.yaml:387-503`):
- a compose profile `re` with `db-re` (its own volume), `rathena-re` and `sniffer-re`;
- `rathena-re`: the same Dockerfile and SHA, build args `PRERE: "no"`, a FIXED image tag `poring-lab/rathena:pv20211103-prere-no`;
- the same pinned IP 10.210.96.6 and LAN ports, so Docker refuses to run both at once;
- `sniffer-re` with `SNIFFER_SERVER_ID: lab-rathena-re`;
- a new environment `lab-rathena-re` (ADR-0006 environment 1c), with its own accounts in `db-re` and `RATHENA_RE_*` secrets.

| Step | What | Window / guard | Cost |
|---|---|---|---|
| A0 (offline, any time) | compose services + `test_guards.py` pins (limits, IP, image tag, one-at-a-time); a `--mode re` for the KB / first workflow / route / econ; the steal and level-penalty maths in econ; `mapcache` mode switch; packet-table regeneration diff (a guarded offline container); ADR-0006 1c (PROPOSED); the L2 naming decision | none (code; the packet diff is a guarded step) | code only |
| A1 | `python3 scripts/guarded_build.py --sustain 30 --spike 25 build:rathena-re` | operator-chosen window; weekend or after close | one compile in tmpfs, ~79 MB layer + build cache on disk |
| A2 | `rotate_secrets.py set` the `RATHENA_RE_*` accounts; switch: `rm:sniffer,rathena`, then `start:db-re@120`, `start:rathena-re@240`, `start:sniffer-re` (the th sequence) | same window | `db-re` volume ~0.16 GB (db-th-data was 0.16 GB, `disk-audit.md:47`); a capped captures volume |
| A3 | verify: `smoke_test.sh` (BUILD_INFO `prere=no`, the "clients will be sent" line); the same client logs in and the server-select line names the renewal server; Batt confirms `lab-rathena-re` on Settings; interlock green; sniffer §2a positive cases; `map_agreement` for the renewal caches | live, Batt present (Settings is human-only) | minutes |
| A4 | the client-data check: a throwaway character, `@job 4072`, judge the sprite on a frame; and/or the read-only GRF table listing on the Dell | live, Batt's go | minutes |
| A5 | build the renewal characters by GM commands (`crusader.py gm`), name tags for the new species (Caramel, Stainer, Horn, Coco …) cut live by the immune GM | live | as the Thief build (≈ 20 min) |
| back | `rm:sniffer-re,rathena-re`, then `start:rathena@240`, `start:sniffer` | minutes | none |

- **Risk: low.** Today's server, `db-data`, its image and its client are untouched, so every pre-renewal number stays valid and 4.03 (pre-registered on pre-re pay_fild07) can still run.
- **What breaks:** nothing on the pre-renewal side. On the renewal side, everything in section 5 until A0 lands.
- **Rollback:** stop the profile, start rathena. Later, `voldump:` db-re to the NAS (extend `VOLUME_ALLOWED`) and `volrm:`.
- **Characters:** fresh in `db-re`. A copy of today's characters is possible: same schema, but it needs an SQL export / import step that does not exist yet.

### Option B: switch in place

The steps:
1. Cold-dump `db-data` (extend `VOLUME_ALLOWED`; db + rathena stopped).
2. Pin `rathena-th`'s image to `-prere-yes`.
3. `.env` `RATHENA_PRERE=no` (`rotate_secrets.py set`).
4. `build:rathena` (new tag), then `recreate:rathena@240`; verify as A3.

| | |
|---|---|
| Cost | the same build; no new volume |
| Risk | **high for the research record.** Every pre-renewal measurement becomes history at once: hunt baselines, orcsdun01's 186 kills/h, the pay_fild07 pre-registration, the econ model and the KB. The Crusader meets L51 orc zombies. A section 5 site that was missed silently computes pre-re numbers on a renewal server |
| What breaks | everything in section 5 at the moment of the recreate |
| Rollback | `.env` back to `yes`, `recreate:rathena` (the old tag is kept), and restore the dump if renewal play changed the characters |
| Characters | carried over (section 1c): stats, skills and gear rows valid; derived numbers change |

### Option C: do nothing now

Stay on pre-renewal and record the community server's facts (section 4) first. This is the right
answer if those facts show the group is NOT on rAthena-style renewal.

### Recommendation

**Option A, after the community server's facts (section 4) are in.** It is the rathena-th pattern
that already worked, it touches no Windows piece, and its rollback is a stop and a start. It also
lets the pre-renewal series finish while the renewal side is proven step by step. If renewal is
adopted for good, retiring the pre-renewal server is a later, separate decision (B's steps without
the risk, because the code is mode-aware by then).

### The decisions Batt must make

1. The community server's mode and job set (section 4). Is matching it the goal, or only third classes?
2. Migrate at all; option A or B.
3. The build window (A1 / B4) and the tolerant guard.
4. Fresh renewal characters (A) or carried-over ones (B, or A with a copy step to be built).
5. The renewal Thief's base level and map(s): a low-level Bigfoot farmer on pay_fild07, an Elder Willow farmer on prt_fild10 / mjolnir_02, or both. And what 4.03 becomes: run on pre-re as registered, or re-registered for renewal.
6. The L2 naming (section 3c).
7. Confirming `lab-rathena-re` on the Settings page (human-only) and the ADR-0006 1c entry.
8. The kRO GRF check on the Dell (A4): a listing, an in-game look, or both.

## 8. What was verified, how, and what is still open

**Verified offline for this study** (scripts in `/dev/shm`, reading the mirror and the fetched
files; nothing committed but this doc):
- the mode selection and every `src` switch cited above;
- stat points, stat cost, job bonuses, base HP/SP and skill trees: identical for our jobs;
- the renewal spawns of both steal targets, and their stats and drops;
- the steal maths in both modes (the pre-renewal rows reproduce thief-payon.md §6 to 0.1 %);
- the drop level penalty table and its fill rule;
- the per-map yields;
- the job availability and ids;
- the client-GAT agreement with both caches;
- the Thai GRF's third-job sprites (a table listing only).

**Not verified (open):**
- the lab's kRO GRF on the Dell (A4);
- the packet tables with `prere: false` (expected identical);
- renewal ATK, ASPD, damage and kills/h for our characters;
- renewal-mode warp spans on pay_fild07 / prt_fild10;
- the community server's facts (section 4);
- the champion variants' sprites in the client (expected: kRO data).
