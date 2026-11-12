// The few GitHub REST API calls poring-lab makes to save and load flows
// (docs/planning/flows-save-load.md section 3): read a repository, list a folder, read a file, and
// create or update a file. Requests go to https://api.github.com ONLY (the CSP's one outside origin,
// csp.ts), only when a person asks, and carry that person's own token, never anyone else's.
//
// Ported from MatPilot (MIT), src/lib/github/client.ts at 4022c87 (https://github.com/lumduan/matpilot,
// Copyright (c) 2026 Sarat Sonsuk; the licence text is in components/flowfile/flowfile.css and
// THIRD_PARTY.md). Ours: the folder is listed with the Git Trees API (the contents API lists at most
// 1,000 files a folder) and a `truncated` answer is said plainly, never shown as a partial list;
// sizes are checked before a file is read; every path is checked by safePath before it reaches a
// URL; the commit link is built from its checked id; a Retry-After is read as the rate limit.
//
// API reference: https://docs.github.com/en/rest/repos/repos#get-a-repository,
// https://docs.github.com/en/rest/git/trees#get-a-tree and https://docs.github.com/en/rest/repos/contents
// (`sha` is required to replace a file; a stale one is refused with 409). The API allows requests
// from any origin (MatPilot checked it, 2026-11-06). Its GET answers may be cached for 60 s, so
// every request bypasses the browser's cache.
import { base64Bytes, decodeBase64Utf8, encodeBase64Utf8 } from "./base64.ts";
import { commitUrl, encodePath, GIT_SHA, repositoryLabel, type RepositoryName, safePath } from "./repository.ts";

export const GITHUB_API = "https://api.github.com";
export const GITHUB_API_VERSION = "2022-11-28";
/** The largest file read (a flow file is a few kilobytes: file.ts FLOW_FILE_MAX_BYTES). */
export const MAX_READ_BYTES = 2_000_000;
/** Tree entries looked at in one answer (GitHub's own limit is 100,000 with `recursive`). */
const MAX_TREE_ENTRIES = 100_000;

export type GitHubErrorKind = "network" | "token" | "not-found" | "forbidden" | "rate-limit" | "conflict" | "invalid" | "too-large" | "other";

export class GitHubError extends Error {
  readonly kind: GitHubErrorKind;
  readonly status: number | null;
  /** For "rate-limit": when GitHub allows requests again. */
  readonly retryAt: Date | null;
  constructor(kind: GitHubErrorKind, message: string, status: number | null = null, retryAt: Date | null = null) {
    super(message);
    this.name = "GitHubError";
    this.kind = kind;
    this.status = status;
    this.retryAt = retryAt;
  }
}

export type RepositoryInfo = {
  readonly fullName: string;
  readonly private: boolean;
  /** Whether the token's owner may push; null without a token. */
  readonly canPush: boolean | null;
  readonly defaultBranch: string;
};
export type FolderEntry = { readonly name: string; readonly path: string; readonly sha: string; readonly size: number };
/** A folder's files. `truncated`: GitHub sent only part of the tree, so `entries` is EMPTY rather
 * than a list that looks complete and is not. */
export type FolderListing = { readonly entries: readonly FolderEntry[]; readonly truncated: boolean };
export type RemoteFile = { readonly path: string; readonly sha: string; readonly text: string };
export type SavedFile = { readonly sha: string; readonly commitUrl: string | null };

