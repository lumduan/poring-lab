# The web console

<!-- Moved from the root README on 2026-11-13 (Batt: "the README only for setup; the rest in docs/"). -->

## Web console now (no image builds): `frontend-dev`

The console runs as a dev server with **no image
builds and no disk-heavy writes** (`compose.dev.yaml`, driven by `scripts/dev.sh`):

- `backend` runs its source straight from the host, mounted read-only and put first on `PYTHONPATH`.
  Picking up code changes is a restart, not a rebuild.
- `frontend-dev` runs `next dev` on the local `node:24.17.0-slim` image (no pull):
  - the source is mounted read-only at `/src`, then copied into tmpfs and kept in sync;
  - tmpfs caps: `/app` 2 GiB (`node_modules` + pnpm store), `/app/.next` 1 GiB, `/tmp` 256 MiB;
  - `mem_limit` 3.5 GiB, read-only rootfs, core dumps off.

```bash
python3 scripts/guarded_build.py --sustain 30 --spike 25 start:backend,frontend-dev@60   # start (desktop keeps RDP)
python3 scripts/guarded_build.py --sustain 30 --spike 25 restart:backend@30   # pick up backend / poring_env code changes
scripts/dev.sh logs -f frontend-dev           # dev server output
scripts/dev.sh stop frontend-dev              # console off
```

Open **http://HOST_LAN_IP:CONSOLE_PORT** (`CONSOLE_PORT` in `.env`, 3000 unless you changed it;
`./setup.sh` asks for it). What it gives you:
- **View:** Fit (aspect ratio kept, letterboxed) or 1:1.
- **Input:** click the screen to give it keyboard focus. That focus lives in a hidden textarea, so
  ⌘V pastes your clipboard into Windows (ADR-0004). Leaving it, or hiding the tab, releases
  everything held. It sends that release only while something IS held, and a closed tab holding
  nothing submits nothing: in ASSIST any human event takes the lease and makes the bot let go
  (Batt, 2026-10-07).
- **Toolbar:** Ctrl+Alt+Del (sent as Ctrl+Alt+End, RDP's secure-attention mapping), Win, Alt+Tab, Esc,
  Release keyboard, Secret typing, and **Watch only**.
  - Watch only forwards no input at all from this tab: no mouse, keys, wheel or paste.
  - So the bot keeps control in ASSIST while you watch; the mux mode is unchanged and switching to
    HUMAN still works.
  - Turning it on first releases what the tab holds. Off restores instant takeover, and every
    page load starts with it off.
  - An amber WATCH ONLY chip shows on the screen and in the header.
- **Top bar (every page):** Console / Maps / Flows / Economy / Hardware / Settings (Batt's order,
  2026-11-13; Label QA left the bar 2026-11-10, `/qa` remains), and the **mode badge**, always
  visible: **BOT** red and pulsing ("BOT in control"), **ASSIST** amber, **HUMAN** blue, grey = no
  status.
- **Hardware** (`/hardware`, Batt 2026-11-08): the lab host's CPU (total and per core, MHz, load),
  memory, `/dev/shm` against rule 7's 4 GB, root-disk free space, the GPU (busy from RC6 residency,
  temperature, power against its limit, clocks, fan), every hwmon temperature, and power (the whole
  server from its power meter, e.g. a BMC's, the GPU, the CPU package), with 10-minute sparklines.
  - The backend samples plain `/proc` + `/sys` files every 2 s in a worker thread
    (`poring_backend/hardware.py`) and serves `GET /hardware` on `:8000` only; `:8001`, the agent's
    listener, answers 404 (counted in `/health` `dropped_messages.hardware_http`).
  - A sensor it cannot read shows `n/a:` and the reason (e.g. the CPU package's RAPL counter is
    root only on the host and masked in containers; i915 has no unprivileged VRAM figure). The
    host's `/dev/shm` is not mounted in the backend, so it shows `n/a` there unless
    `HARDWARE_SHM_PATH` names a path on it. A sample older than 6 s is marked STALE.
- **Economy** (`/economy`, Batt 2026-11-11): banked runs' business results at fixed NPC prices (course
  material too): Income (picked / stolen / total per item, an editable NPC sell price, Overcharge),
  Kills per species, Drops of our kills, Consumables (an editable NPC buy price, Discount) and the
  P&L per hour (gross, cost and net, plain and "best").
  - A run shows only after it is exported: `scripts/econ_dash.py export SESSION_DIR ... --name NAME`
    writes `data/econ/dashboard/NAME.json`; the backend serves it read-only (`GET /economy/list`,
    `GET /economy/data/NAME`, `:8000` only). Formulas and checks: `docs/econ/economics.md` section 10.
  - The runs' counts can also live in one local SQLite file, `data/econ/lab.sqlite`
    (`scripts/econ_db.py build / update / export / dashboard`, ADR-0025). The page still reads
    the JSON exports.
  - Edited prices stay in the browser (localStorage) and are never sent to the server.
- **Route preview** (2026-10-08): the LIVE, world-anchored route of every walk run: a green line
  from the character's feet with square corner nodes, a box on the next click and arrows
  converging on the goal (the RA2 look), re-projected about 20 times a second and matched to the
  frame on screen.
  - The rule publishes its plan in map cells (`scripts/route_plan.py`). The previewer daemon
    (`scripts/route_previewd.py`, started by the first route, one at a time) draws it, and exits
    after 30 idle minutes. Its log: `/dev/shm/poring-lab-route/previewd.log`.
  - The one-shot plan picture (walk@8-12, screen pixels) is gone: it floated off the character
    as the camera scrolled (Batt, 2026-10-08). The protocol refuses a `RoutePreview` without
    `live: true`.
  - Display only (a `RoutePreview` the backend relays like detections, never to the mux).
- **Operator HUD** (2026-10-08; the **HUD** toolbar toggle, per tab, off on every load): the rule's
  detector boxes (class, confidence, distance in cells), its locked target and countdown, the work
  zone, the walk vector, counters, and a short plain-words log in a panel under the stream. Display
  only (an `OperatorHud` the backend relays to viewers, never to the mux); see docs/phase4-ui.md.
- **Header:** mode switch (the same colours) and ASSIST lease. **Panel:** stats. A banner shows if
  the stream or RDP is down, and when bot typing was just refused because the game window was not
  in front.

**Workstation alternative:** run the console on your own machine against this backend.
1. Add your browser's origin to the backend allowlist in `.env`:
   `FRONTEND_ORIGINS=http://HOST_LAN_IP:CONSOLE_PORT,http://localhost:3000` (your console port)
2. Apply it: `python3 scripts/guarded_build.py --sustain 30 --spike 25 recreate:backend@30`.
3. Run the console:

```bash
cd services/frontend && corepack pnpm install
BACKEND_PUBLIC_URL=http://HOST_LAN_IP:8000 corepack pnpm dev    # open http://localhost:3000
```

`FRONTEND_ORIGINS` is the backend's WebSocket Origin allowlist: comma-separated, and unknown origins are
refused. It defaults to `http://${HOST_LAN_IP}:${CONSOLE_PORT}` (3000 when `CONSOLE_PORT` is empty), so a
moved console stays allowed. Stream rate and quality are `STREAM_FPS` (30) and
`JPEG_QUALITY` (80). The stream is sent without WebSocket compression: JPEG doesn't compress, and
deflate cost 8 fps on the event loop.

**Latency (Phase 0, [phase0-latency.md](phase0-latency.md)).** The stream grabs when the
screen changes (`STREAM_CAPTURE=damage`, at most `STREAM_MAX_FPS=60`); `fixed` restores the old
`STREAM_FPS` grid. `/health` has a `latency` block:
- capture/encode/send;
- the open tab's network, decode and paint times, with the clock-offset uncertainty.

