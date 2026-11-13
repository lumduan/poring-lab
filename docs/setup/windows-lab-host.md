# The lab's Windows game PC (RDP)

<!-- Moved from the root README on 2026-11-13 (Batt: "the README only for setup; the rest in docs/"). -->

## The checklist (the RO client side)

**Windows stays clean** ([ADR-0019](../adr/0019-windows-stays-clean.md), Batt 2026-10-06):
- The Windows PC runs the game and streams it. Nothing of poring-lab runs there, and no key of
  ours is stored there.
- The user-facing setup is the **game client with its one-time config, plus Sunshine**. It is in
  [docs/windows-setup.md](../windows-setup.md), the course notes.
- The checklist below is THIS LAB's setup, which adds RDP as the human's admin path.
- The lab-only pieces (the `poring-lab watch` task, the agent's shell, the tscon task) and a live
  audit of everything on the game PC are in ADR-0019.

1. Enable Remote Desktop. Use a dedicated **standard** account in "Remote Desktop Users" and put it in `RDP_*`.
   This lab uses `poring-lab` (`WIN_LAB_USER`/`WIN_LAB_PASSWORD`, 2026-10-01): not an administrator,
   Modify on `C:\RO-rAthena` only (the stopped `C:\RO-rAthena-th` copy is writable through C:\'s inherited
   Authenticated Users: Modify; ADR-0019), plus Performance Monitor Users and Event Log Readers for the RDP
   counters/events. Elevation is the operator's (UAC); see `docs/client/rathena-client.md` "Windows
   account". The lab uses `RDP_GFX=progressive` (`docs/h264-plan.md`). On FreeRDP 3.32.1 it delivers 30 fps outdoors;
   `AVCthin` is the measured alternative: the same frames at ~1/5 of the desktop CPU, but lossy.
2. Give the host a fixed IP (DHCP reservation) → `WIN_HOST`.
3. Disable sleep, the screen lock and the screensaver. A locked session shows the lock screen to the agent.
4. Run the RO client **inside the RDP session** at `SESSION_SIZE` (default 1440x900). The game window is 1296×759,
   which is a 1:1 **1280×720 client area** at (80,77), above the taskbar; frozen for Phase 2. Launch it from the
   "Ragnarok Offline" desktop shortcut.
   - The session is drawn 1:1 at the top-left of a larger Xvfb canvas (`XVFB_RESOLUTION`, default 1920x1200).
   - The stream, the agent's frames and the input mapping all cover only the session.
   - The canvas exists for the console mode: Moonlight opens its window at native size only below 80 % of the
     screen (ADR-0009, 2026-10-02).
5. Use a **separate client copy for rAthena** (ADR-0006). **Leave the existing community-server
   client untouched:** never patch, repoint or reuse it in place.
   - The rAthena copy must match `PACKETVER` (its executable date) and point at `HOST_LAN_IP:6900`.
   - Client patching and `clientinfo.xml` live on Windows. **Never copy client files into this
     repo** (see `.gitignore`).
   - The recipe (exe, data, WARP patches, HKCU settings, the dgVoodoo2 wrapper that RDP needs, Thai
     locale): [docs/client/rathena-client.md](../client/rathena-client.md). It lives in
     `C:\RO-rAthena\` and is launched non-elevated.
6. Pin the RDP certificate: `python3 scripts/rdp_cert_fingerprint.py <WIN_HOST>` prints the
   `RDP_CERT_SHA256=` line for `.env` (pre-auth handshake only; it never logs in). Unpinned means
   `/cert:ignore`.
