# Troubleshooting

<!-- Moved from the root README on 2026-11-13 (Batt: "the README only for setup; the rest in docs/"). -->


**The client says "Failed to Connect to Server" right after logging in (and quits on OK).** This
client gives up when no server is picked within ~1–2 s of the list appearing; it never even dials
the char server. Pick it at once (a human click at 1.3 s works; ro_agent clicks at 0.8 s).

**Login works, then the client hangs or disconnects at server/character select.**
- The char/map servers are advertising the wrong IP. `HOST_LAN_IP` must be this host's LAN address.
- Check `docker compose logs rathena | grep "clients will be sent"`.
- Never set rAthena's `bind_ip` to the LAN IP: it doesn't exist inside the container.

**Keys and clicks show in the input log, but typing never reaches Windows (after console mode).**
The X keyboard focus was left at None: SDL (Moonlight) focuses its window with RevertToNone, and
there is no window manager to take the focus back.
- `rdp-loop` resets the focus to PointerRoot before every connect, and gamestream does the same
  after every stream.
- By hand:

      docker exec poring-lab-desktop-1 bash -c 'source /usr/local/bin/rdp-loop.sh; focus_pointer_root'

- Check: the backend's `Xlib get_input_focus()` must report focus 1 (PointerRoot), not 0.

**The RDP session keeps dropping or never connects.** Windows client editions allow **one**
interactive session. `rdp-loop` reacts to xfreerdp3's exit code:

| Exit | Meaning | What happens |
|---|---|---|
| **5** | someone else took the session | backs off for 10 minutes. Don't use `mstsc` against the Windows host while the stack runs. |
| **132 / 134 / 135 / 148–159** | authentication or account failure | **stops retrying** (account-lockout risk). Fix `.env`, then recreate the desktop ([setup/game-accounts.md](setup/game-accounts.md): a restart keeps the old environment). |
| 16–26 | licensing, or a bad command-line flag | stops |
| anything else | network trouble, host booting | backs off, 2 s → 60 s |

Watch it with `docker compose logs -f desktop`.

**FreeRDP 2 vs 3 flags.** This image pins FreeRDP **3.32.1** from trixie-backports (`xfreerdp3`, a link to
`xfreerdp`; rollback image `poring-lab/desktop:freerdp-3.15` ➡️ removed 2026-10-23 ~03:15 ICT in the host's approved image cleanup (home-assistant-ops OS-039 phase 3 A): a rollback now means
rebuilding 3.15 from git history, not byte-identical: docs/operations/freerdp-315-rollback.md). 2.x spellings aren't even compiled in:

| Purpose | 2.x | 3.x (used here) |
|---|---|---|
| ignore certificate | `/cert-ignore` | `/cert:ignore` (or `/cert:deny,fingerprint:sha256:<hex>`) |
| H.264 | `/gfx-h264`, `/gfx:avc444` | `/gfx:AVC444` (Debian builds only; Ubuntu's FreeRDP 3 has no H.264) |
| keyboard layout | `/kbd:0x409` | `/kbd:layout:0x409` |
| credentials off argv | `/from-stdin` | `/args-from:stdin` (must be the only argument) |
| binary | `xfreerdp` | `xfreerdp3` |

**RDP worked for months, then stopped connecting.** Windows renews its self-signed RDP certificate
about every six months, so the pinned fingerprint no longer matches. `rdp-loop` treats that as a
TLS failure and backs off; no credentials are sent. Re-pin:
`python3 scripts/rdp_cert_fingerprint.py <WIN_HOST>`, update `.env`, then
recreate the desktop: `docker compose up -d desktop` on a plain install, or `python3 scripts/guarded_build.py --sustain 30 --spike 25 recreate:desktop@90` in dev mode (a `restart` keeps the container's old environment, so a new `.env` value would not take effect).

**noVNC is black.** That's normal without RDP credentials: Xvfb is empty. Check the `RDP window` field
in the console's stats panel.

**`cudaGetDeviceCount == 0` in vision, while `nvidia-smi` works on the host.**
- If the GPU is passed through to a VM, check the passthrough's PCI address (BDF) after any
  hardware work: a card can move to another address.
- `no kernel image is available` means the wrong torch wheel. This project needs **cu130** (sm_120).
- A `nvidia/cuda:13.2*` base image refuses to start on an R580-series driver.

**The rAthena build fails in `rapidyaml`.** That's a parallel-make race. Set `RATHENA_MAKE_JOBS=1` in
`.env` and rebuild.

**The client disconnects right after character select, or shows garbled packets.** `PACKETVER` doesn't
match the client executable. Set it in `.env`, then run
`python3 scripts/guarded_build.py --sustain 30 --spike 25 build:rathena start:rathena@240`.

**map-server loops "Connection to Char Server lost" / login logs "Invalid password" for the server
account.** The inter-server `RATHENA_SERVER_USER`/`PASSWORD` must be at most 23 characters. char and
map keep them in 24-byte buffers and silently truncate longer ones.

**Thai shows as `?` or chat lines are missing from `chatlog`.** The database must be tis620
(`scripts/smoke_test.sh --core` checks this). The db volume takes `--character-set-server=tis620`
only when it is first initialised; the rathena entrypoint refuses anything else.

**The client hangs at 100 % CPU with no window, or says "Cannot init d3d".** See
[docs/client/rathena-client.md](client/rathena-client.md). Causes: missing HKCU `RenewSetup`/`Ragnarok`
keys (it loops trying to run Setup.exe), and DirectDraw/Direct3D 7 under RDP (needs the dgVoodoo2 wrapper).

**Paste does nothing, or says "did not paste".** The toast on the screen, or the panel's message,
names the cause. If ⌘V shows no toast at all, the screen didn't have keyboard focus: click it first.
- `rdp_clipboard_not_listening`: `RDP_CLIPBOARD` is not `text-to-remote`, or RDP is reconnecting.
  Check the connect line in `scripts/dev.sh logs desktop`, which reads `clipboard=… drives=…`.
- `no_data_request`: the focused Windows window ignored Ctrl+V. Click a text field in the remote screen
  first. The game's chat box needs to be open.
- `mode_bot`: switch the mux to HUMAN or ASSIST.
- Every refusal is also counted in `/health` (`input_refused`, `clipboard.foreign_owner_clears`).

**`\\tsclient\transfer` is missing in Windows.**
- `RDP_DRIVES=transfer` must be set in `.env`, and the desktop recreated.
- Drives appear only for sessions started after that.
- Explorer may need `\\tsclient` typed in full.

**A message was dropped.** The backend never drops silently. The console banner shows it, and
`/health` has `dropped_messages{channel: {reason: n}}`. A WARNING names the channel, message type and
reason (e.g. `missing:key.t_mono_ns`), never the contents. Script clients must send `t_mono_ns` on
every message.
