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

**Phase 2 (DECIDED, Batt 2026-11-18 14:1x): every screen size, detected all the time.** Batt: "support
it, no limit on the screen size; find a way with calculation, like vectors"; "we do not ask in the
setup: a user may switch back and forth, the project must auto-detect all the time".
➡️ The earlier "weeks" assumed rewriting ~500 client-relative positions and re-proving the runner.
The vector way does it in ONE place instead (section 7).

## 7. Phase 2: the virtual 1280x720 client (Batt's vector idea)

**Why one scale factor is not enough.** RO does not scale its picture with the screen: at 1920x1080
its interface windows (Basic Info, the hotbar, the chat window, the minimap) keep their pixel size
and stay where they are anchored (a corner, an edge), while the 3D world keeps the player at the
screen's centre and shows more (or bigger) world around her -- to be measured.

**The vectors.** Every point of the client is one of:
- a UI point: `real = anchor_real(panel) + (virtual - anchor_virtual(panel))`, a fixed-pixel vector
  from the corner or edge its panel sticks to (scale 1: the UI does not scale);
- a world point: `real = centre_real + k * (virtual - centre_virtual)`, a vector from the screen's
  centre scaled by the world's measured scale `k` at that size (1 at 1280x720).

**The virtual client.** One adapter turns any real frame into the 1280x720 picture the bot already
knows (the world resampled around the centre, each panel moved by its vector to its 1280x720 place)
and every click on that picture back into the real screen (the same vectors, inverted). Everything
built on the 1280x720 client -- the readers, the templates, the detector, the cell projection, the
byte-pinned runner -- then runs unchanged; nothing else is rewritten.

**Detected, every frame, never asked.** The adapter finds the client in each frame: a window (its
title bar, anywhere) or fullscreen (no taskbar, the whole frame); its size; each panel where the
player put it (found by its own picture, not assumed: players drag windows); and builds the view.
A switch between window and fullscreen mid-run is the next frame's view.

**Measured (milestone 2), 2026-11-18 14:4x, the client fullscreen at 1920x1080 (1:1, the taskbar
hidden: 67.6):**
- The interface does NOT scale: the Select Service dialog is its 720p size (the 720p signature
  matches at 2.0).