`scripts/latency_probe.py` (inside the backend container) measures the segments and switches the
knobs live through the loopback-only `/debug/stream-tuning`: `capture`, `max_fps`, `jpeg_quality`,
and the console's `paint` and `move_interval_ms`.

## Typing a password through the console: "Secret typing" (ADR-0004 amendment c)

➡️ Since 2026-11-18 (ADR-0004 amendment d) the input log never keeps a CHARACTER a person types
(letters, digits, symbols, Space): only that a key went down and up, and when. Control keys (Alt,
Tab, Escape, Enter, the F-keys, the arrows) keep their names. Secret typing still hides those too,
so **turn on "Secret typing" in the toolbar before typing or pasting a password** anyway.
- Keys still reach Windows; the log keeps type and timing only, and a paste no length or digest.
- The button turns red for every viewer (`Status.human_secret`).
- It turns off on click, or when that console tab disconnects.
- Older human typing was purged on 2026-10-02 (`scripts/purge_input_log.py`; counts only).

## Clipboard and file transfer (human-only, ADR-0004)

Both are **off by default**. For this lab `.env` sets:

```bash
RDP_CLIPBOARD=text-to-remote   # off | text-to-remote  (text Mac -> Windows only; never Windows -> X)
RDP_DRIVES=transfer            # "" | transfer        (\\tsclient\transfer in Windows)
```

Applying a change reconnects the RDP session once, because desktop and backend are recreated together:
`python3 scripts/guarded_build.py --sustain 30 --spike 25 recreate:desktop,backend@90`.

- **Paste to Windows:** click the target field in the remote screen, then press **⌘V** there, as
  in Windows App.
  - Off macOS the paste chord is Ctrl+V; Shift+Insert works everywhere.
  - On a Mac, physical Ctrl+V still reaches Windows as Ctrl+V (Windows-internal paste).
  - A toast on the screen shows the result.
  - The "Paste to Windows" panel stays as a fallback: paste into its box, check it, then Send (⌘Enter).
  - Up to **64 KiB** of UTF-8; Thai is fine. It works over plain HTTP: the page uses the `paste`
    event, not `navigator.clipboard`.
  - The backend owns the X clipboard for about a second, the mux sends Ctrl+V as the human, and then
    it lets go. Windows keeps no copy.
  - Refused in BOT mode, and only accepted from the console page.
  - Logged as length + sha256, never the text.
- **Files ⇄ Windows** (console panel):
  - Uploads land in `\\tsclient\transfer` (Win+R in Windows).
  - Whatever Windows saves there can be downloaded from the panel.
  - A **512 MiB tmpfs** (RAM, never the disk), emptied when desktop and backend stop.
  - **Large files such as a multi-GB game client: use SMB or a direct download on Windows**, not
    this.
  - Audited in `data/transfer_log/` (name, size, sha256).
- The bot can use neither. The mux refuses a bot Ctrl+V / Meta+V / Shift+Insert, the agent protocol
  has no such messages, and a watchdog clears any foreign X clipboard owner. The remaining gap (vision
  can still reach X directly) is [ADR-0005](adr/0005-vision-x-access.md), which blocks Phase 4.

## Settings: who may play a Run, and the game servers the bot may use

Open **Settings** in the console's top bar (`http://<host>:<CONSOLE_PORT>/settings`).

