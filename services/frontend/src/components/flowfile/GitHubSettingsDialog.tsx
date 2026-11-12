"use client";

// Where on GitHub flows are kept, and the token to save them (flows-save-load.md section 3). Nothing
// is sent until "Check and save"; public repositories need no token to load (the teaching path:
// a teacher shares a repository, the students press Load).
//
// Ported from MatPilot (MIT), src/components/blocks/GitHubSettingsDialog.tsx at 4022c87
// (https://github.com/lumduan/matpilot, Copyright (c) 2026 Sarat Sonsuk; the licence text is in
// flowfile.css and THIRD_PARTY.md). Ours: "Remember" is OFF by default (the token stays in this
// tab), the token's shape is checked, the default branch is kept, the class advice.
import { type FormEvent, useState } from "react";

import { describeGitHubError } from "@/lib/github/describe";
import { cleanFolder, DEFAULT_FOLDER, newTokenUrl, parseRepository, repositoryLabel } from "@/lib/github/repository";
import { tokenProblem } from "@/lib/github/settings";

import Dialog from "./Dialog";
import type { GitHubApi } from "./useGitHub";

type CheckState =
  | { readonly kind: "idle" }
  | { readonly kind: "checking" }
  | { readonly kind: "ok"; readonly message: string; readonly warn: boolean }
  | { readonly kind: "error"; readonly message: string };

const KEPT: Record<string, string> = {
  session: "A token is kept in this browser tab; type to replace it",
  local: "A token is kept on this computer; type to replace it",
  memory: "A token is kept until this page closes; type to replace it",
};

export default function GitHubSettingsDialog({ github, onClose }: { github: GitHubApi; onClose: () => void }) {
  const [repository, setRepository] = useState(github.settings.repository);
  const [folder, setFolder] = useState(github.settings.folder);
  const [author, setAuthor] = useState(github.settings.author);
  const [token, setToken] = useState("");
  const [remember, setRemember] = useState(github.settings.remember);
  const [state, setState] = useState<CheckState>({ kind: "idle" });
  const parsed = parseRepository(repository);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!parsed) {
      setState({ kind: "error", message: "Type the repository as owner/name (for example teacher-class/flows), or paste its link from GitHub." });
      return;
    }
    const cleaned = cleanFolder(folder);
    if (cleaned === null) {
      setState({ kind: "error", message: "The folder name cannot contain “..”, “.” on its own, backslashes, or : * ? \" < > |." });
      return;
    }
    const problem = tokenProblem(token);
    if (problem) {
      setState({ kind: "error", message: problem });
      return;
    }
    const newToken = token.trim() || null;
    setState({ kind: "checking" });
    try {
      const info = await github.check(parsed, newToken);
      github.save({ repository: repositoryLabel(parsed), folder: cleaned, author: author.trim().slice(0, 40), remember, branch: info.defaultBranch }, newToken);
      setToken("");
      const hasToken = newToken !== null || github.hasToken;
      const where = `${info.fullName}${info.private ? " (private)" : ""}`;
      setState(
        !hasToken
          ? { kind: "ok", warn: true, message: `Found ${where}. You can load flows from it; add a token to save.` }
          : info.canPush === false
            ? { kind: "ok", warn: true, message: `Found ${where}, but your GitHub account cannot change it. Ask its owner to make you a member.` }
            : { kind: "ok", warn: false, message: `Connected to ${where}. You can save and load flows.` },
      );
    } catch (err) {
      setState({ kind: "error", message: describeGitHubError(err) });
    }
  };

  return (
    <Dialog title="GitHub for your class" onClose={onClose} testId="github-dialog">
      <form className="dialog-form" onSubmit={(e) => void submit(e)}>
        <label className="dialog-field">
          <span className="dialog-label">Repository</span>
          <input
            className="dialog-input"
            value={repository}
            onChange={(e) => setRepository(e.target.value)}
            placeholder="owner/name, or its link"
            maxLength={300}
            autoComplete="off"
            spellCheck={false}
            required
            data-testid="github-repository"
          />
        </label>
        <label className="dialog-field">
          <span className="dialog-label">Folder for flows</span>
          <input
            className="dialog-input"
            value={folder}
            onChange={(e) => setFolder(e.target.value)}
            placeholder={`${DEFAULT_FOLDER} (empty: the top folder)`}
            maxLength={200}
            autoComplete="off"
            spellCheck={false}
            data-testid="github-folder"
          />
          <span className="dialog-hint">GitHub makes the folder when the first flow is saved. Keep one folder per class (or per student), well under 1,000 files.</span>
        </label>
        <label className="dialog-field">
          <span className="dialog-label">Your name (optional)</span>
          <input className="dialog-input" value={author} maxLength={40} onChange={(e) => setAuthor(e.target.value)} autoComplete="off" data-testid="github-author" />
          <span className="dialog-hint">Shown on GitHub with each save, so the class can see who saved what.</span>
        </label>
        <label className="dialog-field">
          <span className="dialog-label">Token</span>
          <input
            className="dialog-input"
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder={github.where ? KEPT[github.where] : "github_pat_…"}
            maxLength={300}
            autoComplete="off"
            spellCheck={false}
            data-testid="github-token"
          />
          <span className="dialog-hint">Needed to save, and to load from a private repository. Public repositories load without one.</span>
        </label>
        <label className="dialog-check">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} data-testid="github-remember" />
          <span>
            Remember on this computer. Unticked, the token stays in this browser tab only and is gone when the tab closes. Never tick it on a shared computer.
          </span>
        </label>

        <div className="button-row">
          <button type="submit" className="button button-primary" disabled={state.kind === "checking"} data-testid="github-save">
            {state.kind === "checking" ? "Checking…" : "Check and save"}
          </button>
          {github.hasToken && (
            <button
              type="button"
              className="button"
              onClick={() => {
                github.forgetToken();
                setState({ kind: "ok", warn: false, message: "The token is forgotten: it is gone from this tab and this computer." });
              }}
              data-testid="github-forget"
            >
              Forget the token
            </button>
          )}
        </div>
        {state.kind === "ok" && (
          <p className={state.warn ? "notice notice-warn" : "notice notice-ok"} role="status" data-testid="github-result">
            {state.message}
          </p>
        )}
        {state.kind === "error" && (
          <p className="notice notice-error" role="alert" data-testid="github-result">
            {state.message}
          </p>
        )}
      </form>

      <details className="dialog-help">
        <summary>How to get a token</summary>
        <ol>
          <li>Sign in to GitHub with an account that can change the repository.</li>
          <li>
            Open{" "}
            <a href={newTokenUrl(parsed?.owner ?? null)} target="_blank" rel="noreferrer">
              GitHub’s new token page
            </a>
            . It opens with poring-lab’s choices filled in: a fine-grained token, for one year, with “Contents: Read and write”.
          </li>
          <li>
            Under <strong>Repository access</strong>, choose <strong>Only select repositories</strong> and pick the class’s repository.
          </li>
          <li>
            Press <strong>Generate token</strong>, copy it, and paste it above.
          </li>
        </ol>
        <p>The token works like a password for that one repository: never post it in a chat. If it leaks, delete it on GitHub and make a new one.</p>
        <p>
          <strong>A class:</strong> these tokens open repositories you own, or that belong to an organisation you are a member of, but not repositories you
          were only invited to. Make a free GitHub organisation for the class, put the repository in it, and make each student a member.
        </p>
        <p>
          GitHub accounts are for people aged 13 and over: for younger students a teacher or a parent owns the account and the token, and “Your name” still
          records who saved what.
        </p>
      </details>
    </Dialog>
  );
}
