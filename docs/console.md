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

Open **http://HOST_LAN_IP:3000**. What it gives you:
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
   `FRONTEND_ORIGINS=http://HOST_LAN_IP:3000,http://localhost:3000`
2. Apply it: `python3 scripts/guarded_build.py --sustain 30 --spike 25 recreate:backend@30`.
3. Run the console:

```bash
cd services/frontend && corepack pnpm install
BACKEND_PUBLIC_URL=http://HOST_LAN_IP:8000 corepack pnpm dev    # open http://localhost:3000
```

`FRONTEND_ORIGINS` is the backend's WebSocket Origin allowlist: comma-separated, and unknown origins are
refused. It defaults to `http://${HOST_LAN_IP}:3000`. Stream rate and quality are `STREAM_FPS` (30) and
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

The input log records every human key with its code, so **turn on "Secret typing" in the toolbar
before typing or pasting a password**.
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

## Settings: the game servers the bot may use

Open **Settings** in the console's top bar (`http://<host>:3000/settings`).
- **Environments** are game services you manage yourself: **Allowed** (the bot may act while the
  game is connected to one of its servers), **Forbidden** (never; its servers can never be allowed
  anywhere) or **Pending** (not approved). Create, rename and delete them, and edit their server
  lists, on the page. The shipped ones (official Thai, official Korean, the community server, the
  lab's rAthena) are only a starting set.
- **Found by the lab:** servers your game client is set up for. They are suggestions until you
  press **Confirm** (or **Confirm all** for one server's ports). Every save is checked by reading
  the file back ("Saved and checked ✓").
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

Open `http://<host>:3000/flows` (Flows in the top bar). The page edits ADR-0020's flow IR.

**Maps** (`http://<host>:3000/maps`, Maps in the top bar, 2026-11-10): the same flow as a graph of maps:
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
- ➡️ **Since 2026-11-13 the xmas_dun02 runner view has a Run button** (`/flows?runner=xmas_dun02`, "Run in the game"): it starts the proven runner in player mode through the host helper `scripts/flow_run.py`, NOT the flow IR (ADR-0020's executor is still unbuilt). How and why: [planning/player-mode.md](planning/player-mode.md), [setup/new-lab-host.md](setup/new-lab-host.md) 11.1.
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
- **No live run (the block editor):** nothing in the block editor reaches the executor, the mux or an input path. The backend's
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
