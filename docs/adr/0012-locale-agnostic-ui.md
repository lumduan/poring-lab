---
doc_type: decision
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Code half landed 2026-10-02 (anchor map stores keys + label_key, N-way locale-invariant masks). Blocked on Batt's NAS recipe (docs/operations/nas-sink.md -- mounts not present) and the Thai copy plus kRO reference in the drop share; then build the th/en packs, install th, run the en<->th acceptance test, ACCEPT.
---

# ADR-0012: Locale-agnostic UI -- the bot thinks in keys, text lives in locale packs

- **Status:** PROPOSED (2026-10-02). Batt's amendment to the Thai-UI task: "the bot thinks in
  KEYS, never in one language's strings".
- **Code:**
  - `packages/poring_env/src/poring_env/ui_anchors.py`: canonical names, `label_key`,
    `labelled_boxes`, N-way `stable_masks`;
  - `scripts/locale_pack.py` and `scripts/grf_read.py`: the pack builder and the read-only GRF
    reader (offline tools);
  - the never-commit guard (`.gitignore`, `.githooks/pre-commit`, its test).
- **Guide:** [docs/locale-packs.md](../locale-packs.md), "build your own locale pack".
- **Related:**
  - [ADR-0011](0011-ui-anchor-map.md): the anchor map; this ADR makes it store keys;
  - [ADR-0006](0006-sanctioned-test-environments.md): the Thai data is a detached copy, never a
    real client;
  - [ADR-0010](0010-dataset-format.md): OCR auto-labels land in the dataset;
  - [docs/phase2-plan.md](../phase2-plan.md) Part D: resolution independence, the same goal.

## Context

- **The project's featured language is Thai.** Thai OCR is its own contribution. But a bot that
  matches Thai strings is a bot for one client build in one language. The next language, or the
  next client version, would mean re-teaching it.
- **The lab's client shows English UI text today.** It uses ROenglishRE's msgstringtable, commit
  `8e6a3c85`: 3,970 lines. Batt supplied a detached Thai client data copy (no exe) to make the UI
  Thai.
- **The hard rule from Batt:** nothing from that copy, nor anything derived from its content, is
  ever committed or published: extracted files, Thai strings, aligned tables.
- **The same problem twice.** Resolution was handled the same way: the policy never holds a pixel
  (ADR-0011). Language is the second half of that rule. **Screen-size agnostic and
  language-agnostic are the same goal:** the policy never depends on presentation.

## Decision (proposed)

### 1. Three layers

| Layer | Holds | Never holds |
|---|---|---|
| **Policy** | intents on keys: `open(window.basic_info)`, `read(ui.hp_sp_text)`, `click(ui.ok)` | pixels, text |
| **Semantic layer = anchor map** (ADR-0011) | canonical keys + geometry (window-relative boxes) + structure templates (locale-invariant masks) | text |
| **Locale pack** (one per language, outside the repo) | key → text, per-version key → line maps, ID tables, install files, font | geometry, policy |

### 2. Canonical keys survive versions

- **Message keys.** `msg.k` + the first 8 hex of `sha1(normalised Korean source string)`.
  - Korean is the client's source language, so every localisation is a translation of the same
    line.
  - The source is the kRO table of the reference exe (the WARP extract, 3,970 lines).
  - Normalised: decoded from CP949, the trailing `#` separator and surrounding whitespace
    stripped, Unicode NFC.
- **Per-version key → line maps.** Line numbers drift between client builds; a key does not. Each
  pack carries `key → [line indices]` for the client version it was built from. Duplicated Korean
  lines share one key.
- **A collision of two different strings on one 8-hex key stops the builder.** Widening the key is
  a versioned schema change, never a silent fix.
- **IDs are already keys.** Items, skills and monsters are addressed as `item.<id>`, `skill.<id>`,
  `mob.<id>`. Their names come from the pack's ID tables.
- **Curated aliases in code.** A readable name (`ui.ok`, `ui.basic_info.close`) points at a message
  key and never holds text (`ui_anchors.ALIASES`, validated). It stays empty until the kRO
  reference is on the NAS. Committing the keys is allowed (Batt, 2026-10-02; see Open).

### 3. The anchor map stores keys (ADR-0011 amended)

- **Canonical names.** Window and element names are canonical identifiers (`[a-z][a-z0-9_]*`),
  validated: a name can never be a locale's text.
- **`label_key`.** An element whose meaning is a piece of UI text (a button caption, a field label)
  carries a `label_key`: a message key or an alias. Anything else is refused at construction
  ("the map stores keys, never text").
- **Locale-invariant templates.** `stable_masks` keeps only the pixels that agree in EVERY variant.
  The variants are other scenes (translucency drops out) **and other locales** (a title's text drops
  out). So one template finds the window in every language. `ui_anchors_tool.py capture --mask-png
  A --mask-png B` cuts it.

