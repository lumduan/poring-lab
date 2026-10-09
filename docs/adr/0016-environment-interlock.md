---
doc_type: decision
hypothesis: null
status: GO
role: null
verdict_date: 2026-10-04
verdict_ticket: null
supersedes: null
related: []
next_action: "2026-10-06: user-managed environments (Settings page, asymmetric rules, CSRF + rate limit), the game-file finder (in-browser, hostile-file controls, strict CSP) and the typing-only foreground gate are BUILT and live. The lab's Allowed environment is red no_servers until Batt confirms its servers from his own computer; the S2 @stream template was cut and verified 2026-10-07 00:45. ➡️ ADR-0019 (Batt, 2026-10-06): Windows stays clean, so the client-side provider (Part C) and its reporting channel (ADR-0013 Part B) are DEFERRED, and may never be built. The community server stays pending."
---

# ADR-0016: The environment interlock (a LOGIC interlock, config-driven, fail closed)

- **Status:** ACCEPTED (2026-10-04). It is built, and its tests pass (`test_interlock.py`, the
  sniffer and ro_agent tests). The live check is in the S2 session report.
- **History:** PROPOSED on 2026-10-03 with an outbound Windows Firewall rule as signal (iv).
  Batt decided on 2026-10-04 that **the firewall rule is NOT applied in the lab**. The lab must stay
  flexible: future non-rAthena servers and clients. So the interlock is LOGIC checks driven by a
  config allowlist, and OS-level locks belong to production and teaching distributions only (the
  "Production option" section). This document is the accepted rewrite; the original proposal is in
  git history (`git log -- docs/adr/0016-environment-interlock.md`).
