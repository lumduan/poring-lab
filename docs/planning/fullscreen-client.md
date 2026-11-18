---
doc_type: plan
hypothesis: null
status: "ACTIVE (Batt 2026-11-18: \"make fullscreen a supported setup ... the bot must play full screen: when I teach, many users play fullscreen\")"
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../adr/0026-any-host-nothing-locked.md, ../adr/0016-environment-interlock.md, ../windows-setup.md, ../client/rathena-client.md]
next_action: "Phase 1: a fullscreen client at 1280x720 with the session / stream at 1280x720 (1:1). Phase 2 (other resolutions) is a decision for Batt."
---

# The game client in fullscreen

## 1. What Batt saw (2026-11-18 12:56, two screen recordings)

The client set to fullscreen in the lab's RDP session (1440x900): inside the game the game's own
cursor (the white glove) sat away from the mouse he moved; on the Windows desktop the mouse was
exact. The bot could not log in either: `ro_agent launch` timed out on the service-select screen,
and the typing gate needs the client's title bar, which fullscreen does not draw.

## 2. The facts (measured 2026-11-18)

- **The fullscreen picture is the game's 1280x720 STRETCHED to the session.** The same Select
  Service dialog is 280 x 198 px in the windowed client and ~311 x 237 px in fullscreen (x ~1.11,
  y ~1.20; 1440/1280 = 1.125, 900/720 = 1.25): an RDP session cannot change its display mode, so
  Windows scales the game's picture to the session, unevenly (16:9 into 16:10).
- **The game's cursor is not scaled with it:** the game draws its cursor, and resolves a click, at
  the mouse's position in ITS OWN 1280x720 picture; the stretched picture puts that spot elsewhere.
  So in a stretched fullscreen neither a person nor the bot clicks where they aim.
- Everything the bot reads (Basic Info, the HP / SP bars, the hotbar, the chat window, the
  minimap, the name plates, the detector's 1280x720 frames, the cell projection) is calibrated in
  the client's own 1280x720 pixels, relative to GAME_REGION's origin. ~500 sites use those
  client-relative positions; the runner (dungeon_hunt.py) is byte-pinned by its proofs.

## 3. The design

**Phase 1 (built first): fullscreen at 1280x720, with the session / stream at 1280x720.**
- The picture is then 1:1: the client's 1280x720 pixels ARE the frame. With GAME_REGION
  `0,0,1280,720` every reader, template, the detector and the runner work unchanged: the same
  pixels as in a window, at origin (0, 0) instead of (80, 77).
- SESSION_SIZE `1280x720`: the RDP session's size (`xfreerdp /size`), the S2 stream's, and what the
  backend maps input over. On a learner's own PC, an exclusive fullscreen at 1280x720 switches the
  display to 1280x720, and Sunshine streams that; the stream must be asked for at 1280x720 too.
- **Fullscreen is not configured twice:** it is DERIVED. GAME_REGION covering the whole session
  (origin 0,0, size = SESSION_SIZE) means the client is fullscreen.
- **The proof that the client is in front, without a title bar:** Windows hides its taskbar while
  a fullscreen window is in front and shows it when anything else takes the focus (another window,
  the Start menu, the desktop). In fullscreen the typing gate (backend `foreground.py`) and
  ro_agent's `activate_client` take "the taskbar is NOT on a fresh frame" as the proof, with the
  taskbar's own template cut from this session (`foreground_template.py install fullscreen`).
  Activating a fullscreen client that is not in front clicks its taskbar button, never a point of
  the game (a click there would walk her).
- **A stretched fullscreen is refused, in words:** the frame is not the size the game draws at.
- The setup asks "window or fullscreen" and writes both keys; `scripts/client_display.py` switches
  an install (both keys, then the guarded recreates).

**Phase 2 (a decision for Batt): other fullscreen resolutions (1920x1080, ...).** Every reader would
take the client's size and its UI's anchors (the RO interface does not scale: its windows keep
their pixel size, anchored to the screen's edges), the world view's scale would be measured per
size (the detector is trained at 1280x720), and the byte-pinned runner re-proven. Weeks, not hours.

## 4. Status

- [ ] the live facts in the lab at 1280x720 (1:1 picture, the taskbar hidden while in front)
- [ ] the code (gate, ro_agent, the derived mode, the switch script, the setup), tests
- [ ] the live proof: launch, login, the Rogue on xmas_dun02, the start check, a Run
