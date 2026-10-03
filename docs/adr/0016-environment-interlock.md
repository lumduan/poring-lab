---
doc_type: decision
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Batt OKs (or edits) the outbound firewall rule for PoringLab.exe and the signal set; then build the mux gate + the sniffer attestation with the tests below. Closes issue #2 when built.
---

# ADR-0016: The environment interlock (fail closed, defence in depth)

- **Status:** PROPOSED (2026-10-03). Design only; **nothing is built**.
- **Implements:** [ADR-0006](0006-sanctioned-test-environments.md) rule 2, and closes
  [issue #2](https://github.com/lumduan/poring-lab/issues/2) when built.
- **Blocks:** Phase 4, together with ADR-0005.

## Rule
The mux accepts BOT input, and the bot side of ASSIST, **only while a verifiable signal says the
session is on the lab's rAthena**. Everything else is refused with reason
`environment_unattested`, counted and logged.

- Human input is never affected.
- The agent cannot set, claim or see the attestation, only the refusals.
- Missing, stale, ambiguous or contradictory signals all mean NO.

## Signals
| # | Signal | Source | Strength | Fakeable by |
|---|---|---|---|---|
| i | The target is the lab Dell | The capture-backend lock + the paired Sunshine host / RDP host (`WIN_HOST`). The session the mux drives is the Dell's. | structural | nothing in the agent's reach |
| ii | **Session attestation** | The sniffer (ADR-0007) sees a **live map-server connection** from the Dell (`CLIENT_IP`) to OUR rathena (`:5121`) for the lab agent's **account id**, refreshed in the last N s (default 10 s). It sends the backend an internal-only field: `{server: "lab-rathena", aid, age_s}`. | strong | no one: it is our own server's traffic, seen on our host |
| iii | Login-phase evidence | The client was launched from the PoringLab profile (the "Ragnarok Offline" shortcut → `C:\RO-rAthena\client\PoringLab.exe`). The backend's OWN grab matches the server-select template "PoringLab LAN (rAthena)". | medium | a look-alike screen (hence iv) |
| iv | **Outbound firewall rule** | Windows Firewall lets `PoringLab.exe` reach only `192.168.1.13` TCP 6900/6121/5121. | structural | an admin on the Dell (Batt) |

**ADR-0007 ruling for (ii):**
- The sniffer contributes a yes/no plus the aid and freshness. That is **attestation, never world
  data**.
- No position, HP or entity data goes with it, and it reaches the mux only. It is never sent to an
  agent (`poring_packets` stays out of vision; test_guards).

## The login problem (chicken and egg)
Typing the login happens BEFORE any map connection exists, so (ii) cannot yet be green.

**The login phase** is a narrow, time-boxed window. It is allowed only when ALL of these hold:
- (i) holds;
- (iii) holds, re-checked by the backend's grab right before each batch;
- (iv) was read back at session start;
- the batch is one of the login step types: a `sensitive` credential batch, the server-select
  click, character select, Enter.

The window closes at map entry. **From then on (ii) must turn green within 20 s**, or the mux fails
closed and releases everything.

The lab's credentials are worthless on any other server, and (iv) makes the lab exe physically
unable to reach one.

The community server is **out of scope here**. ADR-0006 forbids packet capture there, so (ii) does
not exist for it. It stays forbidden for automation until its own signal set is designed and Batt
records the permission evidence.

## Behaviour per failure
| Situation | BOT | ASSIST, bot side | HUMAN | Visible |
|---|---|---|---|---|
| no attestation (fresh boot, sniffer down, not logged in) | refused | refused | allowed | `/health.environment`, Status, a console banner |
| attestation older than N s | refused | refused | allowed | same; the age is shown |
| another account id on the map connection | refused | refused | allowed | `aid_mismatch` |
| map connection to anything but our rathena (nothing seen by the sniffer) | refused | refused | allowed | `no_session` |
| login phase: template (iii) not matched | login batch refused | refused | allowed | `login_unverified` |
| firewall rule (iv) not read back at session start | login phase refused | refused | allowed | `firewall_unverified` |
| ASSIST auto-restore after a guarded restart | ASSIST returns, but its bot side stays refused until attested | — | — | `mode_restored` + the banner |

## Tests (issue #2's five, plus three)
1. No signal → every BOT event refused, in BOT and in ASSIST; human input passes.
2. Attested rAthena → accepted; the attestation **expires** after N s without a refresh, and the
   mux fails closed again.
3. Profile mismatch (another aid / another server) → refused.
4. `/health`, Status and the banner show the state.
5. Unit tests in `test_mux.py` / `test_app.py`.
6. **The agent cannot claim it:** no `AgentToBackend` message, field or route carries an environment
   (a guard test like the clipboard one).
7. **Only the internal ingest sets it:** `/ingest/packets` already admits only the internal port and
   rathena's pinned `10.210.96.6` (ADR-0007). A forged attestation from anywhere else is refused
   and counted.
8. **Login phase:** a non-login step type during the login phase → refused; the phase times out
   → refused; map entry without (ii) within 20 s → fail closed + ReleaseAll.

## The firewall rule (iv): PROPOSED for Batt, to be applied only on his OK
Windows Firewall's default outbound policy is Allow, and **block rules win over allow rules**. So
the rule is three BLOCKs on the program, and the only outbound traffic left for `PoringLab.exe` is
TCP to `192.168.1.13:6900/6121/5121`. `RagnarokClassic` (the community client) is untouched.

Batt runs this in **his elevated console**; the agent never does (UAC):

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
# read back
Get-NetFirewallRule -Group $g | ForEach-Object {
  $_ | Select-Object DisplayName, Enabled, Direction, Action
  $_ | Get-NetFirewallApplicationFilter | Select-Object Program
  $_ | Get-NetFirewallAddressFilter | Select-Object RemoteAddress
  $_ | Get-NetFirewallPortFilter | Select-Object Protocol, RemotePort }
```

**Undo:** `Remove-NetFirewallRule -Group 'poring-lab interlock'`.

**Verification after applying:**
1. Login, char select and map entry still work (the normal login).
2. The lab can read the rule set back without admin (`Get-NetFirewallRule`) at session start:
   that read-back is signal (iv).