- **Implements:** [ADR-0006](0006-sanctioned-test-environments.md) rule 2. Closes
  [issue #2](https://github.com/lumduan/poring-lab/issues/2) for the lab's rAthena; the community
  server stays forbidden for automation (below).
- ➡️ **2026-10-09: [ADR-0021](0021-external-servers.md) (PROPOSED) would amend:** the community
  entry (an `external` kind, signals `lab_host` + a new `firewall`, no `session`); layer 1 (a
  generated group per external environment, allowing only its endpoints, confirmed by Batt's
  paste-back); the forbidden list (the editing guard unchanged, plus a refusal at rule
  generation); the production option (its rule shape adopted for external environments). The
  History line "OS-level locks belong to production and teaching distributions only" would no
  longer hold for external environments: there, a confirmed OS lock is a required signal.

## Rule
The mux accepts a **BOT press** only while the interlock says so; everything else gets
`environment_unattested`.
- **What counts as a press:** a key or button down, a pointer move, a wheel step.
- **When it passes:**
  - BOT mode: only while an `allowed` environment's signals are all green;
  - ASSIST: also while a bounded operator window is open.
- **What is never gated:**
  - releases: key ups, button ups and ReleaseAll always pass. A gated button-up loses its
    coordinates, so a refused bot never moves the pointer;
  - human input.
- **Fail closed:** missing, stale, ambiguous or contradictory signals mean NO, and so does a
  missing or invalid config.
- **Counting:** refusals are counted in `/health` (`refused.bot.environment_unattested`) and shown
  on the console.
- **Green → red:** the backend releases whatever the bot still holds (`interlock_release`, the
  `set_mode` pattern).

## The allowlist: `config/environments.yaml`
The file is committed and holds no secrets. It is mounted read-only at `/lab-config` in the
backend only (`test_guards`). Per environment it holds:
- `id`;
- `status` (`allowed` | `pending` | `forbidden`);
- `adr`;
- `server` (host, ports);
- `windows_host`;
- the `client` profile (exe, shortcut, server-select entry);
- `accounts` (rAthena `login.account_id`s);
- the required `signals`.

**Adding a server or a client is a config entry plus an ADR-0006 entry, never code.** The file
is re-read when it changes.

Today it holds two environments:
- `lab-rathena`: `allowed`, accounts 2000001 (agent) and 2000002 (validation GM), signals
  `[lab_host, session]`;
- `community-bot-testing`: `pending`, no signals. Packet capture is not allowed there, so it can
  never be green.
  - ➡️ 2026-10-09: ADR-0021 (PROPOSED) would give it (once its evidence exists and Batt allows
    it) the `external` kind and the signals `lab_host` + `firewall`, so it CAN be green without
    packets.

## Signals (what each name means is fixed in `poring_backend/interlock.py`)
| Signal | Holds when | Source | The agent can reach it? |
|---|---|---|---|
| `lab_host` | the capture-backend lock is `steady` on `rdp`/`console`, and the backend's `WIN_HOST` is the environment's `windows_host` | `state/capture-backend` (its only writer is `capture_backend.py`), compose env | no |
| `session` | the sniffer's **attestation** is fresh (≤ `attestation_max_age_s` = 10 s) and says: a map session from `windows_host`, open (no FIN/RST) and recent (≤ 60 s since its last packet), for one of `accounts` | `/ingest/packets`: the internal port and rathena's pinned 10.210.96.6 only (ADR-0007) | no |

➡️ 2026-10-09: ADR-0021 (PROPOSED) would add `firewall` (the environment's intended rule set has
the checksum a person last confirmed, and that confirmation is fresh) for EXTERNAL environments,
and recommends `login_screen` and `operator_start` (its sections 4.2 and 7). `lab_host` is reused
as built: it is already sniffer-free.

**The attestation is attestation, never world data** (ADR-0007 ruling).
- It carries `client_ip`, `session_live`, `aid`, `last_packet_age_ms` and `map_conns`. Nothing
  else: a test pins the field set. ➡️ **Amended 2026-10-05 (Batt, "server id + interlock check"):**
  plus `server`, the attesting sniffer's `SNIFFER_SERVER_ID` (required at its start). The
  `session` signal now also requires `server == the environment's id` (else `server_mismatch`;
  an unnamed sniffer never goes green). Why: the Thai-data experiment runs a second rAthena
  (`lab-rathena-th`) whose fresh database gives its accounts the SAME ids as today's, so the
  account list could not tell the servers apart. This was a one-time code change; adding a server
  is again a config entry + an ADR-0006 entry (+ a sniffer that names it).
- The backend hands it to the interlock only. It is never published to a viewer or an agent.

**Known-forbidden endpoints (Batt, 2026-10-05).** The Thai client data's own clientinfo points at
the official Thai RO login, `thro-acc3.gnjoy.in.th:50001` (49.229.28.13 when resolved on
2026-10-05), and the family `*.gnjoy.in.th` (also `roc.gnjoy.in.th`, the registration site). They
are recorded in `config/environments.yaml` as `official-ro-thai`, `forbidden`, with no signals:
never green. For the th client, the defence is scoped to that client's EXE, **never OS-wide**: a
future user may play official Thai RO normally on the Dell, and an OS-wide block would break that
silently.
1. An outbound Windows Firewall rule bound to `C:\RO-rAthena-th\client\PoringLab.exe` only (Batt
   creates it: it needs admin). A firewall blocks IPs, so a DNS name is only as good as its
   resolution at rule time: this is layer 1 only.
2. A live, read-only watch of that exe's TCP connections (by PID and path): any non-lab remote
   address kills the client at once, and it is reported.
3. The sniffer's attestation: the session belongs to `lab-rathena-th`.

What the layers did on 2026-10-05:
- Layer 1 was created 14:20 ICT by Batt and read back:
  - program `C:\RO-rAthena-th\client\PoringLab.exe` only;
  - remote addresses: the five resolved official Thai IPs;
  - it is the only active rule that names any RO exe.
- Layer 2 FIRED at 14:58:33. At CHARACTER SELECT the 2021 exe opened `kro-assit.ragnarok.co.kr:3000`:
  - that is Gravity's kRO service (Cloudflare 104.18.20.108 / .21.108), which layer 1 did not list;
  - the watcher killed the client.
- The address is DATA, not code: `AssistAddr` in the client's
  `lua files\service_<svc>\externalsettings_<svc>.lub`. The known values are:

  | Service | AssistAddr |
  |---|---|
  | kRO (`_kr`) | `kro-assit.ragnarok.co.kr:3000` |
  | kRO (`_kr_sak`) | `kro-assit-s.ragnarok.co.kr:3000` |
  | kRO (`_qm`) | `kro-qm-1a.ragnarok.co.kr:3000` |
  | Thai | `thro-acc3.gnjoy.in.th:3000` |
  | Thai (stage) | `49.229.28.99:3000` |

  All are recorded as known-forbidden (`official-ro-korea`, `official-ro-thai`).
- The th client now carries loose overrides with `AssistAddr = 127.0.0.1:3000`. This is client
  config only (Batt: never patch the exe; rAthena's web auth stays off). With them, login reaches
  in game and the watcher stays silent (`docs/thai-data-experiment.md` section 4).
- The MAIN lab client (`C:\RO-rAthena`) runs the same exe on the same kRO data. So it very likely
  made this call at every character select, though no trace remains to prove it: the DNS-Client
  log and firewall logging are off. Batt: override first, never a new attempt to prove it.
  - It got the same four loose files at 16:23; a watched login at 16:47 made no outbound
    connection.
  - It has no layer 1 rule. A path-scoped watcher (`mainwatch`) like layer 2 runs while the
    agent's shell lives. ➡️ SUPERSEDED: since 2026-10-06 the main client is in the exe-scoped
    layer-1 group, and `mainwatch` was replaced by the durable `poring-lab watch` task (both
    below; ADR-0019 audit, live).
  - **Any new client copy needs the override before its first login.**

**The client profile** (exe path, launch shortcut, server-select entry):
- ro_agent launches only through the profile's shortcut and checks the login screens by their
  templates before it types. That is the login-phase check.
- The backend's gate does not re-verify the exe, because it cannot see Windows processes. See the
  residual risks.

## Operator windows (the login problem, and desktop work)
Before a map session exists (close, launch, login, character select, entering the game) the
`session` signal cannot be green. The agent's own shell work happens outside the game. For both:
- **`scripts/capture_backend.py window login|desktop --seconds N`** is a HOST tool; the agent
  channel can never open one.
  - It writes `state/interlock-window`: `WINDOW`, `OPENED`, `UNTIL`, `SEQ`, `REASON`. The write is
    atomic and read back on the host and in the backend.
  - `N` ≤ 120 s, and the config's `window_max_s` bounds it again.
- **The backend honours a window only:**
  - in **ASSIST**, never in BOT mode;
  - while it has not expired;
  - for the lock `SEQ` it was opened under (any handover ends it);
  - while the lock is steady. The one exception is a `desktop` window during capture_backend's own
    `switching` handover, because it types `tscon` into its shell after moving the lock and
    re-opens the window for the new SEQ.
- **ro_agent opens windows per phase** (`ensure_window`): close, launch, login, character make,
  entering the game, console focus, open-terminal, minimize-consoles.
  - It skips the window when the interlock is already green, or when one of that kind has
    ≥ 25 s left.
- capture_backend opens its own windows before its ro_agent steps, because it holds the mutation
  lock that `window` needs.
- A window is logged by both tools and shown on the console banner, with its seconds left.

## Behaviour per failure
| Situation | Reason | BOT | ASSIST bot side | HUMAN | Visible |
|---|---|---|---|---|---|
| no or invalid config file | `config_missing` / `config_invalid` | refused | refused (a window still opens ASSIST) | allowed | `/health.environment`, banner |
| lock hold / switching | `lock_not_steady` | refused | refused unless a window | allowed | same |
| `WIN_HOST` ≠ `windows_host` | `host_mismatch` | refused | refused unless a window | allowed | same |
| no attestation since boot (sniffer down) | `no_attestation` | refused | refused unless a window | allowed | same |
| attestation older than 10 s | `attestation_stale` (+ the bot's held keys released) | refused | refused unless a window | allowed | age shown |
| attestation from another host | `client_ip_mismatch` | refused | refused unless a window | allowed | same |
| no live map session (not logged in; sniffer restarted since login) | `no_session` | refused | refused unless a window | allowed | same |
| another account in the session | `account_not_lab` | refused | refused unless a window | allowed | the aid is shown |
| only pending/forbidden environments | `env_pending` / `env_forbidden` | refused | refused unless a window | allowed | same |
| an operator window, ASSIST | `window:<kind>` | refused (never in BOT mode) | **allowed** | allowed | window + seconds left |
| ASSIST auto-restore after a guarded restart/recreate | as attested | as attested | as attested | — | `mode_restored` + the banner |

**After a sniffer restart** the account binding is lost until the next login (CZ_ENTER), so the
interlock says `no_session` (fail closed). `ro_agent recover` or a re-login restores it.

➡️ **Automated (Batt, 2026-10-04).** After a guarded `restart:sniffer` or `recreate:sniffer`,
`guarded_build.py` re-logs the GM in by itself with `ro_agent.py recover gm --retries 0
--agent-id auto_recover`.
- **It runs ONLY when all of these hold:**
  - the mux is ASSIST (never BOT);
  - the capture lock is rdp/steady or console/steady;
  - the interlock config is ok;
  - the interlock is not already green.
- **The login goes through the usual login windows**: ASSIST only, opened by ro_agent through the
  host tool. The credentials go as a sensitive batch.
- **One attempt.** A failure, or no green within 20 s, stops guarded_build with rc 1 and a report;
  nothing retries.
- **Logged and visible:**
  - guarded_build's output says `reason=auto_recover`;
  - the backend's input log records the `agent_hello` of `auto_recover` before its events;
  - the console shows "GM auto-recover running" while it is connected (`Status.bot_agents`).
- Tests: `test_guarded_build.py` (the gate, one attempt, which steps trigger it), `test_app.py`,
  `banner.test.ts`.

## Tests (issue #2's five, plus the ones Batt asked for)
`services/backend/tests/test_interlock.py`, `test_ro_agent_shell.py`, `packages/poring_packets/tests/test_core.py`:
1. **Every failure in the table** → red, in BOT and in ASSIST (no window). An attested lab session
   → green for both lab accounts. Pending/forbidden environments are never green.
2. **Expiry:** 9.9 s green, 10.1 s `attestation_stale`. Live in the app: the bot holds W, the
   attestation ages past 10 s, and the status loop releases W (`interlock_release`). The next press
   is refused.
3. **Windows:** ASSIST passes and BOT mode does not. The window file is checked for:
   - expiry;
   - another SEQ;
   - a lock that is switching (a login window) or on hold;
   - > 120 s, or more than the config's bound;
   - an unknown kind;
   - malformed content.
4. **The mux:** each press type is refused; releases pass; a button-up loses x/y; `release_bot`
   releases everything; the human is never gated.
5. **The agent cannot claim green:**
   - no AgentToBackend message carries an attestation or an environment;
   - an attestation sent on `/internal/agent` is dropped;
   - `/ingest/packets` refuses any peer but the sniffer's pinned address;
   - the agent's copy of Status has `environment: null`, while a human's shows it.
6. **No config file** fails closed. **The committed `config/environments.yaml` validates**, and
   its lab accounts and the pending community entry are pinned.
7. **The sniffer's attestation:** live after CZ_ENTER, with the account and age; ended by silence
   (> 60 s) or a FIN/RST. Its field set is pinned (no world data).
8. **ro_agent** opens a window only when needed. An `environment_unattested` refusal raises
   `Unattested`, which `dataset_activity.safe_gm` never retries.

## Residual risks (stated, not hidden)
- **The window in front is not proven to be the attested client.**
  - The interlock proves that a lab-account session from the Dell to our rathena is live. It does
    not prove that the window the bot clicks belongs to it.
  - If Batt ran the community client by hand on the same Windows session while the mux is in
    BOT/ASSIST, the bot could act on it.
  - **Mitigations:**
    - procedural: Batt plays the community server only with the mux in HUMAN;
    - ro_agent verifies the client by its active title bar before typing;
    - the production firewall option below.
- **Windows are trusted to the host operator.** Anyone with a shell on this host can open one.
  That is the same trust boundary as `state/` and `.env`.

## Layer 1 in the lab: the exe-scoped allowlist (Batt, 2026-10-05 evening)

Batt replaced the th client's IP blocklist with an exe-scoped ALLOWLIST for both lab clients. It is
never OS-wide, and never the community client (`RagnarokClassic\Ragnarok.exe`).

➡️ 2026-10-09: ADR-0021 (PROPOSED) would extend this per EXTERNAL environment: a group
`poring-lab env <id>` for a SEPARATE client copy (never the original community client), allowing
only that environment's endpoints, generated from Settings, run by Batt, and confirmed by a
checksum he pastes back. ~~This group stays as it is unless he decides otherwise (its open
question 6).~~ ➡️ Batt, 2026-10-09 ~15:20 (its Q6 yes): this lab group is to come from the SAME
generator, from the lab environment's endpoints in Settings (ADR-0021 5.7: a replacement PLAN,
his console act; nothing changed yet; the `firewall` signal for lab-rathena is still to confirm).

**Why Block rules.** Windows Firewall's Block rules win over Allow, and the default outbound
policy is Allow. So "allow only the lab host and loopback" is ONE Block rule per exe, whose
RemoteAddress is everything else:
- `0.0.0.0-126.255.255.255`
- `128.0.0.0-192.168.1.12`
- `192.168.1.14-255.255.255.255`
- `::2-ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff`

An Allow rule would be inert, so none is added.

**The exes:** 12, the same six in each client folder (`C:\RO-rAthena\client`,
`C:\RO-rAthena-th\client`):
- `2021-11-03_Ragexe_1635926200.exe`
- `PoringLab.exe`
- `PoringLab_s0.exe` ... `PoringLab_s3.exe`

They are listed with sha256 on 2026-10-05.

**Group and rollout:**
- The group is `poring-lab lab-only`.
- Batt runs three agreed lines in an elevated console: create, read back, then remove the old
  `PoringLab TH: block official RO (th exe only)` rule.
- **Status: APPLIED 2026-10-06 ~08:45-08:48** from Batt's elevated console; the agent typed only
  the three agreed lines:
  - line 1 printed `created 12`; line 2 read back 12 rules: enabled, outbound, Block, the 4
    ranges; line 3 printed `old rule left: 0`. Batt then closed the console.
  - Read back again from the agent's NON-elevated shell: 12 rules, 12 distinct exact lab-exe
    paths, ONE address set (the 4 ranges); no rule names the community client; the old th rule
    is gone.
  - Watched main-client login after it: the interlock green `lab-rathena` (aid 2000002), the
    client's only TCP remote 192.168.1.13:5121, the watcher's KILLED count 0.
  - (Prepared 2026-10-05; parked overnight by Batt.)
- **Undo:** `Remove-NetFirewallRule -Group 'poring-lab lab-only'`.
- ➡️ **2026-10-06 ([ADR-0019](0019-windows-stays-clean.md)):** layer 1 is one-time OS config
  with nothing running, so it fits "Windows stays clean" and is the recommended layer for any
  user setup ([docs/windows-setup.md](../windows-setup.md)). The layer-2 watch task is LAB-ONLY;
  it is retired when ADR-0019's criteria hold. Live 2026-10-06 16:40: all 12 rules present and
  enabled. ➡️ **Since 2026-10-06 18:55: 2 rules**, one per exe actually present in
  `C:\RO-rAthena\client` (the 2021 Ragexe and `PoringLab.exe`). ADR-0019's cleanup removed the th
  copy and the `PoringLab_s0..s3` variants, then their 10 rules, and read back `rules: 2`.

This differs from the Production-option template below: that template's IPv4 range also covered
127.0.0.0/8, and its `::/0` blocked ::1.

## Production option (NOT applied in the lab): the outbound firewall rule

➡️ 2026-10-09: ADR-0021 (PROPOSED) would adopt this three-BLOCK shape (no other hosts; the
allowed host on other ports; no UDP) for every external environment, generated per exe from the
Settings store instead of hand-written.
For a production or teaching distribution, an OS-level lock adds an independent layer: Windows
Firewall lets the lab exe reach only the lab server. Block rules win over the default Allow, so it
is three BLOCKs on the program. The **operator** runs this in an elevated console; the agent never
does (UAC):

```powershell
$exe = 'C:\RO-rAthena\client\PoringLab.exe'
$g   = 'poring-lab interlock'
New-NetFirewallRule -Group $g -DisplayName 'poring-lab: PoringLab.exe, no other hosts' `
  -Direction Outbound -Program $exe -Action Block `
  -RemoteAddress '0.0.0.0-192.168.1.12','192.168.1.14-255.255.255.255','::/0'
New-NetFirewallRule -Group $g -DisplayName 'poring-lab: PoringLab.exe, lab host: only 6900/6121/5121' `
  -Direction Outbound -Program $exe -Action Block -Protocol TCP -RemoteAddress 192.168.1.13 `
  -RemotePort '1-5120','5122-6120','6122-6899','6901-65535'
New-NetFirewallRule -Group $g -DisplayName 'poring-lab: PoringLab.exe, no UDP' `
  -Direction Outbound -Program $exe -Action Block -Protocol UDP
Get-NetFirewallRule -Group $g | Format-Table DisplayName, Enabled, Direction, Action   # read back
```

**Undo:** `Remove-NetFirewallRule -Group 'poring-lab interlock'`. A distribution that applies it
would add a third signal (its read-back at session start) to its environment entry.

## Live verification
*(appended after the S2 session, below this line)*

**2026-10-04, ICT (UTC = ICT − 7 h):**

| Time | Path | What happened | Interlock |
|---|---|---|---|
| 09:58 | RDP | the backend recreated with the allowlist and `WIN_HOST` | red `no_attestation` (the old sniffer sent none: fail closed) |
| 10:06 | RDP | the sniffer rebuilt with the attestation | red `no_session`: 1 map connection seen, no account bound (restart) |
| 10:07 | RDP | `ro_agent recover gm`: close/launch/login through **login windows** | `window:login` → **green** `lab-rathena`, aid 2000002, within ~10 s of map entry |
| 10:08–10:12 | RDP → console | `cleanroom start`: capture_backend's own **desktop window** across its handover (tscon typed while the lock was `switching`, the window re-opened for the new SEQ) | rc 0 |
| 10:14 → 11:32 | console (S2) | the GM's map session survived tscon; every in-game tool (B2, B6′, C3) ran green; no `environment_unattested` refusal | **green** throughout (attestation age 0.3–1.0 s) |
| 10:55:58 | console | a 15 s desktop window opened by hand | `/health` showed `window: desktop, 12.6 s left`; at 10:56:16 it was gone (expired; the file stays, ignored) |
| 11:40 | RDP | the sniffer rebuilt again (effectState) | red `no_session` (as designed) → `ro_agent recover gm` → **green** at 11:41 |

Not exercised live: a refusal in BOT mode with the vision loop running. It is covered by the
tests, and BOT mode was never entered this round.

## The environments: user-managed on the web console's Settings page (Batt, 2026-10-06; BUILT)

**History (same day).** The first version kept a per-environment `allowlist.json` written by
`PUT /settings/servers/{env}`, while the environments themselves stayed fixed in
`config/environments.yaml`. Batt's feedback #2 replaced it the same afternoon with the
user-managed set below. That first version is in git history only; nothing reads `allowlist.json`.

**Why:** other people must be able to use the lab without CLI config, and official servers open
and close over time (the old Asiasoft-era Thai server). So people add, rename and delete
environments themselves, and list each one's servers, from the page.

**One type per environment:**
- **Allowed:** the bot may act while the client is connected to one of its servers.
- **Forbidden:** the bot never acts; its endpoints can never be added to any Allowed environment.
- **Pending:** not approved; the bot never acts.

**The store (human-only by construction):**
- `./settings/environments.json`, gitignored, mounted read-write into the BACKEND ONLY
  (`/lab-settings`; `test_guards.py`). vision can write `./data`, so nothing that decides safety
  lives there.
- It is seeded ONCE from the shipped `config/environments.yaml` (marker `.environments-seeded`).
  The shipped set is only a STARTING SET. Allowed environments are seeded WITHOUT servers: their
  shipped servers become suggestions that a person confirms. Forbidden endpoints are seeded as they
  are.
- From then on the store wins. **The interlock reads only the store and fails closed** when it is
  missing or invalid after the seed (`test_settings.py`). An Allowed environment with no confirmed
  server is red `no_servers`.
- Every write is versioned (`revision`, 409 on a stale base), atomic, and read back before
  "Saved and checked ✓".
- `allowlist_audit/YYYY-MM-DD.jsonl` is append-only. It records each change (environment
  create/delete/rename/type/text, server add/remove, seed), which rule applied (easy, normal or
  hard), the revisions, who (peer, Origin, listener), and every refusal.
- Export/import of the whole set is one file (`poring-lab-environments/1`), for sharing a setup
  (the course). It never carries the technical fields (Windows host, accounts, signals, client).
  An import obeys the same rules as editing.

**Asymmetric rules (`envstore.classify`):**
- **Easy (tightening):** create a Forbidden environment, add to a Forbidden list, delete an Allowed
  environment, remove an Allowed server.
- **Normal (loosening an Allowed list):** create or add Allowed. A person confirms it from their own
  browser.
- **Hard (loosening a Forbidden list):** delete a Forbidden environment, remove a Forbidden
  endpoint, or change Forbidden to Allowed/Pending. It needs a typed reason (at least 10
  characters), the subject typed again, and only one hard change per save. It is audited with the
  reason.

**Forbidden matching:**
- Forbidden entries are names, IP literals, and `.domain` (a whole official domain).
- Forbidden names are also re-resolved every 5 min, and their IPs block too, EXCEPT addresses in a
  CDN range (Cloudflare's list, `allowlist.CDN_RANGES`). Those are shared, so the page warns
  instead.
- A NEW allowed server that matches is refused. An existing allowed server that becomes forbidden
  later is flagged on the page and left out of the interlock config (`usable()`).

**The write rule (human-only), enforced in `routes_settings.py` and tested in `test_settings.py`:**
- `PUT /settings/environments` is served only on the public listener; `:8001` gets 404
  `not_public_listener`.
- It must come from a LAN viewer (compose peers and the gateway are refused), with the console's
  allowlisted Origin.
- **Never from the lab host itself** (`lab_host_peer`). Found live on 2026-10-06: the host reaches
  its own published port as 192.168.1.13, a LAN viewer, so any host process could forge the Origin.
- **Never from `WIN_HOST`** (`windows_host_peer`): the bot drives that desktop.
- **A CSRF token** (added with the finder; Batt's requirement 5):
  - `GET /settings/csrf` returns an HMAC token: a per-process secret, valid 1 h.
  - Only the console's origin can read it (CORS).
  - Every write must send it in `X-CSRF-Token`; otherwise 403 `csrf_invalid`.
  - A backend restart invalidates it; the page fetches a fresh one and retries once.
- **A rate limit:** 20 writes per minute per client; otherwise 429 `rate_limited`.
- **A strict body:**
  - Pydantic models with `extra=forbid` and length limits;
  - a 64 KiB body cap (a malformed `Content-Length` is refused, not a crash);
  - `ServerIn.source` limited to `manual|discovered|file`.
- **Control characters** are stripped from every user string before it is stored or logged (no log
  injection).
- Values are only ever serialised as structured JSON: no shell, path, SQL or YAML is built from
  them.
- The agent network is refused before any route (AgentNetworkGuard).
- Every refused write is counted (`dropped_messages.settings_http`) AND audited.
- The agent may READ (`GET /settings/environments` on `:8001`), never write.

**State:** the lab's Allowed environment is red `no_servers` until Batt confirms the lab's servers
("Confirm all" on Lab rAthena) from his own computer. The first confirmation is a person's act; the
agent never does it, by any route.

➡️ 2026-10-09 ~15:20 (Batt, ADR-0021's decisions): endpoints are config, never hard-coded: every
server endpoint, the lab's included, lives in this store (the single source of truth). Where the
lab endpoint is still hard-coded today, and how each place becomes config-driven:
[docs/planning/endpoints-as-config.md](../planning/endpoints-as-config.md) (PROPOSED; nothing
changed yet).

## "Find servers from a game file" (Batt, 2026-10-06; BUILT)

**What:** the person drops a game file onto the Settings page and gets the servers it names, so
nobody has to reverse-engineer a client again. Accepted files:
- a `data.grf` (any GRF);
- `clientinfo.xml` / `sclientinfo.xml`;
- an `externalsettings` `.lub`;
- the game's `.exe`.

**Parsed in the browser, never uploaded** (`services/frontend/src/lib/gamefile/`):
- The file is read by slices through the File API, inside a Web Worker (no DOM, no page state).
- For a GRF (0x200), only these are read:
  - the 46-byte header and the file table;
  - then only `data\clientinfo.xml`, `data\sclientinfo.xml` and
    `data\luafiles514\lua files\service_*\externalsettings_*.lub`.
- Other entries are never read: a test proves the decoy entry's bytes are never touched.
- **Encrypted entries (flags 0x02/0x04) are NOT decrypted.** MIXCRYPT stays study-only and private.
  They are reported as "encrypted, can't read", and the scan continues.
- **Exe:** visible strings only (ASCII and UTF-16LE), `host:port` only. A protected exe is reported
  plainly as "This exe is protected … Drop its data.grf instead.". Protected means a packer
  section name (`.themida`, `.winlice`, `.vmp*`, `UPX*`, …), blank section names (Themida-style),
  or an executable section with entropy ≥ 7.2 bits/byte.
- Only the endpoints the person ticks are sent, through the same `PUT /settings/environments`
  (source `file`, note "found in <file>: <entry>"). Nothing is stored in the browser.

**Every dropped file is HOSTILE.** The threat model and its controls (`gamefile.test.ts`,
`csp.test.ts`, `test_settings.py`):

| Threat | Control |
|---|---|
| 1. Script injection: a "hostname" of `<script>` or `javascript:` on the page that edits the allowlist | Extracted values are rendered as TEXT only: no `innerHTML` / `dangerouslySetInnerHTML`, never a link (a static test scans `src/`). Display names are cut at the first character outside `[A-Za-z0-9 ._-()]`. A strict CSP on every page (`src/proxy.ts`): a per-request nonce + `'strict-dynamic'` for scripts, no inline script, no eval in production (`next dev` needs `'unsafe-eval'`), `object-src 'none'`, `base-uri 'self'`, `frame-ancestors 'none'`, `worker-src 'self' blob:`, `connect-src` = self + the backend. Styles keep `'unsafe-inline'` (two style attributes; CSS cannot run script). Verified live: zero violations on `/`, `/qa`, `/settings`. |
| 2. Parser denial of service | A Web Worker, terminated after 20 s. Caps: file size; table ≤ 64 MB compressed / 128 MB inflated; ≤ 2 000 000 entries; names ≤ 256 bytes; ≤ 64 settings entries; ≤ 1 MB per entry and 8 MB in total inflated; text files ≤ 1 MB; exe ≤ 128 MB; tokens ≤ 260 characters (an overlong token or string run is dropped whole, never cut into a fragment). Inflate stops one chunk past its cap, and past the size the entry declares (the bomb test). All scanning is a linear character loop: no regex on file text. |
| 3. Injection into the backend | A strict grammar on BOTH sides: IPv4, IPv6 or an RFC 1123 hostname; port 1–65535; length limits. The worker's reply is re-validated on the page; the backend validates again. The backend controls are listed under "The write rule" above. |
| 4. Social engineering: a crafted file that makes the person allow an attacker's server | The DEFAULT action blocks: "create a new Forbidden environment", which is the first option, with usable endpoints pre-ticked. Allowed targets come last and are marked "the bot may act there". Choosing one UNTICKS everything and needs an "I run this server, or its owner allows bots" checkbox. Endpoints outside the LAN get an "outside your network" tag and a confirm: "… is OUTSIDE your network. The bot will act on these servers …". Nothing is ever added without the person's button press. |
| 5. Settings writes | The CSRF token and the rate limit above, on top of the existing origin/host rules. |
| 6. The inflate library | None: the platform's own `DecompressionStream("deflate")`, so nothing to license-check or pin (`THIRD_PARTY.md`). |

IPv6 endpoints are recognised but cannot be allowed or blocked: the lab's checks are IPv4. The
page says so.

## The typing-only foreground gate (Batt, 2026-10-06; BUILT)

Before a BOT batch TYPES (any key down: keys, chords, chat, hotkeys), the lab client must be the
foreground window.

**Evidence:**
- The client's ACTIVE title-bar signature (ro_agent's matcher, now `poring_backend/signature.py`).
- It is taken on a frame captured ≤ 400 ms ago (`CITED_MAX_AGE_MS`, judged by capture time), on
  the path the bot sees: the S2 bus in console mode, else X.
- Each path has its own template in the human-only store: `settings/foreground/`, installed by
  `scripts/foreground_template.py` with an sha256 read-back.
- No template for the path → `foreground_uncalibrated`, fail closed. The S2 path stayed refused
  until its `@stream` template was cut (Batt's answer 2).
  - ➡️ **Cut and installed 2026-10-07 00:40–00:45**, in the unattended clean room after training
    (sha256 `5d488da8…`).
  - Pre-registered limits: active ≤ 6 (measured 0.0 three times, then 0.4 after re-activation);
    inactive ≥ 15 (visible but unfocused 29.5; covered by the shell 163.7).
  - Live on the frame bus with no operator window: unfocused → refused `client_not_foreground`
    (29.52, frame 31 ms); active → ok (0.4, 16.5 ms).

**On refusal:**
- Only the batch's KEY events are refused (`client_not_foreground`, `foreground_stale_frame`,
  `foreground_uncalibrated`).
- The bot's held keys are released (`InputMux.release_bot_keys`); its held mouse buttons are not.
- The refusal is logged, counted, shown on the console banner, and reported in `Status.foreground`
  (null in the agent's copy) and `/health.foreground`.

**Never gated:** clicks, moves and the wheel (Batt: the console shows the mode badge instead, like
a camera LED), key releases, and ReleaseAll.

**Exemption (Batt's answer 1):**
- While a `desktop` operator window is open (ASSIST only, ≤ 120 s, tied to the lock SEQ). These are
  the agent's own console steps: ro_agent console lines, capture_backend's TSCON, launch's Win+D.
- Logged as `foreground_exempt_desktop_window`.

**Live, RDP, 2026-10-06 14:18-14:20:**
- the desktop in front: Shift refused, distance 189.27 (threshold 6.0);
- the client's service-select screen in front: Shift passed, distance 0.87;
- the paced Alt+F4 passed.

## The client-side evidence provider (DEFERRED by ADR-0019; was PROPOSED, Part C)

➡️ **DEFERRED, 2026-10-06 ([ADR-0019](0019-windows-stays-clean.md), "Windows stays clean").** It
needs the Windows-side reporting channel (ADR-0013 Part B), which that principle rules out. A
remote server without a sniffer must first be attested server-side; ADR-0019 lists the
candidates: pixels, the network, or signed attestations from a server we host.
➡️ 2026-10-09: it stays deferred; ADR-0021 (PROPOSED) is the alternative for external servers
(prevention by a confirmed exe-scoped rule set, with no Windows-side reporting). Kept as
history:

- A new signal `client_endpoint`: green when a fresh (≤ 10 s) watcher report shows the
  environment's client exe with an ESTABLISHED remote in that environment's allowlist (DNS names
  through their resolved IPs).
- Each environment declares its providers in `environments.yaml`. The home lab keeps
  `[lab_host, session]` (the LAN sniffer is stronger) and may add `client_endpoint`. External
  servers use `client_endpoint`.
- Fail closed: no report, stale, not listed, or the provider missing means red.

## Remote deployment notes (design only, later; Batt 2026-10-06)

- **Remote monitoring through Cloudflare Access.**
  - Only the console (`:3000`) and the public listener (`:8000`) are exposed, through an Access
    application. `:8001` is NEVER exposed.
  - The backend VALIDATES the `Cf-Access-Jwt-Assertion` JWT itself (the team's JWKS, the
    application's `aud`, expiry). The Access identity (email) then becomes the audit log's "who".
  - Settings writes require an identity on a backend-side allowlist of operator emails. A missing
    or invalid JWT is refused, as today's missing Origin is.
- **A remote server we host (signed attestations).** The sniffer there signs each attestation
  (Ed25519, with a key generated on that host). The backend pins the public key per environment
  in `environments.yaml` and refuses unsigned or stale attestations. The LAN-only ingest peer pin
  then becomes key-based.
