---
doc_type: decision
hypothesis: null
status: GO
role: null
verdict_date: 2026-09-30
verdict_ticket: null
supersedes: null
related: []
next_action: Live-verify on FreeRDP 3.32.1 (Batt) a dummy paste + scrub, then an empty Get-Clipboard on Windows, and that foreign_owner_clears rises only on Windows-side copies (amendment b); resolve ADR-0005 (vision's X access) before Phase 4.
---

# ADR-0004: Clipboard and file transfer are human-only tools

- ➡️ **AMENDED 2026-10-01** (see "Amendment 2026-10-01" at the end): release alone did NOT empty the
  Windows clipboard; every paste is now followed by a **scrub**, and the audit logs only a 12-hex
  digest prefix. E1b below is superseded by that evidence.
- ➡️ **AMENDED 2026-10-01 (b), FreeRDP 3.32.1** (see "Amendment 2026-10-01 (b)" at the end): a
  Windows-side copy now makes xfreerdp *claim* the X CLIPBOARD with **no data targets**. The
  watchdog clears it; content still cannot flow Windows → X. E1c's "owner stayed None" is
  3.15-only.
- **Status:** accepted by Batt, 2026-09-30. T1 + F1 are implemented; F2 stays off; T2 is rejected.
  **Deployed 2026-09-30 11:34 ICT** (dev overlay; one combined desktop + backend recreate). Live-verified
  the same day, through the real feature path:
  - a multi-line ASCII + Thai paste into Notepad (53 characters, exact);
  - that note saved by Windows to `\\tsclient\transfer` and downloaded byte-identical (CRLF);
  - a Thai-named upload visible in Windows Explorer;
  - the watchdog clearing a foreign CLIPBOARD owner;
  - no Origin → 403, and `:8001` → 404;
  - the pasted text found in no log.
- **Code:**
  - `services/backend/src/poring_backend/clipboard.py`: the X CLIPBOARD owner and its watchdog.
  - `routes_transfer.py`: the file routes.
  - `mux.py`: the BOT paste-chord rule.
  - `drops.py`: no silent drops.
  - `services/desktop/bin/rdp-loop.sh`: the keywords.
  - `services/frontend/src/components/PastePanel.tsx` and `FilesPanel.tsx`.
- **Tests:**
  - `services/backend/tests/test_clipboard.py`, `test_transfer.py`, `test_guards.py`, `test_drops.py`;
    `test_app.py` (paste, drops); `test_mux.py`; `packages/poring_env/tests/test_protocol.py`.
  - `scripts/clipboard_x11_check.py`: the service against a real X server.
- **Related:**
  - [ADR-0001 single RDP session](0001-single-rdp-session.md).
  - [ADR-0002 input mux](0002-input-mux.md), amended here: the bot may not paste.
  - [ADR-0005 vision's X access](0005-vision-x-access.md): the gap this ADR cannot close on its own.

## Context

Batt works from a MacBook browser, and the console is plain HTTP on the LAN, which is **not a secure
context**. He needs to:
- paste Mac clipboard text into Windows, Thai included;
- move files Mac → Windows;
- and, nice to have, the reverse.

The lab's hard rule is *pixels in, mouse/keyboard out* for the agent. A clipboard and a file drop are
side channels around that rule, so they must be usable **only by the human**. Their contents must
never be logged.

### Evidence

From the feasibility study, 2026-09-30, on FreeRDP 3.15.0 (Debian trixie) and Windows 11 (dell-3090).
Every key went through the mux as `source=human`. The experiments were reverted afterwards.

| # | Experiment | Result |
|---|---|---|
| E1 | The backend owns the X CLIPBOARD (python-xlib, no new packages) with a 36-char ASCII + Thai string, then Ctrl+V into Notepad | xfreerdp asked for `TARGETS`, then `UTF8_STRING` (70 bytes). Notepad showed the exact text: 36 characters, Ln 1 Col 37, Thai combining marks correct. |
| E1b | Ctrl+V again after the backend released ownership | A pixel-identical frame: nothing pasteable is left on Windows. |
| E1c | Ctrl+A, Ctrl+C inside Windows | The X CLIPBOARD owner stayed `None`. With `direction-to:remote`, the Windows clipboard never appears on the X display. ➡️ FreeRDP 3.15 only; on 3.32.1 xfreerdp claims it empty (amendment b). |
| E2 | A file written into the tmpfs, then Win+R `\\tsclient\transfer` | Explorer listed it, and a folder created from Windows appeared in `/transfer`. **Works both ways.** |
| E3 | The backend owns CLIPBOARD with `text/uri-list`, then Ctrl+V in Windows Downloads | The file arrived, 32/32 bytes, through cliprdr file contents, without FUSE. |

**Source facts** (FreeRDP 3.15.0: `client/common/cmdline.c:3072`, `channels/cliprdr/client/cliprdr_format.c:39`).
`/clipboard:direction-to:remote,files-to:off` leaves only `CLIPRDR_FLAG_LOCAL_TO_REMOTE`:
- the client format list is filtered to data formats (`FileGroupDescriptorW`/`FileContents` are dropped);
- server format lists are filtered to nothing and ignored, so there is no remote → local (3.15; ➡️ on 3.32.1 the empty list reaches the X11 handler, which claims CLIPBOARD with no data targets, and data requests are refused client-side: amendment (b));
- file-contents requests are refused.

> **Correction to the study's wording.** The study said "releasing ownership clears the Windows
> clipboard." FreeRDP ignores an *empty* format list after the first one (`cliprdr_main.c:688`), so
> Windows keeps *advertising* text. But every later paste asks xfreerdp for the data, which finds no
> X owner, and gets **nothing** (E1b). The text is not retained. The claim stands; the mechanism was
> wrong.

## Decision

1. **T1, text.**
   - The console captures text through a real `paste` event in a focused textarea. That works over
     plain HTTP; `navigator.clipboard` does not.
   - It sends `ClipboardPaste{request_id, text}` on `/ws/input`.
   - The backend's `ClipboardService` (its own X connection, on a dedicated thread) then:
     - owns CLIPBOARD and offers `UTF8_STRING` and `text/plain;charset=utf-8`;
     - waits up to 2 s for xfreerdp's `TARGETS` request;
     - waits 0.5 s so Windows has the format list (`CLIPBOARD_SETTLE_S`);
     - has the **mux** inject Ctrl+V as the human;
     - serves the data;
     - releases.
   - Every failure is an explicit `PasteResult` reason (`rdp_clipboard_not_listening`,
     `no_data_request`, `ownership_taken`, …), and **no Ctrl+V is ever sent unless our offer is live**.
2. **Caps (Batt, decision 2).**
   - A paste is at most **64 KiB of UTF-8**, validated in the protocol model and in the console. That
     fits one X request, so no INCR.
   - The transfer area is a **512 MiB tmpfs**.
   - **Large files (e.g. a multi-GB RO client) use other channels** — SMB, or a direct download on
     Windows — **not this feature.** The console says so when the cap is hit.
3. **F1, files.**
   - The tmpfs volume `transfer` is mounted in **desktop and backend only**.
   - It is redirected with `/drive:transfer,/transfer`, so Windows sees `\\tsclient\transfer`.
   - The backend serves `GET /transfer/files`, `PUT`/`GET`/`DELETE /transfer/files/{name}`:
     - raw streamed uploads; a Content-Length cap; `.partial-*` + atomic rename;
     - 409 without `?overwrite=true`;
     - sha256 computed while streaming.
   - New names are sanitised for both sides:
     - NFC; no separators, control characters or hidden names;
     - Windows-reserved characters are replaced;
     - CON/PRN/… are prefixed;
     - at most 200 bytes.
   - Files are not mode-gated, because they inject no input. Paste is.
4. **Configuration by keyword, not raw flags.** This deviates from the prompt's "RDP_CLIPBOARD default
   `-clipboard`": the default still *emits* `-clipboard`, but the variable takes a keyword. A
   free-form value could re-enable Windows → X copying or smuggle in other xfreerdp options.

   | Variable | Keyword | Effect |
   |---|---|---|
   | `RDP_CLIPBOARD` | `off` (default) | `-clipboard` |
   | `RDP_CLIPBOARD` | `text-to-remote` | `/clipboard:direction-to:remote,files-to:off` |
   | `RDP_DRIVES` | empty (default) | no drive |
   | `RDP_DRIVES` | `transfer` | `/drive:transfer,/transfer`, and only if it is mounted |

   - Any other value is logged, and the feature stays off.
   - The backend reads the same two variables, so it offers exactly what the RDP session was started
     with. `Status.clipboard_enabled` and `transfer_enabled` tell the console.
5. **F2** (cliprdr file clipboard) stays **off**. It works Mac → Windows only; Windows → Mac would need
   FUSE, meaning `/dev/fuse` + `CAP_SYS_ADMIN`, which is rejected. F1 already covers both directions.

## Amendment (2026-09-30): ⌘V directly on the remote screen

Batt's manual check found the panel flow too slow. It took three steps (click the target in Windows,
click the panel, ⌘V); Microsoft's Windows App takes two.

**The console's keyboard focus now lives in a visually hidden `<textarea>` inside the screen**, the
technique web RDP clients such as Guacamole use (`StreamCanvas.tsx`).
- An editable element is what lets the browser paste natively; a canvas or `div` never receives a
  `paste` event.
- The policy is the pure `keyDecision()` in `services/frontend/src/lib/keys.ts`, unit-tested:

  | Keys | Decision |
  |---|---|
  | macOS **⌘V**, ⌘⇧V | **paste**: the Mac clipboard |
  | macOS *physical* Ctrl+V | **forwarded**: a Windows-internal copy/paste keeps working, as in Windows App |
  | Other OSes: Ctrl+V, Ctrl+Shift+V | **paste** (Ctrl+Alt is AltGr: forwarded) |
  | Shift+Insert, everywhere | **paste** |
  | Every other key | preventDefault + forwarded by `event.code`, exactly as before |

- **A paste chord is neither prevented nor forwarded.** The browser pastes into the textarea, and
  the `paste` event reads `clipboardData.getData("text/plain")` (this works over plain HTTP). It
  clears the textarea, releases everything held (so a forwarded Ctrl/Shift can't combine with the
  backend's Ctrl+V), then sends the same `ClipboardPaste`.
- **The keystroke itself never reaches Windows.** The V keyup is a stray up for `HeldKeys`, so there
  is no double paste.
- The textarea never keeps text: `beforeinput` is prevented, and `input`/`compositionend` clear it
  (IME composition is not cancelable). Keys are forwarded by physical code even with the Thai input
  source active, since the macOS Thai layouts are plain layouts, not composition IMEs.
- Clicking the screen focuses the textarea (`preventScroll`; the viewport's `mousedown` is prevented
  so the default action can't steal focus). Leaving it still releases held keys.
- A toast on the screen reports the result: "Pasted N characters", or the refusal reason
  (`mode_bot`, `no_data_request`, an oversize paste, a clipboard without text).
- The panel stays as the fallback.
- **Nothing on the backend changed.** The same message, the same Origin requirement, the same mode
  rules (BOT refused; ASSIST takes the human lease), the same logging.
- **Consequence off macOS:** Ctrl+V becomes "paste the viewer's clipboard", so a Windows-internal
  paste there needs Windows' own menu or right-click. On a Mac, Cmd and Ctrl keep the two apart.

## Future work: Windows → Mac clipboard (not planned yet)

Copying in Windows and pasting on the Mac (the other half of what Windows App does) is **blocked on
two things**:
1. **ADR-0005.** The backend would need the Windows clipboard on the X display
   (`direction-to:all`). While the vision container can still connect to X, that exposes every
   Windows copy to it. Only after vision loses X access can Windows → X be switched on.
2. **A secure context (HTTPS).** The Windows copy happens *after* the keystroke, so the text reaches
   the browser asynchronously, and only the async `navigator.clipboard.writeText()` can put it on the
   Mac clipboard then. That API needs HTTPS, or `localhost` through an SSH tunnel. The synchronous
   `copy`-event path works over HTTP, but only for data already present at key time.

Until both are resolved, reverse text goes through a file in `\\tsclient\transfer`.

## Enforcement: how "human-only" is held

| Layer | Rule | Pinned by |
|---|---|---|
| Protocol | `ClipboardPaste` exists in `BrowserToBackend` only: not in `InputEvent`, `AgentInput.events` or `AgentToBackend`. | `test_protocol.py` walks every `$ref` reachable from the agent side. |
| Listener | `/transfer/*` answers only on the public listener `:8000` (`scope["server"]`), never on the agent's `:8001`. | `test_transfer.py` |
| Origin | A paste needs a `/ws/input` connection that presented an allowlisted `Origin`, i.e. a browser: `origin_required`. The `/transfer` routes need an allowlisted Origin on **every** method, GET included. Downloads are fetched as blobs, so the agent and scripts, which send no Origin, cannot list, read or write. CORS is limited to `FRONTEND_ORIGINS`. | `test_app.py`, `test_transfer.py` |
| Mode | A paste is refused in BOT (`mode_bot`) and, in ASSIST, takes the human lease. This holds for the panel and for ⌘V on the screen, which send the same message. | `test_app.py` |
| Mux | A **BOT** Ctrl+V, Meta+V (Windows clipboard history) or Shift+Insert is refused (`paste_chord_bot`), in *both* key orders, because X autorepeats a held XTest key. | `test_mux.py` |
| X display | **Watchdog.** XFixes on CLIPBOARD: any owner other than the backend's window is logged (rate-limited) and cleared at once. In `text-to-remote` xfreerdp never owns CLIPBOARD, so this only ever fires on a foreign client. | `test_clipboard.py`, `scripts/clipboard_x11_check.py` (real Xvfb) |
| x11vnc | `-nosel`: the unauthenticated noVNC viewer never receives selections, so a paste's text is not relayed while the backend owns it. | `test_guards.py` |
| Volumes | `transfer` is in desktop and backend only; never vision, rathena, sniffer, db or frontend. | `test_guards.py` |
| Code | `poring_vision` and `poring_env.remote` mention no selection, clipboard, XFixes or transfer symbol, and do not import the backend. | `test_guards.py` |
| Logging | Text → length + sha256 (input log and `data/transfer_log/`). Files → name, size, sha256. **Never contents.** A unique marker is pasted and uploaded, then searched for in every log file. | `test_app.py`, `test_transfer.py` |
| Drops | An unreadable or invalid message on any channel is counted in `/health` (`dropped_messages`), logged as a rate-limited WARNING, and answered with `ErrorReply`. It is never silent (decision 4). | `test_drops.py`, `test_app.py` |

## Consequences

- Batt can paste text, Thai included, and move files both ways:
  - no image build (the dev overlay bind-mounts `rdp-loop.sh` and `run-x11vnc.sh` until the next
    desktop build);
  - no new package;
  - no disk writes for transfers (tmpfs).
- **Memory.** tmpfs pages are charged to the cgroup of the process that *writes* them, and swap is off.
  Windows → Linux copies are written by xfreerdp, so desktop goes from **1 GiB to 1.5 GiB**. Its peak
  without transfers is ~220 MiB, and overflowing the limit would OOM-kill the RDP session. Backend
  stays at 1 GiB (peak ~90 MiB + 512).
- **New surfaces:**
  - `\\tsclient\transfer` is readable and writable by any Windows process, the game client included,
    for the life of the session;
  - CLIPBOARD is owned for about a second per paste. While it is, **any X client could ask for the
    text** (see ADR-0005).
- **Hashes of very short secrets are guessable.** The log keeps a sha256 of every paste (as asked) and
  sha256 of a 4-digit PIN is trivially reversed, so don't paste secrets through this channel.
- A transfer area is lost when both containers stop. It is a hand-off point, not storage.
- Windows remembers `\\tsclient\transfer` in its Run history and Explorer's recent list.
- **What this ADR cannot close.** The vision container can still connect to the X socket: `:ro` does
  not block `connect()`, and Xvfb runs `-ac`. It can also reach `backend:8000` with a forged Origin.
  Human-only is therefore enforced *by construction for the protocol and the mux*, but only *by
  convention* at the X and network level. **ADR-0005** tracks that, and blocks Phase 4.

## Alternatives considered

- **T2 — typing through `/kbd:unicode:on`:** it turns *every* key with a character, game letters
  included, into a Unicode event, which breaks the RO client's scancode input. **Rejected.**
- **T2 — typing through `/kbd:pipe:<fifo>`:** Thai-capable, but:
  - it is a **second injection channel around XTest and the mux**, so the input log and the
    arbitration would both be bypassed;
  - xfreerdp reads the pipe in 64-byte chunks, which can split a 3-byte Thai character.
  - **Rejected.**
- **F2 — cliprdr file clipboard:** works Mac → Windows (E3), but not the reverse without FUSE. It adds
  nothing over F1, and widens what an X client can push. **Off.**
- **`direction-to:all`** (Windows → Mac text through X): exposes every Windows copy to every X client,
  the vision container included. **Rejected.** Reverse text goes through a file on
  `\\tsclient\transfer`.
- **`navigator.clipboard`:** needs a secure context. `localhost` through an SSH tunnel would qualify,
  as an optional enhancement.

## Amendment 2026-10-01: the Windows clipboard kept pasted text; scrub after every paste

**Evidence.**
- Batt's rAthena test password reached Windows through this feature: the console's ⌘V →
  `ClipboardPaste` path. The input log's paste record (16 chars, sha256 equal to the .env value)
  is at 12:10:57 ICT, followed by his login at 12:10:58.
- It was still pasteable at **13:04 ICT**, when a camera right-drag over a Windows Terminal pasted
  it onto a prompt. It was not executed.
- At 15:17 ICT the Windows clipboard held his 14:37 paste: 4 characters, the same sha256 prefix as
  the paste record.
- Clipboard history and cloud clipboard were OFF (no `EnableClipboardHistory` /
  `EnableCloudClipboard` values; no policy), so this was the live clipboard, not history.
- **E1b ("a pixel-identical frame: nothing pasteable is left") does not hold** once a Windows
  application has actually pasted. The application asked for the data, and Windows keeps the
  rendered copy after we give up ownership.

**Decision.**
1. **Scrub.** After a paste is served and has lingered, the service releases CLIPBOARD and at once
   re-owns it, offering **nothing**:
   - xfreerdp asks TARGETS and announces a fresh, empty text format to Windows, which replaces its
     copy;
   - a data request during the scrub gets `b""`;
   - then it releases.
   - The paste's outcome is unchanged (`ok`).
   - A scrub that cannot complete is counted in `/health` `clipboard.scrub_incomplete` and logged.
     Never silent.
2. **Stale `SelectionClear`.** On a real X server, the SelectionClear of our own release arrives
   after a quick re-own. `OwnershipLost` is ignored while we still own CLIPBOARD. Before this fix it
   could also abort a queued paste that started right after a release.
3. **Audit digest.** Paste records (input log and transfer log) carry only a **12-hex sha256
   prefix**. That is enough to match a paste against a known value, as done here, and too short
   to brute-force a short paste offline. File transfers keep full digests: those are integrity
   (`x-content-sha256`).
4. **The lab's own Windows session** (`poring-lab`, a standard user) has clipboard history and
   cloud clipboard OFF, Windows Terminal's right-click is a context menu (no paste), and conhost
   QuickEdit is OFF ([rathena-client.md](../client/rathena-client.md), "Windows account").

**Verification.**
- `services/backend/tests/test_clipboard.py`:
  - paste + scrub = two own/release rounds;
  - an empty payload is served during the scrub;
  - an incomplete scrub is counted;
  - a stale SelectionClear is ignored.
- `test_app.py`: no full digest anywhere on disk.
- `scripts/clipboard_x11_check.py` against a real Xvfb: **PASS** (2 TARGETS rounds, scrub completed).
- **Not yet verified live end to end:** a dummy paste followed by an empty `Get-Clipboard` on
  Windows (the operator skipped the dummy paste on 2026-10-01). Do it at the next console session.

## Amendment 2026-10-01 (b): FreeRDP 3.32.1 claims CLIPBOARD (empty) on every Windows copy

**Found** during the Arm C regression checks ([h264-plan.md](../h264-plan.md), "Arm C results").
- With `/clipboard:direction-to:remote,files-to:off` unchanged, `Set-Clipboard -Value
  'poring-probe-332'` in the `poring-lab` session moved `/health` `clipboard.foreign_owner_clears`
  from **0 to 3**.
- The backend logged `CLIPBOARD taken by foreign window 0xc00002`, which is xfreerdp's own window
  (class `xfreerdp`).
- After the clears, both CLIPBOARD and PRIMARY were unowned.

**Cause, from the tagged sources:**
- **3.15.0 never reached the X11 handler.** `channels/cliprdr/client/cliprdr_format.c`
  `cliprdr_process_format_list` stopped with `if (filteredFormatList.numFormats == 0) goto error_out;`.
  With REMOTE_TO_LOCAL off, the X11 handler never saw a Windows copy. That is why E1c's owner
  stayed None.
- **3.32.1 always calls the handler.** It calls `ServerFormatList` with the (empty) filtered list.
  `client/X11/xf_cliprdr.c` `xf_cliprdr_server_format_list` then:
  - keeps only the implicit CF_RAW;
  - advertises just TIMESTAMP and TARGETS (no data target is appended for zero formats);
  - **takes selection ownership**.
- **Content still cannot cross Windows → X.** 3.32.1 `cliprdr_main.c`
  `cliprdr_client_format_data_request` returns early ("remote -> local copy disabled, ignoring
  request") when REMOTE_TO_LOCAL is off. Any X requester gets no Windows data.
  - This is from source. An empirical probe could not win the race with the watchdog, which clears
    the claim on the XFixes event.

**Consequences:**
1. **The guarantee holds.** The Windows clipboard's content never appears on the display, by the
   client-side request guard plus the watchdog (defence in depth, as designed).
2. **`foreign_owner_clears` is no longer a clean alarm.** It now also counts xfreerdp's empty claims
   (about 1–3 per Windows-side copy).
   - A rise right after a Windows copy is expected.
   - A rise with no Windows copy, or an owner that is not the `xfreerdp` window, is still the signal.
   - A separate counter for xfreerdp's empty claims would restore it. **Not built**: it is a code
     change for Batt to choose.
3. **T1 paste interplay on 3.32 is unverified.** After the backend's paste, Windows may announce
   its new clipboard, so xfreerdp claims, and the watchdog clears. The live check is Batt's (see
   next_action).
4. **Rolling back to 3.15** (`poring-lab/desktop:freerdp-3.15`) restores the old behaviour, at the
   cost of Arm C's delivery gain (30 → 9 fps outdoor).

