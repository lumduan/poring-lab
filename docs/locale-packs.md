---
doc_type: design
hypothesis: null
status: ACCUMULATING
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Run end to end once the NAS locale-packs mount exists (docs/operations/nas-sink.md) -- build th + en, install th, the ADR-0012 acceptance test; then fix any step this guide got wrong.
---

# Build your own locale pack

[ADR-0012](adr/0012-locale-agnostic-ui.md): the bot thinks in **keys**; a **locale pack** turns
keys into one language's text. This guide covers building a pack from **your own** client copy.

> 🔴 **The repo ships the builder and the schema only, never a pack.** A pack is derived from
> client assets. Nothing it contains, and nothing derived from it, is ever committed or published:
> extracted files, strings, aligned tables, coverage lists with text. The guard below enforces it;
> enable it before you start.

## 0. Enable the guard (once per clone)

    git config core.hooksPath .githooks

- **The pre-commit hook refuses:**
  - staged paths under `locale-packs/`, `locales/`, `*.localepack/` and `/thai*/`;
  - any directory holding a `locale-pack.json`;
  - any staged file containing a string whose sha256 is in `~/.cache/poring-lab/pack-fingerprints.txt`.
    The builder appends there: every pack string of at least 6 characters.
- **The same rules run as a test** (`pytest`), so CI catches a hook that was never enabled.

## 1. What you supply

| Input | Where it comes from | Where it goes |
|---|---|---|
| Your client's data copy (GRF + loose `data/`, **no exe**) | your own install | the NAS dataset `thai-client-data`, written once through a **temporary** Dell-only SMB share (`poring-thai-drop`, deleted after the copy; [nas-sink.md](operations/nas-sink.md) §5), then `readonly=on`, mounted **read-only** on the VM at `/mnt/poring-thai-src` |
| The kRO reference table (Korean msgstringtable of the reference exe) | the WARP extract in `C:\RO-rAthena\_scratch\` (lab) | the same temporary share, `kro-reference\` |
| The English table the lab runs | ROenglishRE commit `8e6a3c85` | fetched by the builder for `en` |

- **Never stage a large source on the VM's local disk**: the disk is shared with live capture. Read
  it from the read-only mount; small extracted files go to `/dev/shm`.
- **Never load or execute** anything from the copy (DLLs, exes, scripts). It is data, read
  offline.

## 2. Look inside the GRF (read-only)

    uv run python scripts/grf_read.py info    /mnt/poring-thai-src/<name>/<file>.grf
    uv run python scripts/grf_read.py ls      /mnt/poring-thai-src/<name>/<file>.grf [--grep PATTERN]
    uv run python scripts/grf_read.py extract /mnt/poring-thai-src/<name>/<file>.grf PATH --out /dev/shm/...

- **`info`:** the version (0x200 / 0x300), entry count, and whether any entry uses the DES /
  mixed-crypt flags.
- **`ls`:** the file table, decoded with the right code page.
- **`extract`:** one entry at a time, into `/dev/shm` only.
- **Encrypted beyond the standard flags?** Stop. The fallback is screenshots (ADR-0012).
- **Identify the client build** from its own files (`System/`, the patch client's info,
  `clientinfo`), never by running it.

## 3. Find the text sources, by content

- **The text sources to find:**
  - the message table (`msgstringtable.txt`);
  - the message lubs (compiled Lua, decompiled with unluac: a pinned jar in `/dev/shm`);
  - the item, skill and monster tables;
  - any textures that bear text.
- **Find them by decoding content** (e.g. TIS-620 / CP874 for Thai), not by trusting file names.

## 4. Keys, then the pack

    uv run python scripts/locale_pack.py keys  --kro /mnt/poring-thai-src/kro-reference/<table> --out /dev/shm/locale/keys.json
    uv run python scripts/locale_pack.py build --lang th --source /mnt/poring-thai-src/<name> --keys /dev/shm/locale/keys.json --out /mnt/poring-locale-packs/th
    uv run python scripts/locale_pack.py check /mnt/poring-locale-packs/th

- **`keys`:** one canonical key per Korean source line. The key is `msg.k` + the first 8 hex of
  sha1 of the line: decoded from CP949, the trailing `#` and surrounding whitespace stripped, NFC.
  - Duplicated lines share a key.
  - A collision of two different strings on one key stops the build.
