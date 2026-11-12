---
doc_type: plan
hypothesis: null
status: BUILT (2026-11-12, branch feat/flows-save-load, not merged; the real-GitHub checks in "Built" 4 are open)
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [flows-studio.md, world-map-flows.md, ../adr/0023-learner-mode.md]
next_action: "Batt reviews and merges feat/flows-save-load; then the real-GitHub checks of 'Built' 4 (a Thai-named round trip, tree sha == contents sha, Windows / macOS clones, an iPhone download) on a throwaway public repository, and tell the matpilot session the result."
---

# /flows and /maps: Save, Download and Load -- on this computer and on GitHub

Written 2026-11-12 11:12 ICT from `date`. ➡️ **BUILT the same day** (section "Built", at the end):
both pages, on this computer and on GitHub; not merged, and the real-GitHub checks are open.

## Why (Batt, 2026-11-12, translated)

> "On the flows and maps pages, make a save and download system too. Ask matpilot how they do it
> and do it that way: save/load on the machine, and through GitHub too. In the future I may teach by
> having students load a flow and carry on from it -- faster than each building their own -- and it
> helps build a community that shares knowledge as code on GitHub."

## What exists today

➡️ This section is the state BEFORE 2026-11-12. Since then Save and Load are dialogs (section
"Built"); the bare IR download below still opens.

- Both pages edit ONE flow (the IR: name, handlers, procedures, variables, workflow ...; no world
  data). It is autosaved in this browser (`prefs.ts` KEYS.flow) and can be downloaded as
  `<name>.flow.json` and opened from a file (`importer.ts` importFlow / exportText).
- The sample world (KEYS.world) is separate and never goes into the file. It holds KB data
  derived from rAthena (GPL) and the client, so it must never go to GitHub (CLAUDE.md rule 4).

## The source: MatPilot (matpilot.org/blocks)

- Permalink base: https://github.com/lumduan/matpilot/blob/4022c870083c38c7ed4c62ff8361ef65a57d41f8/
- docs/adr/0011-save-load-github.md: the decision record and the GitHub facts it checked.
- The matpilot session's own account (2026-11-12, by cross-session message) is summarised below.
- MIT licence: port with attribution (THIRD_PARTY.md; read the LICENSE at that commit first).

## The design (MatPilot's, adapted)

