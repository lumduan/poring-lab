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
| The reference table: the table the LAB client's exe embeds (3,970 lines: the KOREAN original, cp949; corrected 2026-10-03 after the extract) | extracted **offline** from the exe's bytes by `scripts/msgtable_extract.py` (the exe is never run; WARP only as a cross-check if the parse is ambiguous). The exe itself is kept on the NAS dataset `poring-lab/kro-reference` (readonly, no share) | `/dev/shm` (derived text, never the repo) |
| The source client's own embedded table (e.g. the Thai client's exe) | the same offline extract of THAT exe | `--source-ref`: lines the two id spaces up by equal text. ➡️ 2026-10-03: **not possible for the Thai `Ragexe.exe`**: it is packed by a commercial protector (sections `.vm_sec`, `.winlice`, `.boot`, blank names; no `msgStringTable.txt` string), so its data is encrypted until run. Not unpacked, not run |
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

*(Rewritten 2026-10-03 to match the code: the earlier `--kro` / `--keys` flags never existed.)*

    python3 scripts/msgtable_extract.py <lab exe> --out /dev/shm/locale/lab-ref.txt
    python3 scripts/msgtable_extract.py <thai exe> --out /dev/shm/locale/th-ref.txt
    uv run python scripts/locale_pack.py keys --source /dev/shm/locale/lab-ref.txt --out /dev/shm/locale/keys.json
    uv run python scripts/locale_pack.py build --lang th --source <thai msgstringtable> \
        --source-ref /dev/shm/locale/th-ref.txt --reference /dev/shm/locale/lab-ref.txt \
        --en <ROenglishRE msgstringtable> --reindex --out /mnt/poring-locale-packs/th
    uv run python scripts/locale_pack.py check /mnt/poring-locale-packs/th

- **`msgtable_extract.py`:** parses the PE and finds the longest run of `(index, string pointer)`
  records with index 0, 1, 2, … (the layout WARP's ExtractMsgStrings walks). It refuses to guess:
  no `msgStringTable.txt` string, no run of at least 500 records, or a second run longer than half
  the first -> exit 3 and a report. Output: WARP's format, original bytes, `\r`/`\n` escaped.
  It prints counts and offsets only.
- **`keys`:** one canonical key per reference line. The key is `msg.k` + the first 8 hex of sha1
  of the line: CRLF/CR -> LF, ONE trailing `#` removed, NFC. **Nothing else** (spaces are part of
  the message; the earlier text here said whitespace was stripped, which the code never did).
  - Duplicated lines share a key.
  - A collision of two different strings on one key stops the build.
- **`build`:** aligns the language's table to the reference ids, per message:
  - (a) `exact_ref`: the source client's own embedded table (`--source-ref`) has the SAME text as
    the reference at source id i -> the source text at i;
  - (b) `exact_en`: the source build's English table (`--source-en`), text-equal to ours;
  - (c) `index_signature`: the same id, only when neither table contradicts it and the
    `%`-placeholder signatures match.
  - It prints the coverage (counts only, never text) and appends fingerprints to the guard's list.
  - `--reindex` writes `install/data/msgstringtable.txt` in the REFERENCE's id order (the lab's
    3,970 lines): the aligned text where one was found, else our English line, in the source
    encoding. Without it the source table is copied unchanged, which only fits a client with the
    source's own ids.
- **`check`:** validates the schema and the file hashes (it does not print coverage; `build`
  does).
- `--source-untranslated TEXT` (repeatable): a source line that is only TEXT counts as empty, so
  our English stays at that id. The Thai table writes `no msg` for untranslated ids.

**As run for `th`, 2026-10-03 (C4).** The Thai exe could not be parsed (packed), so there is no
`--source-ref`. The ids were checked instead: the Thai table translates the English line at the
SAME id across 0–3969 (decoded spot-checks, including ids 2500–2511 and 3603 where placeholder
agreement is lowest, because of `no msg` and reworded placeholders), and ROenglishRE's 2021 and
2023 tables keep the same ids (append-only). So `index_signature` (same id + equal `%`
conversions) is the method:

    locale_pack.py keys --source lab-ref.txt --version kro-20211103 --out keys.json   # 3,785 keys
    locale_pack.py build --lang th --source <thai msgstringtable.txt> --reference lab-ref.txt \
        --reference-version kro-20211103 --en <ROenglishRE 8e6a3c85> --source-untranslated "no msg" \
        --reindex --client-version th-ro_thai-4733 --font Tahoma --out /mnt/poring-locale-packs/th

- Coverage: 3,055 of 3,785 keys (80.7 %), all `index_signature` (3,179 ids); 786 unmatched; 56
  conflicts (one Korean text translated two ways; the first kept); 1,495 `no msg` lines dropped.
- The reindexed install table: 3,970 lines = 3,223 Thai + 742 English fallback + 5 empty; 7
  English lines (ids 3597–3602, 3647, already garbled in ROenglishRE) lost characters cp874 lacks.
- Printf safety, checked separately: every Thai line has the Korean original's `%` conversions in
  order; 5 differ only in width/precision (`%.1f`→`%.3f`, `%d`→`%02d`), which take the same
  arguments. `check`: valid.

## 5. Pack schema (`<lang>/`)

| File | Content |
|---|---|
*(Rewritten 2026-10-03 to match `locale_pack.py` schema 1.)*

