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
  else: a test pins the field set.
- The backend hands it to the interlock only. It is never published to a viewer or an agent.

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