1. **The file.** Pretty-printed JSON, `<name>.flow.json`:
   `{ format: "poring-lab-flow", version: 1, name, savedBy, savedAt (ISO), python: [lines], flow: <IR> }`.
   - `python` is the generated code as lines, so a diff reads well on GitHub. It is IGNORED on
     load: Python is always regenerated (never trust a derived field in a loaded file).
   - A bare IR file (today's download) still opens.
   - A newer `version` is refused: "saved by a newer poring-lab: pull the update".
   - Names: control characters, `/ \ : * ? " < > |` and leading dots are removed, and a name is
     capped at 60 characters. Thai letters and spaces stay.
2. **On this computer.**
   - Save downloads the file: a Blob, an `<a download>`, and the object URL revoked after 10 s.
   - Load is a file picker (accepts `.json`). The size is checked BEFORE the file is read
     (2 MB). Then strict structure checks.
   - The file then loads into a SCRATCH flow first: a broken file changes nothing. Loading is ONE
     Undo step ("Press Undo to go back").
   - Autosave stays as today (one working flow per browser).
   - Ctrl/⌘+S opens Save; Ctrl/⌘+O opens Load.
3. **On GitHub: the browser talks to api.github.com directly. No server, no OAuth** (OAuth needs a
   server: GitHub's device and token endpoints send no CORS headers).
   - Settings:
     - a repository (`owner/name`, a github.com link, or `git@github.com:...`);
     - a folder (default `poring-lab`);
     - "Your name" (it goes into the commit messages).
   - **Public repositories load WITHOUT a token.** This is the teaching path: the teacher shares a
     repository, and the students press Load.
   - Saving needs a FINE-GRAINED personal access token for one repository, with "Contents: Read
     and write".
     - A link opens GitHub's token page prefilled with the name, description, target_name,
       expires_in=366 and contents=write.
     - "Check and save" reads the repository with the new token before keeping it, and reports
       whether it can push.
   - **The token: OUR rule is stricter than MatPilot's default.**
     - It is held in memory / sessionStorage by default. It goes to localStorage only when a person
       ticks "Remember on this computer" (MatPilot's AI-key pattern).
     - "Forget the token" removes it.
     - It is sent only to `https://api.github.com`, in `Authorization: Bearer`, with
       `X-GitHub-Api-Version: 2022-11-28`.
   - Four calls: get the repository, list the folder, read a file, PUT a file. Every fetch uses
     `cache: "no-store"`, `credentials: "omit"` and `referrerPolicy: "no-referrer"` (GitHub's
     GETs are cached for 60 s).
   - Base64: TextEncoder, then btoa in 32 KB chunks (plain btoa throws on Thai). Decode with
     `TextDecoder("utf-8", {fatal: true})`.
   - **A save never silently replaces a classmate's work.**
     - The file is read first. It is written only if its sha is the one we opened or last saved.
     - Otherwise the person chooses: "Save mine as a new flow" (`<name> 2`), "Replace it", "See
       who changed it" (the github.com history), or Cancel.
     - A 409 (or a 422 mentioning sha) between the read and the write is handled the same way.
   - Commits: one file and one commit per save. The message is the note (or "Add/Update <name>"),
     then "(saved by <name>)", then "Saved from poring-lab."
   - Errors:
     - 401: a bad or expired token.
     - 403: a missing permission.
     - 429, or a 403 with `x-ratelimit-remaining: 0`: the rate limit, shown with
       `x-ratelimit-reset`.
   - The CSP gains exactly `connect-src https://api.github.com` (src/lib/csp.ts; csp.test.ts pins
     it). Nothing is sent to GitHub until a person opens GitHub settings, Save or Load.
   - Gotchas:
     - Fine-grained tokens do not work for an outside collaborator: a class uses a free
       organisation with each student a member.
     - GitHub accounts are for ages 13 and over, so a teacher or parent owns the tokens.
4. **Sharing (later, MatPilot has none):** a link `?repo=owner/name&path=folder/file.flow.json`.
   - It names the source repository and asks for a click before replacing anything.
   - It is undoable, never auto-runs, and the path shape is allow-listed.
5. **The UI** (both pages): Load (a folder icon), Save (a disk icon), Start over.
   - On phones only the icons show; the words stay for screen readers.
   - The Save dialog: "On this computer" (Download) and "On GitHub" (a note, Save, the conflict
     choices; "Set up GitHub..." without settings).
   - The Load dialog: "From this computer" (Choose a file...) and "From GitHub" (the folder link,
     Refresh, Change, the list with sizes).
6. **Lessons kept** (MatPilot):
   - strict structure checks, then a throwaway copy;
   - the size checked before reading;
   - derived fields regenerated;
   - no-store fetches;
   - the sha compare-and-swap;
   - UTF-8-safe Base64;
   - every path segment cleaned and encodeURIComponent'd, the owner and repository by regex;
   - github.com links only on a click, with rel=noreferrer;
   - downloads tested on a real iPhone (MatPilot has not verified iOS Safari).

## Two more lessons (the matpilot session's follow-up, 2026-11-12; neither tested at scale by them)

1. **A folder lists at most 1,000 files through the contents API.** GitHub's docs say it: "This API
   has an upper limit of 1,000 files for a directory ... use the Git Trees API".
   - MatPilot does not handle it: a bigger folder would quietly show only some files.
   - Ours lists with the Git Trees API: `GET /repos/{owner}/{repo}/git/trees/{branch}`, then the
     folder's sub-tree (limit 100,000 entries / 7 MB with `recursive`). ALWAYS check `truncated`
     and say so in the UI, never showing a partial list as complete.
   - The blob sha in a tree entry should equal the contents API's file sha, so the
     compare-before-save keeps working. Verify it with one real file.
   - The advice for classes: one folder per class (or per student), well under 1,000 files.
2. **Thai file names.**
   - Every path segment goes through `encodeURIComponent`, for API URLs and github.com links.
   - The content is UTF-8-safe Base64.
   - Names are normalised to **NFC** (Thai SARA AM, U+0E33, changes under NFKC, not under NFC).
   - Names are capped by **bytes** as well as by characters: 60 characters AND at most 180 UTF-8
     bytes. Thai is 3 bytes a character, and git and some file systems limit bytes.
   - **To check on real GitHub before relying on it** (MatPilot only has mocked tests):
     - save, list and reload a Thai-named file, and compare the name the API returns;
     - clone the repository on Windows and macOS and open the files.
     - Tell the matpilot session what we find; it records the result in its ADR 0011 too.

## Not in scope

- History, diffs and merging inside poring-lab (github.com shows them).
- Branches, deleting or renaming files on GitHub, signing in with GitHub (needs a server).
- Saving the sample world or anything client- / rAthena-derived.

## Built (2026-11-12, from 11:45 ICT by `date`; branch `feat/flows-save-load`)

### 1. What was built

- **The file** (`services/frontend/src/lib/flow/file.ts`): `serializeFlowFile` writes EXACTLY the
  seven fields above, the flow in canonical key order and the Python as lines; never the world.
  `parseFlowFile` checks the size (2,000,000 bytes) and the bracket depth before `JSON.parse`, then
  each field's type, then the IR through `importFlow` (which keeps the IR's own 1 MiB cap), into a
  scratch flow. `python` is never read. A bare IR file opens; a newer `version` gets "this flow was
  saved by a newer poring-lab: pull the update, then open it again".
- **Names** (`cleanFlowName`): NFC; control characters (C0, DEL, C1), `/ \ : * ? " < > |`, bidi
  overrides and isolates, and lone surrogates removed; spaces collapsed; leading dots removed; at
  most 60 characters AND 180 UTF-8 bytes, cut between graphemes (`Intl.Segmenter`), so a Thai letter
  keeps its marks. Thai and spaces stay.
- **On this computer:** Save downloads it (a Blob, `<a download>`, the object URL revoked after
  10 s). Load ▸ "Open a saved flow…" opens the Load dialog's file picker (`.json`). `File.size` is
  checked before the file is read. Autosave is unchanged.
- **Undo and the file meta:** loading is ONE undo step through the page's notice. The notice's undo
  also restores the FILE META: the name the flow was saved as, and the GitHub file (repository,
  path, sha) it came from. So Undo never leaves a classmate's GitHub file attached to your own flow
  (MatPilot ADR 0011 decision 2). The meta is kept in this browser beside the autosaved flow
  (`prefs.ts` KEYS.file, tagged with the IR name), shared by both pages.
- **Shortcuts:** Ctrl/⌘+S opens Save and Ctrl/⌘+O opens Load. They do nothing while typing in an
  input, textarea, select or contenteditable, while a dialog shows, or while the Zones layer is
  open. On a Thai layout the letter is taken from the key's place (`code`).
- **GitHub** (`services/frontend/src/lib/github/`):
  - `repository.ts` reads the repository by regex (`owner/name`, a link, `git@github.com:`) and
    checks the folder (default `poring-lab`). `safePath` refuses empty, `.` and `..` segments
    before any path reaches a URL, and every segment is `encodeURIComponent`'d.
  - `client.ts` sends every request to `https://api.github.com` only, with `cache: "no-store"`,
    `credentials: "omit"`, `referrerPolicy: "no-referrer"`, `X-GitHub-Api-Version: 2022-11-28` and
    the token only as `Authorization: Bearer`.
  - The folder is LISTED WITH THE GIT TREES API: `git/trees/{default branch}`, then each folder
    level's sub-tree. Any `truncated: true` answer shows a plain message and NO list. Symlinks,
    submodules and names with `/` or dot segments are dropped.
  - Files are read through the contents API. GitHub's `size` is checked before the content is read,
    then the Base64's length before it is decoded (TextDecoder fatal). An `encoding: "none"` file
    (1 to 2 MB) is re-read with `Accept: application/vnd.github.raw+json`.
  - Writes are one PUT a save. UTF-8-safe Base64: TextEncoder, then btoa in 32 KB chunks.
  - `flows.ts` holds the sha compare-and-swap: read first, write only when the sha is the one we
    opened or last saved, else a conflict. A 409, or a 422 about the sha, is a conflict too. It also
    makes the commit messages (the note, or "Add/Update <name>", then "(saved by <name>)", then
    "Saved from poring-lab.") and `<name> 2` within both name caps.
  - `settings.ts` is the TOKEN STORE. By default the token is kept in this tab (sessionStorage).
    It goes to localStorage only when "Remember on this computer" is ticked, and to memory when
    storage refuses it. "Forget the token" clears all three. Its shape is checked (visible ASCII,
    at most 255 characters).
  - Errors: 401 / 403 / 404 / 409 / 422 / 429. A 403 with `x-ratelimit-remaining: 0` is the rate
    limit, shown with the time from `x-ratelimit-reset`.
- **The dialogs** (`services/frontend/src/components/flowfile/`): `SaveDialog`, `LoadDialog` and
  `GitHubSettingsDialog`, MatPilot's, are shared by both pages through `FlowFileDialogs`. The
  GitHub settings dialog is opened from either and goes back to it when closed.
  - Save: "On this computer" (Download), and "On GitHub" (a note, Save, the conflict choices: Save
    mine as a new flow, Replace it, See who changed it, Cancel). Without settings it offers "Set up
    GitHub…".
  - Load: "From this computer" (Choose a file…), and "From GitHub" (the folder link, Refresh,
    Change, the list with sizes).
  - Settings: the repository, the folder, your name, the token (with the prefilled token-page link),
    "Remember on this computer" (OFF by default), "Check and save", and "Forget the token".
  - Every github.com link opens only on a click, with `rel="noreferrer"`. Everything renders as
    text: no `innerHTML`, which `gamefile.test.ts` still scans for.
- **The pages:** on /flows and /maps the header's Save opens the Save dialog, and Load's menu
  starts with "Open a saved flow…". On phones only the icons show; the words stay for screen
  readers (studio.css `.button-file .button-text`, unchanged).
- **The CSP** (`csp.ts`): `connect-src` gains EXACTLY `https://api.github.com`. `csp.test.ts` pins
  that it is the one outside origin in the whole policy, that it equals the client's `GITHUB_API`,
  and that no other module of `src/` names `api.github.com`. Nothing is sent to GitHub until a
  person opens GitHub settings ("Check and save"), Save ("Save to GitHub") or Load (the listing).
- **Attribution:** THIRD_PARTY.md, "Save, Download and Load". The licence text is in
  `flowfile.css`, and each ported file starts with "Ported from MatPilot (MIT), <file> at 4022c87".

### 2. Deviations from the design above, and why

1. **Load keeps its menu.** The menu still holds the sample, the starters and the runner links, so
   they stay one click away. Its first item, "Open a saved flow…", opens the Load dialog;
   Ctrl/⌘+O opens the dialog directly. (MatPilot's Load opens the dialog at once.)
2. **Names drop a little more** than section 1 lists:
   - C1 controls, the bidi overrides and isolates (a name that displays differently from its
     bytes), and lone surrogates (not UTF-8) are removed;
   - a Windows device name (`CON`, `PRN`, `AUX`, `NUL`, `COM0-9`, `LPT0-9`) gets a trailing `_`,
     because Windows refuses `CON.flow.json` and a class's clone would fail;
   - the cut is between graphemes.
3. **Folders** also refuse `: * ? " < > |` (a clone on Windows) and are capped at 200 characters.
   They are refused, never quietly changed.
4. **The default branch** that "Check and save" finds is kept in the settings. A listing then
   costs the root tree plus one sub-tree a folder level (2 requests for `poring-lab`), with the
   repository read again only when the branch has changed. Without a token GitHub allows 60
   requests an hour for each internet address, and a class shares one address.
5. **A 403 with `Retry-After`** (GitHub's secondary limit) is treated as the rate limit too.
6. **The commit link is built** from the commit's checked sha. `commit.html_url` from the answer
   is never used as a link.
7. **"See who changed it"** shows in both conflicts ("a file with this name exists" and "changed
   since you opened it"); MatPilot shows it for the second only.
8. **A save whose file would exceed 2,000,000 bytes is refused** with a message, because Load would
   refuse that file.
9. **A version-1 file's unknown top-level fields are ignored** (never read); the known ones are
   type-checked.
10. **The tree sha is not used for the compare-and-swap.** A flow opened from GitHub keeps the sha
    of the contents API's answer (the file is read before it opens), and a save reads the file
    again first. So the swap does not depend on the tree sha equalling the contents sha. The tree
    sha only shows in the list.

### 3. Not built

- The share link of section 4 (later, by design).
- Branches, deleting, renaming, history or diffs inside poring-lab (out of scope).
- Saving the sample world or anything client- or rAthena-derived. The file has exactly the seven
  fields, and a test hands the serializer a `world` and checks that it is not written.

### 4. Open: checks on real GitHub (none was made; every GitHub test is MOCKED)

Run these on a throwaway public repository, then tell the matpilot session the results; it
records them in its ADR 0011.
1. **A Thai-named round trip:** save `ฟาร์ม โพริง.flow.json`, list it, reload it, and compare the
   name the trees API returns with the NFC name we wrote.
2. **The tree's blob sha equals the contents API's sha** for one real file. Our swap does not need
   it (deviation 10), but the list shows the tree sha.
3. **The listing's answers on real GitHub:**
   - an EMPTY repository's `git/trees/{branch}` answer: 409 is assumed (it lists as empty either
     way);
   - a default branch with a `/` in it (sent as `%2F`): untested.
4. **Clones:** clone on Windows and on macOS, and open the files.
5. **A real iPhone:** a download (MatPilot has not verified iOS Safari either), and the
   `<dialog>`.

### 5. Checks run (2026-11-12, in the worktree; node v24.17.0 from /dev/shm)

- `node --test` over the package's test globs: **345 tests, 343 pass, 2 fail**.
  - The 2 failures are the existing `blockly_headless.test.ts` and `runner.test.ts`. They need
    `node_modules/blockly`, which the worktree does not have, and they fail the same way on `main`
    (290 pass + those 2 before this change).
  - New: `lib/flow/file.test.ts` (13 tests), `lib/github/{base64,repository,client,flows,settings}`
    `.test.ts` (38 tests), `lib/csp.test.ts` (+2: 5 tests).
- NOT run here (no `node_modules` in a tmpfs worktree):
  - `pnpm typecheck` and `pnpm lint`. The TypeScript was written strict, and the `.ts` modules run
    under Node's type stripping, but the `.tsx` dialogs and the two pages have had no compiler.
  - Any browser check of the dialogs.
  - These run in `frontend-dev` after the merge.
