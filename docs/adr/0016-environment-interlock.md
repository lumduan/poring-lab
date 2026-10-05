---
doc_type: decision
hypothesis: null
status: GO
role: null
verdict_date: 2026-10-04
verdict_ticket: null
supersedes: null
related: []
next_action: Live check in the S2 session (GM in game -> green; a login window; expiry -> red + releases). The community server stays pending until its own signal set and evidence exist.
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

## Signals (what each name means is fixed in `poring_backend/interlock.py`)
| Signal | Holds when | Source | The agent can reach it? |
|---|---|---|---|
| `lab_host` | the capture-backend lock is `steady` on `rdp`/`console`, and the backend's `WIN_HOST` is the environment's `windows_host` | `state/capture-backend` (its only writer is `capture_backend.py`), compose env | no |
| `session` | the sniffer's **attestation** is fresh (≤ `attestation_max_age_s` = 10 s) and says: a map session from `windows_host`, open (no FIN/RST) and recent (≤ 60 s since its last packet), for one of `accounts` | `/ingest/packets`: the internal port and rathena's pinned 10.210.96.6 only (ADR-0007) | no |

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
    agent's shell lives.
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
- **Status:** prepared on 2026-10-05; applying it is parked to the next morning (Batt).
- **Undo:** `Remove-NetFirewallRule -Group 'poring-lab lab-only'`.

This differs from the Production-option template below: that template's IPv4 range also covered
127.0.0.0/8, and its `::/0` blocked ::1.

## Production option (NOT applied in the lab): the outbound firewall rule
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
