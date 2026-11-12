// A fetch for the GitHub tests: it answers with the replies in order and records every request.
// Nothing here touches the network.
import type { FetchLike } from "./client.ts";

export type Reply = { readonly status: number; readonly body?: unknown; readonly raw?: string; readonly headers?: Record<string, string> };
export type Call = { readonly url: string; readonly init: RequestInit };

export function fakeFetch(...replies: (Reply | Error)[]): { fetch: FetchLike; calls: Call[]; left: () => number } {
  const calls: Call[] = [];
  const fetch: FetchLike = (url, init) => {
    calls.push({ url, init });
    const reply = replies.shift();
    if (!reply) return Promise.reject(new Error(`unexpected request ${init.method} ${url}`));
    if (reply instanceof Error) return Promise.reject(reply);
    const body = reply.raw !== undefined ? reply.raw : reply.body === undefined ? null : JSON.stringify(reply.body);
    return Promise.resolve(new Response(body, { status: reply.status, headers: reply.headers }));
  };
  return { fetch, calls, left: () => replies.length };
}

export const sha = (c: string): string => c.repeat(40);

/** The contents API's answer for a text file, Base64 in GitHub's 60-character lines. */
export const fileReply = (path: string, text: string, fileSha = sha("1")): Reply => ({
  status: 200,
  body: {
    type: "file",
    path,
    sha: fileSha,
    size: Buffer.byteLength(text),
    encoding: "base64",
    content: Buffer.from(text).toString("base64").replace(/(.{60})/g, "$1\n"),
  },
});

export const repoReply = (over: Record<string, unknown> = {}): Reply => ({
  status: 200,
  body: { full_name: "teacher-class/flows", private: false, default_branch: "main", ...over },
});

export const treeReply = (entries: unknown[], truncated = false): Reply => ({ status: 200, body: { sha: sha("e"), tree: entries, truncated } });
export const blob = (path: string, size = 10, s = sha("b")) => ({ path, mode: "100644", type: "blob", sha: s, size });
export const dir = (path: string, s = sha("d")) => ({ path, mode: "040000", type: "tree", sha: s });
