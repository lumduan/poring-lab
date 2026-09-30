---
doc_type: decision
hypothesis: null
status: GO
role: null
verdict_date: 2026-09-30
verdict_ticket: null
supersedes: null
related: []
next_action: Batt's manual check from the MacBook (paste ASCII + Thai, upload and open from \\tsclient\transfer, create a file on Windows and download it); resolve ADR-0005 (vision's X access) before Phase 4.
---

# ADR-0004: Clipboard and file transfer are human-only tools

- **Status:** accepted by Batt, 2026-09-30. T1 + F1 are implemented; F2 stays off; T2 is rejected.
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
| E1c | Ctrl+A, Ctrl+C inside Windows | The X CLIPBOARD owner stayed `None`. With `direction-to:remote`, the Windows clipboard never appears on the X display. |
| E2 | A file written into the tmpfs, then Win+R `\\tsclient\transfer` | Explorer listed it, and a folder created from Windows appeared in `/transfer`. **Works both ways.** |
| E3 | The backend owns CLIPBOARD with `text/uri-list`, then Ctrl+V in Windows Downloads | The file arrived, 32/32 bytes, through cliprdr file contents, without FUSE. |

**Source facts** (FreeRDP 3.15.0: `client/common/cmdline.c:3072`, `channels/cliprdr/client/cliprdr_format.c:39`).
`/clipboard:direction-to:remote,files-to:off` leaves only `CLIPRDR_FLAG_LOCAL_TO_REMOTE`:
- the client format list is filtered to data formats (`FileGroupDescriptorW`/`FileContents` are dropped);
- server format lists are filtered to nothing and ignored, so there is no remote → local;
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

## Enforcement: how "human-only" is held

| Layer | Rule | Pinned by |
|---|---|---|
| Protocol | `ClipboardPaste` exists in `BrowserToBackend` only: not in `InputEvent`, `AgentInput.events` or `AgentToBackend`. | `test_protocol.py` walks every `$ref` reachable from the agent side. |
| Listener | `/transfer/*` answers only on the public listener `:8000` (`scope["server"]`), never on the agent's `:8001`. | `test_transfer.py` |
| Origin | A paste needs a `/ws/input` connection that presented an allowlisted `Origin`, i.e. a browser: `origin_required`. The `/transfer` routes need an allowlisted Origin on **every** method, GET included. Downloads are fetched as blobs, so the agent and scripts, which send no Origin, cannot list, read or write. CORS is limited to `FRONTEND_ORIGINS`. | `test_app.py`, `test_transfer.py` |
| Mode | A paste is refused in BOT (`mode_bot`) and, in ASSIST, takes the human lease. | `test_app.py` |
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
