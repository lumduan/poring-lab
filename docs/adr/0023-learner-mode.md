---
doc_type: decision
hypothesis: null
status: ACCEPTED (decided by Batt 2026-11-07); decision 1 BUILT 2026-11-12
role: null
verdict_date: 2026-11-07
verdict_ticket: null
supersedes: null
related: [0006-sanctioned-test-environments.md, 0016-environment-interlock.md, 0019-windows-stays-clean.md, 0021-external-servers.md, 0001-single-rdp-session.md, ../planning/bot-server-cutover.md]
next_action: "Decision 1 (the `declared` attestation in envstore / interlock / the Settings page) is BUILT 2026-11-12 (section Implementation). Still to design and build: decision 3 (the learner's Windows gets only the remote program), decision 4 (the Windows host as a console session setting) and the per-target remote identity (credentials, RDP certificate pin, Sunshine pairing) on a shared bot server."
---

# ADR-0023: Learner mode -- a person may declare permission; nothing on the learner's Windows

## Context
Batt's decision came from teaching, not from the lab (2026-11-07, during the bot-server cutover):

> "From what I have actually taught, some things are obstacles to learning. At first I even had to
> make a simple Python file for them to download and try (the simple bot you just made)."

- **Who the learners are:** mostly young people who like playing the game and want to go on to
  learn how to work with AI. If they must set up or configure a lot, they give up before they start.
- **What they have:** often ONE machine. Running an rAthena server takes real skill. It is easier
  when a capable person hosts a server and the learners connect to it. Some share ONE bot server
  and take turns, each remoting into their OWN Windows PC.
- **What today's lab requires (ADR-0006, ADR-0016):** the bot may press only while an Allowed
  environment is ATTESTED from packets: our sniffer must see a live session of a lab account on
  that server. A server that permits bots but cannot be packet-verified (a permitted community
  server; a class server a teacher hosts) can therefore never be green. The bot cannot ask such a
  server for anything, and it does not touch the traffic between the client and the server; that
  part is right and stays.
- **Batt's principle:** "We cannot control everyone who uses our open source, but we can help them
  learn. Whoever takes it to an official server, we would never know anyway. Like a shop that
  sells kitchen knives: our job is to make a good, quality knife."
- The student kit (`teaching-kit`, `teaching/simple-bot`: one Python file, the v1 ONNX, 20 sample
  frames) already has no interlock and needs no server of ours.

## Decision
1. **A person may DECLARE permission (a new attestation kind, `declared`).**
   - On the Settings page, a person states that they have the server owner's permission and gives
     the server's address. It can be checked against their OWN client's `clientinfo.xml` with the
     existing in-browser game-file finder (ADR-0016; nothing is uploaded).
   - The bot may then act there. The page and the console show it as **"declared by a person, not
     verified"**, never as verified.
   - The same human-only rules as today: a person's act from their own computer, audited; the agent
     never declares or confirms anything (CLAUDE.md, the settings store).
2. **Research counts only VERIFIED sessions.** Packet attestation stays for the lab's own
   environment: it is the lab's ground truth. Every metric, judge and dataset uses packet-verified
   sessions only; a declared session never enters them.
3. **Nothing is installed on the learner's Windows except the remote program.** The game client and
   the program that lets the bot server see and drive it (Windows' own Remote Desktop, or
   Sunshine for the stream) are all the learner's PC needs. The lab's Windows-side pieces (the
   `poring-lab watch` task, the agent's shell shortcut, the tscon task, the exe-scoped firewall
   group) stay LAB-ONLY (ADR-0019) and are never part of a learner's setup.
4. **The learner enters the Windows host on the bot server.** The IP of the Windows PC to remote
   into is a setting a person enters on the bot server's console, not a `.env` edit and a container
   recreate. A shared bot server serves learners one at a time, each with their own PC.
   ADR-0001 still holds: ONE Windows session and one display path at a time per target.
