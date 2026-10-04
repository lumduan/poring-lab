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
    (`scripts/camera_validate.py`, recorded in `camera_<backend>.json` "indoor");
  - the sprite direction a billboard shows = `(camera_dir + 12 − heading) % 8`, with `camera_dir`
    the camera's look direction as an RO heading.
- The table itself is CLIENT data: extracted from the GRF into `/dev/shm` at run time, never
  committed.

| Source | Commit | License | File read |
|---|---|---|---|
| [nmeylan/nostalro-client](https://github.com/nmeylan/nostalro-client) | `15b3029059c04cf1d54d734f7233e5db3c108a9c` | Apache-2.0 (`LICENSE.md`) | `lib/renderer/src/map_loader.rs` (L85-90), `lib/renderer/src/camera.rs` (L189-209), `lib/renderer/src/act.rs` (L568-570) |

### The GAT file layout
- **Ported to:** `packages/poring_dataset/src/poring_dataset/gat.py`.
- **What:** the layout (header, 20-byte tiles with four corner altitudes and a terrain type),
  re-expressed with a numpy dtype. The terrain types follow rAthena's map cache, which our parser is
  cross-checked against (2026-10-03: prt_church 100 %, prt_fild08 99.999 % of cells equal).

| Source | Commit | License | File read |
|---|---|---|---|
| [RagnarokResearchLab/RagLite](https://github.com/RagnarokResearchLab/RagLite) | `d1ce2b1e2136c46b1409d5c6701f64d7c3cddaf9` | Unlicense **or** Apache-2.0; used under Apache-2.0 (`LICENSE`) | `Core/FileFormats/RagnarokGAT.lua` |

## Our own code from public standards
- **What:** `scripts/grf_des.py`, the GRF archive's header-only "DES" (flag 0x04).
- **Sources:** the DES tables are FIPS PUB 46-3. The GRF construction is the publicly described one:
  the first 20 blocks pass through IP, one zero-key round and FP.
- **No copyleft code was read for it.** rAthena's GPL implementation was deliberately not used.
- **Verified:** the classic DES test vector, and a real DES-flagged GAT that inflates with zlib to
  its exact size.

## Ideas only (copyleft or unclear: no code read for porting)

| Source | Commit | License | Used for |
|---|---|---|---|
| [maxmx03/YggAI](https://github.com/maxmx03/YggAI) | — | GPL-3.0 | Phase 4: behavior trees as an executor option (ADR-0015). Never code. |
| [RagnarokResearchLab/ragnarokresearchlab.github.io](https://github.com/RagnarokResearchLab/ragnarokresearchlab.github.io) | `00ae60fbf53713081c36f77b35962dcf022c92e6` | none found at that commit (unclear) | file-format facts only; no text or code copied |
| rAthena (pinned in `services/rathena`) | the pinned ref | GPL-3.0 | the server we run. Its db is read at run time for the Phase 4 KB (ADR-0015), never committed. |

## ⚠️ Open: a copyleft port made BEFORE this rule
- **What:** `packages/poring_dataset/src/poring_dataset/paths.py` (2a0404a, 2026-10-02) is a
  *literal* port of rAthena's `src/map/path.cpp` A* (GPL-3.0) at the pinned ref. That is
  deliberate: the client and the server walk exactly these cells, so tie-breaking must match.
- **Why it is open:** under the 2026-10-03 rule a copyleft source is "ideas only". This file
  predates the rule.
- **Batt decides one of:**
  - keep it (the repository is private, so GPL obligations apply only on distribution; record the
    exception here);
  - re-implement it clean-room from the documented behaviour, keeping the equivalence tests.

## Noted for later (not used yet)
- **RagLite ACT/SPR decoding** (same commit and license as above) is a path to synthetic training
  data: sprites with exact labels (s2-plan / Phase 3). Its license would be re-read at the commit
  actually used.

## Never opened
- Cheat or memory-patching repositories (e.g. ragnarok-maya-purple).
