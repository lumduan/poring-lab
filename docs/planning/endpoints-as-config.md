---
doc_type: design
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [ADR-0021, ADR-0016, ADR-0006, ADR-0019, ADR-0007, ADR-0013]
next_action: "Batt reviews this inventory BEFORE anything changes (his instruction, 2026-10-09 ~15:20), approves or edits the order of changes (section 6), and answers the open points (section 7: P1-P8). Nothing in it is done."
title: "Endpoints as config: every place the lab endpoint is hard-coded today, and how each becomes config-driven"
date: 2026-10-09
owner: Batt
extends: docs/adr/0021-external-servers.md
gate: "INVENTORY ONLY (Batt 2026-10-09 ~15:20: 'report the list before changing anything'). No code, config, compose, test, Windows rule, watch script, Settings entry or CLAUDE.md sentence changes until Batt approves each step."
---

# Endpoints as config: the inventory

> **Status: PROPOSED. An inventory and a proposed order, nothing changed.** Every change below
> waits for Batt. ADR-0021 (PROPOSED) records the decision this serves; this document is the
> "list before changing anything" he asked for.

## 0. The decision (Batt, 2026-10-09 ~15:20, verbatim)

> - ENDPOINTS ARE CONFIG, NEVER HARD-CODED (Batt). The lab firewall already allows only the lab host
>   (since 10-06), but the lab server may soon move off the quant VM to its own machine. So:
>     * every server endpoint (lab and external) lives in the Settings environments store, the single
>       source of truth; the firewall script, the interlock, the sniffer target and the docs read it;
>     * the same generator produces the lab's own firewall group too (Q6: yes), so moving the lab server
>       = edit the environment in Settings -> regenerate -> Batt runs the reviewed script -> paste-back
>       checksum confirms;
>     * inventory every place that hard-codes the lab endpoint today (192.168.1.13 and its ports in
>       scripts, compose, environments.yaml, windows-setup.md, tests, docs) and list how each becomes
>       config-driven; report the list before changing anything.

**The lab endpoint today:** 192.168.1.13 (the Docker VM, `HOST_LAN_IP`) on TCP 6900 (login),
6121 (char) and 5121 (map). The ports are rAthena's upstream defaults: our conf templates do not
set them (`services/rathena/conf/import/*.tmpl` set only `char_ip`/`map_ip`).

**How this was searched (2026-10-09, branch `docs/adr0021-decisions` at 420732b):** `git grep`
inside the repo for `192.168.1.13`, `HOST_LAN_IP`/`host_lan_ip`, `6900|6121|5121`, every
`192.168.x.y` literal, `10.210.96.*`, `CLIENT_IP`, `LOGIN_PORT`, `PORT_SERVER`, `clientinfo`,
`New-NetFirewallRule`, `lab-only`, `labwatch`, and the ADR-0021 pointers. Nothing outside the repo
was searched; the Windows-side and NAS items (section 3.4) come from the records. The live
Settings store was not read (it is human-only and not in the worktree). The counts in section 2
are as of 420732b, before this branch added its own mentions (ADR-0021's decisions and this
file); line numbers in section 3 are those of this branch.

## 1. The finding that shapes the list: one address, three roles

192.168.1.13 is not only "the lab server". It plays three roles, and `HOST_LAN_IP` carries all
three at once:

| Role | What it is | Examples | Moves when "the lab server" moves? |
|---|---|---|---|
| **R1 game server** | where the lab CLIENT connects: rAthena login/char/map | `config/environments.yaml` `server:`, the Windows firewall group, the watch, `clientinfo.xml`, rathena's advertised `char_ip`/`map_ip` | **yes**: this is what belongs in the store |
| **R2 bot server** | the console `:3000`, the backend `:8000`, noVNC `:6080`, Sunshine's only peer, the NAS's NFS client, the RDP client | `FRONTEND_ORIGINS`, Sunshine's inbound rules, NFS exports, README URLs | only if the bot stack moves too |
| **R3 "this host"** | a safety identity: Settings refuses writes from it (`lab_host_peer`) | `config.py` `host_lan_ip`, `routes_settings.py` | with R2 |

