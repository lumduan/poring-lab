// Names of a GitHub repository and of the folder flows are kept in, and links to them on github.com
// (docs/planning/flows-save-load.md section 3). Links are followed only when a person clicks them,
// and every page shows them with rel="noreferrer".
//
// Ported from MatPilot (MIT), src/lib/github/repository.ts at 4022c87
// (https://github.com/lumduan/matpilot, Copyright (c) 2026 Sarat Sonsuk; the licence text is in
// components/flowfile/flowfile.css and THIRD_PARTY.md). Ours: safePath (no "." / ".." segment ever
// reaches a URL), the Windows-refused characters in folders, the length caps, commitUrl.

export type RepositoryName = { readonly owner: string; readonly repo: string };

/** Account and organisation names: letters, digits and single hyphens, at most 39 characters. */
const OWNER = /^[a-z\d](?:[a-z\d]|-(?=[a-z\d])){0,38}$/i;
/** Repository names: letters, digits, `.`, `-` and `_`, at most 100 characters. */
const REPO = /^[\w.-]{1,100}$/;
/** A git object id: SHA-1 (40) or SHA-256 (64) hex. */
export const GIT_SHA = /^[0-9a-f]{40}(?:[0-9a-f]{24})?$/;

/**
 * Reads what a person typed or pasted: `owner/name`, a github.com link (with or without
 * `https://`, `.git` or a path after it), or an SSH address (`git@github.com:owner/name.git`).
 * `null` when it cannot be a repository.
 */
export function parseRepository(input: string): RepositoryName | null {
  if (input.length > 300) return null;
  const text = input
    .trim()
    .replace(/^git@github\.com:/i, "")
    .replace(/^(?:https?:\/\/)?(?:www\.)?github\.com\//i, "");
  const [owner = "", rawRepo = ""] = text.split(/[/?#]/);
  const repo = rawRepo.replace(/\.git$/i, "");
  if (!OWNER.test(owner) || !REPO.test(repo) || repo === "." || repo === "..") return null;
  return { owner, repo };
}

export const repositoryLabel = ({ owner, repo }: RepositoryName): string => `${owner}/${repo}`;

export const DEFAULT_FOLDER = "poring-lab";
const FOLDER_MAX = 200;
/** What a path segment may not hold: control characters, backslashes, and what Windows refuses
 * (a class clones the repository on Windows too). */
const SEGMENT_BAD = /[\u0000-\u001f\u007f-\u009f\\:*?"<>|]/;

/**
 * A folder path inside the repository: segments split by `/`, without empty, `.` or `..`
 * segments, control characters, backslashes or `: * ? " < > |`; NFC; at most 200 characters.
 * `''` is the repository's top folder; `null` means the path cannot be used (it is refused, never
 * quietly changed, so the person sees why).
 */
export function cleanFolder(input: string): string | null {
  const segments = input
    .normalize("NFC")
    .trim()
    .split("/")
    .map((s) => s.trim())
    .filter((s) => s !== "");
  for (const s of segments) {
    if (s === "." || s === ".." || SEGMENT_BAD.test(s)) return null;
  }
  const out = segments.join("/");
  return out.length > FOLDER_MAX ? null : out;
}

/** A path we may put in a URL: non-empty segments, none `.` or `..` (a URL would resolve them and
 * reach another endpoint), no control characters or backslashes. */
export function safePath(path: string): boolean {
  if (path === "" || path.length > 1000) return false;
  return path.split("/").every((s) => s !== "" && s !== "." && s !== ".." && !/[\u0000-\u001f\u007f\\]/.test(s));
}

/** `folder/file`, or `file` in the top folder. */
export const joinPath = (folder: string, fileName: string): string => (folder === "" ? fileName : `${folder}/${fileName}`);

/** Every segment encodeURIComponent'd (Thai names too); `null` for a path safePath refuses. */
export function encodePath(path: string): string | null {
  return safePath(path) ? path.split("/").map(encodeURIComponent).join("/") : null;
}

export const repositoryUrl = (name: RepositoryName): string =>
  `https://github.com/${encodeURIComponent(name.owner)}/${encodeURIComponent(name.repo)}`;

/** The folder on github.com, on the repository's default branch (`HEAD`). */
export function folderUrl(name: RepositoryName, folder: string): string {
  const p = folder === "" ? null : encodePath(folder);
  return p ? `${repositoryUrl(name)}/tree/HEAD/${p}` : repositoryUrl(name);
}

/** A file's history on github.com: who saved it, and when. */
export function historyUrl(name: RepositoryName, path: string): string {
  const p = encodePath(path);
  return p ? `${repositoryUrl(name)}/commits/HEAD/${p}` : repositoryUrl(name);
}

/** A commit on github.com, built from its checked id (never a link GitHub's answer hands us). */
export function commitUrl(name: RepositoryName, sha: string): string | null {
  return GIT_SHA.test(sha) ? `${repositoryUrl(name)}/commit/${sha}` : null;
}

/**
 * GitHub's page for a new fine-grained personal access token, filled in for poring-lab: the
 * repository owner as the resource owner, "Contents: Read and write", one year. The person still
 * picks the one repository. Parameters:
 * https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#pre-filling-fine-grained-personal-access-token-details-using-url-parameters
 */
export function newTokenUrl(owner: string | null): string {
  const params = new URLSearchParams({
    name: "poring-lab flows",
    description: "Save and load poring-lab flows",
    ...(owner && OWNER.test(owner) ? { target_name: owner } : {}),
    expires_in: "366",
    contents: "write",
  });
  return `https://github.com/settings/personal-access-tokens/new?${params.toString()}`;
}
