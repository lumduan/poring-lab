"use client";

// Save: download the flow file, or save it into the class's GitHub folder (flows-save-load.md
// sections 2 and 3). A save NEVER silently replaces a classmate's work: the file is read first and
// written only when its sha is the one this flow was opened from or last saved as; otherwise the
// person chooses (Save mine as a new flow, Replace it, See who changed it, Cancel).
//
// Ported from MatPilot (MIT), src/components/blocks/SaveDialog.tsx at 4022c87
// (https://github.com/lumduan/matpilot, Copyright (c) 2026 Sarat Sonsuk; the licence text is in
// flowfile.css and THIRD_PARTY.md). Ours: the flow file (lib/flow/file.ts), its size check, the
// history link in both conflicts.
import { useState } from "react";

import { cleanFlowName, DEFAULT_FLOW_NAME, downloadText, type FileMeta, FLOW_FILE_MAX_BYTES, flowFileName, NAME_MAX_CHARS, serializeFlowFile, utf8Bytes } from "@/lib/flow/file";
import type { Project } from "@/lib/flow/project";
import { describeGitHubError } from "@/lib/github/describe";
import { commitMessage, nextFreeName, NOTE_MAX_CHARS } from "@/lib/github/flows";
import { folderUrl, historyUrl, joinPath, repositoryLabel, type RepositoryName } from "@/lib/github/repository";

import Dialog from "./Dialog";
import type { GitHubApi } from "./useGitHub";

type SaveState =
  | { readonly kind: "idle" }
  | { readonly kind: "busy" }
  | { readonly kind: "downloaded"; readonly fileName: string }
  | { readonly kind: "saved"; readonly name: string; readonly url: string | null }
  | { readonly kind: "conflict"; readonly reason: "exists" | "changed"; readonly name: string; readonly path: string }
  | { readonly kind: "error"; readonly message: string };

export type SaveDialogProps = {
  readonly github: GitHubApi;
  readonly meta: FileMeta;
  readonly getFlow: () => Project;
  /** The Python the flow engine made for this flow, when it is current (no request). */
  readonly pythonCached: (flow: Project) => string | null;
  /** The Python for this flow, asking the engine if need be ("" when it is not reachable). */
  readonly pythonFor: (flow: Project) => Promise<string>;
  readonly onMeta: (meta: FileMeta) => void;
  readonly onClose: () => void;
  readonly onSetUpGitHub: () => void;
};