**This inventory reads "the lab server may soon move off the quant VM to its own machine" as
R1 moving** (rathena, its database and its sniffer, which shares rathena's network namespace),
with the bot stack staying on the VM. If the whole stack moves, the R2 rows move too; they are
listed, but not as store items.

The literal itself is mostly NOT what breaks on a move. The live R1 dependencies are:
`HOST_LAN_IP` as rathena's advertised address, the sniffer's compiled filter and its redaction
port, the shipped suggestion in `environments.yaml`, and three Windows-side items (the firewall
group, the watch, the client's `clientinfo.xml`).

## 2. Summary

**Lines found:**

| What | Lines | Split |
|---|---|---|
| `192.168.1.13` | 111 lines in 32 files | docs 54, tests 46, code and config 11. By role: R1 61 (docs 23, tests 34, code and config 4), R2 43, R3 4, mixed 3 (the `HOST_LAN_IP` defaults in `.env.example` and `init_env.sh`) |
| `HOST_LAN_IP` / `host_lan_ip` | 60 lines | 44 outside docs |
| a game port (6900/6121/5121) | 151 lines | 22 in code and config outside tests and docs |

**Occurrence groups (47 rows in section 3, plus 9 look-alikes in section 4), by how each becomes
config-driven:**

| Category | Rows | Which | A change proposed? |
|---|---|---|---|
| (a) read from the Settings store | 8 | C6, C7, C8, C9, C19; W1, W2, W3 | **code** C6, C7+C8+C9 (one change); C19 is a design note; **Windows** W1, W2, W3 |
| (b) `.env` / compose interpolation already: fine as is | 13 | C1, C2, C3, C4, C5, C11, C12, C14, C15, C18; D2, D4, D6 | small **code** additions in C2, C4 (a check), C12 (optional); docs D2 only on acceptance |
| (c) a doc should POINT to Settings | 10 | C13, C16 (text inside code); D1, D5, D7, D8, D9, D10, D11, D15 | **doc** (C13 ships with a frontend deploy) |
| (d) a test fixture that legitimately pins a value | 7 | T1-T7 | none (they follow their code) |
| (e) history: a dated record | 2 | D12, D13 (and the dated parts of D10, D11, C11) | none |
| not an endpoint, but a move breaks it | 3 | C10, C17, D3 | **code + an ADR**, only at a move |
| R2, out of the store's scope | 3 | D14, W4, W5 | none, unless the bot host moves |
| the source itself | 1 | W6 (the live store) | none |

**Code vs doc:** 9 code rows would change (C2, C4, C6, C7, C8, C9, C12 optional, C13, C16), plus
3 more only at an actual move (C10, C15, C17); 9 doc rows (D1, D2, D5, D7, D8, D9, D10, D11, D15:
D1 and D2 are CLAUDE.md, the parent's, on acceptance); 3 Windows-side acts (W1, W2, W3).
Code needs review and a deploy window; the sniffer change also needs its positive cases re-proved.

## 3. The full list

Columns: **where** (file:line), **what** it is, **role**, **read at run time by**, **how it
becomes config-driven** (a-e), **code or doc**.

### 3.1 Code and config in the repo (outside tests)

| # | Where | What | Role | Read at run time by | How (category) | Code / doc |
|---|---|---|---|---|---|---|
| C1 | `.env.example:5-8, 124` | `HOST_LAN_IP=192.168.1.13`, the template default; its comment says rathena advertises it | R1+R2+R3 | `scripts/init_env.sh` → `.env` → compose interpolation | **(b)** fine as is. At a move, the rathena stack's own `.env` on its machine carries its address; this host's keeps R2/R3 | config, only at a move |
| C2 | `scripts/init_env.sh:12, 18, 33` | the fallback `192.168.1.13` when route detection fails | R1+R2+R3 | first-time setup only | **(b)**; proposal: refuse with a message instead of guessing (a guess would make rathena advertise a wrong address) | code, small, no deploy |
| C3 | `compose.yaml:73, 105-107` (rathena); `:432, 460-462` (rathena-th) | rathena's advertise variable and its published game ports `${HOST_LAN_IP}:6900/6121/5121` | R1 | Docker; rathena's entrypoint | **(b)**: the server's own deployment config. It moves with the server's compose; it does not read the store (rathena cannot: the store is backend-only) | config, only at a move |
| C4 | `services/rathena/conf/import/char_conf.txt.tmpl:12`, `map_conf.txt.tmpl:9`; `services/rathena/entrypoint.sh:6, 36, 55, 67, 69, 80` | `char_ip`/`map_ip: ${HOST_LAN_IP}` (the ADVERTISED char/map address), its checks, and the log line `smoke_test.sh` greps | R1 | rathena at every start | **(b)** + a NEW check (ADR-0021 D17): the backend reports when the lab environment's stored host differs from the address the local rathena advertises (Settings and `/health`), and the lab generator refuses then (ADR-0021 5.7) | code (backend), small |
| C5 | `services/rathena/Dockerfile:84, 86` | `EXPOSE` and the HEALTHCHECK on 6900/6121/5121 (127.0.0.1) | R1 ports | Docker | **(b)**: rathena's own listen ports; they move with the image. Change only if the ports change (then rebuild) | none |
| C6 | `config/environments.yaml:31, 49` (+ header lines 4-7) | `lab-rathena` and `lab-rathena-th`: `server: {host: 192.168.1.13, ports: [6900, 6121, 5121]}` | R1 | read ONCE at the seed (allowed servers are seeded EMPTY), then on every Settings read by `envstore.suggestions()` as "Found by the lab" | **(a)**: the store already wins (ADR-0016); the literal survives as a SUGGESTION. Proposal: offer the lab suggestion only while it equals what the local rathena advertises (C4's check), else none; or drop the host at the move | code (envstore) + config |
| C7 | `packages/poring_packets/src/poring_packets/capture.py:1-11, 18-27` | the sniffer's kernel filter, COMPILED to constants: client 192.168.1.169 + ports 6900/6121/5121; `PORT_SERVER` maps port → login/char/map | R1 ports (+ the Dell) | the sniffer at start | **(a)**: the target is the environment's `windows_host` + its servers' ports (with roles), from the store. HOW the sniffer receives it is open (ADR-0021 D18, section 7 P2). The filter is then built at start (the slim image has no libpcap today: a small builder, tested against libpcap as `test_core.py` already does) | code, sniffer rebuild, positive cases re-proved |
| C8 ➡️ fixed in code f36276e, not deployed (section 5 risk 1) | `packages/poring_packets/src/poring_packets/pcapng.py:4-7, 18, 36` | `LOGIN_PORT = 6900`: the login-password REDACTION keys on it | R1 port | every pcapng write | **(a)**, from the SAME value as C7's login port, and fail closed: no pcapng without a known login port (section 5, risk 1) | code, with C7 |
| C9 | `packages/poring_packets/src/poring_packets/sniffer.py:88, 319`; `replay.py:4, 27, 72` | the role lookup by port; `CLIENT_IP` env with the default `"192.168.1.169"` (it changes the session filter but NOT the compiled kernel filter: a half-wired knob); replay's `--client-ip` default | R1 ports + the Dell | the sniffer; offline replay | **(a)** with C7: ONE target object, no second default | code, with C7 |
| C10 | `services/backend/src/poring_backend/config.py:80`; `compose.yaml:103, 187, 458` | rathena's pinned compose address 10.210.96.6 = the backend's only `/ingest/packets` peer (the sniffer shares rathena's namespace) | not an endpoint | the backend's ingest check | **a move breaks it** (ADR-0021 D19): the sniffer moves with rathena; `:8001` is never published. Needs the remote-attestation design (ADR-0016 "Remote deployment notes": signed attestations), or lab-rathena stays red `no_attestation` | code + an ADR, only at a move |
| C11 | `services/backend/src/poring_backend/config.py:102-106`; `routes_settings.py:26-27, 168` | `host_lan_ip` → the `lab_host_peer` refusal of Settings writes. Line 27 is the dated 2026-10-06 finding | R3 | every Settings write | **(b)**; open point P6: after a move, should the rathena machine also be refused as a writer? | none now |
| C12 | `services/backend/src/poring_backend/config.py:30-31` | the code default `frontend_origins = "http://192.168.1.13:3000"` | R2 | the backend, only outside compose (compose sets `FRONTEND_ORIGINS` from `HOST_LAN_IP`) | **(b)** in practice; optional: an empty default derived from `host_lan_ip` (T3 pins it) | code, optional |
| C13 | `services/frontend/src/lib/settings.ts:89, 261` | UI error text "an IP like 192.168.1.13" and a comment example | R1 (as an example) | the Settings page | **(c)**: a neutral documentation address (e.g. 192.0.2.10) | code (frontend copy), trivial |
| C14 | `compose.yaml:143, 172, 197, 219, 241, 243`; `compose.dev.yaml:94, 95, 112`; `services/frontend/next.config.ts:8-9`; `scripts/bench.py:311` | the bot host's binds, URLs and Origin default, from `HOST_LAN_IP` | R2/R3 | Docker, the backend, the frontend, bench | **(b)**; out of the store's scope | none |
| C15 | `scripts/smoke_test.sh:6, 17, 38-50` | reads `HOST_LAN_IP` from `.env`, probes the three ports, greps rathena's advertise line | R1 (the local server) | a person, after a deploy | **(b)** for a local rathena; at a move it runs where rathena runs, or takes the lab host and ports from the store | code, only at a move |
| C16 | `scripts/ws_probe.py:3-4` | usage examples `http://192.168.1.13:8000` | R2 | nobody (a docstring) | **(c)**: `http://<HOST_LAN_IP>:8000` | doc text in code, trivial |
| C17 | `scripts/lab_servers.py:11-13` | environment id → the LOCAL sniffer container; `record_session`, `measure_delay`, `replay_states` read `/captures` through it | not an endpoint | host scripts | **a move breaks it** (D19): the captures would live on the rathena machine | code + design, only at a move |
| C18 | `compose.yaml:375, 486` | `SNIFFER_SERVER_ID: lab-rathena` / `lab-rathena-th` | an environment id, not an address | the sniffer; the interlock's `server` check | **(b)** fine (`test_lab_servers.py` pins it to the environment ids) | none |
| C19 | `packages/poring_skills/src/poring_skills/l1/session.yaml:28` | `L3.server.address` named as a binding the login concept needs; no value exists yet | R1 (future) | nothing yet | **(a)** design note: when L3 bindings land, the address resolves from the store, never from a KB file | none now |

### 3.2 Tests (category (d): keep; named here)

| # | Where | What it pins | Note |
|---|---|---|---|
| T1 | `services/backend/tests/test_settings.py:37, 106, 177-178, 193-194, 211, 244, 248, 272, 319-321, 456-458, 597` (16 lines of the address, 31 port lines) | the lab address as realistic data: a YAML fixture, the confirm/suggestion/validation/forbidden-flag cases; `:106` and `:272` are the `lab_host_peer` (R3) case | they pin behaviour, not the address. Optional later: a documentation address, so a grep for the lab address finds only live config |
| T2 | `services/backend/tests/conftest.py:145`; `test_interlock.py:45` | interlock config fixtures with the lab servers | keep |
| T3 | `services/backend/tests/test_pacing_and_config.py:52-53, 57` | `:57` pins C12's code default (R2) | changes only with C12 |
| T4 | `services/backend/tests/test_guards.py:470, 851, 877` | compose guards: rathena's `HOST_LAN_IP` interpolation; rathena and rathena-th publish exactly 6900/6121/5121 (its docstring names the compiled filter, the HEALTHCHECK and `smoke_test` as the other users) | keep; they guard C3 and C5 |
| T5 | `packages/poring_packets/tests/test_core.py:146-206` (the filter recompile guard at `:178-183`), `test_actions.py`, `test_interactions.py`, `test_items.py`, `helpers.py` | decoder fixtures on the lab ports and the Dell | keep; with C7 they take the default target from the same object, and the recompile guard becomes a test of the start-time builder |
| T6 | `services/frontend/src/lib/settings.test.ts` (11 lines), `gamefile/gamefile.test.ts` (7), `csp.test.ts` (5: the console's origin, R2) | page logic, the game-file finder, the CSP | keep |
| T7 | `services/vision/acceptance/adr0005.py:27, 128-129` | R2: a forged console Origin, and the host ports vision must NOT reach (SSH, the backend, Ollama) | keep: it targets the BOT host, which does not move with rathena |

### 3.3 Docs

| # | Where | What | Role | How (category) | When |
|---|---|---|---|---|---|
| D1 | `CLAUDE.md:164` | rule 9: layer 1 is "one Block rule per lab exe, for every remote address except 192.168.1.13 and loopback" | R1, living | **(c)**: "a group generated from the lab environment's endpoints in Settings" | the parent, the day W1 lands (ADR-0021 section 14) |
| D2 | `CLAUDE.md:255` | invariant: `char_ip`/`map_ip` "must be `HOST_LAN_IP`" | R1, server config | **(b)** true; add "and equal the lab environment's host in Settings" (D17) | the parent, on acceptance |
| D3 | `CLAUDE.md:342`; `README.md:107` | `/ingest/packets` only from rathena's pinned 10.210.96.6 | not an endpoint | **a move breaks it** (C10) | at a move |
| D4 | `README.md:27, 33, 101-106, 113` | the topology and the ports table, symbolic `HOST_LAN_IP` | R1+R2 | **(b)**: describes this compose; split only at a move | at a move |
| D5 | `README.md:399` | Windows checklist: the client must "point at `HOST_LAN_IP:6900`" | R1 | **(c)**: "the lab environment's login server (Settings → Lab rAthena)" | doc, any time after approval |
| D6 | `README.md:451` | troubleshooting: char/map advertise `HOST_LAN_IP` | R1, server config | **(b)** | none |
| D7 | `README.md:143, 181, 187`; `services/frontend/README.md:9` | console URL, `FRONTEND_ORIGINS` and `BACKEND_PUBLIC_URL` examples with the literal | R2 | **(c)**, low: `<HOST_LAN_IP>` placeholders | optional |
| D8 | `docs/windows-setup.md:74` | the user firewall rule: "Block ... to every address except **the bot server** and loopback" | **R1 worded as R2** | **(c)**, needed: "except the game server's endpoints (Settings) and loopback". Today both are 192.168.1.13; after a move a user following it would allow the wrong machine. (`:43` "your server's address" could point to Settings; `:59` Sunshine's "bot server" is R2 and right.) | doc, user-facing |
| D9 | `docs/client/rathena-client.md:66` | the lab client recipe: `clientinfo.xml`/`sclientinfo.xml` "address 192.168.1.13, port 6900" | R1, Windows-side | **(c)**: point to the lab environment's login server in Settings | doc |
| D10 | `docs/ROADMAP.md:73` (and `:81`) | the interlock row: layer 1 "for everything but 192.168.1.13 and loopback" (current description) and "the only remote 192.168.1.13:5121" (a dated watched login); `:81` Sunshine (R2, dated) | R1 / R2 | **(c)** for the current description, **(e)** for the dated facts | when W1 lands |
| D11 | `docs/adr/0019-windows-stays-clean.md:287, 302` | the watch's purpose and retirement criterion 2 ("excluding only 192.168.1.13 and loopback"): LIVING criteria. (`:113, 121, 236, 275, 311` are audit records and a pointer: (e)) | R1 | **(c)**: "excluding only the lab environment's endpoints in Settings and loopback" (ADR-0021 already plans re-wording criterion 2) | on acceptance |
| D12 | ADR records: `0009:39, 104` (R2); `0013:131` (the watcher amendment), `:180, 209-211` (Part B, deferred design); `0016:270-271` (the ranges applied 2026-10-06), `:296`, `:325-328` (the production option: the lab host and its port complements, the generator's shape), `:415` (the R3 finding); ADR-0021 itself (section 1's layer rows, D10, D19, 5.7 and section 14: its context and plans) | dated decisions and records | R1/R2/R3 | **(e)**: keep, add nothing | none |
| D13 | plans and experiment records: `thai-data-experiment.md:44, 89, 95, 123, 136, 170` (R1); `phase1-plan.md:47-50` (the filter's design: ports + the Dell); `console-capture-plan.md:243, 395, 488`; `s2-plan.md:284, 297`; `phase0-latency.md:286, 298`; `phase3-plan.md:119` (R2) | dated | R1/R2 | **(e)** | none |
| D14 | runbooks: `docs/operations/sunshine-msi-replace.md:10, 73, 85, 95, 110, 132, 138` (Sunshine's peer); `docs/operations/nas-sink.md:36, 62, 94-96` (NFS exports to the VM) | R2 procedures | R2 | out of the store's scope; change only if the bot host moves | none |
| D15 | `config/environments.yaml` header lines 4-7 ("lab host + loopback only") and 14-20 (ADR-0021 D16) | config comments | R1 | **(c)**: point to the generated group and to Settings | on acceptance (a config file: not touched now) |

### 3.4 Outside the repo (from the records; not inspected here)

| # | Where | What | Role | How | Who |
|---|---|---|---|---|---|
| W1 | Windows firewall, group `poring-lab lab-only` | 2 Block rules (the 2021 Ragexe, `PoringLab.exe` in `C:\RO-rAthena\client`), RemoteAddress = everything except 192.168.1.13 and 127.0.0.0/8, any port, any protocol (ADR-0016) | R1 | **(a)** Q6: replaced by the GENERATED `poring-lab env lab-rathena`, from the store (ADR-0021 5.7, a plan) | Batt's elevated console |
| W2 | Windows, `%USERPROFILE%\poring-lab-watch\labwatch.ps1` (task `poring-lab watch`, LAB-ONLY) | kills any exe under `C:\RO-rAthena\client\` that reaches anything but 192.168.1.13 or loopback. Not in the repo: typed in and read back by sha256; `scripts/ro_agent.py:1373-1381` only reads its status | R1 | **(a), carried by hand**: it cannot read Settings (ADR-0019: no channel). Either re-typed by the agent's own shell (a lab-only exception) from the address list Settings shows, read back by sha256, BEFORE any lab endpoint change; or retired under ADR-0019's criteria | the agent's shell, with Batt's approval |
| W3 | Windows, `C:\RO-rAthena\client\data\clientinfo.xml` + `sclientinfo.xml` | the login server the lab client dials: 192.168.1.13:6900 (rathena-client.md) | R1 | **(a), checked**: a person edits the two files at a move; dropping one on Settings' game-file finder lists the endpoint it names, to compare with the lab environment (no code; a "matches environment X" badge would be a small frontend change) | Batt |
| W4 | Windows, Sunshine's two inbound rules | RemoteAddress 192.168.1.13 (ADR-0019 audit) | R2 | out of the store's scope; only if the bot host moves | Batt |
| W5 | TrueNAS, NFS exports 7/8/9 | hosts 192.168.1.13 (nas-sink.md) | R2 | out of scope (Batt's infra) | Batt |
| W6 | the live store, `settings/environments.json` → `lab-rathena.servers` | whatever Batt confirmed | R1 | **the source of truth** itself | Batt (Settings page) |

## 4. Look-alikes that are NOT the lab server

| # | Literal | Where (main ones) | In scope? |
|---|---|---|---|
| X1 | 192.168.1.169, the Dell (`WIN_HOST`): 41 lines | `config/environments.yaml:32, 50` (`windows_host`, a technical field taken from the YAML only), `.env` `WIN_HOST`, C7/C9 (the sniffer), `scripts/rdp_cert_fingerprint.py:3`, tests (`test_nas_drop.py` 7, `poring_packets` tests 10, `test_settings.py` 3, others), docs | **No** for a lab-server move. It enters this work only through C7/C9: the sniffer's copy duplicates `WIN_HOST`/`windows_host` and should come from the same target object |
| X2 | 192.168.1.6, TrueNAS | `compose.yaml:529` (NFS volume), `scripts/nas_drop.py:3, 33`, `nas-sink.md` | No (infra) |
| X3 | 192.168.1.1, the router | `CLAUDE.md:127`, `adr0005.py:129` | No |
| X4 | 192.168.110.55, the operator's MacBook segment | `CLAUDE.md:127` (the subnet health check), `test_packets.py:25, 218`, `test_secret_input.py:30`, `s2-plan.md:284` | No |
| X5 | 192.168.1.50 / .20 / .99 / .170 | test LAN peers and mismatch fixtures | No |
| X6 | 192.168.0.0/16, 192.168.1.0/24, 192.168.96.0/20 | `VIEWER_NETWORKS` default (`config.py:86`), a test, the 2026-09-29 incident (CLAUDE.md, a compose comment) | No |
| X7 | 10.210.96.0/24, 10.210.97.0/24, 10.210.96.250 | compose and agent subnets, db-th's pin | No; only 10.210.96.6 is move-affected (C10) |
| X8 | 127.0.0.1 | Frigate `:5000` and Ollama `:11434` (`scripts/frigate_r3.py:65-66`), the AssistAddr override `127.0.0.1:3000` in the Windows client, rathena's HEALTHCHECK | No (loopback stays allowed in every generated group) |
| X9 | official endpoints (`thro-acc3.gnjoy.in.th:50001/3000`, 49.229.28.13, `49.229.28.99:3000`, `.gnjoy.in.th`, `kro-assit*.ragnarok.co.kr:3000`, Cloudflare 104.18.20.108/.21.108) | `config/environments.yaml`, tests, ADR-0016 | No: FORBIDDEN endpoints are seeded into the store once, then the store wins (already config) |

## 5. The five riskiest occurrences

1. **C8, the password redaction keyed on port 6900** (`pcapng.py`). Today the kernel filter
   passes only 6900/6121/5121, so it covers every login. If the login port ever comes from config
   while this constant stays, a login on another port is written UNREDACTED: plaintext passwords
   in captures. It must move in the same change as C7, from the same value, and fail closed.
   ➡️ **2026-10-09 ~17:10, FIXED IN CODE (Batt: "do it before any endpoint change"; f36276e),
   NOT DEPLOYED.**
   - `pcapng.LoginScrub` takes the login port(s) from `SNIFF_LOGIN_PORTS` (compose sets "6900" for
     both sniffers).
   - Defense in depth: it also scrubs, on ANY port, every connection whose first client payload is
     a login request id (the pinned rAthena login packet db).
   - With the ports unset or invalid it scrubs by that shape alone (fail closed).
   - A continuation segment now keeps no bytes; the old scrub kept 2 per segment.
   - Live only after a guarded `build:sniffer` + `recreate:sniffer` (and the section 2a positive
     cases re-run).
   - C7's filter itself is unchanged (later).
2. **W2, the lab-only watch on Windows.** 192.168.1.13 is typed into a script that has no channel
   to Settings, by design. On a move it kills the lab client at its first connection to the new
   address. It must change, or be retired, BEFORE W3 repoints the client.
3. **C7/C9/C10/C17, the sniffer.** Its kernel filter is a compiled constant; its `CLIENT_IP` knob
   is half-wired (the kernel filter ignores it: change it and the sniffer silently sees nothing,
   so the lab reads `no_session`); and it lives in rathena's namespace with a compose-internal
   ingest. Any change is a rebuild of the safety sensor and a re-proof of its positive cases
   (demonstrations.md §2a); a move leaves lab-rathena red until a remote-attestation design exists.
4. **C6, the shipped suggestion.** After a move, Settings still offers 192.168.1.13:6900/6121/5121
   as "Found by the lab": one "Confirm all" away from re-allowing it, and then from being generated
   into the lab firewall group.
5. **C4 against the store (D17).** rathena advertises `HOST_LAN_IP` for char and map, and the
   client follows the server, not Settings. If the two differ, the generated group blocks the
   char/map hop (login fails after the service select: fail closed, but confusing), or the store
   keeps an address the server no longer uses. Next in line: **D8**, `windows-setup.md:74`, which
   tells a user to allow "the bot server", wrong once the game server is elsewhere.

## 6. The proposed order of changes (smallest blast radius first)

Every step waits for Batt's approval. Nothing has started.

1. **Docs that only point** (no runtime effect, no deploy): D8 (the `windows-setup.md` firewall
   line), D9 (`rathena-client.md`), D5 (`README.md:399`); optional D7 and C16.
2. **Trivial code with no safety role:** C13 (the Settings page's example text; ships with the
   next frontend deploy), C2 (`init_env.sh` refuses to guess; host script, no deploy); optional
   C12 (with T3).
3. **Read-only consistency reporting in the backend** (one guarded `restart:backend`; ASSIST
   survives it): C4's check (the advertised address vs the stored lab host, on Settings and
   `/health`) and C6 (offer the lab suggestion only while it matches). It reports; it changes no
   gate.
4. **The sniffer, as ONE change** (a guarded `build:sniffer` + `recreate:sniffer` in an operator
   window; the automatic GM re-login; the §2a positive cases re-run before any scored run): C7 +
   C8 + C9 → one target object (client address, ports with their roles), the kernel filter built
   at start, the redaction port taken from the login role, fail closed. The delivery from the store
   is Batt's choice (P2). T5 follows.
5. **After ADR-0021 is accepted and its generator is built and reviewed:** W1 (ADR-0021 5.7's
   replacement plan) with D1, D10, D11, D15 the same day; W2 re-typed from Settings' list, or
   retired.
6. **Only at an actual move** (largest blast radius, last): the remote-attestation design (an ADR)
   for C10, C17 and D3; the rathena stack's compose and `.env` on its machine (C1, C3, C5, C15,
   D4); then, in this order: W2 updated → the Settings edit → regenerate → Batt runs the script →
   the paste-back confirms (W1) → W3 (the client's files) → a watched login (green, the only
   remote the new map port, KILLED 0).

**What must NOT change until Batt approves: everything in this document.** No code, config,
compose, test, Windows rule, watch script, Settings entry, CLAUDE.md sentence or other ADR status
changes because this list exists.

## 7. Open points for Batt (where the decision meets the records; flagged, not resolved)

| # | The point | Why it matters |
|---|---|---|
| P1 (ADR-0021 D17) | "Single source of truth" vs the server's own address: rathena ADVERTISES `HOST_LAN_IP` (CLAUDE.md invariant) and cannot read the backend-only store | Proposal: the store is the truth for where CLIENTS may connect; the server's address stays its deployment config; C4's check keeps them equal |
| P2 (D18) | "The sniffer target reads it", but the store is mounted into the BACKEND ONLY (`test_guards.py`) | Options: (i) the backend hands the sniffer its target on the existing ingest connection; (ii) a guarded step renders the sniffer's environment from the store at each recreate (a host read of `./settings`, read-only); (iii) compose values plus a check against the store. Each needs its own review |
| P3 (D19) | A move is more than a Settings edit: the sniffer moves with rathena, its ingest (`:8001`, never published) and its captures (a local volume) do not | The remote-attestation design (ADR-0016 "Remote deployment notes") must exist before a move, or the lab stays red |
| P4 (D20) | Q6 "yes" covers the generator; the question's second half (the `firewall` SIGNAL on lab-rathena) is not restated in the 15:20 text | Adopting it makes an OS lock a required LAB signal, against ADR-0016's History and CLAUDE.md rule 9 ("The interlock itself adds no OS lock") |
| P5 | The watch (W2) cannot read Settings: ADR-0019 forbids a channel | Config-driven only by a person or the agent's shell carrying the value; or retire it |
| P6 | `lab_host_peer` (C11) after a move | Should Settings also refuse writes from the new rathena machine (it runs our processes)? |
| P7 | ADR-0006 says "record that rule here" (the permission record); ADR-0021 4.5 puts the capture evidence in Settings | Both, or Settings with the doc pointing to it? |
| P8 | The community server's `summary` (and any future `capture` field) lives in the STORE after the seed | Editing `config/environments.yaml` changes only a fresh seed; the live text ("packet capture is not allowed on that server") needs a person's edit on the Settings page |