- **`build`:** aligns the language's table to the keys.
  - (a) Its own client build's English table, matched text-equal to ours.
  - (b) A same-index fallback, checked by `%`-placeholder signatures and tagged with a confidence.
  - The output is the pack, plus fingerprints appended to the guard's list.
- **`check`:** validates the schema and prints coverage (counts and key ids only, no text):
  - how many of the 3,970 keys resolved;
  - by which method;
  - the gaps.
- **`en`** is built the same way from ROenglishRE `8e6a3c85`.

## 5. Pack schema (`<lang>/`)

| File | Content |
|---|---|
| `locale-pack.json` | `schema` (int), `language` (BCP-47, e.g. `th`), `client_version` (build id), `source` (a description, never a path to publish), `coverage` (`resolved`, `by_method`, `total`), `font` (face + size used by the client) |
| `msg.json` | `messages`: key → text; `lines`: key → [line indices] for this client version |
| `items.json`, `skills.json`, `mobs.json` | ID → name (only the tables the pack has) |
| `install/` | the client files this pack replaces: the message table, the message lubs, textures |

Validation rules:
- every key matches `msg\.k[0-9a-f]{8}`;
- every line index is within the table;
- coverage adds up;
- no file outside the listed set.

## 6. Install a pack into the client (lab, Windows)

- **The route:** the VM writes the pack to the NAS (`/mnt/poring-locale-packs/<lang>`). Windows
  reads it from the **read-only** share `\\192.168.1.6\poring-locale-packs\<lang>`.
- **The steps:**
  1. Back up the files to be replaced into `C:\RO-rAthena\_backup\<date>-locale-<lang>\`.
  2. Copy `install\` over the client with a hash read-back.
  3. Relaunch the client.
- **Client settings already in place:** langtype 5, ACP 874, Tahoma.
- **After an install:**
  - frames of the login, Basic Info, a menu and an NPC dialog;
  - Thai chat must stay byte-exact: check `chatlog` `HEX(message)` decoded as cp874.
- **The community-server client is never touched** (ADR-0006).

## 7. C6: auto-labelling OCR crops with the anchor map

ADR-0012 §3 + §8. For every frame the recorder keeps, with the active pack known:

1. `UiAnchors.locate(frame)` finds the visible windows. Locale-invariant masks find them in any
   language.
2. `UiAnchors.labelled_boxes(origins)` returns, for each visible element with a `label_key`, its
   **box in client pixels** and its **key**.
3. The pack's `msg.json` turns the key into the **exact text** that crop shows in this pack's
   language: OCR ground truth with no hand labelling.
4. Crops and their texts are dataset content (ADR-0010). They go to the gitignored data / NAS
   dataset, **never the repo**.

Elements without a fixed box (icons), or without a `label_key`, produce no OCR label. Server text
(NPC dialogs) is labelled from the script source and packets instead (ADR-0012 §6).

## 8. Make the anchor templates locale-invariant

With the same window visible in two packs (and over two scenes):

    uv run python scripts/ui_anchors_tool.py capture --png en_scene1.png \
        --mask-png en_scene2.png --mask-png th_scene1.png

Only pixels that agree in every variant stay in the mask, so title text drops out and one
template matches every language. Check with `ui_anchors_tool.py check` on a frame from each pack.

## 9. Acceptance (ADR-0012 §8)

- **Switch en ↔ th** (client relaunch each time).
- **The same keys resolve in both** for:
  - the login dialog;
  - Basic Info;
  - the chat window;
  - OK / Cancel;
  - one NPC dialog.
- **"open Basic Info, read HP, close it"** succeeds in both, with no code change.
- **Report per element.**