**Who may play a Run** (the top of the page; ADR-0020 Amendment R, Batt 2026-11-19): the first
line of a Run's check asks who is on screen. A Save works at once: the next check or Run uses it,
with no restart (`.env`'s `RUN_IDENTITY` is no longer read).
- **Any character (the default)**, every install's and the lab's: any name, any job; a Run does
  not check who plays.
- **Only the characters remembered here:** the character's name line must match one in the list;
  a character of another server is refused at the first line, before any key is pressed.
- **Only the lab's own character (advanced):** the name and the job against the reference pictures
  `crusader.py` cut; an install without them refuses every Run, in words.
- **Remember the character on screen:** put the character in front with Basic Info open at the top
  left, type a name for the list (any language: the bot compares the PICTURE, never the letters)
  and press **Remember**. The Run helper reads the name line (116 x 14 pixels) twice, 0.5 s apart,
  once, now; it must hold still and show letters, and a character already in the list is refused.
  Nothing cuts a name line at any other time. Each remembered character shows its name line;
  rename it or **Forget** it, then **Save**. Remember again after changing between window and
  fullscreen. Up to 50 characters.
- The same rules as the servers below: only a person in a browser on another computer of your
  network can change it (never the lab computer or the game PC), with a CSRF token, every change in
  the change history. The store is `./settings/run-identity.json`; a file that does not parse
  fails every Run's check, in words, until a Save replaces it (never back to "any" by itself).

**The game servers:**
- **Environments** are game services you manage yourself: **Allowed** (the bot may act while the
  game is connected to one of its servers), **Forbidden** (never; its servers can never be allowed
  anywhere) or **Pending** (not approved). Create, rename and delete them, and edit their server
  lists, on the page. The shipped ones (official Thai, official Korean, the community server, the
  lab's rAthena) are only a starting set.
- **Found by the lab:** servers your game client is set up for. They are suggestions until you
  press **Confirm** (or **Confirm all** for one server's ports). Every save is checked by reading
  the file back ("Saved and checked ✓"). The lab's own rAthena is suggested at THIS server's
  address and ports (`HOST_LAN_IP`, `RATHENA_*_PORT`; since 2026-11-17).
- **Windows PC** (each Allowed environment; ADR-0023 decision 4, 2026-11-17): the game PC the
  environment is played from, beside the one this lab drives (`WIN_HOST`). The bot acts only while
  they match; **Set Windows PC** changes it (an IP address of one machine, never this server's),
  **Use this lab's PC** copies `WIN_HOST`. An import never changes it. The red banner
  `host_mismatch` points here.
- **Blocking is easy; unblocking is hard.** Removing a forbidden server, deleting a Forbidden
  environment, or making it Allowed needs a written reason and the name typed again, one change at
  a time.
- **Find servers from a game file:** drop a `data.grf`, `clientinfo.xml` / `sclientinfo.xml`, an
  `externalsettings` .lub or the game's .exe on the page.
  - It is read in your browser only, and never uploaded. Encrypted parts are skipped, not
    decrypted. A protected exe says so: drop its `data.grf` instead.
  - You pick what to do with each server found. The default is to **block** it; allowing is a
    separate, deliberate choice with a warning for anything outside your network.
- **Share a setup:** export the whole set as one file, and import it elsewhere (same rules).
- **Change history:** every save and every refused attempt, with the browser's address.
- **Who can change it:** only a person in a browser on your network, on another computer. The bot
  can read the list but never change it. The lab computer itself and the game PC the bot drives
  are refused too; every save carries a CSRF token and is rate limited.
- The set lives in `./settings/` (gitignored, mounted into the backend only); see ADR-0016.

## Flows: block programs, SIMULATE only (MW2, 2026-10-08)

Open `http://<host>:<CONSOLE_PORT>/flows` (Flows in the top bar). The page edits ADR-0020's flow IR.

**Maps** (`http://<host>:<CONSOLE_PORT>/maps`, Maps in the top bar, 2026-11-10): the same flow as a graph of maps:
START -> Login -> Choose character (MOCKS: only the lab rAthena is selectable, no credential field)
-> the map nodes, each bound to its own flow ("Open flow" opens its /flows tab; /flows' `Map` picker
names the bound map). Simulate plays the bot on each map's walk grid: walks, seeded monsters, NPC
talks, warps ([planning/world-map-flows.md](planning/world-map-flows.md)). A map's walk
grid needs its GAT in `data/gat` (`scripts/flows_gat.py`, client-derived, gitignored).
➡️ **Since 2026-11-13 (round 6, Batt: "like n8n")** each map node shows its ENTRIES on the left (how
the character arrives: the start, a warp in, an NPC / Kafra warp, a Butterfly Wing) and its EXITS on
the right (where each goes and how), one port each; drag from a map's "+" port onto another map to
add an exit. Under the graph, **Links** lists the selected map's entries and exits (or every link)
beside the **Map view**. The node **Any other map** holds the **world rules** for every map of the
flow: the save point (stated once, at the run's first step) and what to do on a map none of the
nodes is on (stop, the built-in; or a Butterfly Wing home). On /flows a strip under the tabs says
which map the tab's flow is bound to, how the character arrives and where each exit goes; a plain
flow says it is bound to no map. Design: [planning/world-map-flows.md](planning/world-map-flows.md)
section 14.
➡️ **Since 2026-11-13 evening /maps edits a PROJECT** ([planning/project-model.md](planning/project-model.md)):
its nodes are real project nodes, each with its own tabs on /flows (double-click a node, or "Open
flow": `/flows?node=<id>`). **Login** (a server and a credential BY NAME, `lab_gm` / `lab_player`;
never a secret) -> **Choose character** (the remembered slot, or one) -> the first map are the
project's connections, drawn from a node's right port, dragged to another node or deleted (one
path); map -> map links stay the exits. **Global** (dashed, "shared by every node", no ports) lists
its tabs and names, which keys its functions press, and which map nodes override each name; its
**World rules** write the save point as the start map's first step and the unknown-map rule as
Global's event `unexpected_map` (the node "Any other map" is gone). The side panel's **Node** tab
is the node inspector (id and rename, the map's entries / targets / zones, the login and character
in words, tabs and names with the override marks, delete a map node); **Simulation** is the run.
Load offers the two ready-made projects and "Open a project file…"; Save downloads
`<name>.project.json`. (➡️ Since 2026-11-13 ~21:4x the xmas_dun02 ready-made is ONE box,
START > xmas_dun02, and /maps has a **Run** from START: the Flows part below.) An old flow in this browser is not converted (a notice says so). Login and
Choose character are played as a mock timeline until the engine's trace names them.
➡️ **Since 2026-11-09 it is laid out as matpilot.org/blocks** (a "studio", Batt: learners who know
matpilot are at home), in matpilot's colours, light or dark as the system is
([planning/flows-studio.md](planning/flows-studio.md)): a header (Blocks | Python, Load,
Save, Start over, the green **Simulate**), tabs over the blocks (`main` and `events`; a workflow
adds a **Map** tab with the canvas below and one tab per map block), the **Python beside the
blocks** (open by default on a wide screen), output panes in a drawer (Inspect, Lint, Results,
Path map, Hunt rules), the problems under the blocks and a status line. The **trained models** are
Sensors blocks ("detector v1 sees monster", "detector xmas02 count of cookie xmas"; ADR-0020
Amendment B); a not-adopted model is never offered.
- **Canvas:** map blocks joined by typed exits (walk exit, NPC warp, item warp; the death respawn
  is derived from the save point), the global and per-map events, a lint / run line under each.
  Draw an exit from a port onto another block; double-click a block for its blocks.
- **Blocks:** Blockly (MakeCode look). Each skill block shows its L1 verification badge (verified
  RDP / S2, unverified), its lint findings and its last simulated run.
- **Lint, Simulate, JSON, Python:** MW1's linter; a simulated run against static data (the
  synthetic sample sheets, or the lab's own data/kb) with a scenario you choose; JSON import /
  export (➡️ Save and Load, below); the Python view, read-only.
- **Save and Load (2026-11-12, the same on /flows and /maps;
  [planning/flows-save-load.md](planning/flows-save-load.md)):**
  - **Save** (the disk icon, Ctrl/⌘+S) downloads `<name>.flow.json`: the flow, and its Python as
    lines so a diff reads well. Never the sample sheets or the lab data. **Load** ▸ "Open a saved
    flow…" (Ctrl/⌘+O) opens one from this computer or from GitHub. It is checked before anything
    changes, and Undo on the notice goes back. A `.flow.json` downloaded before 2026-11-12 (the bare
    IR) still opens.
  - **GitHub:** "Set up GitHub…" in either dialog takes a repository (`owner/name` or its link), a
    folder (default `poring-lab`) and your name (it goes into the commit message). A **public**
    repository LOADS without a token. Saving needs a fine-grained token for that one repository
    ("Contents: Read and write"; the dialog links GitHub's prefilled page). The token stays in this
    browser tab unless you tick "Remember on this computer"; "Forget the token" removes it.
  - A save never silently replaces someone else's newer version. You choose: Save mine as a new
    flow (`<name> 2`), Replace it, See who changed it, or Cancel.
  - **A teacher sharing a folder:** make a public repository in a free GitHub organisation, with
    one folder per class (well under 1,000 files). The students set that repository and folder and
    press Load, then carry on from the flow. Students who save are members of the organisation,
    each with their own token (fine-grained tokens do not work for outside collaborators). GitHub
    accounts are for ages 13 and over. Without a token GitHub allows 60 requests an hour for each
    internet address; a Load and one open cost 3-4, so a class behind one school address shares
    that budget.
  - Saving a flow you opened from GitHub, under the same name, UPDATES that file when nobody changed
    it since (GitHub keeps every version). So a teacher keeps the starting flows where the students
    can only read, and each student saves into their own folder.
  - The page talks to `https://api.github.com` only (the CSP's one outside origin), and only after
    you open GitHub settings, Save or Load.
- **The hunt block (B2, 2026-10-21):** one dropdown per parameter (engage; dead + loot; search),
  each a list of rule versions: ★ the adopted base's, ◆ hunting evidence (Batt's D8). The "Hunt
  rules" pane lists each version's numbers, read-only.
- **Zones (B2):** a map block's "Open the Zones layer" draws `config/map_zones/<map>.yaml`'s lines
  and areas, checks them with the runner's own loader and EXPORTS the YAML (a person commits it;
  `config/map_zones/README.md`). `zones_engine_unavailable` = the backend cannot import
  `scripts/map_zones.py`: the dev backend needs its read-only `./scripts` mount (compose.dev.yaml,
  a guarded `recreate:backend`).
- ➡️ **SUPERSEDED 2026-11-14 ~15:2x: the runner view below is GONE** (Batt: "there should be no
  runner [page]; everything in the xmas_dun02 flow, split into tabs; make them ALL blocks"): every
  setting it showed is a SETTING BLOCK in the map node's tabs, and `/flows?runner=...` opens that
  map's node ([planning/live-blocks.md](planning/live-blocks.md) section 12; the last bullet of
  this section). The history it carried stays below as written.
- ➡️ **Since 2026-11-13 the xmas_dun02 runner view has a Run button** (`/flows?runner=xmas_dun02`, "Run in the game"): it starts the proven runner in player mode through the host helper `scripts/flow_run.py`, NOT the flow IR (ADR-0020's executor is still unbuilt). How and why: [planning/player-mode.md](planning/player-mode.md), [setup/new-lab-host.md](setup/new-lab-host.md) 11.1.
  ➡️ **Since 2026-11-18 (Batt, ADR-0020 Amendment O) Run works in ASSIST or BOT** (never HUMAN). In
  BOT your input is dropped, so you can watch the run on the Console without pausing it; Stop, or
  HUMAN, ends it. A run that goes shows a "Running in the game" strip under the /flows header, and
  its Stop, on every node and after you come back from another page.
  ➡️ **Since 2026-11-18 ~19:4x (Batt, ADR-0020 Amendment P) a Run PAUSES while the game is off the
  screen** (Alt+Tab, the Start menu, a Windows pop-up; fullscreen: the taskbar shows; a window: its
  title bar is not lit): it presses nothing, the page shows "PAUSED since ...", and it plays on by
  itself 1.5 s after the game is back. Pressed while the game is away, Run waits for it before its
  start check. The Run panel also shows the Run's OWN start check line by line and the Run's log
  (40 lines: the screen, the input mode, each check line, the pauses, a fault's traceback). A Run
  saves no picture (Batt 2026-11-18 ~22:3x: a frame can show other people's chat).
  ➡️ **Since 2026-11-19 (Batt, ADR-0020 Amendment R) who may play is chosen on the SETTINGS page**
  ("who may play a Run", below): any (the default, the lab's too), known (the characters remembered
  there) or mine; a Save applies to the next check or Run at once. `.env`'s `RUN_IDENTITY` is no
  longer read; the history:
  ➡️ **Since 2026-11-18 21:19 (Batt, ADR-0020 Amendment Q) a Run plays ANY character** on an install
  whose `.env` leaves `RUN_IDENTITY` empty or `any` (the default): no name or job is compared, and
  the checklist's first line reads "a character in the game (any name, any job)". `mine` keeps the
  name plate check; `known` plays any character this install cut once (the lab's since
  2026-11-18 ~22:1x: another server's character is refused at the first line). Every start rule
  for teaching:
  [planning/teaching-prerun.md](planning/teaching-prerun.md).
  ➡️ **Since 2026-11-13 11:3x** Run sits beside Simulate (amber; press, then press again within 4 s
  to confirm) with Stop; a "your run settings" strip sets the Fly Wing key, the Butterfly Wing key
  and the weight to go home at (defaults F8, F9, 50 %; the blocks show them); the map's exits: a bag
  over the limit -> a Butterfly Wing home, a death -> the death dialog's move to saved location
  ([planning/player-mode.md](planning/player-mode.md), dungeon@9.41). The strip also sets the respawn
  function block's points (the death menu's button; the confirmation's OK, or none for a server that
  asks nothing). Live-verified 2026-11-13: the weight exit flies her home on F9; a death respawns her
  in Geffen (her save point since 11:5x).
  ➡️ **Since 2026-11-13 ~13:2x it is named after its map** (Batt: "I don't see the xmas_dun02
  flow; the Knife swap has no block? name it after the map"): the title is **xmas_dun02**, it is the
  FIRST entry of Load (bold, on /flows and on /maps), the link is `/flows?runner=xmas_dun02`, and a
  /maps map card's button reads "The xmas_dun02 flow". Its blocks are on **four tabs**, so no stack
  sits off-screen: `xmas_dun02` (the run), `knife swap` (Batt's Knife swap as two functions,
  `knife_on()` at idle and `knife_back()` on every tick), `respawn` and `safety rules`. The run's loop
  CALLS both Knife functions where the runner runs them; Simulate plays the swap by default (it is in
  the base since 4DQ) and turns to the tab of the block it is on.
  ➡️ **~13:4x (Batt: "nothing fixed, we only put the defaults"):** the run settings strip sets every
  hotbar key (heal item, Fly Wing, Butterfly Wing, Knife, dagger: each its own key, none taken by
  the run), the Knife swap's time (0.2-20 s; "F4, wait 200 ms, F5" = 0.2) and its HP rule, the
  weight to go home at and the respawn's two points. A **FLOWS row** under the header names every
  flow on both views (your own flow, then each map flow): one press switches. The description, the
  Run panel and the chips fold into one line that opens by itself while a run is active; the canvas
  keeps at least 22rem and the page scrolls instead (matpilot's 1440 x 900 review).
  ➡️ **~14:2x, "heal and escape" (Batt: a global config for every map's flow, a map's own on top):**
  a strip under the run settings sets the heal item's HP %, the Fly Wing's HP % and the fast-fall
  rule (HP/s, under a %), for **every map** or for **this map only**; each change is saved at once
  on the bot server (`settings/flowrun/survival.json`, the Settings write gate) and says which
  values the next Run uses: this map's own, every map's, or the defaults. Unlike the run settings
  (this browser), these follow the person to any browser.
  ➡️ **SUPERSEDED ~15:0x by ONE settings panel (dungeon@9.44):** every setting, 70 in 12 groups
  (scripts/flow_config.py): hotbar keys, the Knife swap, heal and escape, leaving the map and the
  respawn open; the start, the fight, choosing and striking, loot, walking, safety and the loop
  under "all the other numbers". Each group edits **every map** or **this map only**; each change
  is saved at once on the bot server (settings/flowrun/config.json) with an undo line; a value
  equal to the level below is not stored (it keeps following it); a tag says where a value comes
  from (this map / every map / nothing = the default). Run sends no settings: the Run helper reads
  the same file. The run settings strip and the heal-and-escape strip above are history.
  ➡️ **~15:2x, the techniques' switches too:** each group also holds its techniques' on/off
  switches and choices (shown first): e.g. the Knife swap group's "Batt's Knife swap", the loot
  group's item model, the aiming group's value target. A setting that needs another one off is
  dimmed "(not in use: needs …)" and is not passed; a safety switch turned off says what it
  risks; the blocks of a technique switched off turn grey and begin "off:".
  ➡️ **~15:4x, matpilot's player test (a real 10-min run, Batt's yes):** while she plays, the Run
  panel shows ONE live line (HP, what she does, kills, loot steps, Knife swaps and steals,
  potions, Fly Wings, the time of the time box; the Run helper reads the run's own session events)
  and the block she is on is highlighted as Simulate does (a click on a tab or a block stops
  following until "follow the run"). The end is in plain words ("Stopped by you after 10 min. She
  flew home on a Butterfly Wing. 23 kills …") with the end picture (GET /flows/run/end.png, the
  helper's copy), never a server path or a raw JSON line. Before Run the start conditions are a
  checklist made from the run's own settings. The groups' radios read "change for:" and follow
  the file. The version chip says "dungeon@9.44 (base 8.7)": 8.7 is the default behaviour's
  version, each newer technique has its own; the same runner plays.
  ➡️ **~18:xx, ONE STUDIO (Batt: "why is the xmas_dun02 flow separate? make it like my_first_flow;
  every key a function; global functions in a tab of their own; take the Map tab off /flows, the
  Maps page is the map graph"):** xmas_dun02 is now an ORDINARY flow of the studio (Load ▸
  xmas_dun02, or the FLOWS row). Its tabs: `xmas_dun02` (hunt with the runner while the bag is under
  50 %, then "item warp: call butterfly_wing → geffen.save"), `geffen` (the save point; the run
  ends there), **every map** (the events every map shares) and **functions** (heal = press F1,
  fly_wing = F8, butterfly_wing = F9, knife_on = F4, knife_back = F5). A function is a block hat
  ("function NAME ( )") with any blocks in it; "press key F1-F9" presses one hotbar key; "call NAME"
  runs a function from any tab; Save and Load carry the functions with the flow. **Run** (beside
  Simulate, on a flow whose map holds the block "hunt with the runner") reads its five keys FROM THE
  FUNCTIONS: each role function must be exactly one "press key"; the Run pane (in the drawer) holds
  the live run, the start checklist and the settings (the keys group says "your functions"). The
  runner's own blocks (the four tabs above) are now **inside the hunt block**, read only ("See inside
  the runner ↗"; `/flows?runner=xmas_dun02` still opens them). The FLOWS row switches flows by name
  and KEEPS the one left in this browser. The Map tab is gone: the maps graph is the Maps page; each
  map's tab is its flow. my_first_workflow's wing is a function too (butterfly_wing = F9), and the
  world rule calls it. Design: [planning/world-map-flows.md](planning/world-map-flows.md) section 15.
  ➡️ **~18:2x, the live ticks (dungeon@9.45, Batt "do it"):** the checklist is ticked from the
  game screen: ✓ / ✗ (red, with the reason) / ? (not read), with the value read ("10 Fly Wings on
  F8"). "Check the game" (also once by itself when the panel opens) runs the runner's read-only
  check through the Run helper: it presses nothing, needs no ASSIST, and is refused while a run
  goes. The time of the last check is shown; lines whose settings changed since are greyed. A ✗
  does not lock Run: its title says the runner will refuse. The map's NAME is not read from the
  screen: the cell line ticks her cell on the map's open ground, and you check the map. The
  version chip reads dungeon@9.45 since. Details: [planning/player-mode.md](planning/player-mode.md).
  ➡️ **SUPERSEDED by dungeon@9.46 (the same evening):** the map's name IS read, from the minimap's
  picture (`scripts/minimap_id.py`). The cell line ticks only when the minimap is the run's map,
  is a red ✗ on another map ("she is on geffen, not xmas_dun02 (the minimap shows geffen's map
  picture with a match score of 0.47, where 1.00 is the same picture and a map is named at 0.40 or
  more, 0.15 ahead of the next; xmas_dun02's picture scores at most 0.21)": every score with its
  scale, since matpilot's round 16 #10), and
  a ? asking you when it cannot tell; the runner's player start refuses both before any input.
  It needs the references built once per host (`OMP_NUM_THREADS=2 python3 scripts/minimap_id.py
  build --decode-mixcrypt`); without them the line is a ? and a player start refuses. The version chip
  reads dungeon@9.46.
  ➡️ **dungeon@9.47:** the wings / heals / home / Knife lines read WHICH ITEM each key shows, from
  its icon (`scripts/slot_items.py`; built once per host: `OMP_NUM_THREADS=2 python3
  scripts/slot_items.py build --decode-mixcrypt`): another item is a red ✗ ("F1 shows a White Potion,
  not a Fly Wing: ..."), unread a ?, and a player start refuses both before any input.
- ➡️ **SUPERSEDED 2026-11-13 ~20:xx by THE PROJECT MODEL** (Batt: "/maps first: login, character, each
  map and a Global node, linked like modular code; double-click a node for its flows; one main
  tab, the rest the person's; every tab and Global imported into main"; design:
  [planning/project-model.md](planning/project-model.md)). /flows shows ONE NODE of the project
  (`/flows?node=<id>`; the node chip switches, "◂ Maps" goes back): its tabs are `main` (the node's
  program; Global has none) and the person's own (`+ tab`, double-click to rename, × to close).
  Functions take inputs as Python writes them (`key, times=1, *args, **kwargs`), return values,
  and an EVENT is a function with a "when …" trigger. A node's function, event or variable of a
  Global name replaces Global's on that node (the strip under the tabs says which). The Python
  panel shows one file per tab (this node's and Global's). Login and Choose character are real
  nodes with their own main (a server and a credential by NAME, never a password; simulated: Run
  starts on a map node). Run is on a map node holding "hunt with the runner": its five keys are
  that node's functions (its own first, then Global's). The drawer's "Before Run" (renamed from
  "Run", matpilot) holds the checklist, the live run and the settings, and says the settings are
  saved on the bot server at once. Save / Load carry PROJECTS (file version 2); flows of the old
  format are refused in words, not converted. The read-only check has its own route
  (`POST /flows/run/check`).
  ➡️ **~21:3x (Batt: "the FLOWS row confuses; a project is /maps' save; every flow has Simulate
  and Run, to tune one map, then chain them"):** no FLOWS row; /maps and /flows Save and Load the
  SAME project with the same dialogs (this computer or GitHub); Load of a ready-made project asks
  first (Undo still brings yours back). On a map node, Simulate plays THAT map alone (/maps plays
  the whole chain) and Run is always there: it plays in the game where the bot can (the block
  "hunt with the runner" on xmas_dun02) and is greyed with the reason elsewhere ("Before Run"
  lists what the flow engine says is not ready for a live run on that node). The toolbox no longer
  closes by itself; a function's input can be used in its body ("press key <value>", the input by
  name); both pages open the lab's xmas_dun02 project first.
  ➡️ **~21:4x, THE ONE BOX and Run from START** (Batt: "take every box out: START > map
  xmas_dun02, one box is enough; build this box's flow with everything the bot has trained; login
  and choosing the character come later; the user puts the character on xmas_dun02 themself. On
  the Maps page add a Run button too: it runs from START, box by box";
  [planning/live-blocks.md](planning/live-blocks.md) section 3). The ready-made **xmas_dun02** is
  ONE map node: its START is the map itself (the run starts where a person put her; no login, no
  character), its `main` the save point (Geffen), "hunt with the runner" with five roles (heal, Fly
  Wing, Knife on, Knife back and **home**: the Butterfly Wing the runner flies home on when the bag
  is half full or on Stop) and a stop; its `keys` tab every key a function (heal F1, fly_wing F8,
  butterfly_wing F9, knife_on F4, knife_back F5). A project may start on any map node.
  ➡️ **2026-11-14 (stage 3, [planning/live-blocks.md](planning/live-blocks.md) 3.3):** the runner
  block has a last line "after a death: call ... then confirm: call ..." (the death dialog's two
  clicks; empty: the runner's own points), and the one box has five tabs: keys (wield_knife F4,
  wield_damascus F5 among them), survival (+ bag_full at 50 % weight), knife (the swap's two
  functions), exits (the way home, the respawn's two `click_at` functions).
  ➡️ **2026-11-14 (stage 4a, [planning/live-blocks.md](planning/live-blocks.md) 3.4):** the one box
  has a sixth tab, `monsters` (one function per monster, `attack_<monster>(t, priority=1)`, each a
  recipe of the runner's steps), and its main names the trained data, `use_model("xmas02")`, before
  the runner block (➡️ **2026-11-17, [planning/live-blocks.md](planning/live-blocks.md) 18.15:** the
  ready-made xmas_dun02 box and its cookie twin name `use_model("xmas02sk")`, the map's deployed
  model, whose alarm flies on the Christmas Goblin and the Stormy Knight as well as the Garm Baby;
  the old one box and the A/B reference arms keep `xmas02`, now the map's REFERENCE model -- loaded
  only by a box that names it, never a node's default; the model picker says "live, a reference
  arm's"). On /flows the toolbox offers `use_model(...)` under Movement in a map's main,
  and in a tab named `monsters` a **Monsters** category: a function per monster of the node's model,
  each monster as a `mob(<id>)` value, and the recipe's steps in their order (knife_on(), strike,
  wait_steal, knife_back(), wait_kill, loot; use_skill marked "not played live yet: 4b"). The steps
  are no longer listed under "More skills" (they play only inside a monster's function). Run's
  readiness reads the monsters' functions too.
  ➡️ **2026-11-14 (stage 5b-2, [planning/live-blocks.md](planning/live-blocks.md) 14):** a tab named
  `hunt` of a map node offers a **Hunt** category: `def hunt_loop(t)`, `while True`, `t =
  find_target()` and `fight_target(t)` (the canonical loop: the hunt core then plays this loop instead of
  its own, `fight_target(t)` being the monsters tab's recipe for t's species), walk_to_target, the recipe
  steps, choose_target, look, use_skill (the heal key) and `if known(value=t)`. The hunt loop's own
  blocks show their value's variable and their time box on rows of their own ("t = find_target" /
  "( )" / "at most 120 s"): the variable is a variable picker (the loop's input t first), the time box
  a stepper (1-600 s), a target in a block's inputs a variable row, use_skill's key the hunt core's
  declared one (live-blocks 14.10).
  The Load lists of /flows and /maps offer **xmas_dun02_hunt** (the one box plus that tab); the
  one box itself has no hunt tab. Run's readiness reads the hunt loop too.
  ➡️ **2026-11-15 (stage 5c, [planning/live-blocks.md](planning/live-blocks.md) 15; Batt: "dungeon_hunt.py
  should be blocks the user sees and can edit himself"):** the ready-made **xmas_dun02** that /flows
  and /maps open first has no "hunt with the runner" block. Its main calls `hunt_loop()` there (the
  toolbox offers it under Movement in a map's main); the tab `hunt` holds a **role block** per role
  (heal, Fly Wing, Knife on, Knife off, home, died, confirm, eat: each a picker of the node's and
  Global's functions, the usual one first; delete an optional one for none) and the loop
  (`def hunt_loop(t=False)`); the tab `tick` holds `hunt_tick()` with run()'s 20 **step blocks** in
  their order, each showing its class: SAFETY and REQUIRED steps cannot be left out or moved (the lint
  says what each protects), an optional one (step_loot, step_ready, step_plant) may be dragged out and
  the runner then never plays it. The toolbox offers a **Roles** category on the tab hunt and a
  **Tick** category on the tab tick. Run plays it exactly as the hunt box. The old shape (the runner
  block) is **xmas_dun02_runner** in the Load lists; a saved project with the runner block loads and
  runs as before. ➡️ **Since round 29 (2026-11-16, Batt: "keep it as a backup, but it is no longer
  used in real runs"), a box with the runner block LOADS but does not RUN**: Run says "this box uses
  the old one-block runner; real runs use hunt_loop() (load xmas_dun02)", and the Run route and the
  Run helper refuse it in the same words (round 29 below).
  The /maps Load list also offers **xmas_dun02_cookie_noswap** (live-blocks 16: the one box with
  no Knife swap on the Christmas Cookie and the Cookie, `attack_cookie` / `attack_cookie_xmas` =
  strike, wait_kill, loot; the other monsters keep the swap): load it there and Run it from START. ➡️ **Since
  round 29 (2026-11-16):** that entry is the FUNCTIONS-shape twin: the ready-made xmas_dun02 with
  those two recipes, an example of a recipe edit, not the default. Its Run is a real run. The
  one-box version (the old runner block, stage-6 A/B arm C) is off the Load lists; the A/B still
  plays it through `flow_play.py`.
  - **/maps:** a small **START** pill left of the start map, joined to its entry; drag that
    connection onto another map and the run starts there (or "Start here" in a node's inspector).
    **Run** (amber, beside Simulate; press, then press again within 4 s) plays the project in the
    game from START, box by box, through the Run helper's live block player (`POST
    /flows/run/project`), and the live line shows while she plays; Stop ends it. It is greyed with
    the reason while a block on the way is not live yet ("walk_to, talk_npc: not live yet") or
    START is a login node ("login is not live yet").
  - **/flows:** Run on a map node plays the same project run from THAT node, enabled when every
    block it can reach is live in the player (the catalogue says so), else greyed with the reason.
    "Before Run" keeps the checklist, the live line, the settings and the read-only check.
  ➡️ **2026-11-14, matpilot's round 16 #6-#8** ([planning/project-model.md](planning/project-model.md)
  section 10; built offline, the reviewer re-measures in a browser):
  - **/maps' lint chip is a button:** it opens, in the side panel, the list of EVERY finding it
    counts: the project's own (on no node, so no card shows it: e.g. "a death returns to the save
    point on geffen, where no block is") first, then each node's as its card counts them (a node's
    name selects it). With nothing selected the panel names the project's own findings too.
  - **/maps' graph:** an exit's label sits in the GAP between its two cards, in what fits there
    (one line, wrapped on words, one word, or none: the card's port row says the exit in full);
    "+ map" places a new map 300 units right of the rightmost one (the widest card plus a lane for
    a two-line label); an entry's or exit's caption wraps instead of ending in "…"; on a phone the
    graph has no minimap (it covered the start card's corner; a finger pans, Fit brings the maps
    back).
  - **/flows on a phone:** the node row (◂ Maps, Inside the runner) never shrinks under an open
    pane; the drawer is as tall as its panes, so the page is the one scroller (Before Run's
    checklist no longer scrolls inside a 333 px box), and the status row with More ▾ stays at the
    screen's bottom.
  ➡️ **2026-11-14, matpilot's round 17 N1-N8** ([planning/project-model.md](planning/project-model.md)
  section 10c; built offline, the reviewer re-measures in a browser):
  - **Which threshold a Run uses:** in a Run of a project the box's events and functions decide
    what they play inside the hunt core and the runner's own handler is off (the potion, the Fly
    Wing on HP, the boss fly, the weight exit on a read weight, the death dialog's clicks); the
    setting then applies to the runner alone (the old Run path, a box without that event). Before
    Run's settings rows say so ("in this project: replaced by the box's drink event (HP < 30 %,
    until HP >= 31 %); this value is the runner's alone ..."); a tab the box plays has a strip
    line **IN A RUN** naming each event or function, what it replaces with Before Run's setting
    and value, and what stays the runner's (the HP-rate fly); /maps' inspector marks those names
    in its tabs list. The words come from the flow engine (POST /flows/lint `box`).
  - **/maps' lint lines:** every list is most serious first (error, not ready, warning, info),
    each line starts with its severity, and the inspector's capped list says what it hides
    ("…and 18 more (18 info): …").
  - **A runner node's monsters:** the lint says per spawn whether the runner strikes it (every
    class its model strikes: use_model's, else the map's own detector; a monster's function only
    chooses HOW) or never does (garm_baby, the boss); the inspector says so under the target /
    ignore lists, which are the simulator's on such a node.
  - **Event blocks:** every trigger field the Python writes is on the block, one row each (pause
    after each run = cooldown_s, at most N a run / a minute, N per 10 minutes, an insert's failures
    and its escalation; empty = none, except the 10-minute guard and the insert failures: empty =
    the engine's default, which their rows name: 10 and 3); a tab's first block starts below Undo
    / Redo. On a phone the blocks start smaller (scale 0.6) and the strip under the tabs folds to
    one line (its button opens it: "IN A RUN: 3 events replace the runner's own · 2 more ▸").
  - **Run waits for another input writer:** while a night chain, a runner, the live block player
    or an A/B series of ours plays, the Run helper's state is **busy** with those words, Run and
    "Check the game" are greyed with them (the check's title says the CHECK waits), both pages'
    status lines say "Run is off now: <the words>", and the backend refuses a start or a check
    (`input_writer_busy`). A ✓ checklist line adds the words after its last ";" outside
    parentheses.
  - **/maps' Fit:** at a readable size (0.85) it shows every card, else the run's path (all but
    Global), else START and the map cards; on a canvas of 768 px or less START and every map card
    are scaled down until they fit (after a load, after "+ map", on Fit). The button's tooltip
    says what the last fit showed and what it left out; its accessible name is that tooltip's
    first sentence ("Fit the maps" before the first fit). The fit keeps the zoom buttons' column
    (bottom left) free, so no fitted card's left edge is under them.
  - **/maps' connection labels:** every label (the session's "log in, then choose", "enter the
    game → <entry>", and the exits) sits in the gap between its two cards -- beside: at the
    line's height, wrapped or one short word or none; one under the other: in the vertical gap,
    as many lines as fit -- never under a card; a shortened label's full words are its tooltip. A
    label whose text would be under 9 px at the view's zoom is not drawn (the cards' port rows
    name the exits).
  ➡️ **2026-11-14 ~15:2x, THE SETTINGS ARE BLOCKS; the runner page is gone** (Batt: "there should
  be no runner [page]: it makes learning very hard. Everything in the xmas_dun02 flow, split into
  tabs ... make them ALL blocks, no hardcoding"; [planning/live-blocks.md](planning/live-blocks.md)
  section 12):
  - **Every setting of the runner's hunt core is a block** (121 of them -- ➡️ 123 since
    2026-11-16, with the safety tab's `fly_first`, "a boss seen, at any distance: the Fly Wing
    first, no Knife swap before it" (➡️ ON in the ready-made xmas_dun02 and its cookie twin since
    s7ab passed, Batt 18.10 #1; the old one box, the hunt box and the A/B reference arms keep it
    off), and `fly_first_hp`, "HP low, no boss in sight: the Fly Wing first too" (➡️ ON in the same
    two ready-made boxes since s8ab passed, 18.13; the reference boxes keep it off); ➡️ 125 since
    2026-11-17 (18.17, dungeon@9.60), with the safety tab's `fly_first_land`, "after a Fly Wing:
    no Fly Wing again on what the picture showed before the landing" (➡️ ON in the same two
    ready-made boxes since s10ab passed, 18.18; the reference boxes keep it off), and `FF_LAND_S`,
    "after a Fly Wing, ignore boss sightings in the pictures of the first" 0.75 s (0.2-2.0 s; used
    only with fly_first_land on),
    [planning/live-blocks.md](planning/live-blocks.md) 18 --: heal and escape, the Knife swap, leaving the map, the respawn, the start, the fight, choosing and striking, loot,
    walking and exploring, safety and the end, timing), in the TAB of its group on a map node or
    on Global: its words, its value as it is set (a number or a percent with its range, step and
    unit; on / off; a choice's options; a point's x and y, or none), its Python name after it
    (`· knife_hp_min`). ➡️ Since round 20 (2026-11-14) a block is laid out on ROWS -- its words
    wrapped over one or more rows, then the value with its unit and `· var` (the var on a row of
    its own when the row would be too wide) -- so no row is wider than what shows at 390 px beside
    the toolbox and before Blockly's zoom buttons and trashcan; a safety switch (respawn,
    npc_guard, garm_fly, alarm_fast) shows its warning on rows of its own while it is off, and the
    lint counts it as a WARNING (the chip and the /maps card show it). In Python it is a plain
    assignment with its words as a comment (`knife_hp_min = 0.5  # or at once under HP (50 %)`);
    the comment also carries the lint's words for that block (`· ⚠ off: ...`, `· not used here:
    the drink event plays it`). The hotbar keys stay the keys tab's functions.
  - **The name rule:** a map node's block replaces Global's there; a deleted block falls back to
    Global's, else our default (each block's tooltip says which; it names Global only when the
    project has a Global node). One setting has ONE block on a node: a second one on another tab
    is refused on the block, naming that tab (the engine refuses a name on two tabs of a node; ➡️
    round 21: the message names both tabs, the copy's own rows say it, and Run and Check are held
    until it is fixed). The
    toolbox has a **Settings** category with one sub-category per group, named as its tab and in
    the tabs' order, each with a short header; the block search finds a setting by its group's
    words and its own (`knife` finds all six Knife settings, `garm` the Garm Baby ones).
  - **The ready-made xmas_dun02** has a block for every setting it uses: survival, knife and exits
    hold their settings beside their functions; respawn, start, fight, aim, loot, walk, safety and
    timing are tabs of settings. ➡️ Since round 20 it holds NO block of the five settings its own
    events and functions play in a Run (potion_below: drink, fly_below: fly_away, weight_home:
    bag_full, respawn_at / respawn_confirm_at: the exits tab's respawn_button / respawn_ok); a
    block a person adds that a Run of the box does not use -- one of those five, or one whose
    switch is off (quick_drop_scaled while quick_drop is off) -- is GREYED with a row saying why
    ("· not used while npc_guard is off"), in its tooltip and in its Python line too: the lint's own
    facts, so the three never disagree. A Run, and "Check the game", send the project: the blocks
    are what the runner gets. The lint says it in words on the block: a value out of range or of
    the wrong kind (an error: Run refuses), a name that looks like a typo of a setting's or a
    hotbar key as a variable (a warning), a safety switch off (a warning), two settings that cannot
    run together (an error), and a setting not in use ("while the Knife swap is off") or replaced
    by the box's own event (info).
  - **On a phone** (round 20): the Python sheet's file buttons are ONE row that scrolls sideways
    (the selected one kept in view), the sheet scrolls, and the code always keeps its room; the
    Python view's file buttons likewise. On /maps, the inspector's "Tabs and names" folds each
    tab (folded by default, its line saying what it holds: "aim · 33 settings (1 changed)"), a
    setting reads as its block does ("heal at HP under 40 %"), and one that differs from our
    default comes first, marked "changed".
  - **Gone:** the runner description page (`/flows?runner=...` now opens that map's node), its
    "Inside the runner" link and Load entry, Before Run's settings panel ("saved on the bot server
    at once") and the settings file behind it (GET / PUT /flows/config).
  ➡️ **2026-11-14 ~19:4x, round 21: PICKERS instead of textboxes** (Batt: "fields that choose a
  value ... should be DROPDOWNS with the values to choose from ... typing should work like a
  search ... a visual UI, e.g. the turn angle"; [planning/live-blocks.md](planning/live-blocks.md)
  section 12.5; ADR-0020 Amendment K). Free text stays ONLY where a name is DEFINED (a function's
  name and inputs, a variable's name, an event's name, a tab's name); every other field opens a
  picker under it, in the block's colour, by touch or by keyboard:
  - **A reference** (the function a call, a runner role or an exit calls; the function an event
    escalates to; use_model's model; the save point's and an exit's map; a stop reason; an exit's
    node and entry; the window; the login server; the variable a `set` sets) shows `▾` and opens a
    LIST of what exists now (the node's and Global's functions with what each presses, the models
    with their map and status, the map names the world knows with a Kafra marked, ...). Typing
    filters it (a word's start first, then inside, then letters in order). A word the list does
    not have is kept as typed where it may be (a new stop reason); a value loaded that is not in
    the list (an unknown function, a model not in models.yaml) is KEPT, shown with `⚠`, and the
    lint names it as before.
  - **A number**: seconds, counts and ranks a stepper (− / +) with a slider; a percent setting a
    lever bar that fills like an HP bar (the bag's the other way round); a point of the game
    picture (respawn_at) two steppers and the 1280 x 720 picture with its dot (tap to place it); a
    map cell (the save point, walk to, a walk exit) two steppers. An event's "at most …", "rank"
    and "insert fails" are a stepper with a "no limit" / "the default" button; an empty one shows
    `—`, `auto` or `default 10`.
  - **A condition** (an event's when / until / rearm, if, while, wait until): sensor ▾, comparison
    ▾ and a value that follows the sensor (the lever for hp_percent()), and under it the text
    itself, which autocompletes sensors, functions, variables and the comparisons while typing.
    and / or is a block of its terms, one a row. A catalogue block's inputs (use_model's model,
    use_skill's key) and a call's inputs are rows of pickers above the same text.
  - The picker changes the SAME text or number the field held: the IR and the Python view are as
    before, and old projects load unchanged.
  - **The map names** come from the backend at run time (`GET /flows/maps`: the local KB's maps,
    or the sample's), never from a committed list.
  - **At 390 px** (round 20's re-measure): every block of the ready-made box ends before Blockly's
    zoom buttons and trashcan -- the runner's block a role a row, its words beside its picker; the
    save point, an action's inputs, an event's fields and a function's name on rows of their own; a
    long condition shows shortened in the middle on a phone (➡️ round 22: it WRAPS onto more rows of its box, whole, at a token boundary; `hotbar_count(…) > 0` read the same twice; its tooltip
    and its picker show it whole). The Settings category is LAST in the toolbox, so opening it
    never pushes Functions and Advanced away. In the Settings flyout and the search, a setting the
    node's box replaces is greyed with the lint's words ("not used here: the drink event plays
    it"). A setting dropped onto a second tab of the node is marked on the block itself (`⚠
    already set in tab knife; one block per setting on a node`) and the message names both tabs;
    while the blocks hold such a problem, Run and Check are held and say why (the project they
    would send is the one from before it). The folded strip line fits ("IN A RUN: 3 events replace
    the runner · +4"); "Global" is named only in a project that has a Global node. The Python sheet
    keeps its file row and × in place while the code scrolls.
  - **Round 22** (the reviewer's browser measure of round 21; [planning/live-blocks.md](planning/live-blocks.md)
    12.6): a picker opens below or above its field and never covers it -- when it fits on neither
    side the blocks scroll so the field sits where it fits, else it opens compact, else it scrolls
    inside; every picker ends with **Cancel** and **Done** ("Esc: cancel · Enter or Done: keep"):
    Escape or Cancel puts every value back as it was when the picker opened (no undo step left),
    Done, Enter or a tap outside keep it; the arrow keys browse a list inside the condition picker
    without closing it; +/− take a round step (about 1 % of the range) and the presets are round
    values (10 / 25 / 50 / 75 / 90); a percent shows its lever only; an unfinished condition says
    so in plain words ("not finished: a value is missing after >="); the point picture outlines
    the client's fixed windows (basic info, hotbar, minimap, chat: where they usually are); a
    role's list holds only the functions it can call (no inputs needed, no event, no monster's
    recipe); a greyed block's picker is drawn in a darker shade so its words read.
  - **Round 23** (the reviewer's browser measure of round 22; [planning/live-blocks.md](planning/live-blocks.md)
    12.7): a tab's blocks never overlap -- once drawn they are stacked from their measured
    heights, 24 units apart, in their order, and a block that grows (a wrapped condition, a note)
    pushes the ones under it down (a move, not an edit: no undo step, nothing saved); Escape or
    Cancel leaves Undo exactly as it was (Ctrl+Z after a cancel does nothing), a kept change is one
    Ctrl+Z; the point picture reads the right place in the compact picker too; a tap on any row of
    a wrapped condition opens its picker; the presets and the lever's ticks are round (END_HOT_S 2
    / 10 / 15 / 25 / 30 s; 10 / 25 / 50 / 75 / 90 %); a broken condition says what is missing
    ("after < a value is missing"), never a character number; Blockly's own menus stay inside the
    blocks area.
  - **Round 24** ([planning/live-blocks.md](planning/live-blocks.md) 12.8): a drag in the point
    picture is read against the picture as it was pressed, so the first drag reads like the second
    on a wide screen too; while the lint checks an edit, the strip's IN A RUN words stay (faded)
    instead of going, so the canvas under the strip never jumps.
  - **Round 25** ([planning/live-blocks.md](planning/live-blocks.md) 12.9,
    [planning/project-model.md](planning/project-model.md) 2.6): the block editor REMEMBERS
    where a person puts blocks -- every block dragged (or arranged by "Clean up Blocks") keeps
    its place through a refresh, a trip to /maps, Save and Load (saved in the project's tab as
    `layout`, by the function's, event's or variable's name; outside the engine: no new lint,
    hash or Run). Blocks nobody placed go LEFT TO RIGHT while they fit the canvas (the monsters
    tab's four recipes in one row at 1440), one column on a phone. A block that grows pushes
    only the blocks under it or right of it; a block dropped onto another stays where it was
    dropped. /maps' nodes already kept their dragged places.
  - **Round 26** ([planning/live-blocks.md](planning/live-blocks.md) 12.10, the 5c review): on the
    tick tab a SAFETY or REQUIRED step is LOCKED (🔒; it cannot be deleted or dragged out of
    hunt_tick(), until Batt decides 15.10), each class has its colour (SAFETY red, REQUIRED blue,
    optional green), and dragging an optional step takes that ONE step (the others close up). The
    role pickers never offer hunt_loop, hunt_tick or a function that plays the hunt's blocks.
    hunt_tick and hunt_loop say what they are on their own rows; find_target shows no empty "( )"
    and its target picker lists no settings; an info never shows a ⚠ (the Lint pane lists it, in
    plain words); the Python view notes a hunt block's time box (`# at most 120 s`); the old
    one-block runner is in Advanced > Old projects.
  - **Round 27** ([planning/live-blocks.md](planning/live-blocks.md) 12.11): the tick tab's toolbox
    has **Tick steps** (hunt_tick() and the 20 step blocks; the search finds them by name and by
    what they do, e.g. "survive", "loot"), so a deleted optional step can be put back; dropped in
    the wrong place, the lint says where it goes. hunt_tick and hunt_loop now show their own rows
    and tooltips on the page; a function's tooltip names Global only where the project has one.
  - **Round 28** ([planning/live-blocks.md](planning/live-blocks.md) 12.12): only the copy of a
    SAFETY or REQUIRED step that stands in its place is locked; an extra copy (a second
    step_survive) or one out of its place shows no 🔒, can be deleted or moved, and its rows say
    why ("an extra copy: delete it" / "out of its place: it goes after ..."), as the lint does. The
    words say "the runner's order", never "run()".
  - **Round 29** ([planning/live-blocks.md](planning/live-blocks.md) 12.13; Batt 2026-11-16, 17):
    - **Every step can be edited.** SAFETY and REQUIRED steps delete and drag like any block (a
      drag still takes that one step; the others close up). Their 🔒 is gone. Their class line
      says "SAFETY · needed to run" (or "REQUIRED · needed to run"), in the class colours. A tick
      without one of them is not a Run: the lint says which step it leaves out and what it
      protects, and the Run button is held with that reason. Undo it (Ctrl+Z), or load the saved
      file.
    - **The old one-block runner is not a real run.** A box whose hunt core is the old runner
      block (Advanced > Old projects, xmas_dun02_runner) still loads and simulates. Its Run
      button is held: "this box uses the old one-block runner; real runs use hunt_loop() (load
      xmas_dun02)". The check and the Run are refused in the same words (`old_runner`).
    - **Every run records its economy.** When a Run ends, its hunt sessions go into
      `data/econ/lab.sqlite` (`econ_db.py update`), so that file holds every real run. The
      /economy page itself still reads the JSON exports
      ([econ/economics.md](econ/economics.md) section 10).
- **No live run (the block editor):** nothing in the block editor reaches the executor, the mux or an input path (➡️ Run, above, is the one live path: the Run helper's player, never the editor). The backend's
  `/flows/*` routes only compute (public listener, LAN viewer, Origin; POSTs need the CSRF token,
  20 a minute; the Python view 120 a minute on its own budget since 2026-11-09). See [planning/mw2-block-editor.md](planning/mw2-block-editor.md) and
  [planning/blocks-from-hunt-flow.md](planning/blocks-from-hunt-flow.md) (7b).

**Bot typing needs the game window in front.** Before the bot types anything, the backend checks
the game client's title bar on a fresh frame; clicks are never blocked.
- The reference picture is installed with
  `uv run python scripts/foreground_template.py install rdp|stream`.
- The console (S2) view has its own picture, cut on the stream (2026-10-07). Re-cut it with
  `ro_agent.py calibrate client_title_active@stream` + `foreground_template.py install stream`
  if the client window moves.