- Its place is the 720p box moved by the vector (320, 225): x exactly centred ((1920-1280)/2), y at
  0.625 of the extra height (not 0.5). So a panel's place is affine per axis, `fraction x size +
  offset`; two sizes give each panel's fractions -- or the panel is simply FOUND by its picture.
- The taskbar's tray sticks to the screen's bottom-right (the box moved by the size difference:
  (1660, 1032) at 1080p, 1.0 shown); the desktop icons draw differently per session size (720p /
  900p signatures 25-72 off at 1080p: `@1080` variants cut).

**Measured in game at 1920x1080 fullscreen (14:5x, the same spot as a 720p frame, Geffen 119,41):**
- **The 3D world is scaled by exactly 1.50 = 1080 / 720, about the screen's centre (offset 0, 0)**:
  `real = (960, 540) + 1.5 x (virtual - (640, 360))` (a scale fit of the central world: 5.5 mean grey
  difference at 1.50, >= 9.9 at 1.49 / 1.51). The camera keeps its view and draws it bigger: the
  world's scale is the client's HEIGHT / 720 (a 16:10 screen then shows less width: outside = black).
- **The interface keeps its size and its SAVED place**: Basic Info (0, 0) and the hotbar (230, 0)
  as at 720p; the minimap sticks to the top-right (x 1776, i.e. +640); the chat window stays at its
  saved pixels (y 580-720), floating mid-left -- it does NOT follow the bottom edge. So panels are
  FOUND, not assumed (players drag windows, and RO restores them where they were).
- The login at 1080p works end to end with the found dialogs (service, login (a `login@1080`
  variant: the 720p signature scores 6.29 there, just over 6), character select): in game online=1.
  It then stops at the chat-window standard check (the 720p place): the next milestones.

**The wiring (milestone 4), one chokepoint, the runner untouched.** Every frame the runner and its
helpers read goes through ro_agent's `Screen` and `game_region()`; every input through its `Agent`.
So the virtual client lives inside ro_agent:
- `game_region()` returns the virtual client at a far origin (x >= 100000: never a desktop pixel)
  whenever the real client is not 1280x720; the real one stays `real_game_region()`;
- `Screen.grab` of a box at that origin returns that box of the virtual frame;
- every pointer position at that origin (move, click, drag, and the runner's raw double-click
  through `Agent.send`) is mapped to the real screen by the view's vectors;
- the login dialogs stay in REAL pixels (found by their picture, as above);
- Windows' own UI (the taskbar, the desktop icons, the shell) keeps real pixels.
**Native-size things inside the world** (the cursor, floor-item labels, "Miss", the small HP bars)
are not scaled with the world: in the virtual frame the cursor's area is pasted unscaled at the
virtual mouse position (ro_agent knows where it put the pointer); the text cues are measured after
the first run at 1080p.

**Status, 2026-11-18 15:3x (main d6da315a):**
- 1 the geometry: DONE (poring_env.clientview, with the panels' ghosts blanked).
- 2 the measurements: DONE at 1920x1080 (above); 1440x900 not measured yet.
- 3 finding panels: the login dialogs are FOUND (signature.find, a hint search for text); the
  in-game panels are the lab's measured layout (LAB_PANELS), not yet found by their picture.
- 4 the wiring: DONE in ro_agent (+ the HUD); the runner untouched.
- 5 the live proof at 1920x1080 fullscreen: the login (found dialogs), GM lines, the start check
  9 / 9, and a 2-minute run (15:31:38-15:33:40, the Run helper's own command): 30 walk clicks
  (19 trusted), 6 strikes, 6 Knife-swap recipes, 5 kills, 51 cursor reads, the Battle Log read
  live, the species read (cruiser, mystcase); a normal end home on the Butterfly Wing.
- 6 the console stream's taskbar template: not yet.
- Alt+Tab (Batt 2026-11-18 ~19:2x): a fullscreen game Alt+Tabbed away shows the desktop; a Run now
  PAUSES on it (the taskbar shows) and plays on by itself when the game is back (ADR-0020
  Amendment P, `ro_agent.away_gate`).
- Not yet verified at 1080p: the world's native-size text cues ("Miss"), the death dialog's
  points (respawn_at, a centred dialog: to be found like the login ones), a window of another size.

**Milestones**
1. The geometry: the view, its vectors and their inverse, the virtual frame -- pure, tested with
   synthetic frames (no lab change).
2. The measurements in the lab at three sizes (1280x720, 1440x900, 1920x1080), window and
   fullscreen: where each panel sits (its anchor), the world's scale `k`, the login and character
   select dialogs (centred?), the taskbar's tray (anchored to the bottom-right).
3. The detector of the client and its panels, from frames.
4. Wiring: the frame path (ro_agent's Screen and Agent, the backend's grab for the gate and the HUD,
   the detector's frames) through the adapter; the runner untouched.
5. The live proof at 1920x1080 fullscreen: login, the start check, a Run.
6. The console (S2) stream's taskbar template (Batt: "do it if you can"), once the stream's size no
   longer matters.

## 4. Status (2026-11-18 13:3x)

- [x] the live facts in the lab at 1280x720 (below)
- [x] the code: the gate, ro_agent, the derived mode, the template installer, tests (main cfb9c2a0)
- [x] the live proof: close + launch + login + the Rogue in game (`ro_agent.py recover gm`, rc 0),
  GM lines through the gate, the runner's start check 9 / 9 on the fullscreen client
- [ ] the setup wizard's "window or fullscreen" question (today the keys of section 5 by hand)
- [ ] the console (S2) path's own taskbar cut (H.264 softens pixels; on RDP the frames come from the
  RDP ring, a copy of X, so the same cut serves both templates)
- [ ] a real Run by Batt (only a person presses Run)

**Measured live, 2026-11-18** (the lab's RDP session switched to 1280x720):
- `OptionInfo.lua` held `WIDTH`/`HEIGHT` 1296 / 759 -- the WINDOW's outer frame that gives a 1280x720
  client area (rathena-client.md, 2026-10-02). A fullscreen client draws that size and squeezes it
  into the screen: its cursor sat at ~0.976 x / 0.905 y of the mouse (the glove drawn away from the
  pointer, Batt's recording). Set to 1280 / 720 (backup `OptionInfo.lua.bak-20261118-fs`), the
  windowed client's service-select signature matches at (0, 0) at 2.9 (<= 6): 1:1.
- The taskbar box: the whole bar shifts with every program opened (Windows 11 centres its
  buttons: 15.6 between two layouts), so the box is the TRAY left of the clock (1020, 672, 170, 48):
  0.0 for every taskbar layout seen (no client, client button, the shell in front); 49.9 with the
  client in front at the login screen, 111.7 in game. The rule: absent at >= 20.
- Win+D minimizes the fullscreen client and its taskbar button restores it (it took two clicks).
- `recover gm` on the fullscreen client: Alt+F4 through the gate, the launch (ENG read on the desktop
  first), the credentials (sensitive), character select, in game, online=1. `crusader.py` GM lines:
  name and job crops 0 px from their references (the same pixels as the window).
- The runner's read-only start check (the Run helper's argv, the 12:44 project): 9 / 9.

## 5. Switching an install between window and fullscreen (the lab's values)

| | window (the lab's standard since 2026-10-02) | fullscreen 1280x720 |
|---|---|---|
| `client\savedata\OptionInfo.lua` | `ISFULLSCREENMODE` 0, `WIDTH`/`HEIGHT` 1296 / 759, `Window_XPos/YPos` 72 / 46 | 1, **1280 / 720** |
| `client\dgVoodoo.conf` `FullScreenMode` | false | true |
| `.env` `SESSION_SIZE` | 1440x900 | **1280x720** |
| `.env` `GAME_REGION` | 80,77,1280,720 | **0,0,1280,720** |
| `.env` `RO_SHORTCUT` / `SHELL_SHORTCUT` (the desktop icons move with the session) | 37,543 / 37,645 | 37,568 / 112,568 |
| the gate's templates (`foreground_template.py install ...`) | `rdp`, `stream` (the title bar) | `fullscreen`, `fullscreen-stream` (the taskbar) |

The order: close the client; the client's two files; `.env` through `rotate_secrets.py set`; the
guarded `recreate:desktop@90` and `recreate:backend@30` (a restart keeps a container's old
environment); for fullscreen, with the desktop showing, `ro_agent.py calibrate taskbar 1020 672 170 48`
(the tray, desktop pixels) and `calibrate taskbar_client_icon X Y 38 40` (the client's button, while it
runs behind another window), then `install fullscreen` and `install fullscreen-stream`. The windowed
client does not fit a 1280x720 session (1296x759 + the taskbar), so the two keys always move together.

## 6. Known limits of phase 1

- The keyboard layout (ENG) is read from the tray, which fullscreen hides: `launch` reads it on the
  desktop just before the client starts, and that reading stands for the login of the same process
  (`recover`), for 10 minutes. A separate `ro_agent.py login` on a fullscreen client refuses.
- A fullscreen client that is not in front is never clicked into focus: ro_agent stops with the
  reason (a click would land in the game). Its taskbar button brings it back.
- "No client" is decided only when proven (the taskbar shown and the client's button absent): a
  minimized client never gets a second one.
- Only 1280x720. Phase 2 (above) is the rest.