| File | Content |
|---|---|
| `locale-pack.json` | `schema` (1), `kind`, `language`, `client_version`, `reference_version`, `source` (a description, never a path to publish), `font`, `encoding`, `key_rule`, `built_at`, `builder`, `coverage` (`reference_lines`, `reference_keys`, `covered_keys`, `covered_share`, `exact_ref`, `exact_en`, `index_signature`, `unmatched`, `ambiguous`, `conflicts`, `source_lines`, `source_ref_lines`, `reindexed`), `tables`, `files` (sha256 of every file) |
| `msg.json` | `schema`, `lang`, `messages`: key → {`text`, `confidence`, `source_ids`}; `index`: version → {key: [ids]} for the reference and for this client version |
| `tables/NAME.json` | optional numeric id → text tables (`--table NAME=FILE.json`) |
| `install/` | files to place in the client: `data/msgstringtable.txt` (reindexed, or the source's unchanged), plus `--install` |

Validation rules (`check`):
- the manifest fields and types above, `schema == 1`, `msg.json` `lang` == `language`;
- every key matches `msg\.k[0-9a-f]{8}`, every confidence is one of the three methods;
- `index` maps version -> {key: [ids]};
- every listed file exists with its sha256;
- `coverage.covered_keys` == the number of messages.

## 6. Install a pack into the client (lab, Windows)

- **The route:** the VM writes the pack to the NAS (`/mnt/poring-locale-packs/<lang>`). Windows
  reads it through a **temporary guest SMB share** (Batt, 2026-10-03, for the install only):
  read-only, `hostsallow` the Dell (192.168.1.169) only, not browsable, scoped to
  `locale-packs/<lang>`. Created right before the install and deleted right after, both read back
  ([nas-sink.md](operations/nas-sink.md)), with Frigate checked before and after.
  - ➡️ **2026-10-03 15:40–15:44: WINDOWS REFUSES IT.** Share id 20 (`poring-locale-th`) was
    created as approved; from the Dell, `[IO.Directory]::GetFiles(...)` failed with "You can't
    access this shared folder because your organization's security policies block
    unauthenticated guest access" (error 1272; Windows 11 24H2+ blocks insecure guest logons and
    requires SMB signing by default). The share was deleted at once (read back: none left; no
    sessions; NAS permissions never changed; Frigate unchanged). **The install route is Batt's
    decision** (an authenticated read-only share as in nas-sink.md §5, or a one-off through
    `\\tsclient\transfer`); weakening Windows' SMB policy is not proposed.
    ➡️ **Batt chose the one-off through `\\tsclient\transfer`; C5 DONE 2026-10-03 15:46–16:07.**

**C5 as run (2026-10-03).**
- Backup `C:\RO-rAthena\_backup\20261003-locale-th\msgstringtable.txt` = sha256 `EDE8A073…E59F5C5`
  (the live ROenglishRE table); installed `A640B2E7…ACFF2B0`, 126,968 B = the manifest. The file
  went through `/transfer` once and was deleted (ADR-0004 "Exceptions log").
- **Thai, in frames** (the frames stay in `/dev/shm`; pack text is never quoted here): the
  service-select title, the Basic Info title, the chat's system lines, the game-option menu's title. Unchanged (not in
  msgstringtable): the login dialog's labels, the chat TABS (`msgstring_kr.lub`, still the English
  one), HP/SP/Lv/Weight labels, the menu's buttons (Korean images).
- **ro_agent under Thai:** `service_select` needed a locale variant (`service_select@th`, the
  English signature kept); `login` and `char_select` matched as they are. The ENG tray template
  had drifted (8.3–11.0 vs 6.0, a half-pixel re-render, unrelated to the pack) and was
  recalibrated while the tray visibly said ENG (the old one kept as `.bak`).
- **Acceptance on the registered windows (ADR-0011 anchors), th then en:**

      element                      th                          en
      basic_info located           0.39 accepted               0.39 accepted
      hp_bar / sp_bar / hp_sp_text resolved (102,57)…          resolved, the same pixels
      hotbar + 9 slots             1.00 accepted, 9/9          0.81 accepted, 9/9
      chat                         12.79 NOT accepted          12.78 NOT accepted
      open/close Basic Info (Alt+V) start, closed, opened, closed, restored: all true in both
      HP read (bar pixels)         93.3 % blue columns = full; DB 40/40 in both
      Thai chat -> chatlog HEX     B7B4CACDBA20E4B7C2 (row 8)  B7B4CACDBA20E4B7C2 (row 9)

  - `basic_info` failed in Thai (39.76) until its stable mask took the Thai frame as a variant
    (`ui_anchors_tool.py variant`, add-only: the template is kept and the mask only shrinks;
    0.982 -> 0.816 stable). `chat` fails in BOTH languages: its mask is 17 % text edges, and the
    tab row now renders ~half a pixel differently (12.78 vs a 12.0 limit). That is a stale template,
    not the pack: re-cut it (`capture --windows chat` over 2+ scenes, then `variant` with a Thai
    frame). `game_option` (not in the acceptance list) is English-only and opened elsewhere.
- **End state: English restored** (`EDE8A073…`), the client relaunched, the GM in game.
- **Follow-ups (recorded, not done):** login / OK-Cancel / NPC-dialog anchors; the chat template
  re-cut; the `game_option` locale variant; a Thai `msgstring_kr.lub` for the chat tabs.
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
