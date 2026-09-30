---
doc_type: decision
hypothesis: null
status: GO
role: null
verdict_date: 2026-09-30
verdict_ticket: null
supersedes: null
related: []
next_action: Batt records the community server's bot/AI-testing permission (docs/environments/community-server.md); build the environment interlock (GitHub issue, blocks-phase-4) before Phase 4.
---

# ADR-0006: Sanctioned test environments — self-hosted rAthena and a community bot-testing server

- Status: ACCEPTED
- Date: 2026-09-30
- Deciders: Batt
- Supersedes: the "never run against public servers" wording in the project brief (official servers
  remain forbidden)

## Context
poring-lab needs two kinds of environment that no single server provides:

1. Controlled ground truth: known entity positions, deterministic spawns, server logs and passive
   packet capture for labeling and evaluating perception. Only a self-hosted rAthena gives this.
2. A live multi-party social environment: many independent participants (humans, LLM agents, other
   bots) talking at the same time, in Thai and other languages, with their own intentions. This is
   required for research such as addressee detection — deciding which chat lines are directed at
   our character (name, pronoun reference like "that person", context) and which are other people
   talking to each other, analogous to selective attention in a crowded room ("cocktail party
   effect"). This cannot be simulated credibly on a private rAthena: the other speakers would be our
   own scripts, which leaks our own assumptions into the data.

A community-run online server exists for exactly this purpose: developers of bots and AI agents
use it to test LLM chat, vision agents, and protocol tools (e.g. OpenKore) together. It is not an
official server and bot testing is its stated purpose.

## Decision
Two environments are sanctioned. Everything else is forbidden.

| Environment | Purpose | Allowed |
|---|---|---|
| rAthena (self-hosted, LAN) | Perception ground truth, auto-labeling, evaluation, fast-loop control, humanizer experiments, packet ground truth | Everything in the project principles, including passive packet capture of our own traffic |
| Community bot-testing server (`<COMMUNITY_SERVER_NAME>`, `<HOST:PORT>`) | Multi-party social/chat research (addressee detection, turn-taking, Typhoon slow loop), agent behavior among other agents and humans | Pixel + input only (principle 1). No packet capture or modification unless the server's rules explicitly allow it; record that rule here if so |
| Official servers and any other public server | — | FORBIDDEN, for all components, in all modes |

Rules that apply on the community server:
1. Evidence of permission: `docs/environments/community-server.md` records the server's rules or
   announcement that permits bot/AI testing (link and date checked, no credentials). Re-check the
   rules before each new experiment series; if they change or cannot be confirmed, the server is
   treated as forbidden until this ADR is updated.
2. Target allowlist + interlock: the agent may act only when the connected server is on the
   allowlist (rAthena or the community server). The check must not rely on the agent's own
   judgment: define a verifiable signal (e.g. the client folder/exe used, window title, a marker on
   screen, or the backend's knowledge of which client profile was launched). If the signal is
   missing or unknown, the mux refuses BOT/ASSIST automation.
3. Etiquette: rate-limit chat and actions; follow the server's rules on identifying bot characters;
   do not disrupt other participants' experiments; a human can always take over (ASSIST/HUMAN).
4. Other participants' data: chat lines and names from other players are stored locally only,
   pseudonymized in any dataset, never published, and excluded from anything pushed to GitHub.
5. The LLM (Typhoon) stays in the slow loop and emits intents only; any chat it produces is sent
   through the mux like any other input and logged with source=bot.

## Consequences
- Research on multi-party chat becomes possible without touching official servers.
- A second client profile (community server) must be kept separate from the rAthena client
  profile; never modify one in place to serve the other.
- The interlock in rule 2 becomes a prerequisite for roadmap Phase 4 (together with ADR-0005).
- Roadmap Phase 6 (Typhoon slow loop) targets the community server for social experiments and
  rAthena for deterministic tests.

## Implementation notes (added 2026-09-30, not part of the decision text above)

**Evidence status: PENDING, so the community server is currently treated as forbidden** for any
automation (rule 1). What is recorded, and what is missing:
[docs/environments/community-server.md](../environments/community-server.md).

**An observation that the evidence must settle.** On 2026-09-30 at 12:52 ICT, a frame of the RO
client (then logged in) showed:
- a Cash Shop button and RODEX mail;
- server-wide gacha broadcasts ("Ragnarok Urgent Call2026 Scroll");
- a "RagnarokClassic" installer in the Windows Downloads folder.

Those resemble the official Thai Ragnarok Classic service. Batt states the server is a community
bot-testing server. The permission record has to name **the exact host** the client connects to, so
that the two cannot be confused.

**Where each rule stands today:**

| Rule | Status |
|---|---|
| 1 Evidence | The file exists; the evidence is pending (Batt to supply the rules/announcement link). |
| 2 Interlock | **Not built.** It is tracked as [issue #2](https://github.com/lumduan/poring-lab/issues/2) (`blocks-phase-4`, `security`). Until it exists, **no agent automation runs against the community server** (CLAUDE.md rule 9). Batt may play there manually through the console, as the human. |
| 3 Etiquette | Applies once automation exists (the Phase 4+ humanizer/rate limits). |
| 4 Other players' data | Nothing is stored in the repo. The one debug frame with other players' names and chat (latency work, 2026-09-30) was deleted from scratch memory. |
| 5 Typhoon | Phase 6, [ROADMAP](../ROADMAP.md). |

**Client profiles.** The existing community-server client on Windows stays **untouched**. The
rAthena work gets a **separate client copy** (README, "Windows host checklist").