export default function SaveDialog({ github, meta, getFlow, pythonCached, pythonFor, onMeta, onClose, onSetUpGitHub }: SaveDialogProps) {
  const [name, setName] = useState(meta.name);
  const [note, setNote] = useState("");
  const [state, setState] = useState<SaveState>({ kind: "idle" });
  const flowName = getFlow().name;
  const saveName = cleanFlowName(name) || cleanFlowName(flowName) || DEFAULT_FLOW_NAME;
  const author = github.settings.author.trim();
  const repository = github.configured ? github.repository : null;
  const folder = github.folder ?? "";
  const busy = state.kind === "busy";

  /** The file's text, or null (and the reason shown) when it is too large to open again. */
  const fileText = (flow: Project, python: string, saveAs: string): string | null => {
    const text = serializeFlowFile({ name: saveAs, savedBy: author, savedAt: new Date().toISOString(), python, project: flow });
    const bytes = utf8Bytes(text);
    if (bytes <= FLOW_FILE_MAX_BYTES) return text;
    setState({ kind: "error", message: `This flow makes a file of ${bytes} bytes; Load opens at most ${FLOW_FILE_MAX_BYTES}. Split it into smaller flows.` });
    return null;
  };

  const saveToComputer = () => {
    const flow = getFlow();
    const go = (python: string) => {
      const text = fileText(flow, python, saveName);
      if (text === null) return;
      const fileName = flowFileName(saveName, flow.name);
      downloadText(fileName, text);
      onMeta({ ...meta, name: saveName });
      setState({ kind: "downloaded", fileName });
    };
    // the Python is almost always current already: then the download starts in the click itself
    const cached = pythonCached(flow);
    if (cached !== null) go(cached);
    else {
      setState({ kind: "busy" });
      void pythonFor(flow).then(go);
    }
  };

  const saveToGitHub = async (target: RepositoryName, saveAs: string, replace: boolean): Promise<void> => {
    const label = repositoryLabel(target);
    const path = joinPath(folder, flowFileName(saveAs, flowName));
    const link = meta.link;
    const expectedSha = link && link.repository.toLowerCase() === label.toLowerCase() && link.path === path ? link.sha : null;
    setState({ kind: "busy" });
    try {
      const flow = getFlow();
      const text = fileText(flow, await pythonFor(flow), saveAs);
      if (text === null) return;
      const out = await github.write({ path, text, message: (created) => commitMessage({ name: saveAs, created, note, author }), expectedSha, replace });
      if (out.kind === "conflict") {
        setState({ kind: "conflict", reason: out.reason, name: saveAs, path });
        return;
      }
      onMeta({ name: saveAs, link: { repository: label, path, sha: out.sha } });
      setName(saveAs);
      setNote("");
      setState({ kind: "saved", name: saveAs, url: out.commitUrl });
    } catch (e) {
      setState({ kind: "error", message: describeGitHubError(e) });
    }
  };

  const saveCopy = async (target: RepositoryName, saveAs: string) => {
    setState({ kind: "busy" });
    try {
      const listing = await github.list();
      if (listing.truncated) {
        setState({ kind: "error", message: "This folder is too big for GitHub to list in one answer, so a free name cannot be checked. Type a new name above instead." });
        return;
      }
      await saveToGitHub(target, nextFreeName(saveAs, listing.flows.map((f) => f.name)), false);
    } catch (e) {
      setState({ kind: "error", message: describeGitHubError(e) });
    }
  };

  return (
    <Dialog title="Save your project" onClose={onClose} testId="save-dialog">
      <label className="dialog-field">
        <span className="dialog-label">Name</span>
        <input
          className="dialog-input"
          value={name}
          maxLength={NAME_MAX_CHARS}
          onChange={(e) => {
            setName(e.target.value);
            if (state.kind !== "busy") setState({ kind: "idle" });
          }}
          spellCheck={false}
          data-testid="flow-file-name"
        />
        <span className="dialog-hint">Letters in any language and spaces are fine; / \ : * ? &quot; &lt; &gt; | are left out.</span>
      </label>

      <section className="dialog-section" aria-labelledby="save-computer-heading">
        <h3 id="save-computer-heading">On this computer</h3>
        <p className="muted">
          Downloads <strong>{flowFileName(saveName, flowName)}</strong>. Keep it as a backup, or send it to a friend: <strong>Load</strong> opens it again.
          The sample sheets and the lab data never go into the file.
        </p>
        <button type="button" className="button" onClick={saveToComputer} disabled={busy} data-testid="save-computer">
          Save to this computer
        </button>
        {state.kind === "downloaded" && (
          <p className="notice notice-ok" role="status">
            Your browser saved <strong>{state.fileName}</strong>, usually in Downloads.
          </p>
        )}
      </section>

      <section className="dialog-section" aria-labelledby="save-github-heading">
        <h3 id="save-github-heading">On GitHub</h3>
        {repository ? (
          <>
            <p className="muted">
              Saves into{" "}
              <a href={folderUrl(repository, folder)} target="_blank" rel="noreferrer">
                {repositoryLabel(repository)}
                {folder ? ` › ${folder}` : ""}
              </a>
              , where the class can load it.{" "}
              <button type="button" className="link-button" onClick={onSetUpGitHub}>
                Change
              </button>
            </p>
            {github.hasToken ? (
              <>
                <label className="dialog-field">
                  <span className="dialog-label">What did you change? (optional)</span>
                  <input
                    className="dialog-input"
                    value={note}
                    maxLength={NOTE_MAX_CHARS}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder="for example: loot before the next pack"
                    data-testid="save-note"
                  />
                </label>
                <div className="button-row" style={{ marginTop: "0.6rem" }}>
                  <button type="button" className="button button-primary" onClick={() => void saveToGitHub(repository, saveName, false)} disabled={busy} data-testid="save-github">
                    {busy ? "Saving…" : "Save to GitHub"}
                  </button>
                </div>
              </>
            ) : (
              <p className="notice notice-warn">
                Saving to GitHub needs a token.{" "}
                <button type="button" className="link-button" onClick={onSetUpGitHub}>
                  Add a token
                </button>
              </p>
            )}
          </>
        ) : (
          <>
            <p className="muted">Keep flows in a GitHub repository, so a class can share them and see who changed what.</p>
            <button type="button" className="button" onClick={onSetUpGitHub} data-testid="save-setup-github">
              Set up GitHub…
            </button>
          </>
        )}

        {state.kind === "saved" && repository && (
          <p className="notice notice-ok" role="status" data-testid="save-result">
            Saved <strong>{state.name}</strong> to GitHub.{" "}
            {state.url && (
              <a href={state.url} target="_blank" rel="noreferrer">
                See it on GitHub
              </a>
            )}
          </p>
        )}
        {state.kind === "error" && (
          <p className="notice notice-error" role="alert" data-testid="save-result">
            {state.message}
          </p>
        )}
        {state.kind === "conflict" && repository && (
          <div className="notice notice-warn" role="alert" data-testid="save-conflict">
            <p>
              {state.reason === "exists" ? (
                <>
                  There is already a flow called <strong>{state.name}</strong> in this folder. Saving would replace it.{" "}
                </>
              ) : (
                <>
                  Someone saved <strong>{state.name}</strong> on GitHub after you opened it. Saving now would replace their version.{" "}
                </>
              )}
              <a href={historyUrl(repository, state.path)} target="_blank" rel="noreferrer">
                See who changed it
              </a>
            </p>
            <div className="button-row">
              <button type="button" className="button button-small" onClick={() => void saveCopy(repository, state.name)} data-testid="save-copy">
                Save mine as a new flow
              </button>
              <button type="button" className="button button-small" onClick={() => void saveToGitHub(repository, state.name, true)} data-testid="save-replace">
                Replace it
              </button>
              <button type="button" className="button button-small" onClick={() => setState({ kind: "idle" })}>
                Cancel
              </button>
            </div>
          </div>
        )}
      </section>
    </Dialog>
  );
}
