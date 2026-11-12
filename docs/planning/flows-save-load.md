---
doc_type: plan
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [flows-studio.md, world-map-flows.md, ../adr/0023-learner-mode.md]
next_action: "Build it (after the setup manual and ADR-0023 decision 1): one Save / Load for /flows and /maps, on this computer and on GitHub, ported from MatPilot (MIT, 4022c870) with attribution in THIRD_PARTY.md."
---

# /flows and /maps: Save, Download and Load -- on this computer and on GitHub

Written 2026-11-12 11:12 ICT from `date`.

## Why (Batt, 2026-11-12, translated)

> "On the flows and maps pages, make a save and download system too. Ask matpilot how they do it
> and do it that way: save/load on the machine, and through GitHub too. In the future I may teach by
> having students load a flow and carry on from it -- faster than each building their own -- and it
> helps build a community that shares knowledge as code on GitHub."

## What exists today

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
