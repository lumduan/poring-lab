---
doc_type: design
hypothesis: null
status: ACCUMULATING
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Batt supplies the server's bot/AI-testing rules or announcement (link + date) for the exact host below; until then the server is FORBIDDEN for any automation (ADR-0006 rule 1).
---

# Community bot-testing server: permission record (ADR-0006 rule 1)

> **Status: EVIDENCE PENDING, so FORBIDDEN for any automation.**
> - Batt may play there manually, through the console, as the human.
> - Even once evidence is recorded, **no agent automation** runs there until the environment
>   interlock exists (ADR-0006 rule 2, [issue #2](https://github.com/lumduan/poring-lab/issues/2)).

| Field | Value |
|---|---|
| Server name | `<COMMUNITY_SERVER_NAME>` (pending: from the client config Batt supplies) |
| Host:port (login) | `<HOST:PORT>` (pending: from the client config Batt supplies) |
| Client profile on Windows | The existing client in the Windows session. It is **untouched**: never modified, patched or repointed. rAthena uses a separate copy. |
| Rules / permission statement | **Evidence pending: Batt to supply** (a link to the server's rules or announcement permitting bot/AI testing) |
| Packet capture allowed? | Not unless the server's rules say so explicitly (record the rule here). Until then: pixels and input only. |
| Bot identification rule | Pending (from the server's rules) |
| Date checked | 2026-09-30: the identity and rules are **not yet confirmed** |
| Checked by | – |

## An observation the evidence has to settle (2026-09-30)

The RO client was logged in at 12:52 ICT. The frame showed:
- a Cash Shop button and RODEX mail;
- server-wide gacha broadcasts ("Ragnarok Urgent Call2026 Scroll");
- a "RagnarokClassic" installer in Windows Downloads.

These resemble the **official** Thai Ragnarok Classic service, which ADR-0006 forbids. Batt states the
server is a community bot-testing server. The record above therefore has to show that the
**permission statement covers the exact host** the client connects to.

## Before each new experiment series

1. Re-open the rules or announcement link above. Confirm that bot/AI testing is still permitted and
   note any new rule (rate limits, how bot characters must be labelled).
2. Confirm the client still connects to the host above.
3. Update "Date checked".
4. If anything cannot be confirmed, the server is **forbidden** until ADR-0006 is updated.

## Other participants' data (ADR-0006 rule 4)

- Chat lines, names and screenshots showing other players stay **local only**:
  `data/`, gitignored, or scratch.
- They are **pseudonymized** in any dataset, never published, and never pushed.
- Debug frames holding them are deleted once they are no longer needed.
