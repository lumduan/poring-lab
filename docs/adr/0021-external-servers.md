---
doc_type: decision
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [ADR-0006, ADR-0007, ADR-0013, ADR-0016, ADR-0019, ADR-0020, ADR-0004, ADR-0009]
next_action: "Still PROPOSED (Batt has not accepted it). Batt answered on 2026-10-09 ~15:20: endpoints are config, never hard-coded (lab included); capture is DEFAULT-OFF with a per-environment, evidence-backed permission (Q2, corrected); Q5, Q6, Q7, Q10, Q11 yes; Q1, 3, 4, 8, 9, 12, 13, 14 DEFERRED until a real external server is chosen (section 'Decisions of 2026-10-09'). Next: Batt reviews the endpoint inventory (docs/planning/endpoints-as-config.md) BEFORE anything changes, and the open points it flags (D17-D20). NOTHING is built: the community/dev bot-testing server is still Pending in Settings and its permission evidence is pending. The only related code in flight is the Packet timeline's source state on feat/console-layout, whose `external` state stays dormant until this ADR is accepted. On acceptance: the pointers added to ADR-0006/0007/0013/0016/0019/0020 and community-server.md become amendments, and the parent updates the CLAUDE.md sentences listed in section 14."
---

# ADR-0021: External servers -- the bot on an allowed server we do not run (pixels only, no packet capture by default, a default-deny firewall that a person confirms)

- **Status:** PROPOSED (2026-10-09). Design only. **No implementation now** (Batt): the
  community/dev bot-testing server is still Pending in Settings. Batt's answers of 2026-10-09
  ~15:20 are recorded in the next section; they do not change the status.
- **Asked for by:** Batt, 2026-10-09 ~14:40. His brief is quoted verbatim in Appendix A; the
  decisions below are his. What this document adds is marked **Proposal** or **Recommendation**.
- **Amends (on acceptance; pointers added 2026-10-09, nothing rewritten):**
  - [ADR-0006](0006-sanctioned-test-environments.md): the community server's row and rule 2;
  - [ADR-0007](0007-packet-ground-truth-channel.md): the viewer channel's state on an external
    server; the pixels-only calibration becomes the only path there;
  - [ADR-0013](0013-windows-status-indicator.md) Part B: remote attestation without a Windows
    channel;
  - [ADR-0016](0016-environment-interlock.md): the community entry, the signals, layer 1, the
    forbidden list's role, the production option;
  - [ADR-0019](0019-windows-stays-clean.md): the known need "attest a REMOTE server that has no
    sniffer", the user setup, the watch's retirement criteria 2 and 5;
  - [ADR-0020](0020-block-programming-flows.md): lint layer 6 and the flow safety rules (not in
    Batt's list; its text says flows never run on the community server, so it is amended too);
  - [docs/environments/community-server.md](../environments/community-server.md): its status box.
- **Builds on, unchanged:** ADR-0002 (one input writer, the mux), ADR-0004 (human-only clipboard
  and files), ADR-0005 (vision isolation), ADR-0009/0014 (one session, one display path).

## Decisions of 2026-10-09 ~15:20 (Batt)

Batt's words, verbatim (the status stays PROPOSED: he has not accepted the ADR):

> d. ADR-0021 (status stays PROPOSED):
>    - ENDPOINTS ARE CONFIG, NEVER HARD-CODED (Batt). The lab firewall already allows only the lab host
>      (since 10-06), but the lab server may soon move off the quant VM to its own machine. So:
>        * every server endpoint (lab and external) lives in the Settings environments store, the single
>          source of truth; the firewall script, the interlock, the sniffer target and the docs read it;
>        * the same generator produces the lab's own firewall group too (Q6: yes), so moving the lab server
>          = edit the environment in Settings -> regenerate -> Batt runs the reviewed script -> paste-back
>          checksum confirms;
>        * inventory every place that hard-codes the lab endpoint today (192.168.1.13 and its ports in
>          scripts, compose, environments.yaml, windows-setup.md, tests, docs) and list how each becomes
>          config-driven; report the list before changing anything.
>    - CAPTURE (Q2, corrected): no capture BY DEFAULT on external servers. Exception: capture is allowed only
>      when that server's own rules explicitly permit it, recorded per environment in Settings (a capture
>      permission field, off by default, with the server's rule text/link as evidence, enabled only through
>      the hard path of ADR-0016's asymmetric rules). This keeps ADR-0006's condition, with default-off as
>      the tightening.
>    - Q5 yes (read-back may only turn red); Q7 yes (gate all presses); Q10 yes (refuse irreversible blocks
>      and free chat in v1); Q11 yes (always stop on mismatch / unexpected map; off-console notify later).
>    - Q1, 3, 4, 8, 9, 12, 13, 14: deferred until a real external server is chosen.

**Where each answer lands in this ADR:**

| Answer | Section(s) now | What changed |
|---|---|---|
| Endpoints are config | 3 (item 6), **4.6** (new), 14 | Every endpoint lives in the store; the readers are named. **The inventory of today's hard-coded lab endpoint, and how each becomes config-driven, is [docs/planning/endpoints-as-config.md](../planning/endpoints-as-config.md)** (PROPOSED; nothing changes until Batt approves it) |
| Q2, capture (corrected) | 2 (D3), 3 (item 2), 4.1, **4.5** (new: the field design), 8, 9.3, 10 (S3, S5), 11, 12, 14 | "No capture, whatever the rules allow" is replaced by DEFAULT-OFF plus a per-environment, evidence-backed, hard-path permission; ADR-0006's condition stands |
| Q5 yes | 5.6, 12 | The lab-only read-back may turn the signal red, never green: decided |
| Q6 yes | **5.7** (new), 12, 14 | The lab's own group comes from the same generator; the replacement of `poring-lab lab-only` is a plan (Batt's console act). The `firewall` SIGNAL for lab-rathena is flagged for confirmation (D20) |
| Q7 yes | 6.3, 12 | ALL bot presses gated on external environments: decided |
| Q10 yes, Q11 yes | 9.2, 9.4, 12 | Irreversible blocks and free chat refused in v1; always stop on a mismatch / `unexpected_map`; an off-console notification later |
| Deferred: Q1, 3, 4, 8, 9, 12, 13, 14 | 12 (and where each is cited) | Marked DEFERRED until a real external server is chosen; their text and the recommendations stay |

Where these answers meet the records in ways this document does not resolve, section 2 says so
(D17-D20).

## 1. Context: the system today (as the records say, 2026-10-09)

