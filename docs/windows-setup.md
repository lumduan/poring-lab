---
doc_type: design
hypothesis: null
status: GO
role: null
verdict_date: 2026-10-06
verdict_ticket: null
supersedes: null
related: [ADR-0019, ADR-0016, ADR-0009, ADR-0006]
next_action: "The user-facing Windows setup (course notes). Keep it to the game client + its one-time config + Sunshine (ADR-0019); anything new on Windows needs a new ADR first."
---

# Windows setup: the game PC

The Windows PC has ONE job: **run the game and stream it** (ADR-0019, "Windows stays clean").
Everything else lives on the bot server:
- the bot and its vision;
- the safety checks: the interlock, the forbidden list, the input mux;
- the list of servers the bot may use.

Nothing of poring-lab runs on Windows, and no key of ours is stored there.

## The whole list

1. **The game client**: a separate copy, with its one-time config.
2. **Sunshine**, paired with the bot server only.
3. **A display** Sunshine can capture.

Recommended one-time OS settings (nothing runs): an exe-scoped firewall rule for the client, a
standard Windows account, and no sleep or screen lock. See "Optional" below.

## 1. The game client (a separate copy)

- Put it in its own folder, e.g. `C:\RO-<server>\`. **Never patch, repoint or reuse another
  client in place**; the lab's community-server client is never touched (ADR-0006).
- The lab's client: the 2021-11-03 exe with kRO data, WARP-patched, with dgVoodoo2, `DATA.INI`
  and HKCU settings. The full recipe is in
  [docs/client/rathena-client.md](client/rathena-client.md).
- Launch it **without elevation**.
- **Smart App Control (Windows 11) must not block it.**
  - SAC decides by each exe's cloud reputation (per file hash). The client exe and Sunshine's exes
    are unsigned.
  - The lab's client ran under SAC (ON, enforce) from 2026-09-30 to 2026-10-13. It was refused
    from 2026-10-15: Code Integrity event 3033, "did not meet the Enterprise signing level
    requirements". Nothing starts and no window opens.
  - The lab's setting: **SAC OFF** (Batt, 2026-10-15; Microsoft Defender stays on). See ADR-0019,
    "Operator changes".
  - Read it back (a standard user can):
    `(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy').VerifiedAndReputablePolicyState`.
    0 = off, 1 = on (enforce), 2 = evaluation.
  - When a launch starts nothing, read `Microsoft-Windows-CodeIntegrity/Operational` first.

## 2. Its one-time config (static files; nothing runs)

- **`data\clientinfo.xml` and `data\sclientinfo.xml`:** your server's address and port. With
  the `DataFolderFirst` patch, these loose files win over the copies inside the GRF.
- **The AssistAddr override, BEFORE the first login.** The 2021 exe on kRO data calls Gravity's
  `kro-assit.ragnarok.co.kr:3000` at character select.
  - Put loose `data\luafiles514\lua files\service_korea\externalsettings_kr*.lub` files next to
    the client, with `AssistAddr = 127.0.0.1:3000`. The lab uses four.
  - This is client config, never an exe patch (ADR-0016, known-forbidden endpoints).
- **Data fixes the client needs.** The lab added Equip-window placeholder textures: kRO data
  lacks the button images, and the missing files raise modal boxes that stop the game loop.

## 3. Sunshine

- Install the signed MSI: the lab runs LizardByte's 2026.914. The steps, backup and rollback are in
  [docs/operations/sunshine-msi-replace.md](operations/sunshine-msi-replace.md).
- **Pair only the bot server's stream client.** To remove another pairing, use that row's own
  delete button, never "Unpair All".
- **Firewall:** Sunshine's inbound rules admit only the bot server's address.
- **Web UI:** `origin_web_ui_allowed = pc`, so it is open only on the PC itself.
- The lab's encoder and capture settings are in
  [ADR-0009](adr/0009-console-session-capture.md).

## 4. A display

- A real monitor works, or a virtual display driver.
- The lab uses "VDD by MTT" at 1440×900, and the console layout is VDD-only. See
  [docs/operations/console-display.md](operations/console-display.md), which also has the
  emergency path.

## Optional, recommended (one-time OS settings, nothing runs)

- **An exe-scoped outbound firewall rule:**
  - What: Block, for the client's exe(s) only, to every address except the bot server and
    loopback (ADR-0016, layer 1). It stops the client reaching official servers even if its data
    names them.
  - An administrator applies it. **Never OS-wide, and never on another client.**
- **A standard (non-admin) Windows account** for the game.
- **Sleep, the screen lock and the screensaver off.** A locked session shows the lock screen to
  the bot.

## Updating official endpoints (occasionally)

1. Drag the official client's `data.grf` (or its `clientinfo.xml`) onto the bot server's
   **Settings** page, in "Find servers from a game file".
2. Block what it finds.

The file is read in your browser and never uploaded. Nothing on Windows reports anything.

## Not part of the user setup

These exist only in the poring-lab research lab (ADR-0019 says why, and when each goes):
- RDP: the lab's human admin path;
- the `poring-lab watch` task;
- the "poring-lab shell" shortcut and the lines the agent types there;
- the tscon SYSTEM task.

**Never install on the game PC for poring-lab:**
- a program, script or task that runs;
- keys or tokens;
- a reporting channel back to the server;
- another remote-desktop or streaming tool;
- antivirus exclusions.