### 4. Locale packs live outside the repo

- **Where:**
  - the NAS dataset `tank-main/poring-lab/locale-packs/<lang>/` (VM: `/mnt/poring-locale-packs`;
    Windows: the read-only SMB share `poring-locale-packs`);
  - a working cache in `/dev/shm`.
- **The repo ships only the builder and the schema**, never pack contents.
- **Built by a script from the operator's own data:** `scripts/locale_pack.py build --lang th
  --source <the Thai copy on the ro mount>`. `en` is built from ROenglishRE `8e6a3c85`.
- **Alignment of a non-Korean table to keys:**
  - (a) the English table of the same client build, text-equal to ours;
  - (b) a same-index fallback, checked by `%`-placeholder signatures and tagged with a confidence.
  - The coverage of the 3,970 keys is reported, with the gaps.
- **Format** (details in the guide):
  - `locale-pack.json`: language, client version, source description, coverage, font;
  - `msg.json`: key → text, plus the per-version key → line map;
  - ID tables (items/skills/monsters by ID);
  - `install/`: the client files the pack replaces (msgstringtable, msgstring lubs, textures).

### 5. Recognition, built in this order

1. **Icon / layout.** Structure templates and fixed boxes (ADR-0011) need no text at all. Most
   decisions stop here.
2. **OCR + reverse lookup.** Read the crop, look the string up in the active pack's text → key
   table, act on the key.
3. **Render-and-match (prototype).** Render the pack's string in the pack's font, match pixels. For
   strings OCR reads badly.

### 6. Text by type

| Text | How the bot gets it |
|---|---|
| Client UI (buttons, labels, system messages) | keyed: msgstringtable / msgstring lubs → message keys |
| Items, skills, monsters | IDs → the pack's ID tables |
| Server text (NPC dialogs, announcements) | on our rAthena: the script source and the packets (offline ground truth only, ADR-0007) |
| Chat | not keyed: the slow-loop LLM, pseudonymised and local (ADR-0006) |
| Strings hard-coded in the exe; text baked into textures | layout (§5.1) and per-locale templates |

### 7. The never-commit guard

- **`.gitignore`** covers `locale-packs/`, `locales/`, `*.localepack/` and `/thai*/`.
- **A pre-commit hook** (`.githooks/pre-commit`, enabled by `git config core.hooksPath .githooks`)
  and a test refuse:
  - any tracked or staged path under those patterns, and any directory holding a
    `locale-pack.json`;
  - any staged file containing a string from the local fingerprint list,
    `~/.cache/poring-lab/pack-fingerprints.txt`: the sha256 of every pack string of at least 6
    characters, written by the builder, outside the repo.
- **Thai already in tests and docs stays allowed.** The guard checks against pack fingerprints, not
  against a script range.

### 8. The acceptance test (ACCEPT gate)

- **Switch packs en ↔ th**, relaunching the client each time.
- **The SAME keys must resolve in both** for:
  - the login dialog;
  - Basic Info;
  - the chat window;
  - OK / Cancel;
  - one NPC dialog (Next / Close; our NPC).
- **One scripted action, in keys:** "open Basic Info, read HP, close it" must succeed in both packs,
  **with no code change**. It uses the verified hotkey and digit templates.
- **Results per element**, en and th side by side.

## Consequences

- **A new language is data, not code.** Run the builder on the operator's own client copy, cut
  masks with one more `--mask-png`, run the acceptance test.
- **OCR labels come for free** (the guide's C6 section). Each visible element's box plus
  `label_key`, through the active pack, gives the exact expected text of that crop. That is
  ground truth for the Thai OCR set without hand labelling.
- **The guard is part of the deliverable.** The packs are derived from client assets: one stray
  commit would publish them.
- **The policy's vocabulary grows by keys**, never by strings. A test can check a policy for string
  literals.

## Open (Batt to confirm)

- **May one-way 8-hex message key ids be committed in `ALIASES`?** They hold no text and cannot
  reconstruct it, but they are derived from the kRO reference, a client asset. Until Batt answers,
  aliases stay empty in the repo and can live in a local, gitignored alias file.
  ➡️ **DECIDED by Batt, 2026-10-02: ALLOWED.**
  - Canonical keys (`msg.k<8hex>`, `ui.*`) may be committed: keys only, never text.
  - The never-commit guard (`.gitignore` + `.githooks/pre-commit`, path rules and pack-string
    fingerprints) still blocks any pack text.
  - `ALIASES` is filled from the kRO reference once it is on the NAS.
- **Pack licensing for sharing outside the lab:** out of scope. Packs never leave the lab.

## Not decided here

- Which OCR engine (the Thai OCR track decides, with the C6 auto-labels as its data).
- The S2 capture path (ADR-0009). Keys are capture-agnostic by construction.
