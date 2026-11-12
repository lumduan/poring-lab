"use client";

// Load: open a flow file from this computer or from the class's GitHub folder (flows-save-load.md
// sections 2 and 3). Every file is HOSTILE: its size is checked BEFORE it is read, then
// lib/flow/file.ts parseFlowFile checks it into a scratch flow; the page's flow changes only when it
// all passes, as ONE undo step (the page's notice). Names and errors render as text only.
//
// Ported from MatPilot (MIT), src/components/blocks/LoadDialog.tsx at 4022c87
// (https://github.com/lumduan/matpilot, Copyright (c) 2026 Sarat Sonsuk; the licence text is in
// flowfile.css and THIRD_PARTY.md). Ours: the truncated folder, the size refused before a GitHub
// read, the flow file and its meta.
import { useEffect, useRef, useState } from "react";

import { type FileMeta, FLOW_FILE_EXTENSION, FLOW_FILE_MAX_BYTES, flowNameFromFileName, parseFlowFile } from "@/lib/flow/file";
import type { Flow } from "@/lib/flow/ir";
import { describeGitHubError, describeSaved, describeSize } from "@/lib/github/describe";
import type { RemoteFlow } from "@/lib/github/flows";
import { folderUrl, repositoryLabel } from "@/lib/github/repository";

import Dialog from "./Dialog";
import type { GitHubApi } from "./useGitHub";

type RemoteState =
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly flows: readonly RemoteFlow[]; readonly truncated: boolean }
  | { readonly kind: "error"; readonly message: string };

/** A flow that passed every check, its meta, and the words for the page's notice. */
export type Opened = { readonly flow: Flow; readonly meta: FileMeta; readonly notice: string };