export type FetchLike = (url: string, init: RequestInit) => Promise<Response>;
export type GitHubClientOptions = {
  readonly repository: RepositoryName;
  /** A personal access token, or null to read public repositories only. */
  readonly token: string | null;
  /** The default branch if it is known already (saved by "Check and save"): one request fewer. */
  readonly branch?: string | null;
  readonly fetch?: FetchLike;
};

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
/** A branch name as git allows it (roughly: no controls, spaces or ~^:?*[\ , no "..", no leading "-"). */
const BRANCH = /^(?!-)(?!.*\.\.)[^\u0000- \u007f~^:?*[\\]{1,255}$/;
/** GitHub's own words in an error, made one plain line. */
const said = (data: unknown): string =>
  isObj(data) && typeof data.message === "string" ? data.message.replace(/[\u0000-\u001f\u007f]+/g, " ").trim().slice(0, 200) : "";

type TreeEntry = { name: string; type: "blob" | "tree"; sha: string; size: number };

export class GitHubClient {
  readonly repository: RepositoryName;
  private readonly token: string | null;
  private readonly fetchImpl: FetchLike;
  private branch: string | null;

  constructor(options: GitHubClientOptions) {
    this.repository = options.repository;
    this.token = options.token?.trim() || null;
    this.branch = options.branch && BRANCH.test(options.branch) ? options.branch : null;
    // bound, so a mock or the browser's fetch is called with the right `this`
    this.fetchImpl = options.fetch ?? ((url, init) => globalThis.fetch(url, init));
  }

  get hasToken(): boolean {
    return this.token !== null;
  }

  private get base(): string {
    const { owner, repo } = this.repository;
    return `${GITHUB_API}/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`;
  }

  private contentsUrl(path: string): string {
    const p = encodePath(path);
    if (!p) throw new GitHubError("invalid", "That path cannot be used on GitHub.");
    return `${this.base}/contents/${p}`;
  }

  private async request(
    method: "GET" | "PUT",
    url: string,
    body?: object,
    /** Ask for the file itself rather than JSON (files of 1 to 100 MB need it). */
    raw = false,
  ): Promise<{ status: number; data: unknown; bytes: ArrayBuffer | null }> {
    if (!url.startsWith(`${GITHUB_API}/repos/`)) throw new GitHubError("invalid", "poring-lab talks to api.github.com only.");
    const headers: Record<string, string> = {
      Accept: raw ? "application/vnd.github.raw+json" : "application/vnd.github+json",
      "X-GitHub-Api-Version": GITHUB_API_VERSION,
    };
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    if (body) headers["Content-Type"] = "application/json";
    let response: Response;
    try {
      response = await this.fetchImpl(url, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
        cache: "no-store",
        credentials: "omit",
        referrerPolicy: "no-referrer",
      });
    } catch {
      throw new GitHubError("network", "Could not reach GitHub. Check the internet connection.");
    }
    let data: unknown = null;
    let bytes: ArrayBuffer | null = null;
    try {
      if (raw && response.ok) bytes = await response.arrayBuffer();
      else data = await response.json();
    } catch {
      // some errors have no JSON body
    }
    if (!response.ok) throw this.errorFor(response, data);
    return { status: response.status, data, bytes };
  }

  private errorFor(response: Response, data: unknown): GitHubError {
    const { status } = response;
    const words = said(data);
    const remaining = response.headers.get("x-ratelimit-remaining");
    const reset = Number(response.headers.get("x-ratelimit-reset"));
    const retryAfter = Number(response.headers.get("retry-after"));
    if (status === 429 || (status === 403 && (remaining === "0" || (Number.isFinite(retryAfter) && retryAfter > 0)))) {
      const retryAt =
        Number.isFinite(reset) && reset > 0
          ? new Date(reset * 1000)
          : Number.isFinite(retryAfter) && retryAfter > 0
            ? new Date(Date.now() + retryAfter * 1000)
            : null;
      return new GitHubError(
        "rate-limit",
        this.token
          ? "GitHub says too many requests were made. Wait a little and try again."
          : "GitHub allows only a few requests without a token (60 an hour for each internet address). Add a token, or wait and try again.",
        status,
        retryAt,
      );
    }
    if (status === 401) return new GitHubError("token", "GitHub did not accept the token. It may be mistyped or expired: make a new one.", status);
    if (status === 403) {
      return new GitHubError(
        "forbidden",
        this.token ? "The token is not allowed to do this. It needs “Contents: Read and write” for this repository." : "GitHub needs a token for this.",
        status,
      );
    }
    if (status === 404) return new GitHubError("not-found", "Not found on GitHub.", status);
    if (status === 409 || (status === 422 && /\bsha\b/i.test(words))) {
      return new GitHubError("conflict", "Someone else changed this file on GitHub at the same time.", status);
    }
    if (status === 422) return new GitHubError("invalid", `GitHub did not accept this: ${words || "invalid request"}.`, status);
    return new GitHubError("other", `GitHub answered with an error (${status}${words ? `: ${words}` : ""}).`, status);
  }

  /** The repository: its name, whether the token may push, and its default branch. */
  async getRepository(): Promise<RepositoryInfo> {
    let data: unknown;
    try {
      ({ data } = await this.request("GET", this.base));
    } catch (e) {
      if (e instanceof GitHubError && e.kind === "not-found") {
        throw new GitHubError(
          "not-found",
          this.token
            ? `GitHub has no repository ${repositoryLabel(this.repository)} that this token can open. Check the name, and that the token was made for this repository.`
            : `GitHub has no public repository ${repositoryLabel(this.repository)}. Check the name; a private repository needs a token.`,
          404,
        );
      }
      throw e;
    }
    if (!isObj(data)) throw new GitHubError("other", "GitHub sent an unexpected answer.");
    const branch = typeof data.default_branch === "string" && BRANCH.test(data.default_branch) ? data.default_branch : null;
    if (!branch) throw new GitHubError("other", "GitHub did not say which branch this repository uses.");
    this.branch = branch;
    const permissions = isObj(data.permissions) ? data.permissions : null;
    return {
      fullName: typeof data.full_name === "string" ? data.full_name.slice(0, 200) : repositoryLabel(this.repository),
      private: data.private === true,
      canPush: this.token && permissions ? permissions.push === true : null,
      defaultBranch: branch,
    };
  }

  private async tree(ref: string): Promise<{ entries: TreeEntry[]; truncated: boolean }> {
    const { data } = await this.request("GET", `${this.base}/git/trees/${encodeURIComponent(ref)}`);
    if (!isObj(data) || !Array.isArray(data.tree)) throw new GitHubError("other", "GitHub sent an unexpected answer.");
    const entries: TreeEntry[] = [];
    for (const e of data.tree.slice(0, MAX_TREE_ENTRIES) as unknown[]) {
      if (!isObj(e) || typeof e.path !== "string" || typeof e.sha !== "string" || !GIT_SHA.test(e.sha)) continue;
      if (e.path.includes("/") || !safePath(e.path)) continue;
      // files (not symlinks: mode 120000) and folders; submodules ("commit") are not ours
      const file = e.type === "blob" && (e.mode === "100644" || e.mode === "100755");
      if (!file && e.type !== "tree") continue;
      const size = typeof e.size === "number" && Number.isFinite(e.size) && e.size >= 0 ? e.size : 0;
      entries.push({ name: e.path, type: file ? "blob" : "tree", sha: e.sha, size });
    }
    return { entries, truncated: data.truncated === true || data.tree.length > MAX_TREE_ENTRIES };
  }

  /**
   * The files in a folder (`''` for the top folder), through the Git Trees API: the default
   * branch's tree, then each folder's sub-tree. Empty when the folder does not exist yet (GitHub
   * makes it at the first save) or the repository is empty. Throws "not-found" when the repository
   * itself cannot be opened.
   */
  async listFolder(folder: string): Promise<FolderListing> {
    const segments = folder === "" ? [] : folder.split("/");
    if (folder !== "" && !safePath(folder)) throw new GitHubError("invalid", "That folder cannot be used on GitHub.");
    let branch = this.branch;
    if (!branch) branch = (await this.getRepository()).defaultBranch;
    let level: { entries: TreeEntry[]; truncated: boolean };
    try {
      level = await this.tree(branch);
    } catch (e) {
      if (!(e instanceof GitHubError && (e.kind === "not-found" || e.kind === "conflict"))) throw e;
      // a renamed branch, an empty repository (409), or no repository: ask the repository again
      const info = await this.getRepository();
      if (info.defaultBranch === branch) return { entries: [], truncated: false };
      try {
        level = await this.tree(info.defaultBranch);
      } catch (e2) {
        if (e2 instanceof GitHubError && (e2.kind === "not-found" || e2.kind === "conflict")) return { entries: [], truncated: false };
        throw e2;
      }
    }
    for (const seg of segments) {
      const sub = level.entries.find((x) => x.type === "tree" && x.name === seg);
      // not there: the folder is new (unless the answer was cut, and then we cannot know)
      if (!sub) return { entries: [], truncated: level.truncated };
      level = await this.tree(sub.sha);
    }
    if (level.truncated) return { entries: [], truncated: true };
    const prefix = segments.join("/");
    return {
      entries: level.entries.filter((x) => x.type === "blob").map((x) => ({ name: x.name, path: prefix ? `${prefix}/${x.name}` : x.name, sha: x.sha, size: x.size })),
      truncated: false,
    };
  }

  /** A text file, or null when there is none at `path`. Its size is checked before its content is
   * read; larger than `maxBytes` is "too-large". */
  async readFile(path: string, maxBytes = MAX_READ_BYTES): Promise<RemoteFile | null> {
    const url = this.contentsUrl(path);
    let data: unknown;
    try {
      ({ data } = await this.request("GET", url));
    } catch (e) {
      if (e instanceof GitHubError && e.kind === "not-found") return null;
      throw e;
    }
    if (!isObj(data) || data.type !== "file" || typeof data.sha !== "string" || !GIT_SHA.test(data.sha)) {
      throw new GitHubError("invalid", `“${path}” on GitHub is not a file.`);
    }
    const size = typeof data.size === "number" && Number.isFinite(data.size) ? data.size : null;
    const tooLarge = () => new GitHubError("too-large", `“${path}” on GitHub is too large to be a flow file.`);
    if (size !== null && size > maxBytes) throw tooLarge();
    const gotPath = typeof data.path === "string" && safePath(data.path) ? data.path : path;
    // files of 1 to 100 MB come without their content; GitHub sends them raw when asked
    if (data.encoding === "none") {
      if (size === null) throw tooLarge();
      const { bytes } = await this.request("GET", url, undefined, true);
      if (!bytes || bytes.byteLength > maxBytes) throw tooLarge();
      return { path: gotPath, sha: data.sha, text: this.utf8(bytes, path) };
    }
    if (data.encoding !== "base64" || typeof data.content !== "string") throw tooLarge();
    if (base64Bytes(data.content) > maxBytes) throw tooLarge();
    let text: string;
    try {
      text = decodeBase64Utf8(data.content);
    } catch {
      throw new GitHubError("invalid", `“${path}” on GitHub is not a text file.`);
    }
    return { path: gotPath, sha: data.sha, text };
  }

  private utf8(bytes: ArrayBuffer, path: string): string {
    try {
      return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    } catch {
      throw new GitHubError("invalid", `“${path}” on GitHub is not a text file.`);
    }
  }

  /**
   * Creates the file at `path`, or replaces it when `sha` is the sha of the file there now.
   * Throws "conflict" when the file changed (or appeared) since that sha was read.
   */
  async writeFile(args: { readonly path: string; readonly text: string; readonly message: string; readonly sha: string | null }): Promise<SavedFile> {
    if (!this.token) throw new GitHubError("token", "Saving to GitHub needs a token.");
    if (args.sha !== null && !GIT_SHA.test(args.sha)) throw new GitHubError("invalid", "That file version cannot be used on GitHub.");
    const { data } = await this.request("PUT", this.contentsUrl(args.path), {
      message: args.message,
      content: encodeBase64Utf8(args.text),
      ...(args.sha ? { sha: args.sha } : {}),
    });
    const content = isObj(data) && isObj(data.content) ? data.content : null;
    const commit = isObj(data) && isObj(data.commit) ? data.commit : null;
    if (!content || typeof content.sha !== "string" || !GIT_SHA.test(content.sha)) {
      throw new GitHubError("other", "GitHub saved the file but sent an unexpected answer.");
    }
    return { sha: content.sha, commitUrl: commit && typeof commit.sha === "string" ? commitUrl(this.repository, commit.sha) : null };
  }
}