5. **The forbidden list of official servers stays a DEFAULT.** It ships as today, and a person can
   lift an entry with a typed reason (ADR-0016's asymmetric rules). It costs a learner nothing and
   protects them from a ban by accident. Example: the 2021 client exe calls Gravity's AssistAddr at
   character select (ADR-0016).

## What this changes (pointers added in the older records)
- **ADR-0006:** the community server's rule "no agent automation runs there" becomes: no automation
  until a person DECLARES permission (or packet capture becomes allowed there). Its permission
  evidence is still pending: a declaration is the person's own statement.
- **ADR-0016:** the signals gain `declared`; an environment is green either by packet attestation
  (as today) or by a person's declaration (labelled "declared, not verified").
- **ADR-0019:** reaffirmed and extended to learners: their Windows gets only the remote program.
- **CLAUDE.md rule 9:** a pointer here. Until the build lands, rule 9 stands as written.
  ➡️ 2026-11-12: decision 1 is built (section Implementation); decisions 3 and 4 are not.

## Open questions for the build (not decided here)
- **Per-target identity on a shared bot server:** each learner's RDP credentials, the RDP
  certificate pin (`RDP_CERT_SHA256`) and the Sunshine pairing are per Windows PC today, in `.env`
  and one volume. They need a per-target store: who may enter them, and where secrets live.
- **The sniffer's client filter** names the Windows PC by IP (compiled today): with packets
  unavailable on a declared server it is unused there, but the lab's own server still needs it per
  target.
- **How long a declaration lasts:** per session, or until revoked; how it is shown to the next
  learner who takes a turn. ➡️ 2026-11-12 build: until a person withdraws it (section
  Implementation); how it is shown to the next learner is still open.

## Consequences
- A learner with one PC, a class server someone hosts, and a shared bot server can run the bot
  after a few entries on one web page, with nothing extra on their Windows.
- The lab keeps its verified ground truth: a declared session is visible as such and never counted.
- The code to build it does not exist yet; the lab runs under ADR-0006 / ADR-0016 until it does.
  ➡️ SUPERSEDED 2026-11-12 for decision 1: it is built (next section). Decisions 3 and 4 and the
  per-target identity are still not built.
- ➡️ 2026-11-12: on a declared server the account is no GM, so the hunting runner has a
  `--player-mode` that types no line and reads no lab DB (docs/planning/player-mode.md, first cut
  BUILT, not live-verified; docs/setup/new-lab-host.md section 11.1).

## Implementation (2026-11-12): decision 1

- **The parent's review (2026-11-12):** a declaration is REFUSED on an environment the lab verifies
  by packets (one with `signals`, e.g. the lab's own rAthena): `declaration_not_for_attested`.
  - Such an environment keeps its packet check alone.
  - A declaration there would have turned it green whenever its attestation fails (a non-lab
    account, character select).
  - Declarations are for the servers the lab CANNOT verify: a learner's class server, or a public
    rAthena whose owner permits bots.
Why now, in Batt's words (2026-11-12, translated): "Don't lock: we cannot control other people
anyway; just write a warning." and "The more we lock, the more it breaks later: a user configures
their own rAthena on a public IP, but we lock it, and when they pull our git again their config
breaks at once." Before this build a user-created Allowed environment could never be green: the
interlock needs `signals`, a technical field neither the page nor an import can set, so it said
`no_signals_configured`; packet attestation works only for the lab's own rAthena (our sniffer).

What was built:
- **The store** (`envstore.py`, `settings/environments.json`, gitignored: a pull never touches
  it). An environment may carry `declared` = {`at` (ISO 8601 with offset), `peer` (the browser's
  address from the write gate), `statement` (the person's own words, 10 to 500 characters)}.
  Only an ALLOWED environment carries one (`validate`: `declaration_not_allowed_here`); changing
  it away from allowed drops it. It is a technical field: export never writes it, and an import
  that carries one is refused (`declaration_not_importable`); an import keeps the current ones.
- **The rules** (`classify`): a new or changed declaration is its own change kind, `declare`, which
  needs the statement; withdrawing it is `easy` (tightening). Every existing rule stands (easy /
  normal / hard, one hard change per save). Audited as `declare` / `withdraw`: the environment, the
  peer, the time and the statement.
- **The write path** (`routes_settings.py`): the same `PUT /settings/environments` and the same
  human-only gate (LAN browser + Origin + CSRF, never `:8001`, never the lab host, never
  `WIN_HOST`, rate limit, audit). The page sends only the statement; the backend stamps `at` and
  `peer` itself. The page sends the whole set, so a kept declaration comes back as the same
  statement and keeps its time and peer.
- **The interlock** (`interlock.py`): packet-attested environments are tried FIRST, exactly as
  before. Only when none is green, a declared allowed environment is green when it has servers
  (else `no_servers`), the capture lock is `rdp`/`console` and steady (else `lock_not_steady`),
  and, only if the environment names a Windows host, `WIN_HOST` is that host (else
  `host_mismatch`). No attestation and no signals are needed. Its reason is `declared` (the
  attested one stays `ok`); the verdict's `verified` is False. A shipped `environments.yaml` that
  sets `declared` is refused (`config_invalid`): a declaration is never a file's.
- **The protocol**: `EnvironmentStatus.verified` (true = packet-verified, false = declared by a
  person, not verified, null when not green), in `/health` and the console's Status.
- **The console**: on an allowed environment's Settings card, a "Declare permission" section with
  Batt's warning before the statement box, then "Declared by a person, not verified -- <date>" and
  Withdraw. The form is offered only where the lab has no packet check of its own (no `signals`):
  the lab's own environments do not show it, though the backend would accept one there too (it
  would only ever be tried after the attested path, and labelled). A declaration that exists can
  always be withdrawn. The banner and the mode badge say a declared green is a person's
  declaration, not verified; a verified green reads as before. Text only (no HTML from stored
  values).

What it means for decision 2: a declared server is one our sniffer cannot see, so no packet
metric, judge or dataset can contain its sessions; the `verified` label marks the rest. No
research tool reads `verified` yet: a lab script that only checks `state == "green"` treats a
declared green as green.

How long a declaration lasts (an open question above): until a person withdraws it, or the
environment stops being allowed. It survives restarts and pulls (the store is gitignored).

NOT built here: decision 3 (nothing on the learner's Windows but the remote program), decision 4
(the Windows host as a console setting; today `windows_host` is still technical, so a
user-created environment has none and the declared path does not check the host), the per-target
identity on a shared bot server, and a link from the game-file finder's `clientinfo.xml` check to
the declaration (the finder works as before, separately).
