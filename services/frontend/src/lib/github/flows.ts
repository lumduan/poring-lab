// Flows in a GitHub folder (docs/planning/flows-save-load.md section 3): list them, and save one
// WITHOUT silently replacing a classmate's work (the sha compare-and-swap).
//
// Ported from MatPilot (MIT), src/lib/github/programs.ts at 4022c87
// (https://github.com/lumduan/matpilot, Copyright (c) 2026 Sarat Sonsuk; the licence text is in
// components/flowfile/flowfile.css and THIRD_PARTY.md). Ours: the truncated listing, the byte cap in
// nextFreeName, the cleaned note and author.
import { cleanSavedBy, fitText, flowNameFromFileName, isFlowFileName, NAME_MAX_BYTES, NAME_MAX_CHARS, utf8Bytes } from "../flow/file.ts";
import { type GitHubClient, GitHubError } from "./client.ts";

export type RemoteFlow = { readonly name: string; readonly path: string; readonly sha: string; readonly size: number };
export type FlowListing = { readonly flows: readonly RemoteFlow[]; readonly truncated: boolean };

/** The flow files in `folder`, by name, as people sort (Thai too). */
export async function listFlows(client: GitHubClient, folder: string): Promise<FlowListing> {
  const listing = await client.listFolder(folder);
  const flows = listing.entries
    .filter((e) => isFlowFileName(e.name))
    .map((e) => ({ name: flowNameFromFileName(e.name), path: e.path, sha: e.sha, size: e.size }))
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" }));
  return { flows, truncated: listing.truncated };
}

export type SaveOutcome =
  | { readonly kind: "saved"; readonly sha: string; readonly commitUrl: string | null; readonly created: boolean }
  /** "exists": a file with this name is there already; "changed": it changed since it was opened. */
  | { readonly kind: "conflict"; readonly reason: "exists" | "changed" };

/**
 * Saves `text` at `path`. The file there is replaced only when it is the version this flow was
 * opened from or last saved as (`expectedSha`), or when `replace` is set after the person agreed
 * to it; otherwise the outcome is a conflict and NOTHING is written.
 */
export async function saveFlow(
  client: GitHubClient,
  args: {
    readonly path: string;
    readonly text: string;
    /** The commit message, given whether the file is new. */
    readonly message: (created: boolean) => string;
    readonly expectedSha: string | null;
    readonly replace: boolean;
  },
): Promise<SaveOutcome> {
  const current = await client.readFile(args.path);
  if (current && !args.replace && current.sha !== args.expectedSha) {
    return { kind: "conflict", reason: args.expectedSha ? "changed" : "exists" };
  }
  try {
    const saved = await client.writeFile({ path: args.path, text: args.text, message: args.message(current === null), sha: current?.sha ?? null });
    return { kind: "saved", ...saved, created: current === null };
  } catch (e) {
    // someone saved between our read and our write (409, or a 422 about the sha)
    if (e instanceof GitHubError && e.kind === "conflict") return { kind: "conflict", reason: "changed" };
    throw e;
  }
}

/** The commit message: the person's note, or "Add/Update <name>", who saved it, and where from. */
export function commitMessage(args: { readonly name: string; readonly created: boolean; readonly note: string; readonly author: string }): string {
  const note = fitText(oneLine(args.note), NOTE_MAX_CHARS, 4 * NOTE_MAX_CHARS).trim();
  const author = cleanSavedBy(args.author);
  const subject = note || `${args.created ? "Add" : "Update"} ${args.name}`;
  return `${subject}${author ? ` (saved by ${author})` : ""}\n\nSaved from poring-lab.`;
}

export const NOTE_MAX_CHARS = 100;

/** One line: no control characters or bidi overrides, spaces collapsed. */
const oneLine = (text: string): string =>
  text
    .slice(0, 4 * NOTE_MAX_CHARS)
    .normalize("NFC")
    .replace(/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();

/** "name 2", "name 3", ...: the first not taken (names compare without case), each within the name
 * caps (60 characters, 180 bytes). */
export function nextFreeName(name: string, taken: readonly string[]): string {
  const used = new Set(taken.map((t) => t.normalize("NFC").toLowerCase()));
  const base = name.replace(/ \d+$/, "");
  for (let n = 2; n < 10_000; n++) {
    const suffix = ` ${n}`;
    const head = fitText(base, NAME_MAX_CHARS - suffix.length, NAME_MAX_BYTES - utf8Bytes(suffix)).trim();
    const candidate = `${head}${suffix}`;
    if (!used.has(candidate.normalize("NFC").toLowerCase())) return candidate;
  }
  return `${fitText(base, NAME_MAX_CHARS - 14, NAME_MAX_BYTES - 14).trim()} ${Date.now()}`;
}
