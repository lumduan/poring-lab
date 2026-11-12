# Third-party work used in poring-lab

**Batt's rule (2026-10-03):**
- A permissive license → reuse or port, with attribution here.
- Copyleft or unclear → read for ideas only and write our own code.
- Every LICENSE is read **at the exact commit** before anything is ported. That commit and the
  license are recorded below.
- Cheat and memory-patching repositories are never opened.

**Data rule:**
- Client data (GAT, GND, sprites, any GRF content) is read into `/dev/shm` at run time and never
  committed. `.gitignore` and `.githooks/pre-commit` refuse it, even with `git add -f`.
- Knowledge-base data derived from rAthena (GPL) is generated locally at run time and is never
  committed either.

## Ported (permissive)

### The perspective camera model
- **Ported to:** `packages/poring_dataset/src/poring_dataset/camera.py`.
- **What:** the camera rig, re-expressed in numpy from the model (no code copied verbatim). The eye
  sits on a sphere around the player (yaw, pitch, distance), with a look-at view and a narrow
  vertical FOV. The defaults the two clients agree on (pitch ≈ 55°, FOV 15–15.5°, distance 400)
  only seed our fit. The parameters in `camera_<backend>.json` are fitted to our client.

| Source | Commit | License | File read |
|---|---|---|---|
| [nmeylan/nostalro-client](https://github.com/nmeylan/nostalro-client) | `15b3029059c04cf1d54d734f7233e5db3c108a9c` | Apache-2.0 (`LICENSE.md`) | `lib/renderer/src/camera.rs` |
| [vE5li/korangar](https://github.com/vE5li/korangar) | `e14d3203ad63f35962f6492d8a6b348eb8f47d47` | MIT, © 2023 Lucas Pütz (`LICENSE.md`) | `korangar/src/world/cameras/player.rs`, `mod.rs` |

### The indoor camera rule and the billboard facing (2026-10-04, Post-S2 round B1/B4)
- **Ported to:** `packages/poring_dataset/src/poring_dataset/camera.py` (`load_indoor_table`,
  `is_indoor`, `camera_for_map`, `look_heading`, `displayed_direction`).
- **What:** two rules, re-expressed (no code copied verbatim):
  - a map is INDOOR iff `<map>.rsw` is listed in the client's `data/indoorrswtable.txt`, and the
    client then draws it with the yaw 45° off the default (pitch, FOV and distance unchanged; only
    the zoom/pitch clamp bands narrow). The sign in our yaw convention is measured, not assumed
    (`scripts/camera_validate.py`, recorded in `camera_<backend>.json` "indoor"). Measured
    2026-10-04: +45.96° in our convention, and the camera is CLOSER (distance 273 vs 400): that
    distance is OUR measurement (the narrower clamp band pulls the default in), not a ported value;
  - the sprite direction a billboard shows = `(camera_dir + 12 − heading) % 8`, with `camera_dir`
    the camera's look direction as an RO heading.
- The table itself is CLIENT data: extracted from the GRF into `/dev/shm` at run time, never
  committed.

| Source | Commit | License | File read |
|---|---|---|---|
| [nmeylan/nostalro-client](https://github.com/nmeylan/nostalro-client) | `15b3029059c04cf1d54d734f7233e5db3c108a9c` | Apache-2.0 (`LICENSE.md`) | `lib/renderer/src/map_loader.rs` (L85-90), `lib/renderer/src/camera.rs` (L189-209), `lib/formats/src/act.rs` (L568-570) |

### The GAT file layout
- **Ported to:** `packages/poring_dataset/src/poring_dataset/gat.py`.
- **What:** the layout (header, 20-byte tiles with four corner altitudes and a terrain type),
  re-expressed with a numpy dtype. The terrain types follow rAthena's map cache, which our parser is
  cross-checked against (2026-10-03: prt_church 100 %, prt_fild08 99.999 % of cells equal).

| Source | Commit | License | File read |
|---|---|---|---|
| [RagnarokResearchLab/RagLite](https://github.com/RagnarokResearchLab/RagLite) | `d1ce2b1e2136c46b1409d5c6701f64d7c3cddaf9` | Unlicense **or** Apache-2.0; used under Apache-2.0 (`LICENSE`) | `Core/FileFormats/RagnarokGAT.lua` |

### The sprite formats (SPR/ACT) and the sprite render rule (2026-10-04, Phase 3 M1/M2)
- **Ported to:**
  - `packages/poring_dataset/src/poring_dataset/sprites.py`: `parse_spr`, `parse_act`, `layer_quad`,
    `compose_frame`, `quad_extent`, `opaque_bbox`;
  - `packages/poring_dataset/src/poring_dataset/render.py`: `predict_sprite`, `motion_at`,
    `anchor_and_depth`, `K_NOSTALRO`, `MonsterAction`.
- **What:** re-expressed in Python/numpy, with no code copied verbatim:
  - the SPR 1.0–2.1 layout: 2.1 zero-run RLE; ABGR bottom-up RGBA images; the palette at the end;
    index 0 and the magenta key transparent;
  - the ACT 2.0–2.5 layout;
  - the layer quad: centred at anchor + offset, with zoom, angle, mirror and tint;
  - the billboard scale: perspective px per world unit × GND zoom / 75;
  - the action index;
  - the frame timing: 24 ms units; the walk frame by distance (delay/24/7.4 cells); one-shots that
    hold their last frame;
  - the monster action groups: idle 0, walk 1, attack 2, hurt 3, die 4.
- korangar was read to CROSS-CHECK only (k = 1.4/10, its billboard, its action groups); nothing was
  ported from it. Where the two differ (k by 5 %, frame timing, walk frames by distance vs time,
  the layer-centring half pixel) is recorded in phase3-plan.md M2.
- **The client data is NOT ours to ship:** SPR/ACT are read from the client GRF into `/dev/shm`
  only, and the catalog (`data/kb/sprite_catalog.json`) is gitignored.
  - 2026-10-04: every monster SPR in the Thai `data.grf` is MIXCRYPT, and was refused (C8 stop).
  - Only the ACTs (header-only DES) are read.

| Source | Commit | License | File read |
|---|---|---|---|
| [nmeylan/nostalro-client](https://github.com/nmeylan/nostalro-client) | `15b3029059c04cf1d54d734f7233e5db3c108a9c` | Apache-2.0 (`LICENSE.md`) | `lib/formats/src/spr.rs`, `lib/formats/src/act.rs` (L7-13, 568-571, 620-634, 641-679), `lib/formats/src/lib.rs` (`read_string`, `version_at_least`), `lib/formats/src/map_coordinates.rs`, `lib/renderer/src/sprite.rs` (L842-956), `lib/renderer/src/sprite_projection.rs` (L154-178), `lib/renderer/src/camera.rs` (L425-439), `lib/game/src/entity.rs` (L1170-1178); read without porting: `client/src/game_updates/animation.rs`, `lib/game/src/shadow.rs`, `lib/game/src/sprite_loader.rs` |
| [vE5li/korangar](https://github.com/vE5li/korangar) | `e14d3203ad63f35962f6492d8a6b348eb8f47d47` | MIT, © 2023 Lucas Pütz (`LICENSE.md`) | `korangar/src/world/animation/mod.rs` (L15-16, 40-68, 256-303), `korangar/src/world/cameras/mod.rs` (L47-67), `korangar/src/loaders/animation/mod.rs`, `korangar/src/loaders/map/mod.rs` (L31-32): cross-check only. ➡️ **2026-10-05:** `korangar/src/loaders/archive/native/mixcrypt.rs` (sha256 `6a682441…227b`) was read and ported into a **host-local study decoder that is never committed** (Batt: MIXCRYPT option (a), study only; loaded by `scripts/grf_read.py --decode-mixcrypt` from outside the repo; the pre-commit hook refuses it by name and fingerprint). Its DES helpers (a copy of RustCrypto `des`, Apache-2.0) were not ported: the DES block is our own `scripts/grf_des.py`, which reproduces korangar's test vector |

### The RSW / RSM model geometry (2026-10-21, the orcsdun01 label fix 1c)
- **Ported to:** `packages/poring_dataset/src/poring_dataset/rsw.py`.
- **What:** the RSW object list (models, and the light / sound / effect records walked past) and
  the RSM 1.x node mesh, plus the placement rule that puts a map model's vertices in the world
  (the node chain T R S, the single-node rule, the box shift that puts the model's bottom on the
  ground, the RSW instance's T Rz Rx Ry S about the map centre), re-expressed in Python/numpy (no
  code copied verbatim), frame 0 only (no animation).
- **Why:** docs/planning/orcsdun01-detector.md 3b (1c): a label whose sprite box overlaps a map
  model's projected box is excluded. The projected boxes were checked by eye against the drawn
  models on a col3 frame (an orc flag, a brazier, a firewood pile, a dead tree).
- **The client data is NOT ours to ship:** the RSW and its RSMs are read from the client GRF into
  `/dev/shm` only (`scripts/grf_read.py --decode-mixcrypt`, study only); the tests build theirs
  from synthetic bytes.

| Source | Commit | License | File read |
|---|---|---|---|
| [nmeylan/nostalro-client](https://github.com/nmeylan/nostalro-client) | `15b3029059c04cf1d54d734f7233e5db3c108a9c` | Apache-2.0 (`LICENSE.md`) | `lib/formats/src/rsw.rs`, `lib/formats/src/rsm.rs`, `lib/formats/src/lib.rs` (`read_vec3`, `version_at_least`), `lib/renderer/src/model.rs` (`load_rsw_instances`, `build_instance_matrix`, `bbox_shift_matrix`, `node_post_matrix`, `node_accum_matrices`, `calc_bounding_box`), `lib/renderer/src/rsm_anim.rs` (`node_local_matrix`, frame 0), `lib/formats/src/map_coordinates.rs`, `lib/renderer/src/sprite_projection.rs` (`project_entity_screen`: where an entity's cell stands in that world) |

### The /flows studio's layout, theme, code view and block search (2026-11-09)

Batt (2026-11-09): "a layout like matpilot.org/blocks … use matpilot's colour theme"
([docs/planning/flows-studio.md](docs/planning/flows-studio.md)); Batt teaches children with
matpilot.org. Its LICENSE was read at the exact commit (`LICENSE`, MIT, sha256
`519e79d4387e85cd8fb36588804fdadfa5e65bb1183f732ed2947a00b9f1e606`); each file below keeps the
copyright and permission notice. No dependency was added: MatPilot's `@lezer/python` colouring is
replaced by our own tokenizer (`services/frontend/src/lib/flow/pycolor.ts`).

| Source | Commit | License | File read | Ported into |
|---|---|---|---|---|
| [lumduan/matpilot](https://github.com/lumduan/matpilot) | `d639909` | MIT, © 2026 Sarat Sonsuk (`LICENSE`) | `src/lib/blocks/colours.ts`, `src/lib/blocks/theme.ts` | `services/frontend/src/lib/flow/theme.ts` (category colours, block / category styles, font, light and dark component styles) |
| same | `d639909` | same | `src/components/blocks/CodeView.tsx` | `services/frontend/src/components/flows/CodeView.tsx` (the read-only code view) |
| same | `d639909` | same | `src/lib/blocks/search.ts`, `src/lib/blocks/words.ts` | `services/frontend/src/lib/flow/search.ts` (normalise, matchEntries, searchFlyout), `services/frontend/src/components/flows/blockly-search.ts` (the toolbox search row, its Blockly 13 focus fix, blockWords) |
| same | `d639909` | same | `src/app/globals.css` (the tokens, `.studio*`, `.segmented*`, `.button*`, `.notice*`, `.block-tab*`, `.code-*`, `.py-*`, `.toggle-button`, the narrow-screen rules) | `services/frontend/src/components/flows/studio.css` |
| same | `d639909` | same | `src/components/blocks/BlocksApp.tsx` (the layout, the icons), `src/lib/blocks/python-colors.ts` (the token kinds and rules only: its lezer code was not copied), `src/lib/blocks/generator.ts` (the `# --- Section ---` heading style), `src/lib/blocks/simple-definitions.ts` (the sensor blocks' shape) | `services/frontend/src/components/flows/FlowsApp.tsx`; the rules re-written in `pycolor.ts`; `packages/poring_flow/src/poring_flow/pyview.py` (`section_rule`); `blockdefs.ts` (`pl_detect_*`) |

### The Maps page: matpilot's mat page, for maps (2026-11-10)

Batt (2026-11-10): "like matpilot's mat page where you watch the robot walk … binding a program to a
robot in matpilot" ([docs/planning/world-map-flows.md](docs/planning/world-map-flows.md)). The same
commit and LICENSE as above (read again 2026-11-10: sha256 unchanged). Ideas only, our own code:
the graph (React Flow, already a dependency) and the simulator (poring_flow.trace); matpilot's
MicroPython simulator and its mat geometry were not copied.

| Source | Commit | License | File read | Ported into |
|---|---|---|---|---|
| [lumduan/matpilot](https://github.com/lumduan/matpilot) | `d639909` | MIT, © 2026 Sarat Sonsuk (`LICENSE`) | `src/components/mats/MatRunPanel.tsx` (`PlaybackBar`: play / pause, the time slider, the speed; `Checks`: the ✓ / ✗ list), `src/hooks/useMatRun.ts` (the playback clock: real time × speed, on `requestAnimationFrame`) | `services/frontend/src/components/maps/SidePanels.tsx` (`PlaybackBar` + our step and reset, `Checks`), `services/frontend/src/components/maps/MapsApp.tsx` (the clock) |
| same | `d639909` | same | `src/components/mats/MatsApp.tsx` (the stage with the playback bar over it, the panel beside it), `src/components/blocks/RobotPicker.tsx` (the Robot choice at the end of the tab row) | `MapsApp.tsx` (the layout); `services/frontend/src/components/flows/FlowsApp.tsx` (`MapPicker`: the map a tab's flow is bound to) |
| same | `d639909` | same | `src/app/globals.css` (`.mat-playback*`, `.robot-checks*`, `.run-result`, `.run-output`, `.run-time`, `.mats-side`, `.robot-picker*`) | `services/frontend/src/components/maps/maps.css`; `.robot-picker*` in `services/frontend/src/components/flows/studio.css` |
| same | `d639909` | same | `src/components/blocks/BlocksApp.tsx` (the folder, save and play icons; round 2) | `services/frontend/src/components/maps/icons.tsx` (with our own pause, step and back-to-start icons) |

### Save, Download and Load, on this computer and on GitHub (2026-11-12)

Batt (2026-11-12): "make a save and download system too. Ask matpilot how they do it and do it that
way: save/load on the machine, and through GitHub too"
([docs/planning/flows-save-load.md](docs/planning/flows-save-load.md)). MatPilot at commit
`4022c870083c38c7ed4c62ff8361ef65a57d41f8`; its LICENSE was read at that commit (MIT, Copyright (c)
2026 Sarat Sonsuk, sha256 `519e79d4387e85cd8fb36588804fdadfa5e65bb1183f732ed2947a00b9f1e606`, the
same as at `d639909`). The full copyright and permission notice is in
`services/frontend/src/components/flowfile/flowfile.css`; every ported file starts with "Ported from
MatPilot (MIT), <file> at 4022c87". No dependency was added; MatPilot's vitest tests were re-written
for `node:test`. Ours, not MatPilot's: the folder listed with the Git Trees API (and `truncated` said
plainly), the size checked before a GitHub read, names capped by UTF-8 bytes and NFC, `safePath`
(no `.` / `..` segment in a URL), the token in this tab by default, the commit link built from its
checked id, and the flow IR inside the file.

| Source | Commit | License | File read | Ported into |
|---|---|---|---|---|
| [lumduan/matpilot](https://github.com/lumduan/matpilot) | `4022c87` | MIT, © 2026 Sarat Sonsuk (`LICENSE`) | `src/lib/blocks/program-file.ts` (+ `.test.ts`) | `services/frontend/src/lib/flow/file.ts` (+ `file.test.ts`): the file's shape, the name cleaning, the file names; `src/hooks/downloadFile.ts` as `downloadText` |
| same | `4022c87` | same | `src/lib/github/client.ts`, `base64.ts`, `repository.ts`, `programs.ts` (+ their tests) | `services/frontend/src/lib/github/client.ts`, `base64.ts`, `repository.ts`, `flows.ts` (+ tests, with `testkit.ts`) |
| same | `4022c87` | same | `src/hooks/useGitHub.ts`; `src/hooks/useAiHelper.ts` (only its key-storage pattern: this tab unless "Remember") | `services/frontend/src/lib/github/settings.ts` (+ test), `services/frontend/src/components/flowfile/useGitHub.ts` |
| same | `4022c87` | same | `src/components/blocks/SaveDialog.tsx`, `LoadDialog.tsx`, `GitHubSettingsDialog.tsx`, `describe.ts`; `src/components/Dialog.tsx` | `services/frontend/src/components/flowfile/` (`SaveDialog.tsx`, `LoadDialog.tsx`, `GitHubSettingsDialog.tsx`, `Dialog.tsx`), `services/frontend/src/lib/github/describe.ts` |
| same | `4022c87` | same | `src/app/globals.css` (the "Dialogs (Save, Load, GitHub)" rules) | `services/frontend/src/components/flowfile/flowfile.css` (renamed `.dialog-*`, `.flow-list*`) |
| same | `4022c87` | same | `docs/adr/0011-save-load-github.md` (the decision and the GitHub facts it checked); `src/lib/github/files.ts` (read only: robots and mats, not ported) | `docs/planning/flows-save-load.md` |

## Our own code from public standards
- **What:** `scripts/grf_des.py`, the GRF archive's header-only "DES" (flag 0x04).
- **Sources:** the DES tables are FIPS PUB 46-3. The GRF construction is the publicly described one:
  the first 20 blocks pass through IP, one zero-key round and FP.
- **No copyleft code was read for it.** rAthena's GPL implementation was deliberately not used.
- **2026-10-05:** MIXCRYPT (flag 0x02) is decoded only by a host-local study module outside this
  repo (see the korangar row above); this file still holds no MIXCRYPT code.
- **Verified:** the classic DES test vector, and a real DES-flagged GAT that inflates with zlib to
  its exact size.
- **KEPT in the repo (Batt, 2026-10-05).** It is standard FIPS DES, and the lab needs it for map
  data (DES-flagged GATs/RSWs). The private, never-committed rule covers MIXCRYPT only. Revisit
  this only before a public release (8980613 is in the history either way).

- **What:** `services/frontend/src/lib/gamefile/` (2026-10-06), the Settings page's game-file
  finder: the GRF 0x200 header/table layout, clientinfo.xml tags, PE section headers.
- **Sources:** the publicly described GRF layout (the same facts as `scripts/grf_des.py` above);
  Microsoft's PE/COFF specification. **No copyleft code was read for it.**
- **No inflate library:** it uses the browser's own `DecompressionStream("deflate")`, so there is
  nothing third-party to license-check or pin. Encrypted entries are never decrypted (no DES or
  MIXCRYPT code in the frontend).

## Ideas only (copyleft or unclear: no code read for porting)

| Source | Commit | License | Used for |
|---|---|---|---|
| [maxmx03/YggAI](https://github.com/maxmx03/YggAI) | — | GPL-3.0 | Phase 4: behavior trees as an executor option (ADR-0015). Never code. |
| [RagnarokResearchLab/ragnarokresearchlab.github.io](https://github.com/RagnarokResearchLab/ragnarokresearchlab.github.io) | `00ae60fbf53713081c36f77b35962dcf022c92e6` | none found at that commit (unclear) | file-format facts only; no text or code copied |
| rAthena (pinned in `services/rathena`) | the pinned ref | GPL-3.0 | the server we run. Its db is read at run time for the Phase 4 KB (ADR-0015), never committed. |

## ✅ Closed: the copyleft port made BEFORE this rule was REMOVED (2026-10-04)
- **What it was:** `packages/poring_dataset/src/poring_dataset/paths.py` (2a0404a, 2026-10-02), a
  *literal* port of rAthena's `src/map/path.cpp` A* (GPL-3.0) at the pinned ref. Under the
  2026-10-03 rule a copyleft source is "ideas only"; this file predated the rule.
- **Batt's decision (2026-10-04):** replace it with a clean implementation.
- **Done:** `packages/poring_dataset/src/poring_dataset/walk.py`, a textbook A* (Hart, Nilsson &
  Raphael 1968): octile heuristic, 10/14 costs, no corner cutting, deterministic ties, 128-step cap.
  `paths.py` and its import are deleted in the same commit; the property tests moved to `walk.py`.
  **Scope, stated plainly:** written without the GPL source open and copying none of its structure,
  but by an author who had read it, so NOT a strict clean-room implementation.
- **Evidence** (`scripts/walk_check.py --compare-port`, run against the old port before its
  deletion, on the 5 NAS datasets' packets):
  - 2540/2540 recorded walks found;
  - the cells equal the port's on 2534 (99.8 %), the same length on 2539;
  - every arrival on the exact cell (120/120);
  - the 10 walks cut mid-way: 6 on the exact cell, all ≤ 1 cell off.
- The port stays in git history only (2a0404a..the removal commit); nothing imports it.

## GPL-3.0 material in the repository (labelled 2026-11-07, ADR-0018's publication checklist)
The repository is public, so these are distributed under the GPL-3.0, like rAthena itself
(https://github.com/rathena/rathena, the ref pinned in `services/rathena`):

| File | What | Where |
|---|---|---|
| `services/rathena/patches/0001-thai-trim-chars.patch` | a 19-line change to rAthena's `TRIM_CHARS` (Thai names), the same as upstream PR #9990 | the tree; applied at image build |
| `packages/poring_dataset/src/poring_dataset/paths.py` | the literal port of rAthena's `src/map/path.cpp` A* (the closed section below) | git history only: 2a0404a .. d384d1e (2026-10-02 .. 10-04) |

## Runtime dependencies with licence obligations (2026-10-04, ADR-0018)
Batt's decision (2026-10-04): the lab trains and runs YOLO with ultralytics, which is AGPL-3.0. The
consequences are recorded in [ADR-0018](docs/adr/0018-component-licensing.md):
- `services/vision` is AGPL-3.0;
- everything that does not import ultralytics stays Apache-2.0.

| Dependency | Version / source | License | Where |
|---|---|---|---|
| [ultralytics](https://github.com/ultralytics/ultralytics) | 8.4.165, PyPI wheel `ultralytics-8.4.165-py3-none-any.whl`, sha256 `1eab69f73fdec8f23475510dde086aacfd3536c33c10980a57d75a644eb4ab1e` (`uv.lock`) | AGPL-3.0 (PyPI metadata) | `services/vision` only |
| ultralytics-thop | 2.2.1 (a dependency of ultralytics) | AGPL-3.0 (PyPI metadata) | `services/vision` only |
| ultralytics-platform | 0.1.70 (a dependency of ultralytics) | AGPL-3.0-only (PyPI `license_expression`) | `services/vision` only |
| [torch](https://github.com/pytorch/pytorch) / torchvision | 2.14.0+cu130 / 0.29.0+cu130 (`pytorch-cu130` index) | Apache-2.0 AND BSD-2/3-Clause AND MIT AND BSL-1.0 (PyPI `license_expression`) | `services/vision` only |

**Pretrained weights** (a download, never committed: `.gitignore` refuses `*.pt` and `data/`):

| File | Source | Size / sha256 | License | Stored |
|---|---|---|---|---|
| `yolo11n.pt` | [ultralytics/assets release v8.3.0](https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt) (downloaded 2026-10-04 on the host; vision has no internet) | 5,613,764 B, sha256 `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1` | AGPL-3.0 (the `ultralytics/assets` repository licence) | `data/weights/` → `/data/weights` in vision |

Models trained from these weights or with ultralytics are treated as AGPL-3.0, following
Ultralytics' stated terms (ADR-0018). They live in `data/` and are never committed.

**A local model used by HOST scripts only** (Batt 2026-10-07: qwen3-vl as a label-QA FLAGGER, never
ground truth; phase3-plan §6 LABEL-QA):

| Model | Source / version | License | Where |
|---|---|---|---|
| `qwen3-vl:4b` | Ollama library tag, digest `1343d82ebee38e26a4dd6b0180b915eb91550184e67c505dea97509571c8f683` (3,295,636,135 B, gguf Q4_K_M, 4.4 B params, family `qwen3vl`, capabilities completion / vision / tools / thinking), pulled 2026-09-18 by the infra side; served by Ollama 0.34.2 | Apache-2.0: the licence text in the Ollama manifest (`/api/show`), the Ollama library page, and the upstream model cards. The tag reports a `thinking` capability, and the library page does not say which variant it is built from; both [Qwen/Qwen3-VL-4B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct) and [Qwen/Qwen3-VL-4B-Thinking](https://huggingface.co/Qwen/Qwen3-VL-4B-Thinking) are `apache-2.0`. Checked 2026-10-07 | the infra side's `ollama` container, `127.0.0.1:11434`. ONLY host scripts call it; no poring-lab container joins Ollama's network (ADR-0005 isolation). R1-R3 apply (`scripts/frigate_r3.py`) |

**Test data** (approved by Batt 2026-10-04, not downloaded yet):
- The public Roboflow Ragnarok Online set, CC BY 4.0.
- It is used **test-only** (out of distribution, never trained on).
- The exact URL, version and the attribution line required by CC BY 4.0 are recorded here when it
  is downloaded, under `data/` and never committed.

## Frontend dependencies of the MW2 flow editor (Batt approved, 2026-10-08)
The `/flows` page ([mw2-block-editor.md](docs/planning/mw2-block-editor.md) section 6): pinned EXACT
in `services/frontend/package.json`, installed into tmpfs only, never on the host disk. Each LICENSE
was read from the installed package at that exact version (`node_modules/<pkg>/LICENSE`, the files
pnpm extracted from the registry tarball), 2026-10-08.

| Package | Version | License | Where used | Licence file read |
|---|---|---|---|---|
| [blockly](https://github.com/RaspberryPiFoundation/blockly) | 13.3.0 (registry tarball `blockly-13.3.0.tgz`, `latest` on 2026-10-08) | Apache-2.0: the full Apache License 2.0 text plus its appendix, 202 lines | the block editor (`src/components/flows/BlockEditor.tsx`), lazy-loaded on `/flows` only | `node_modules/blockly/LICENSE`, sha256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` |
| [@xyflow/react](https://github.com/xyflow/xyflow) | 12.12.0 (`latest` on 2026-10-08) | MIT, © 2019-2025 webkid GmbH | the workflow canvas (`src/components/flows/FlowCanvas.tsx`), lazy-loaded on `/flows` only | `node_modules/@xyflow/react/LICENSE`, sha256 `023119ac20fb1c8c9930abe0bcd196989a1960388529a96fc43cebf96f07c9ff` |

Their transitive packages (the `license` field and the LICENSE file present in each installed
package; all permissive):

| Package | Version | License |
|---|---|---|
| @xyflow/system | 0.0.83 | MIT |
| zustand | 4.5.7 | MIT |
| classcat | 5.0.5 | MIT (`LICENSE.md`) |
| use-sync-external-store | 1.7.0 | MIT |
| d3-drag, d3-zoom, d3-selection, d3-interpolate, d3-transition, d3-dispatch, d3-color, d3-timer | 3.0.0, 3.0.0, 3.0.0, 3.0.1, 3.0.1, 3.0.1, 3.1.0, 3.0.1 | ISC |
| d3-ease | 3.0.1 | BSD-3-Clause (the plan expected ISC: a correction, still permissive) |
| @types/d3-color, -drag, -interpolate, -selection, -transition, -zoom | 3.1.3, 3.0.7, 3.0.4, 3.0.12, 3.0.9, 3.0.9 | MIT (type declarations only) |

- **Blockly's peer `jsdom` is NOT installed:** it serves Blockly's headless Node use only, and the
  package's own `browser` field maps it to `false`. pnpm 10 auto-installs peers even under
  `peerDependencyRules.ignoreMissing`, so `pnpm-workspace.yaml` removes it with the override
  `blockly>jsdom: "-"` (the lockfile has no jsdom).
- **No `eval`, no `new Function`:** neither appears in `blockly_compressed.js`,
  `blocks_compressed.js`, `blockly.mjs`, `msg/en.mjs` or `@xyflow/react` / `@xyflow/system` /
  `zustand` (checked 2026-10-08). The CSP is unchanged.
- **Blockly's media are SELF-HOSTED:** the images and cursors of `node_modules/blockly/media/`
  (Apache-2.0, same licence file) are copied into `services/frontend/public/blockly-media/`; its
  sounds (`*.mp3`) are not copied and sounds are off. No outside request.

**Ideas only (no code, no assets, no text):**

| Source | License | Used for |
|---|---|---|
| Node-RED | Apache-2.0 (as stated by the project; its code was not opened) | status badges under nodes, typed output ports |
| n8n | Sustainable Use License: NOT OSI open source (its code was not opened, never read) | per-node run data after a run, "run a single node" |
| MakeCode | — | the block look comes from Blockly's own `zelos` renderer, nothing from MakeCode |

## Noted for later (not used yet)
- ~~**RagLite ACT/SPR decoding** (same commit and license as above) is a path to synthetic training
  data: sprites with exact labels (s2-plan / Phase 3). Its license would be re-read at the commit
  actually used.~~ ➡️ Superseded 2026-10-04: the SPR/ACT parsers were ported from nostalro-client
  instead (see "The sprite formats" above); RagLite's ACT/SPR code was not read.

## Never opened
- Cheat or memory-patching repositories (e.g. ragnarok-maya-purple).
