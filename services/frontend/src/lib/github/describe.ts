// Words for the Save and Load dialogs: GitHub's errors, who saved a file and when, a file's size.
// Rendered as TEXT only.
//
// Ported from MatPilot (MIT), src/components/blocks/describe.ts at 4022c87
// (https://github.com/lumduan/matpilot, Copyright (c) 2026 Sarat Sonsuk; the licence text is in
// components/flowfile/flowfile.css and THIRD_PARTY.md).
import { GitHubError } from "./client.ts";

/** A message for a person from anything a GitHub call threw. */
export function describeGitHubError(error: unknown): string {
  if (error instanceof GitHubError) {
    if (error.kind === "rate-limit" && error.retryAt) {
      const time = error.retryAt.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
      return `${error.message} (GitHub allows it again at ${time}.)`;
    }
    return error.message;
  }
  return error instanceof Error ? error.message : "Something went wrong.";
}

/** "Ploy, 12 Nov 10:42": who saved a flow and when, from its file; "" when unknown. */
export function describeSaved(savedBy: string, savedAt: string): string {
  const time = savedAt ? new Date(savedAt) : null;
  const when =
    time && !Number.isNaN(time.getTime()) ? time.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
  return [savedBy, when].filter(Boolean).join(", ");
}

/** "2.3 KB", "1.6 MB". */
export function describeSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