| Piece | What it is today | Source |
|---|---|---|
| Sanctioned environments | Two: our rAthena (and its stopped Thai-data twin, 1b) and ONE community bot-testing server. Everything else is forbidden | ADR-0006 |
| The community server | Evidence PENDING, so forbidden for automation. Its entry is `pending` with NO signals ("packet capture is not allowed there"), so it can never be green. Batt may play there by hand | ADR-0006, ADR-0016, community-server.md, `config/environments.yaml` |
| Packet capture on the community server | "No packet capture or modification unless the server's rules explicitly allow it" | ADR-0006 table; CLAUDE.md rule 9 |
| The interlock | A LOGIC interlock over the user-managed set (`settings/environments.json`). An allowed environment is green when ALL its signals hold: `lab_host` (lock steady, `WIN_HOST` = its `windows_host`) and `session` (the sniffer's attestation ≤ 10 s old: a live map session from `windows_host`, `server` = this environment's id, a listed account). Its server list gates only by being empty (`no_servers`); the live connection is never compared with it | ADR-0016; `interlock.py` `_env_signals` |
| The sniffer | Captures in rathena's network namespace: it sees our server's traffic only. It cannot see the Dell's traffic to any other server | ADR-0007 context |
| Layer 1 (Windows) | Group `poring-lab lab-only`: ONE outbound **Block** rule per LAB exe whose RemoteAddress is everything except 192.168.1.13 and loopback (4 ranges, any port, any protocol). 2 rules since 2026-10-06 18:55: `2021-11-03_Ragexe_1635926200.exe` and `PoringLab.exe` in `C:\RO-rAthena\client`. Never OS-wide, never the community client (`RagnarokClassic\Ragnarok.exe`) | ADR-0016 "Layer 1 in the lab"; ADR-0019 audit |
| Layer 2 (Windows, LAB-ONLY) | The `poring-lab watch` task kills any exe under `C:\RO-rAthena\client\` that reaches anything but 192.168.1.13 or loopback | ADR-0013 amendment; ADR-0019 |
| The forbidden list | An EDITING guard (a new allowed server that matches is refused) and a CONFIG filter (`usable()` drops an allowed server that later matches; names re-resolved every 5 min; CDN ranges warn instead) | ADR-0016 "Forbidden matching"; `envstore.usable` |
| Settings writes | Human-only: public listener, LAN viewer with the console's Origin, CSRF token, 20/min, 64 KiB body, never `:8001`, never the lab host (`lab_host_peer`), never `WIN_HOST` (`windows_host_peer`), every refusal audited | ADR-0016 "The write rule" |
| Windows | Stays clean: the game, its one-time config, Sunshine. One-time OS config with nothing of ours running (an exe-scoped firewall rule) is allowed; a script of ours that RUNS, a key, or a reporting channel is not. A new Windows-side piece needs a NEW ADR showing why each server-side option fails | ADR-0019 |
| Windows → Mac text | No clipboard path (RDP clipboard `text-to-remote` only). "Reverse text goes through a file on `\\tsclient\transfer`", which exists only on the RDP path | ADR-0004 |

## 2. Where Batt's brief and the records differ

Accuracy first: each row says what the brief assumes, what the documents say, and what this ADR
does about it. None of these changes Batt's decisions; they change how they are written down.

| # | The brief | The records | This ADR |
|---|---|---|---|
| D1 | The exe-scoped rules "change from 'block listed ranges' to 'allow ONLY the allowlisted endpoints'" | Layer 1 is ALREADY an allowlist in effect: "allow only the lab host and loopback", written as ONE Block rule per exe on the complement (ADR-0016: decided 2026-10-05 evening, applied 2026-10-06 ~08:45). The "block listed ranges" rule was the th exe's blocklist of five official IPs (2026-10-05 14:20), replaced on 2026-10-06. An Allow rule is inert under the default outbound Allow, because Block wins | "Allow only X" stays Block-on-the-complement. What changes is the allowed SET (the lab host → the environment's endpoints) and the grain (per port, the Production option's shape, ADR-0016) |
| D2 | "the existing exe-scoped Windows firewall rules for the RO executables" | They cover only the 2 LAB exes. Rule 9 and ADR-0016: "never the community client"; ADR-0006, community-server.md and windows-setup.md: the community client stays **untouched**, a separate copy per server | **Proposal:** the bot uses a NEW separate client copy for each external environment; the original community client stays untouched and outside every rule (open question 1, DEFERRED) |
| D3 | "core principle 2" forbids capturing an external server's packets | The repo has no numbered principles list (searched 2026-10-09). "Principle 2" is used by ADR-0007 and phase1-plan.md for "no packet data at decision time"; ADR-0006 uses "principle 1" for pixels in / input out; the README's one "Core principle" allows sniffing as offline ground truth. None of them forbids CAPTURE; the community rule is ADR-0006's "unless the server's rules explicitly allow it" | ~~Recorded as a NEW decision that TIGHTENS ADR-0006: no capture on an external server, even where its rules allow it (open question 2 asks Batt to confirm the closed door)~~ ➡️ **Batt, 2026-10-09 ~15:20 (Q2, corrected): capture is DEFAULT-OFF; allowed only where that server's own rules explicitly permit it, recorded per environment in Settings (section 4.5).** ADR-0006's condition stands; default-off is the tightening |
| D4 | The Forbidden list "moves from a runtime gate to an EDITING guard" | It already is an editing guard (since 2026-10-06), plus a config filter (`usable()`). It never gated live connections: the interlock never compares the live connection with it | The change is small: the editing guard stays as is; NEW, the rule-set generator refuses (fails closed) a rule set that would admit a forbidden or CDN address (section 4.4) |
| D5 | "The only gate is the ALLOWLIST of server endpoints" | For the lab, the real proof is the sniffer's attestation; the endpoint list gates only by being non-empty | For external environments the firewall makes the endpoint list the real gate, as Batt intends |
| D6 | "the bot works normally ... it decides from pixels only" | Its perception and L2 bindings are calibrated for the LAB client: the 2021 kRO exe, English UI text, 1280×720, the login/foreground templates, cursor references, a detector trained on lab frames | "Normally" holds only for a client copy that is identical to the lab's. Another client or locale needs its own L2 calibration first; `resolve()` already fails closed until then |
| D7 | (not mentioned) | The `session` signal also proves, implicitly, that the client is IN GAME with one of OUR accounts. Clicks are not foreground-gated (ADR-0016, typing-only) | External environments lose that. Section 6.3 holds the replacement (open question 7, DECIDED 15:20: gate all presses) |
| D8 | Packet tools report "not available" | `record_session.write_packets` writes `packets.jsonl.gz` from the lab sniffer's window whatever it holds. On an external session it would be EMPTY, and every scorer would read "0 safety events": the failure demonstrations.md §2a forbids | The manifest carries the environment and `packets: not_captured_by_design`; no packets file is written; every tool checks the manifest first (section 8) |
| D9 | (ADR-0020 not listed) | ADR-0020 lint layer 6 and its safety rules: flows never run on the community server, only on an "attested" environment. Its `verified` means "both paths passed for the active client, server and locale", which an external server can never satisfy (alone-tests are scored with packets) | ADR-0020 is amended too (pointer added). "Verified in the lab" is defined in section 9.2 |
| D10 | (not mentioned) | ADR-0019's watch kills any exe under `C:\RO-rAthena\client\` that reaches a non-lab address; retirement criterion 2 says "excluding only 192.168.1.13 and loopback", criterion 5 "green only on a fresh lab-session attestation", criterion 1 "no new client copy is being tried" | An external client copy must live outside `C:\RO-rAthena\client\` (the watch kills any exe there that reaches a non-lab address); **Proposal:** its own folder outside `C:\RO-rAthena\`. Adding one re-opens criterion 1; criteria 2 and 5 are re-worded on acceptance |
| D11 | Batt pastes the script's output back into Settings | No Windows → Mac clipboard path (ADR-0004); the reverse-text path is a file on `\\tsclient\transfer`, RDP path only; Settings refuses writes from `WIN_HOST` | The paste goes: script output → a file in `\\tsclient\transfer` → downloaded in the console's transfer panel on Batt's own computer → pasted into Settings (section 5.3) |
| D12 | (implicit) | ADR-0016 History (2026-10-04): "OS-level locks belong to production and teaching distributions only"; CLAUDE.md: "The interlock itself adds no OS lock" | Still literally true (Batt applies the lock, the interlock does not), but for an external environment a CONFIRMED OS lock becomes a REQUIRED signal |
| D13 | Optional signal: the server name on the login screen | Partly exists: ro_agent checks the login screens by templates before it types, and each client profile has a `server_select` entry; ADR-0019 lists it as server-side candidate (a) | Weighed in section 7 |
| D14 | "an allowed EXTERNAL server (e.g. a community/dev server that permits bots)", as a class | ADR-0006 sanctions exactly two environments; adding a server is a Settings entry plus an ADR-0006 entry. The community server's 2026-09-30 observation (a client resembling the official Thai Ragnarok Classic service) is unresolved: the record must name the exact host | Every external server needs its own ADR-0006 entry and permission record (open question 3, DEFERRED). Nothing here relaxes ADR-0006 rule 1 |
| D15 | "(one-time client config, already permitted by ADR-0019)" | ADR-0019 allows "one-time OS config with nothing of ours running (an exe-scoped firewall rule ...)". Firewall rules are OS config, not client config. "A poring-lab program, script ... that RUNS" is NOT allowed, and a Windows-side piece for a new need requires the server-side analysis | Section 10 argues it explicitly |
| D16 | (record drift, found here) | `config/environments.yaml`'s header says `lab_host` also checks "the sniffer's client_ip"; the code checks `client_ip` under `session`, so `lab_host` is already sniffer-free | External environments can reuse `lab_host` as built. The comment is fixed on acceptance (section 14) |
| D17 | 15:20: the store is "the single source of truth" for every endpoint, lab included | rAthena ADVERTISES its char/map address itself (`char_ip`/`map_ip` = `HOST_LAN_IP`, CLAUDE.md invariant; `services/rathena/conf/import/*.tmpl`), and the client follows what the server advertises, not what Settings holds. rathena cannot read the store (it is mounted into the backend only) | **Flagged, not resolved.** Proposal (4.6): the store is the truth for where CLIENTS may connect; the server's own address stays its deployment config; a check makes the two agree and fails loudly when they differ |
| D18 | 15:20: "the sniffer target ... read[s] it" | The human-only store is mounted into the BACKEND ONLY (`test_guards.py`; CLAUDE.md "The human-only settings store"). The sniffer's target today is a COMPILED kernel filter (`capture.py`: the Dell's address and ports 6900/6121/5121), and the login-password redaction keys on port 6900 (`pcapng.py`) | **Flagged, not resolved.** How the sniffer receives its target from the store (and keeps the redaction port tied to it) is a design decision for Batt; the inventory lists the options |
| D19 | 15:20: "moving the lab server = edit the environment in Settings -> regenerate -> Batt runs the reviewed script -> paste-back checksum confirms" | The sniffer runs in rathena's network namespace (it moves WITH the server) and posts its attestation to the backend's internal `:8001`, which is never published, from rathena's pinned compose address (`INGEST_PEER` 10.210.96.6); banked captures live in a local volume that host scripts read through the local container (`scripts/lab_servers.py`). The lab-only watch on Windows hard-codes 192.168.1.13 and has no channel to read Settings (ADR-0019) | **Flagged, not resolved.** The Settings edit and the firewall cover the CLIENT side of a move. A move also needs: the remote-attestation design (ADR-0016 "Remote deployment notes": signed attestations), or lab-rathena loses `session` and stays red; the watch updated BEFORE the client is repointed (or retired); the Windows client's `clientinfo.xml`. The inventory orders these |
| D20 | Q6 "yes" | Q6 asked two things: regenerate the lab's group with the same generator, AND give lab-rathena the `firewall` signal on top of `session`. The 15:20 text restates only the first. The second would make a confirmed OS lock a REQUIRED lab signal, against ADR-0016's History ("OS-level locks belong to production and teaching distributions only") and CLAUDE.md rule 9 ("The interlock itself adds no OS lock") | **Flagged for Batt to confirm.** Recorded as decided: the generator produces the lab group (5.7). Not recorded as decided: the `firewall` signal on lab-rathena |

## 3. Decision (Batt, 2026-10-09)

1. **The bot works normally on an allowed external server.** It decides from pixels only
   (ADR-0007): no packet value is ever a decision input, so nothing it decides needs packets.
2. **No packet capture there BY DEFAULT** (Batt, 2026-10-09 ~15:20, Q2 corrected). Capture is
   allowed only when that server's own rules explicitly permit it, recorded per environment in
   Settings: a capture permission, OFF by default, with the server's rule text or link as
   evidence, turned on only through ADR-0016's hard path (section 4.5). This keeps ADR-0006's
   condition; default-off is the tightening. While it is off (always, today), the console and
   every packet-based tool say so explicitly: **not available on this environment**, never an
   error, never an empty list, never a zero.
   - *Superseded wording (14:40 brief, as first written here): "Not by us, by any path, whatever
     that server's rules allow (D3: this tightens ADR-0006)." Replaced by the 15:20 answer
     above.*
3. **The interlock is DEFAULT DENY via the allowlist.** The only gate is the allowlist of server
   endpoints in Settings; anything not allowed is blocked; no runtime blocklist.
   - Enforcement without packets: the exe-scoped Windows firewall rules for the bot's client
     exes allow ONLY the allowlisted endpoints, so the client cannot connect anywhere else.
   - Windows is kept in sync by a reviewed one-time script that Batt runs whenever the allowlist
     changes. It is generated from the Settings store; Settings shows a checksum of the intended
     rule set; Batt pastes the script's own output (rule listing + checksum) back to confirm.
     **Until confirmed, the environment is not runnable (fail closed).**
   - The forbidden list (official endpoints) is an EDITING guard: an allowlist entry that
     matches a forbidden endpoint is refused. ADR-0016's asymmetric rules stay: easy to forbid,
     hard to allow, human-only writes.
   - In the lab, the sniffer's attestation may stay as an additional check; on external servers
     it is absent by design. (A capture permission, 4.5, does not make an attestation a signal
     of an external environment; this ADR does not decide that.)
4. **What is lost there is accepted, and runs are evaluated another way** (section 9): the HUD,
   the per-block outcome log, recorded sessions for human review, conservative defaults.
5. **External sessions are never training or scoring data**, unless a later ADR decides
   otherwise.
6. **Endpoints are config, never hard-coded** (Batt, 2026-10-09 ~15:20). Every server endpoint,
   the lab's included, lives in the Settings environments store, the single source of truth; the
   firewall script, the interlock, the sniffer target and the docs read it. The same generator
   produces the lab's own firewall group (Q6), so moving the lab server is: edit the environment
   in Settings, regenerate, Batt runs the reviewed script, the paste-back checksum confirms
   (sections 4.6 and 5.7; what the records say a move also needs: D17-D19). Today's hard-coded
   places: [docs/planning/endpoints-as-config.md](../planning/endpoints-as-config.md).
7. **Answered at 15:20:** Q5 (5.6), Q7 (6.3), Q10 and Q11 (9.2, 9.4) are decided; Q1, 3, 4, 8,
   9, 12, 13 and 14 are DEFERRED until a real external server is chosen (section 12).

## 4. External environments in the store (Proposal)

### 4.1 A new kind
- Each environment gets `kind`: `lab` (ours, sniffer-attested) or `external` (not ours; not
  captured unless its capture permission is on, 4.5). Set by a person in Settings.
  **Recommendation:** a kind change is a HARD change (typed reason, the subject retyped,
  audited), like loosening a Forbidden list (open question 13, DEFERRED).
- `external` implies: no `session` signal, the signal set in 4.2, the conservative defaults in
  9.2, and the packet-free tool behaviour in section 8.
- The client profile gains its **folder**: every `*.exe` under it is covered by the rule set
  (section 5), not only the one the shortcut starts.

### 4.2 The signals of an external environment

| Signal | Holds when | Source | The agent can reach it? |
|---|---|---|---|
| `lab_host` (exists) | the capture lock is steady on rdp/console, and `WIN_HOST` = the environment's `windows_host` | `state/capture-backend`, compose env | no |
| `firewall` (new) | the environment's CURRENT intended rule set (computed now from the store) has the same checksum as the last rule set a person confirmed for it, and that confirmation is younger than its maximum age | the human-only store (`settings/`, backend only) | no |
| `login_screen` (Recommendation, section 7) | at the last login, the server-select line matched the profile's `server_select` template | the BACKEND's own template match on its own frames during the login phase, as the foreground gate does (`signature.py`) | no: never reported over the agent channel (ADR-0016 test 5: the agent cannot claim green) |
| `operator_start` (Recommendation, section 7) | a person confirmed this run's start, under the current lock SEQ | a human-only Settings-style write | no |

- **Fail closed, with new reasons:** `firewall_unconfirmed` (never confirmed), `firewall_changed`
  (the intended set changed since: an edit, a DNS re-resolution, a newly forbidden address),
  `firewall_expired` (older than the maximum age, open question 4, DEFERRED).
- Adding the signal names is a one-time code change, like the 2026-10-05 `server` amendment;
  adding an external server stays a Settings entry plus an ADR-0006 entry.
- `no_attestation` is never reported for an external environment: the sniffer is not one of its
  signals, so its absence is not a fault.

### 4.3 What turns an external environment red at once
Any change to its servers or client profile; any change in what its host names resolve to; an
allowed address that newly matches the forbidden list or a CDN range; a confirmation past its
age; the lock leaving `steady`; `WIN_HOST` changing. Green → red releases what the bot holds
(ADR-0016, unchanged).

### 4.4 The forbidden list: an editing guard (D4)
- Unchanged: a NEW allowed endpoint that matches a forbidden name, IP or `.domain` is refused
  (`envstore.classify`); the asymmetric rules stay.
- Unchanged: `usable()` leaves out an allowed endpoint that later matches. For an external
  environment that changes the intended rule set, so the environment goes red
  (`firewall_changed`) until Batt re-runs the script. Tightening needs no confirmation to take
  effect on the server side; on Windows the old, wider rules stay until he does, and the
  environment stays red meanwhile.
- **New, at generation:** the generator refuses to emit a rule set that would admit:
  - an address that any forbidden name resolves to (resolved at generation time);
  - an address in a CDN range (`allowlist.CDN_RANGES`): a CDN address is shared, so allowing it
    for the client would also allow every other site behind it, the official kRO assist host
    among them (ADR-0016: Cloudflare 104.18.20.108 / .21.108);
  - an IPv6 endpoint (the lab's checks are IPv4; the rules block all IPv6 but `::1`);
  - a host name that does not resolve.

### 4.5 The capture permission (DECIDED default-off, Batt 15:20 Q2; the field design is a Proposal)

**The decision:** no capture BY DEFAULT on an external server. Capture is allowed only when that
server's own rules explicitly permit it, recorded per environment in Settings, off by default,
with the rule as evidence, turned on only through ADR-0016's hard path. This keeps ADR-0006's
condition ("unless the server's rules explicitly allow it"); default-off is the tightening.

**The field (Proposal):**

| Part | Design |
|---|---|
| Name and place | `capture` on the environment entry in the human-only store (`settings/environments.json`, backend only). Not a technical field: it is edited on the Settings page, never in `config/environments.yaml` |
| Type | `{state: "off" \| "on", evidence: Evidence \| null, history: [Evidence + off_at, off_by]}` |
| Default | `state: "off"`, no evidence, for every environment. A seed never sets `on`; an import always carries `off`, whatever the file says (an import must not loosen by the back door) |
| Where it can be on | Only on an `allowed` environment of kind `external`. A `pending` one is treated as forbidden (ADR-0006 rule 1), a `forbidden` one never; a change of type away from `allowed` turns it off (easy, automatic, audited). A `lab` environment shows it read-only as "ours: ADR-0006 environment 1", which already permits passive capture of our own traffic |
| Evidence (all required to turn it on) | `rule_text`: the server's rule, quoted verbatim (plain text, ≤ 2000 characters); `rule_source`: where it is published (an `https` URL, or "given by the owner, <how>", ≤ 300 characters); `rule_checked_at`: the date the person read it there (not in the future); `recorded_at` (server time) and `recorded_by` (peer, Origin; the Access identity later, ADR-0016 remote notes); `reason`: the typed reason. The scope is fixed, never typed: "passive capture of our own client's traffic to this environment's listed endpoints". Modification or injection is never permitted by this field (ADR-0006: "capture or modification"; the sniffer never sends) |
| The evidence is untrusted text | Control characters stripped, length caps, stored and rendered as TEXT only (no `innerHTML`, never a link built from it), never fetched or resolved by the backend (no URL fetch, no DNS), never used in a path, shell, SQL or YAML (ADR-0016's write rules and hostile-input controls) |
| Turning it ON: the hard path | A HARD change in `envstore.classify` (`capture_on`): a typed reason (≥ 10 characters), the environment's name typed again, one hard change per save, every evidence field present, audited in `allowlist_audit` with the reason and the evidence. The same route and write rule as every Settings write (public listener, a LAN viewer with the console's Origin, the CSRF token, 20/min, never `lab_host_peer` or `windows_host_peer`, never `:8001`). **The agent never turns it on, by any route** |
| Turning it OFF: easy | A tightening, like removing an allowed server: one save, no reason needed (an optional note), audited (`capture_off`), in force at once. The evidence moves to `history`; nothing is deleted, so the record of what was permitted, when and on what rule stays |
| Lapse | ADR-0006 rule 1: "Re-check the rules before each new experiment series; if they change or cannot be confirmed, the server is treated as forbidden". The permission reads as OFF once `rule_checked_at` is older than the bound for re-checking (the same question as the firewall confirmation's age, open question 4, DEFERRED). Renewing it is turning it on again, with fresh evidence, by the hard path |
| The permission record | ADR-0006 says "record that rule here" (in the environment's permission record, e.g. `docs/environments/community-server.md`). The Settings field is what the software reads; the permission doc points to it rather than restating it (whether both must carry the rule text is Batt's call when a server is chosen) |

**What it changes, and what it does not:**
- Any capture of an external environment's traffic may run ONLY while the field is on (allowed,
  external, evidence complete, not lapsed). A capture component reads the field from the store at
  its start and again on every store revision and at least every 5 minutes (the re-resolution
  cadence), and stops at once when it reads off, missing or invalid (fail closed).
- **It enables nothing by itself.** No capture path can see an external server's traffic today:
  the sniffer runs in rathena's network namespace (section 1). A path (section 10's S3 or S5) would
  be a NEW design with its own review and Batt's approval (the router is his infrastructure). The
  field is the permission, not the mechanism.
- It is not an interlock signal: it never makes an environment green or red. The firewall stays
  the gate (section 3).
- Section 8: for sessions recorded while it was on, and only if a capture path exists, the
  manifest would carry `packets: "captured_under_permission"` plus the evidence's `recorded_at`,
  and the packet tools could then report for that environment instead of "not available". Sessions
  recorded while it was off stay `not_captured_by_design`.
- **Section 9.3 still holds:** external sessions are never training, label or scoring data, unless
  a later ADR decides otherwise. A capture permission does not change that, and this ADR does not
  decide it.
- ADR-0006 rule 4 binds harder with packets: they carry other players' names and chat, so captures
  stay local, pseudonymized in any derived dataset, never pushed, never in `./data` or git (CLAUDE.md
  rule 4). The login-password redaction must cover that server's login port, taken from its
  endpoints, never a constant (the inventory's top risk).
- Turning it off does not delete captures banked while it was on; they keep the captures' own
  retention. Whether OFF should also purge them is not decided here (a question for Batt when a
  capture path is designed).

### 4.6 Endpoints are config, never hard-coded (DECIDED, Batt 15:20)

- **The source:** every server endpoint, lab and external, is an entry in its environment's
  `servers` (host + port) in the human-only store. The field exists since 2026-10-06 and the
  interlock already reads only it (ADR-0016); what is missing is that other places still restate
  the lab's endpoint.
- **The readers (Batt):** the firewall script generator (section 5, and 5.7 for the lab), the
  interlock (already), the sniffer's target (how it receives it is open: D18), and the docs, which
  POINT to Settings instead of restating a value.
- **Moving the lab server (Batt):** edit the lab environment in Settings → regenerate → Batt runs
  the reviewed script → the paste-back checksum confirms. What the records say a move also needs
  (the server's own advertised address, the sniffer's transport and captures, the lab-only watch,
  the Windows client's `clientinfo.xml`) is in D17-D19 and in the inventory's order of changes.
- **The inventory, before anything changes (Batt):**
  [docs/planning/endpoints-as-config.md](../planning/endpoints-as-config.md): every place the lab
  endpoint is hard-coded today, what reads it, and how each becomes config-driven. PROPOSED; no
  code, config, test, compose, Windows rule or CLAUDE.md sentence changes until Batt approves it.

## 5. The rule set, the script and the checksum (Proposal)

### 5.1 The rule set (Block rules only)
Per external environment (and, since Q6, for the lab's own environment too: 5.7), one firewall
group `poring-lab env <env-id>`. For every exe the profile's folder holds, the generator emits the
shape of ADR-0016's Production option:

| Rule | Protocol | Remote addresses | Remote ports |
|---|---|---|---|
| A: no other hosts | any | the IPv4 complement of {the allowed IPs, 127.0.0.0/8}, plus `::2-ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff` | any |
| B: allowed host, other ports | TCP | one allowed IP | the complement of that IP's allowed ports |
| C: no UDP to allowed hosts | UDP | the allowed IPs | any |

- Direction outbound, action Block, enabled, profile Any, local address and port Any. No Allow
  rule (inert, D1).
- Loopback stays reachable, as in the lab (the AssistAddr override points there).
- Host names are resolved by the backend at generation; the rules hold IPs only. If the server's
  address changes, the client simply cannot connect (fail closed) and Settings shows
  `firewall_changed` after the next re-resolution.

### 5.2 The script
- **One template, committed and reviewed in the repo.** The generated file is that template plus
  ONE data block: the canonical intended text of 5.4, byte for byte what Settings displays.
  Settings also shows the generated file's sha256.
- **Delivery:** downloaded from Settings on Batt's computer, uploaded through the console's
  transfer panel (ADR-0004 F1, RDP path) to `\\tsclient\transfer`. Batt checks it on Windows with
  `Get-FileHash` against Settings, then runs it in HIS elevated console with a process-scoped
  `-ExecutionPolicy Bypass` (the machine policy is not changed; the same pattern as the watch
  task). The agent never runs it, never types it, and never answers UAC.
- **What it does, in order:**
  1. refuses, changing nothing, unless it is elevated, its data block parses, and NO process whose
     path is a covered exe is running (close the game first: so there is no unprotected moment
     between steps 2 and 3);
  2. removes the rules of its OWN group only (`poring-lab env <env-id>`); it never touches another
     group, the lab's `poring-lab lab-only`, Sunshine's rules, or any profile setting;
  3. creates the rules from its data block;
  4. reads back from Windows' EFFECTIVE state (the active store, so a Group Policy rule shows
     too), builds the canonical text of 5.4 from what it reads (never from its data block), and
     prints it with the checksum and `match yes|no` against its embedded intended checksum;
  5. writes the same output to `\\tsclient\transfer\poring-lab-fw-<env-id>-g<gen>.txt` when that
     path exists; exits 0 only on `match yes`.
- `-ReadBackOnly` runs step 4 alone and should need no elevation (the agent's non-elevated shell
  read the lab's rules back on 2026-10-06; the profile lines are re-checked when the template is
  reviewed).
- **It leaves nothing running and nothing of ours:** no task, service, listener, startup entry,
  key, token or log. Batt deletes the `.ps1` and the output file afterwards.

### 5.3 The paste-back (D11)
1. The script prints its output and, on the RDP path, writes it to the transfer area.
2. Batt downloads that file in the console's transfer panel on his own computer (ADR-0004's
   reverse-text path; the backend never reads the transfer area for this, so it stays a human
   act, never a channel).
3. He pastes the text into the environment's "Confirm firewall" box in Settings, from his own
   computer: a LAN browser, never the Dell (`windows_host_peer`) and never the lab host
   (`lab_host_peer`).

In console mode (S2) there is no `\\tsclient`: firewall work happens on the RDP path, the human's
admin path (CLAUDE.md rule 2). A typed-checksum fallback is open question 12 (DEFERRED).

### 5.4 The checksum: exactly what is hashed
**The canonical text** (ASCII only; the generator refuses a non-ASCII exe path):

    poring-lab-fw/1
    env <env-id>
    group poring-lab env <env-id>
    <body lines, sorted by byte value>

Body lines, one per item, fields in this fixed order, single spaces:

    fw <domain|private|public> enabled=<true|false|notconfigured> outbound=<allow|block|notconfigured>
    rule exe=<path> dir=out action=block enabled=<true|false> profile=<any|...> proto=<any|tcp|udp> raddr=<ranges|any> rport=<ranges|any> laddr=<ranges|any> lport=<ranges|any>
    other exe=<path> group=<name> action=<allow|block> enabled=<true|false>
    present dir=<folder> exe=<path>

- `fw`: each profile's state. Rules are inert when a profile's firewall is off, so the intended
  set says `enabled=true outbound=allow` for all three.
- `rule`: every rule in the group.
- `other`: every OUTBOUND rule in ANY other group that names a covered exe. The intended set has
  none: a stray rule is a mismatch to look at, not something to hash around.
- `present`: every `*.exe` found under the profile's folder (recursive, bounded). An exe the rule
  set does not cover is therefore a mismatch (ADR-0019 retirement criterion 2's idea, per
  environment).
- **Canonical values:** paths lower-cased (ToLowerInvariant), backslashes, no trailing separator,
  no environment variables, no `..`. Addresses: each entry parsed (single, range, CIDR or mask)
  into numeric ranges, merged, sorted numerically, IPv4 before IPv6, written `start-end` even for
  one address (IPv4 dotted decimal; IPv6 compressed lower case, RFC 5952), comma-separated. Ports
  the same (`a-b`, merged, sorted). A keyword Windows may return (`LocalSubnet`, `Internet`, ...)
  is written `unsupported:<keyword>`, which can never match. Protocols `any|tcp|udp`; any other
  protocol is written as its number, which can never match.
- **The hash:** SHA-256 over the UTF-8 bytes of the canonical text, lines joined by `\n`, with a
  final `\n`. Written as 64 lower-case hex digits. Settings shows it in full, plus the first 16
  digits in groups of four for the eye.

**The script's output** (what Batt pastes):

    poring-lab firewall readback v1
    rev <store revision> gen <generation>
    <the canonical text, exactly as hashed>
    checksum sha256 <64 hex>
    match <yes|no>
    end

- `rev` and `gen` tie an output to the script that made it (the store revision it was generated
  at and a per-environment counter). They are NOT credentials: no secret, no authority, printed
  openly (ADR-0019: no key or token of ours on Windows).

### 5.5 How Settings parses and compares the paste (untrusted input)
- **The route:** a new human-only write, `POST /settings/environments/{id}/firewall-confirmation`,
  under ADR-0016's write rule unchanged: the public listener only (`:8001` gets 404), a LAN
  viewer with the console's Origin, the CSRF token, 20 writes/min per client, never
  `lab_host_peer`, never `windows_host_peer`, the agent network refused before any route, every
  refusal counted and audited. **The agent never confirms, by any route** (as it never confirms an
  environment entry).
- **Size first:** the body ≤ 32 KiB (inside the 64 KiB cap), ≤ 512 lines, each ≤ 4 KiB.
- **Strict decoding:** UTF-8; CRLF normalised to LF; any byte outside printable ASCII plus LF
  refuses the WHOLE paste (refused, not stripped: stripping could make a different text look
  like the intended one).
- **Strict grammar:** every line must match exactly one production of 5.4, by a linear,
  anchored tokenizer (no backtracking regex on pasted text). An unknown or malformed line refuses
  the paste with its line number (`malformed_line:<n>`).
- **The comparison:**
  1. the canonical text's `env` line = the route's environment (`env_mismatch`);
  2. `rev`/`gen` = the latest script generated for it (`stale_generation`);
  3. the backend RECOMPUTES the SHA-256 over the pasted canonical lines and requires it to equal
     the printed checksum (`checksum_not_recomputed`): a hand-edited or truncated paste fails;
  4. that checksum = the environment's CURRENT intended checksum (`not_intended`);
  5. `match yes` (`script_reported_mismatch`).
- **On a refusal:** a line diff (intended vs pasted canonical lines), rendered as TEXT only (no
  `innerHTML`, no links; ADR-0016's hostile-file controls apply to pasted text too).
- **Never:** executed, evaluated, resolved (no DNS), used as a path, or built into a shell, SQL or
  YAML string. It is only compared.
- **On success:** a confirmation record `{env, checksum, rev, gen, confirmed_at, who (peer,
  Origin), the pasted canonical text}` in the human-only store (`settings/`, backend only; vision
  can write `./data`, so nothing that decides safety lives there), and one line in the
  `allowlist_audit` log. The `firewall` signal reads only this record.

### 5.6 Afterwards: drift on Windows
The confirmation is a picture of one moment. A later change on Windows (a person editing rules, a
reset) is invisible to the server: there is no channel, by design (ADR-0019). Mitigations:
- the confirmation has a maximum age (open question 4, DEFERRED until a real external server is
  chosen; **Recommendation:** at the start of each experiment series, as ADR-0006 rule 1 already
  asks for the permission record, and at most 7 days);
- **DECIDED (Batt, 2026-10-09 ~15:20, Q5 yes; lab only):** before a run, the agent's OWN shell
  (already a lab-only exception, ADR-0019) may run `-ReadBackOnly`, and the printed checksum is
  compared from pixels. It may only turn the signal RED, never green: the first and every
  confirmation stays a person's act. Never part of a user setup.

### 5.7 The lab's own group, from the same generator (DECIDED, Batt 15:20, Q6; the replacement is a PLAN)

**How the lab environment's rule set is produced:**
- **Input, from the store only:** `lab-rathena`'s confirmed `servers` (host:port; the shipped
  suggestion today is 192.168.1.13 with 6900, 6121 and 5121) and its client profile's folder
  (4.1; today `C:\RO-rAthena\client`, holding 2 exes: `2021-11-03_Ragexe_1635926200.exe` and
  `PoringLab.exe`). No address, port or path is written into the generator or the template.
- **Output:** the group `poring-lab env lab-rathena`, the three Block rules of 5.1 per exe, with
  the same canonical text, checksum, script and paste-back as an external environment (5.2-5.5).
- **It is a tightening of today's group.** `poring-lab lab-only` lets the lab exes reach ANY port
  and protocol on 192.168.1.13; the generated group admits only TCP to the listed ports there. No
  other port on the lab host is known to be needed (the watched logins of 2026-10-06 saw only the
  map port in game); the read-back and a watched login prove it the day it is applied.
- **rAthena specifics the generator must respect:** the client reaches the char and map servers at
  the address the SERVER advertises (`char_ip`/`map_ip` = `HOST_LAN_IP`), not at the one its
  `clientinfo.xml` names. So the lab environment's servers must hold the login, char AND map ports
  at the advertised host; a missing one is fail closed (that leg is blocked) but the client cannot
  enter the game. **Proposal (D17):** while the lab's rathena runs in this compose, the generator
  refuses a `lab` rule set whose host differs from the address rathena advertises.
- **The interlock:** whether lab-rathena also gets the `firewall` signal on top of `session` is
  NOT recorded as decided (D20). Until Batt confirms it, the lab stays `[lab_host, session]`.

**Replacing the hand-written group `poring-lab lab-only` (a plan; nothing done; Batt's console
act, after this ADR is accepted and the generator is built and reviewed):**
1. In Settings, lab-rathena's servers are the confirmed lab endpoints (the generator's input).
2. Settings generates the lab script; Batt carries it over (5.2), checks `Get-FileHash` against
   Settings, and closes the game (the script refuses while a covered exe runs).
3. Batt runs it in his elevated console. It creates `poring-lab env lab-rathena` and does not
   touch `poring-lab lab-only`. Both groups are Block-only, so together they admit only what both
   admit: there is no moment without a block. Its read-back says `match no`: the old group's 2
   rules appear as `other` lines (5.4), as expected.
4. Batt removes the old group with its recorded undo line,
   `Remove-NetFirewallRule -Group 'poring-lab lab-only'` (ADR-0016): a separate, agreed line,
   because the generated script never touches another group.
5. `-ReadBackOnly` prints `match yes`; Batt pastes it into Settings; the confirmation is stored.
6. A watched lab login, as on 2026-10-06: the interlock green on lab-rathena, the client's only
   remote the lab host's map port, the watch's KILLED count 0.
7. The same day, the records: ADR-0016's layer-1 section, ADR-0019's audit and retirement
   criterion 2, CLAUDE.md rule 9, the ROADMAP's interlock row, `config/environments.yaml`'s header.
- **Rollback:** `Remove-NetFirewallRule -Group 'poring-lab env lab-rathena'`, then the old group's
  create line of 2026-10-06 (its 4 ranges are recorded in ADR-0016), then a read-back.
- **The lab-only watch** (`labwatch.ps1`) keeps its own 192.168.1.13 and cannot read Settings
  (ADR-0019: no channel). It is unaffected while the lab host stays where it is, and must be
  updated, or retired under ADR-0019's criteria, BEFORE any change of the lab's endpoint, or it
  kills the lab client at its first connection to the new address (the inventory, W2).

## 6. The client and what the interlock no longer proves

### 6.1 Which client copy (D2, open question 1, DEFERRED until a real external server is chosen)
- **Proposal:** a NEW separate copy per external environment, in its own folder outside
  `C:\RO-rAthena\` (e.g. `C:\RO-<env-id>\`, windows-setup.md's pattern), never the original
  community client, which stays untouched and outside every rule.
- Two ways to fill it, Batt's choice:
  - (a) the LAB client (the same 2021 exe and data) pointed at the external server by its own
    `clientinfo.xml`: the same L2 bindings and calibration, IF the server accepts that client;
  - (b) a copy of the server's own client: new L2 bindings, templates and calibration first
    (D6), and the game-file finder checks what its data names (ADR-0016).
- Either way: the AssistAddr override before its first login (CLAUDE.md), the Equip-window
  placeholders if it is the 2021 exe, and its exes covered by the environment's rule set.

### 6.2 The watch (D10)
The lab-only watch kills any exe under `C:\RO-rAthena\client\` that reaches a non-lab address. A
copy outside that folder is not killed and not watched; the firewall group is its layer 1. A new
client copy re-opens the watch's retirement criterion 1 (a client experiment is open).

### 6.3 What `session` proved and nothing replaces by itself (D7, open question 7: DECIDED)
In the lab, `session` also proves the client is IN GAME with one of OUR accounts. On an external
environment the firewall proves only where the covered exes CAN connect; it proves nothing about
which window the bot acts on. Clicks are not foreground-gated today (ADR-0016, Batt's decision
for the lab).
- **DECIDED (Batt, 2026-10-09 ~15:20, Q7 yes: "gate all presses"):** on an external environment,
  ALL bot presses (clicks, moves and the wheel too) need the profile's ACTIVE title-bar signature
  on a fresh frame (the foreground gate's evidence, ≤ 400 ms), and the in-game HUD anchors
  visible. Releases always pass. The lab keeps its typing-only gate (ADR-0016), so the gate
  differs per environment kind.
- **Residual even then:** a copy of the same client has the same title bar as the original. If a
  person runs the untouched community client by hand while the mux is in BOT or ASSIST, the bot
  could act on it, and that client is covered by no rule. ADR-0016's procedural mitigation stays:
  play the community server by hand only with the mux in HUMAN.

## 7. The optional extra signals, weighed (Recommendations, not decisions)

Open question 8 is DEFERRED until a real external server is chosen (Batt, 2026-10-09 ~15:20);
the recommendations below stay as written.

| Signal | For | Against | Recommendation |
|---|---|---|---|
| **Login-screen server name** (pixels: the server-select line matches the profile's `server_select` template) | Server-side and pixel-only (ADR-0019 candidate (a)); already half-built (ro_agent checks the login screens by templates before it types); catches a copy whose config names the wrong server; costs one template per client | It shows what the CLIENT's config says, not where it connects; a crafted or mistaken config can name anything; visible only at login; a copy of the same client pointed at a same-named server is indistinguishable | **Adopt as REQUIRED at each login** (`login_screen`, reset by a logout, a client restart or a lock handover). It is a consistency check, not proof; the firewall is the proof |
| **A human confirmation at session start** (`operator_start`) | Covers what nothing else can: "the lab copy, launched by its shortcut; the original community client not running; the server I expect". Cheap; the same human-only write route as Settings | Confirmation fatigue (a click-through proves little); one more step per run; adds nothing to the connection itself | **Adopt for the first external series**: per run, tied to the lock SEQ (any handover ends it), a short checklist of exactly those facts. Review after the first series whether it still earns its click |
| Also considered: the character name on the HUD = the registered bot character | Pixels; replaces `session`'s account check | Needs a name reader; other players' names are nearby on screen (ADR-0006 rule 4) | Later, not required; parked |
| Also considered: the router's view of the Dell's connections (OPNsense) | Real endpoints, no payload | Machine-wide, Batt's infra, close to capture (section 10) | Not proposed |

## 8. Packet-based tools: "not available on this environment" (D8)

**The rule (Proposal):**
- The recorder writes `environment: <id>` and `kind` into every session manifest (from the
  backend's interlock verdict at record start). For `external` it writes
  `packets: "not_captured_by_design"` and NO `packets.jsonl.gz`: an empty file would read as
  "nothing happened".
- Every packet-based tool reads the manifest FIRST. On `external` it prints
  `not available on this environment (<env-id>: packets not captured by design)`, writes no
  verdict file, emits no counts (never `SAFETY: 0`), and exits with one distinct, documented exit
  code. JSON outputs carry `"available": false` and a `reason`, and nothing else.
- A consumer of tool output (`walk_readiness.py`, the demonstrations tables) treats
  `available: false` as NOT AVAILABLE, never as a pass: "zero safety events" cannot be met by
  absence (demonstrations.md §2a: a zero from a sensor that cannot see is not evidence).
- Sessions without the field are lab sessions by record (automation never ran anywhere else). From
  the change on, the recorder refuses to record without an environment.
- **With a capture permission (4.5):** only if an environment's permission was on when a session
  was recorded AND a capture path existed (none does today), the manifest carries
  `packets: "captured_under_permission"` with the evidence's `recorded_at`, and the tools below
  may report for that session instead of "not available". Their verdicts are still never training,
  label or scoring data (9.3, unless a later ADR says otherwise). The table below is the default:
  the capture permission off.

| Tool | What it reads | On an external environment |
|---|---|---|
| Console Packet timeline (`PacketTimeline.tsx`, `/ws/packets`, `routes_packets.py`, `packets.py`) | the sniffer's live events through `/ingest/packets` | the explicit state "External server: packet log not available (not captured by design)" instead of the reconnect warning or an empty list (section 11) |
| Interlock `session` (`interlock.py`) | the sniffer's attestation | not in the signal set; never `no_attestation` |
| `guarded_build.py`: the auto GM re-login after a sniffer restart; `replay:` | the interlock; banked `/captures` | lab only: refused for an external environment or session window |
| `record_session.py` (`write_packets`, `--repack`) and the harnesses that call it (`rule_run.py`, `walk11.py`'s run loop and the walk rules built on it) | the sniffer's `/captures` window | no packets file; manifest marker; `--repack` refuses |
| `replay_states.py`, `measure_delay.py` | `/captures` | refuse: not available |
| `demo_verify.py` (+ `poring_dataset.verify`) | `demo.jsonl` + `packets.jsonl.gz` | not available; no `demo.verified.jsonl` |
| `demo_labels.py` | `demo.verified.jsonl` | refuses (no verified file; and never labels from an external session, section 9.3) |
| `demo_interruptions.py` | the backend's input log (no packets) | WORKS: human takeovers are still marked |
| `walk17_score.py` (its docstring cites `walk15_score.py`, which was in no commit, `git ls-files` 2026-10-09; ➡️ since 0648ade it is kept verbatim in `docs/records/scorers/` with walk@7–16's) | packets + the run's logs | not available; its first JSON object is `available: false` with no `scored` or `SAFETY` |
| `walk_readiness.py` | the scorers' JSON | any `available: false` input → `not available`, never READY |
| `loot1_score.py`, `loot_truth.py` | packets | not available |
| `talk1_score.py` | `trials.json` + packets | not available |
| `where_run.py --score`, `reloc_run.py` (scoring) | packets | not available (their harnesses also use GM `@warp`: lab only) |
| `replay_safety.py` | replayed events | not available |
| `safety_signal_check.py` | live packets after a deliberate click; GM commands | lab only: refuses (no positive case is possible without the sensor) |
| `detector_check.py score`, `qa_export.py`, `m4_validate.py`, `selfpos_calibrate.py`, `selfpos_eval.py`, `walk_check.py`, `weight_calibrate.py --packets`, `weight_resolution.py`, `weight_digits.py`'s offline proof, `calibrate_projection.py` | packet truth (the Timeline, `self_move_request`, acts) | not available; camera calibration there uses the pixels-only path (ADR-0007 amendment, ruling 3) |
| `build_frame_cache.py`, `dataset_ship.py`, `gold_eval.py`, `label_check.py` (not packet readers) | sessions and labels | refuse an `external` session as training, label or scoring input (section 9.3) |

## 9. What is lost there, and how runs are judged instead

### 9.1 Lost (accepted, Batt)
- **Automatic safety measurement:** `attack_request`, `npc_contact`, pickup acts. Nothing counts
  an unintended attack or NPC contact there.
- **Ground truth for scoring:** true positions, outcomes, deaths, drops.
- **Packet-derived labels:** no new training labels from external sessions.
- **L3 certainty:** an external server may change scripts, NPCs, menus, prices or maps; our L3
  data comes from our own rAthena (pre-renewal). The community server's 2026-09-30 frame
  resembled the official Thai Ragnarok Classic service (ADR-0006 notes), not a stock pre-renewal
  rAthena, so mismatches should be EXPECTED there, not treated as rare.

### 9.2 Instead (conservative defaults; Proposal, except where marked DECIDED)
- **The HUD** (perception and decision layers, display only) and the route preview.
- **The per-block outcome log** (ADR-0020): block, parameters, start/end, outcome, cause, the
  evidence frame id.
- **Recorded sessions for human review** (frames only, `kind: external`).
- **Only blocks verified in the lab.** A block may run on an external environment only if its L1
  concept is `verified` on lab-rathena for the SAME L2 client, L4 locale and capture path (D9:
  ADR-0020's "verified for the active server" cannot be met there). Unverified or unsupported
  blocks are refused by the run-start check; no supervised trials there (ADR-0020 open
  question 1 stays open for the lab).
- **L3 there is an assumption, checked by pixels** (open question 9, DEFERRED until a real
  external server is chosen). **Recommendation:** an
  external environment's L3 bindings are a copy of lab-rathena's, marked
  `assumed: lab-rathena@<kb hash>`. A block runs there only if every L3 fact it relies on has a
  mismatch detector (9.4) that runs BEFORE its irreversible step; otherwise it is refused.
- **DECIDED (Batt, 2026-10-09 ~15:20, Q10 yes):** irreversible blocks (`sell`, `refine`,
  `insert_card`, trading) and free chat are refused on external environments in the first
  version. ADR-0006 rule 3 (etiquette, rate limits, bot identification) applies to everything that
  runs.
- **DECIDED (Batt, 2026-10-09 ~15:20, Q11 yes: "always stop on mismatch / unexpected map"):**
  `unexpected_map` (ADR-0020's safety-critical event) and every L3 mismatch (9.4) STOP the run
  there, with no relocation: relocation trusts L3 map blocks, which are in doubt. An off-console
  notification comes later (not designed here).

### 9.3 Never training or scoring data (Batt)
External sessions never feed training, labels, gold sets, benchmarks or alone-test verdicts,
unless a later ADR decides otherwise. A capture permission (4.5) does not change this, and this
ADR does not decide it. They hold other players' names and chat in pixels (and, with a capture
permission, in packets too) (ADR-0006 rule 4): local only, never pushed, never a dataset. Where
they live and for how long is open question 14 (DEFERRED until a real external server is chosen).

### 9.4 L3 mismatches, detected from pixels (Proposal)

| Detector | What it compares | Fires when |
|---|---|---|
| **NPC absent** | before `talk_npc`: the unit detector's NPC boxes and the TALK cursor around the L3 cell, on a fresh frame with the character standing still | no NPC box within the L3 cell's radius, or the TALK cursor never reads on that cell |
| **Menu differs** | after contact: the dialog's options, read from pixels, against the L3 option list through the L4 locale keys | a different count, an option text that resolves to no expected key, or a different order (talk1_score's offline check, "menu differs from L3", done live). Today every L4 binding is `unsupported` (ADR-0020 section 12), so menu blocks run nowhere until L4 lands |
| **Warp leads elsewhere** | after `take_warp` / `npc_warp`: `current_map()` / `position()` (ADR-0020 13.6.6) against L3's destination | another map, or a cell outside the destination entry (it also raises `unexpected_map`) |
| **Price differs** | in a shop window, BEFORE the confirm: the price read from pixels against L3's price (with the known discount/overcharge rule) | any difference: the confirm is never clicked |
| **Also** | an unknown map name (minimap or `/where`) not in the KB; a monster species the map's L3 spawns do not list | stop; never attack an unknown species |

**The safe stop, every time:**
1. **Release** everything the bot holds (ReleaseAll through the mux).
2. **Stop the flow:** the run ends with cause `l3_mismatch:<kind>:<key>`; no automatic resume.
3. **Close only by known steps:** an open dialog or shop is closed through its own known cancel
   path, step by step, each step checked on a fresh frame; if no known path exists, it is LEFT
   OPEN for a person (closed by steps, never blind, as `safety_signal_check.py` does).
4. **Log** the expectation and the observation (pixel-read text stored as text, rendered as text)
   with the evidence frame ids in the per-block log.
5. **Notify** the operator: the console banner and the run report. An off-console notification
   comes later (Batt, Q11: "off-console notify later"; not designed here).

**Never on a mismatch:**
- retries that look like probing: re-clicking the NPC, cycling options, trying other warps or
  other cells to "find" the right one;
- guessing a different option by position, by similar text, or by order;
- confirming a transaction whose price, item or count differs;
- writing what was seen into the KB: the L3 data is changed only by a person, offline, and never
  from an external session automatically.

## 10. ADR-0019: why this Windows-side piece is allowed, and what it still owes

ADR-0019 says: look server-side first; a Windows-side piece needs a NEW ADR showing why each
server-side option fails, and Batt's approval. The need here is ADR-0019's own first row:
"attest a REMOTE server that has no sniffer".

| Option (server side first) | What it would give | Why it is not THE gate for an external server |
|---|---|---|
| S1. Logic only, nothing on Windows (today) | nothing | Without a sniffer there is no signal at all: the community entry can never be green (ADR-0016) |
| S2. Pixels: the server name at login (candidate a) | a consistency check | It shows the client's config, not where it connects; only at login; detection, not prevention. Kept as `login_screen` (section 7) |
| S3. Network, observe: the router's state table or flow log (candidate b) | the Dell's real endpoints | Per machine, not per exe (a person's own play, browsers and Windows Update look the same); after the fact; an OPNsense change (Batt's infra); reads an external server's connection data, close to capture, which is default-off there (section 3, 4.5) |
| S4. Network, enforce: a router rule for the Dell | prevention | Machine-wide in effect: it breaks every other use of the Dell, including a person's normal official play, which ADR-0016 explicitly protects ("never OS-wide") |
| S5. Route the Dell's game ports through the bot server for the sniffer (candidate b) | lab-style attestation | It IS capture of an external server's traffic: ~~ruled out (section 3) and by that server's rules~~ ➡️ default-off since 15:20 (Q2): possible only for an environment whose capture permission is on (4.5), and then a NEW capture-path design of its own. Even then it detects, it does not prevent: never THE gate |
| S6. Signed attestations from the server's own sniffer (candidate c) | strong | Only for a server WE host |
| **W1. Exe-scoped Block rules, generated and confirmed (this ADR)** | **prevention, per exe, never OS-wide** | Windows-side, so it must fit ADR-0019 (below) |

**Why W1 fits ADR-0019:**
- Its RESULT is exactly ADR-0019's allowed row: "one-time OS config with nothing of ours running
  (an exe-scoped firewall rule ...)". windows-setup.md already recommends such a rule for users.
- The script is the delivery of that config, not "a program that RUNS": it runs once per
  allowlist change, under Batt's hand, in his elevated console, and exits. It registers no task,
  service, listener or startup entry.
- No key, token or secret: its data are IP ranges and exe paths; `rev`/`gen` carry no authority.
- No channel: its output reaches the server only by a person carrying it (section 5.3). The
  backend never reads the transfer area for it, no watcher reports it, the agent never types it.
- Precedent: layer 1 itself was applied by agreed lines in Batt's elevated console (2026-10-06
  ~08:45, and the cleanup at 18:52; he opened it, the agent typed only the agreed lines). This is
  the same act, generated instead of hand-written, run by Batt himself, with the read-back
  compared by the server instead of by eye.

**What ADR-0019 still requires (owed by this ADR):**
1. The server-side analysis above. ✔ (here)
2. Batt's approval: PROPOSED until he accepts.
3. Nothing added on Windows by amending an older ADR: hence a new ADR. ✔
4. The user setup lists it, free of keys and channels: windows-setup.md on acceptance.
5. The paste-back stays human forever: automating it (a backend reading `/transfer`, ro_agent
   typing the confirmation, a watcher posting it) would make it the reporting channel ADR-0019
   forbids, and needs its own ADR.
6. Nothing left behind: the `.ps1` and its output file are deleted after the run.
7. The lab-only watch interplay (D10, section 6.2), and retirement criteria 2 and 5 re-worded.

## 11. The Packet timeline's source state (being built now)

The Packet timeline's explicit source state (**live / sniffer offline / external**) is being
built now as a UI addition on a separate branch (`feat/console-layout`), with the `external`
state DORMANT until this ADR is accepted. Nothing can make it show `external` before then: no
environment has `kind: external` (on that branch, as seen 2026-10-09 ~15:00, the backend's hook
for it is a stub that reads no store field and never reports `external`). On acceptance, that
hook reads the active environment's `kind` (section 4.1). The state is display only; it never
reaches the agent (ADR-0007 decision 4 unchanged).
- Its text, "packet log not available (not captured by design)", is the DEFAULT (capture
  permission off, 4.5). Should a capture permission and a capture path ever exist for an
  environment, what the timeline shows there is part of that capture path's design, not of this
  state.

## 12. Open questions for Batt

**Answered 2026-10-09 ~15:20 (Batt):** DECIDED Q2, Q5, Q6, Q7, Q10, Q11; DEFERRED Q1, 3, 4, 8,
9, 12, 13, 14 until a real external server is chosen. The questions' text is kept as asked.

| Q | State |
|---|---|
| 1, 3, 4, 8, 9, 12, 13, 14 | **DEFERRED** until a real external server is chosen |
| 2 | **DECIDED** (corrected): capture DEFAULT-OFF; a per-environment, evidence-backed permission turned on only by the hard path (4.5) |
| 5 | **DECIDED** yes: the lab-only read-back may only turn the signal red (5.6) |
| 6 | **DECIDED** yes: the lab's own group comes from the same generator (5.7). Its second half, the `firewall` signal for lab-rathena, is flagged for confirmation (D20) |
| 7 | **DECIDED** yes: gate all presses on external environments (6.3) |
| 10 | **DECIDED** yes: irreversible blocks and free chat refused in v1 (9.2) |
| 11 | **DECIDED** yes: always stop on a mismatch / `unexpected_map`; off-console notification later (9.2, 9.4) |

1. **[DEFERRED]** **The client copy (D2, 6.1):** a NEW separate copy per external environment,
   never the original community client? Filled with (a) the lab client pointed at the server, or
   (b) a copy of the server's own client (new L2 work first)?
2. **[DECIDED 15:20: default-off, with a per-environment permission; 4.5]** **No capture, closed
   door (D3):** confirm that an external server gets NO capture even where its rules allow it
   (ADR-0006 left that door open). ➡️ Batt: no, the door stays as ADR-0006 left it, with
   default-off as the tightening: "no capture BY DEFAULT on external servers. Exception: capture
   is allowed only when that server's own rules explicitly permit it, recorded per environment in
   Settings (a capture permission field, off by default, with the server's rule text/link as
   evidence, enabled only through the hard path of ADR-0016's asymmetric rules)."
3. **[DEFERRED]** **One server or a class (D14):** does this ADR widen ADR-0006 from "the
   community server" to any external server Batt registers (each with its own ADR-0006 entry and
   permission record)?
4. **[DEFERRED]** **Confirmation age (5.6):** re-confirm at each experiment series and at most 7
   days? Another bound?
5. **[DECIDED 15:20: yes, "read-back may only turn red"; 5.6]** **Lab-only read-back (5.6):** may
   the agent's own shell run `-ReadBackOnly` before a run, able to turn the signal red but never
   green?
6. **[DECIDED 15:20: yes, the same generator produces the lab's group; 5.7. The `firewall` signal
   half: to confirm, D20]** **The lab's own group:** regenerate `poring-lab lab-only` with the same
   generator (one mechanism, with ports), and give lab-rathena the `firewall` signal on top of
   `session`? Or leave the lab as it is?
7. **[DECIDED 15:20: yes, "gate all presses"; 6.3]** **What replaces `session`'s implicit checks
   (6.3):** on external environments, gate ALL bot presses on the client's active title bar plus
   the in-game HUD? (The lab's typing-only gate was your decision; this would differ per
   environment kind.)
8. **[DEFERRED]** **The optional signals (section 7):** `login_screen` required at each login, and
   `operator_start` per run for the first series?
9. **[DEFERRED]** **L3 on an external server (9.2):** lab-rathena's bindings copied as `assumed`,
   usable only for facts that have a pixel mismatch detector? Or a hand-curated file per server?
   Or no L3-dependent blocks at first?
10. **[DECIDED 15:20: yes, "refuse irreversible blocks and free chat in v1"; 9.2]** **Irreversible
    blocks and chat (9.2):** refused on external environments in the first version?
11. **[DECIDED 15:20: yes, "always stop on mismatch / unexpected map; off-console notify later";
    9.2, 9.4]** **On a mismatch or `unexpected_map` there (9.2, 9.4):** always stop (no
    relocate)? And should a stop reach you off the console (e.g. through Home Assistant, as
    ADR-0019 suggests for the indicator)?
12. **[DEFERRED]** **The paste path (5.3):** the transfer-area file on the RDP path is the only
    Windows → Mac text path today. Accept that, or allow typing only the checksum (no diff on a
    mismatch) as a fallback in console mode?
13. **[DEFERRED]** **The kind change (4.1):** `lab` ↔ `external` as a HARD Settings change?
14. **[DEFERRED]** **External recordings (9.3):** `data/` only, or the NAS in a never-trained
    area? Retention (e.g. 30 days unless pinned)? Who may view them?

## 13. Residual risks (stated, not hidden)

- **A window the rules do not cover** (6.3): the original community client, a browser, the
  desktop. Mitigated by the full foreground gate (DECIDED, Q7) and the recommended
  `operator_start` (Q8, DEFERRED); the procedural rule (HUMAN mode while a person plays by hand)
  stays.
- **The lab endpoint is still restated in many places** until the inventory's changes land
  ([docs/planning/endpoints-as-config.md](../planning/endpoints-as-config.md)). Until then a move
  of the lab server is NOT a Settings edit alone (D17-D19); the inventory's order of changes is
  what makes it one.
- **Drift on Windows after a confirmation** (5.6): invisible to the server by design; bounded by
  the confirmation's age.
- **A local relay:** loopback stays open for the covered exes (the AssistAddr override). A program
  that listens on loopback and forwards elsewhere would bypass exe-scoped rules. Nothing of ours
  installs one; a client folder's `present` inventory covers exes there only.
- **Protocols other than TCP and UDP** to an allowed address are not blocked (one Windows rule
  takes one protocol). The client has no use for them.
- **No safety measurement there** (9.1): an unintended attack or NPC contact goes uncounted. The
  defaults (lab-verified blocks only, L3 detectors before irreversible steps, stop on mismatch)
  are what stands in for it.

## 14. On acceptance

**CLAUDE.md sentences that would change** (the parent edits them; this ADR does not):

| Where | The sentence today | It would say |
|---|---|---|
| Header | "There are exactly **two sanctioned environments**" | unchanged, unless open question 3 (DEFERRED) widens ADR-0006 to a class of external servers |
| Rule 1 | "Packet capture (the `sniffer` service) is **offline ground truth only**." | ~~... offline ground truth only, and never of an external server's traffic (ADR-0021)~~ ➡️ (Q2, 15:20) ... offline ground truth only; of an external server's traffic only while that environment's capture permission is ON (its own rules permit it, recorded in Settings, hard path; ADR-0021 4.5), which is never by default |
| Rule 9 | "an `allowed` environment is attested: the lock is steady, `WIN_HOST` matches, and the sniffer's attestation is ≤ 10 s old for a live lab-account session;" | split by kind: a lab environment as today; an external one by `lab_host` + a confirmed firewall rule set (+ the adopted optional signals) |
| Rule 9 | "The interlock itself adds no OS lock." | ... no OS lock of its own; an external environment needs a person-confirmed exe-scoped rule set (ADR-0021) |
| Rule 9 | "one Block rule per lab exe, for every remote address except 192.168.1.13 and loopback; never OS-wide, never the community client." | ~~the lab group as today (or regenerated, open question 6)~~ ➡️ (Q6, 15:20) per environment, the lab's included, a group GENERATED from its endpoints in Settings (no address written here), applied by Batt and confirmed by his paste-back; never OS-wide; never the ORIGINAL community client. Until the lab group is replaced (5.7), the sentence about today's group stays true as a dated fact |
| Rule 9 | "Its client-side provider and the Windows reporting channel are DEFERRED (ADR-0019, rule 10)." | unchanged, plus: an external environment is confirmed by Batt's paste-back of the generated script's read-back (ADR-0021) |
| Rule 9, community server | "even with evidence, **no agent automation runs there**: its config entry is `pending` with no signals (packet capture is not allowed there), so it can never be green;" | with evidence, an `external` entry and a confirmed rule set, automation may run there under ADR-0021's defaults |
| Rule 9, community server | "pixels and input only; no packet capture unless its rules allow it." | ~~pixels and input only; NO packet capture, whatever its rules allow (ADR-0021)~~ ➡️ (Q2, 15:20) pixels and input only; no packet capture by default; only while its capture permission in Settings is ON (its rules permit it explicitly, the rule recorded as evidence, turned on by the hard path; ADR-0021 4.5) |
| Rule 9 | "**Client profiles:** the existing community-server client on Windows stays **untouched**. rAthena gets a **separate client copy**." | ... and every external environment gets its own separate copy (open question 1, DEFERRED) |
| Rule 10 | "The user setup is the game client with its one-time config, plus Sunshine" | ... plus, for an external environment, the generated firewall script run once per allowlist change |
| Rule 9 | "Adding a server = a person on the Settings page (+ an ADR-0006 entry for this lab), never code." | ... never code. Every server endpoint, the lab's included, lives ONLY in Settings: scripts, compose defaults, tests and docs do not restate it; docs point to it (Batt, 15:20; ADR-0021 4.6; [the inventory](../planning/endpoints-as-config.md)) |
| Rule 9 | "The interlock itself adds no OS lock." (lab) | unchanged for the lab UNLESS Batt confirms the `firewall` signal on lab-rathena (D20) |
| Invariants | "**rAthena `char_ip` / `map_ip` are ADVERTISED addresses and must be `HOST_LAN_IP`.**" | ... must be the address of the machine rathena runs on, and must equal the lab environment's host in Settings (checked, D17) |
| Invariants, "The human-only settings store" | "It holds the USER-MANAGED environment set (`environments.json`, `envstore.py`) + its audit log and the foreground gate's templates." | ... plus, per environment, its endpoints (the single source of truth) and its capture permission: OFF by default, ON only by the hard path with the server's rule as evidence, never by the agent, never by an import (ADR-0021 4.5) |

**Other docs:**
- `config/environments.yaml`: the community entry's comment (`signals: []`, "packet capture is
  not allowed there"), and the header's `lab_host` description (D16).
- `docs/windows-setup.md`: the firewall rule becomes REQUIRED for an external environment, with
  the script, its hash check and the paste-back.
- `README.md`: the Settings page's firewall confirmation, the Packet timeline's states, and its
  "Windows stays clean" section. (➡️ Since 2026-11-13 the README is setup only: these items belong in `docs/console.md` (the
  Settings page, the Packet timeline) and `docs/setup/windows-lab-host.md` ("Windows stays
  clean"). The README of 2026-11-12 had no Packet-timeline or firewall-confirmation text.)
- `docs/ROADMAP.md`: the "Environment interlock" row (its last cell says the community server
  can never be green) and the "Windows stays clean" row.
- `docs/environments/community-server.md`: its status box (pointer added now).
- The pointers added now in ADR-0006, 0007, 0013, 0016, 0019 and 0020 become amendments.
- `docs/demonstrations.md` §2a: "not available" is neither a pass nor a zero.
- The endpoints-as-config changes (code, config, tests and docs), in the order the inventory
  proposes and only as Batt approves them: [docs/planning/endpoints-as-config.md](../planning/endpoints-as-config.md).
  Among them: `docs/windows-setup.md`'s firewall line says "every address except the bot server
  and loopback", which stops being right once the game server and the bot server differ; and
  `docs/client/rathena-client.md` restates the lab's `clientinfo.xml` address.
- The community server's `summary` and `capture` live in the STORE after the seed: editing
  `config/environments.yaml` changes only a fresh seed. The live summary ("packet capture is not
  allowed on that server") needs a person's edit on the Settings page (a normal change).

---

## Appendix A: Batt's brief, verbatim (2026-10-09 ~14:40)

> No implementation now: the community/dev bot-testing server is still Pending in Settings. Write
> the ADR (next free number), cross-reference ADR-0006, ADR-0007, ADR-0013 Part B, ADR-0016 and
> ADR-0019, and update their pointers where this ADR amends them.
>
> **1. The bot works normally on an allowed external server**
> - On an allowed EXTERNAL server (e.g. a community/dev server that permits bots), the bot works
>   normally: it decides from pixels only (ADR-0007), so packets are not needed for any decision.
>
> **2. No packet capture there**
> - We do NOT capture an external server's packets (core principle 2; also a matter of that
>   server's rules).
> - The Packet timeline panel shows a clear state: "External server: packet log not available
>   (not captured by design)", never an error and never an empty list that looks like "nothing
>   happened".
> - Every packet-based tool (verifiers, scorers, safety counts, demo_verify, readiness) reports
>   "not available on this environment" instead of failing or showing zero.
>
> **3. Interlock: DEFAULT DENY via the allowlist (Batt's decision)**
> - The only gate is the ALLOWLIST of server endpoints in config (Settings environments). Anything
>   not allowed is blocked; no runtime blocklist is needed.
> - Enforcement without packets: the existing exe-scoped Windows firewall rules for the RO
>   executables (one-time client config, already permitted by ADR-0019) change from "block listed
>   ranges" to "allow ONLY the allowlisted endpoints": the client physically cannot connect
>   elsewhere. The interlock therefore needs no sniffer on external environments.
> - Keeping Windows in sync without running anything of ours there: propose a reviewed one-time
>   script Batt runs on Windows whenever the allowlist changes, generated from the Settings store,
>   with a checksum of the intended rule set shown in Settings and the script's own output (rule
>   listing + checksum) pasted back by Batt to confirm the match. Until confirmed, the environment
>   stays not-runnable (fail closed).
> - The Forbidden list (official endpoints) moves from a runtime gate to an EDITING guard: adding
>   an allowlist entry that matches a forbidden endpoint is refused. ADR-0016's asymmetric rules
>   stay (easy to forbid, hard to allow; human-only writes).
> - Optional extra signals, to be weighed in the ADR (not required by the decision): the server
>   name/list seen on the login screen matching the registered environment (pixels); a human
>   confirmation at session start.
> - In the lab, the sniffer attestation may remain as an additional check; on external servers it
>   is absent by design.
>
> **4. What we lose there, and how runs are evaluated instead**
> - Lost: automatic safety measurement (attack / NPC-contact / pickup requests), ground truth for
>   scoring (true positions, outcomes), packet-derived labels (no new training labels from
>   external sessions), and L3 certainty (an external server may change scripts, NPCs, menus or
>   maps; our L3 data comes from our own rAthena).
> - Instead: evaluation by the HUD (perception + decision layers), the per-block outcome log,
>   recorded sessions for human review, and conservative defaults (e.g. only skills verified in
>   the lab may run there; unverified blocks refused). Propose how L3 mismatches are detected from
>   pixels (e.g. an NPC or menu option not where L3 says) and how a run stops safely on one.
> - External sessions are never used as training or scoring data unless a later ADR decides
>   otherwise.
