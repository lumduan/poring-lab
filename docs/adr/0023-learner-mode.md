---
doc_type: decision
hypothesis: null
status: ACCEPTED (decided by Batt 2026-11-07; NOT BUILT yet)
role: null
verdict_date: 2026-11-07
verdict_ticket: null
supersedes: null
related: [0006-sanctioned-test-environments.md, 0016-environment-interlock.md, 0019-windows-stays-clean.md, 0021-external-servers.md, 0001-single-rdp-session.md, ../planning/bot-server-cutover.md]
next_action: "Design the build (a plan doc): the `declared` attestation in envstore / interlock / the Settings page, the Windows host as a console session setting, and the per-target remote identity (credentials, RDP certificate pin, Sunshine pairing) on a shared bot server. Until it is built, ADR-0006 / ADR-0016 and CLAUDE.md rule 9 stand as written."
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

## Open questions for the build (not decided here)
- **Per-target identity on a shared bot server:** each learner's RDP credentials, the RDP
  certificate pin (`RDP_CERT_SHA256`) and the Sunshine pairing are per Windows PC today, in `.env`
  and one volume. They need a per-target store: who may enter them, and where secrets live.
- **The sniffer's client filter** names the Windows PC by IP (compiled today): with packets
  unavailable on a declared server it is unused there, but the lab's own server still needs it per
  target.
- **How long a declaration lasts:** per session, or until revoked; how it is shown to the next
  learner who takes a turn.

## Consequences
- A learner with one PC, a class server someone hosts, and a shared bot server can run the bot
  after a few entries on one web page, with nothing extra on their Windows.
- The lab keeps its verified ground truth: a declared session is visible as such and never counted.
- The code to build it does not exist yet; the lab runs under ADR-0006 / ADR-0016 until it does.