export default function LoadDialog({ github, onClose, onOpened, onSetUpGitHub }: { github: GitHubApi; onClose: () => void; onOpened: (o: Opened) => void; onSetUpGitHub: () => void }) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const repository = github.configured ? github.repository : null;
  const folder = github.folder ?? "";
  const [remote, setRemote] = useState<RemoteState>({ kind: "loading" });
  const [listRequest, setListRequest] = useState(0);
  const { list } = github;

  // the folder is listed when a person opened Load (and on Refresh), never before
  useEffect(() => {
    if (!repository) return;
    let current = true;
    list().then(
      (l) => current && setRemote({ kind: "ready", flows: l.flows, truncated: l.truncated }),
      (e: unknown) => current && setRemote({ kind: "error", message: describeGitHubError(e) }),
    );
    return () => {
      current = false;
    };
  }, [repository, list, listRequest]);

  const refresh = () => {
    setRemote({ kind: "loading" });
    setListRequest((n) => n + 1);
  };

  const words = (name: string, savedBy: string, savedAt: string, from: string): string => {
    const saved = describeSaved(savedBy, savedAt);
    return `Opened “${name}”${from}${saved ? ` (saved by ${saved})` : ""}. Press Undo to go back to the flow you had.`;
  };

  const openFromComputer = async (file: File) => {
    setError(null);
    if (file.size > FLOW_FILE_MAX_BYTES) {
      setError(`${file.name}: ${file.size} bytes is too large to be a flow file (at most ${FLOW_FILE_MAX_BYTES}).`);
      return;
    }
    let text: string;
    try {
      text = await file.text();
    } catch {
      setError(`${file.name} could not be read.`);
      return;
    }
    const r = parseFlowFile(text, flowNameFromFileName(file.name));
    if (!r.ok) {
      setError(`${file.name}: ${r.errors.slice(0, 8).join(" · ")}`);
      return;
    }
    onOpened({ flow: r.flow, meta: { name: r.name, link: null }, notice: words(r.name, r.savedBy, r.savedAt, "") });
  };

  const openFromGitHub = async (f: RemoteFlow) => {
    if (!repository) return;
    setError(null);
    if (f.size > FLOW_FILE_MAX_BYTES) {
      setError(`“${f.name}” is too large to be a flow file.`);
      return;
    }
    setOpening(f.path);
    try {
      const file = await github.read(f.path);
      if (!file) {
        setError(`“${f.name}” is no longer on GitHub. Refresh the list.`);
        return;
      }
      const r = parseFlowFile(file.text, `${f.name}${FLOW_FILE_EXTENSION}`);
      if (!r.ok) {
        setError(`“${f.name}”: ${r.errors.slice(0, 8).join(" · ")}`);
        return;
      }
      onOpened({
        flow: r.flow,
        meta: { name: r.name, link: { repository: repositoryLabel(repository), path: file.path, sha: file.sha } },
        notice: words(r.name, r.savedBy, r.savedAt, ` from ${repositoryLabel(repository)}`),
      });
    } catch (e) {
      setError(describeGitHubError(e));
    } finally {
      setOpening(null);
    }
  };

  return (
    <Dialog title="Load a flow" onClose={onClose} testId="load-dialog">
      <p className="muted">
        Loading replaces the flow on the page. Changed your mind? Press <strong>Undo</strong> on the notice.
      </p>
      {error && (
        <p className="notice notice-error" role="alert" data-testid="load-error">
          {error}
        </p>
      )}

      <section className="dialog-section" aria-labelledby="load-computer-heading">
        <h3 id="load-computer-heading">From this computer</h3>
        <input
          ref={fileInput}
          type="file"
          accept=".json,application/json"
          className="visually-hidden"
          tabIndex={-1}
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (file) void openFromComputer(file);
          }}
          data-testid="load-file-input"
        />
        <button type="button" className="button" onClick={() => fileInput.current?.click()} data-testid="load-computer">
          Choose a file…
        </button>
        <p className="muted" style={{ marginTop: "0.5rem" }}>
          A <code>.flow.json</code> file saved here, or a flow&apos;s JSON from before (checked before it opens).
        </p>
      </section>

      <section className="dialog-section" aria-labelledby="load-github-heading">
        <h3 id="load-github-heading">From GitHub</h3>
        {repository ? (
          <>
            <p className="muted">
              <a href={folderUrl(repository, folder)} target="_blank" rel="noreferrer">
                {repositoryLabel(repository)}
                {folder ? ` › ${folder}` : ""}
              </a>{" "}
              <button type="button" className="link-button" onClick={refresh} data-testid="load-refresh">
                Refresh
              </button>{" "}
              <button type="button" className="link-button" onClick={onSetUpGitHub}>
                Change
              </button>
            </p>
            {remote.kind === "loading" && <p className="muted">Looking on GitHub…</p>}
            {remote.kind === "error" && (
              <p className="notice notice-error" role="alert">
                {remote.message}
              </p>
            )}
            {remote.kind === "ready" && remote.truncated && (
              <p className="notice notice-warn" role="status" data-testid="github-truncated">
                This folder is too big: GitHub sent only part of its list, so none of it is shown (a part would look like the whole). Use a folder with fewer
                files: one folder per class or per student.
              </p>
            )}
            {remote.kind === "ready" &&
              !remote.truncated &&
              (remote.flows.length === 0 ? (
                <p className="muted" data-testid="github-empty">
                  No flows here yet. Save one to start the folder.
                </p>
              ) : (
                <ul className="flow-list" data-testid="github-flows">
                  {remote.flows.map((f) => (
                    <li key={f.path}>
                      <button type="button" className="flow-list-item" onClick={() => void openFromGitHub(f)} disabled={opening !== null || f.size > FLOW_FILE_MAX_BYTES}>
                        <span className="flow-list-name">{f.name}</span>
                        <span className="flow-list-meta">{opening === f.path ? "Opening…" : f.size > FLOW_FILE_MAX_BYTES ? "too large" : describeSize(f.size)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              ))}
          </>
        ) : (
          <>
            <p className="muted">Open flows a class saved in a GitHub repository. A public repository needs no token.</p>
            <button type="button" className="button" onClick={onSetUpGitHub} data-testid="load-setup-github">
              Set up GitHub…
            </button>
          </>
        )}
      </section>
    </Dialog>
  );
}
