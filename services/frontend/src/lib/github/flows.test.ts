// Flows in a GitHub folder, and the sha compare-and-swap that never silently replaces a classmate's
// work. Ported from MatPilot's src/lib/github/programs.test.ts at 4022c87 (MIT, Copyright (c) 2026
// Sarat Sonsuk), in node:test, plus the same paths end to end through a MOCKED fetch.
import assert from "node:assert/strict";
import { test } from "node:test";

import { utf8Bytes } from "../flow/file.ts";
import { GitHubClient, GitHubError, type SavedFile } from "./client.ts";
import { describeGitHubError, describeSaved, describeSize } from "./describe.ts";
import { commitMessage, listFlows, nextFreeName, saveFlow } from "./flows.ts";
import { blob, dir, fakeFetch, fileReply, repoReply, sha, treeReply } from "./testkit.ts";

const REPO = { owner: "teacher-class", repo: "flows" };
const message = (created: boolean) => (created ? "Add" : "Update");
const base = { path: "poring-lab/a.flow.json", text: "{}", message, replace: false };

type Overrides = Partial<Pick<GitHubClient, "listFolder" | "readFile" | "writeFile">>;
type WriteArgs = Parameters<GitHubClient["writeFile"]>[0];
function clientWith(over: Overrides): GitHubClient {
  const c = new GitHubClient({ repository: REPO, token: "x", fetch: () => Promise.reject(new Error("no network in tests")) });
  return Object.assign(c, over);
}
/** A writeFile that records what it was asked to write. */
function recorder(saved: SavedFile) {
  const calls: WriteArgs[] = [];
  return { calls, fn: async (a: WriteArgs): Promise<SavedFile> => (calls.push(a), saved) };
}

test("listFlows keeps flow files, named and sorted as people sort (Thai too); truncated passes through", async () => {
  const client = clientWith({
    listFolder: async () => ({
      entries: [
        { name: "farm 10.flow.json", path: "p/farm 10.flow.json", sha: "a", size: 3 },
        { name: "README.md", path: "p/README.md", sha: "b", size: 1 },
        { name: "Farm 9.flow.json", path: "p/Farm 9.flow.json", sha: "c", size: 2 },
        { name: "ฟาร์ม.flow.json", path: "p/ฟาร์ม.flow.json", sha: "d", size: 1 },
        { name: "alberta.flow.json", path: "p/alberta.flow.json", sha: "e", size: 1 },
        { name: ".flow.json", path: "p/.flow.json", sha: "f", size: 1 },
      ],
      truncated: false,
    }),
  });
  const out = await listFlows(client, "p");
  assert.deepEqual(out.flows.map((f) => f.name), ["alberta", "Farm 9", "farm 10", "ฟาร์ม"]);
  assert.equal(out.truncated, false);
  const cut = clientWith({ listFolder: async () => ({ entries: [], truncated: true }) });
  assert.deepEqual(await listFlows(cut, "p"), { flows: [], truncated: true });
});

test("saveFlow creates a new file (no sha)", async () => {
  const w = recorder({ sha: "new", commitUrl: "u" });
  const client = clientWith({ readFile: async () => null, writeFile: w.fn });
  assert.deepEqual(await saveFlow(client, { ...base, expectedSha: null }), { kind: "saved", sha: "new", commitUrl: "u", created: true });
  assert.deepEqual(w.calls, [{ path: base.path, text: "{}", message: "Add", sha: null }]);
});

test("saveFlow replaces the version it was opened from (the sha matches)", async () => {
  const w = recorder({ sha: "new", commitUrl: null });
  const client = clientWith({ readFile: async () => ({ path: base.path, sha: "mine", text: "" }), writeFile: w.fn });
  assert.deepEqual(await saveFlow(client, { ...base, expectedSha: "mine" }), { kind: "saved", sha: "new", commitUrl: null, created: false });
  assert.equal(w.calls[0].sha, "mine");
  assert.equal(w.calls[0].message, "Update");
});

test("NEVER silently replaces: a file with the same name, or a classmate's newer version, is a conflict and nothing is written", async () => {
  const w = recorder({ sha: "x", commitUrl: null });
  const client = clientWith({ readFile: async () => ({ path: base.path, sha: "theirs", text: "" }), writeFile: w.fn });
  assert.deepEqual(await saveFlow(client, { ...base, expectedSha: null }), { kind: "conflict", reason: "exists" });
  assert.deepEqual(await saveFlow(client, { ...base, expectedSha: "mine" }), { kind: "conflict", reason: "changed" });
  assert.equal(w.calls.length, 0);
});

test("'Replace it' writes over the version just read, once the person agreed", async () => {
  const w = recorder({ sha: "new", commitUrl: null });
  const client = clientWith({ readFile: async () => ({ path: base.path, sha: "theirs", text: "" }), writeFile: w.fn });
  await saveFlow(client, { ...base, expectedSha: "mine", replace: true });
  assert.equal(w.calls[0].sha, "theirs");
});

test("a save that races another (409, or a 422 about the sha) is a conflict; other errors pass on", async () => {
  for (const status of [409, 422]) {
    const client = clientWith({ readFile: async () => null, writeFile: async () => Promise.reject(new GitHubError("conflict", "x", status)) });
    assert.deepEqual(await saveFlow(client, { ...base, expectedSha: null }), { kind: "conflict", reason: "changed" });
  }
  const bad = clientWith({ readFile: async () => Promise.reject(new GitHubError("token", "bad token", 401)) });
  await assert.rejects(saveFlow(bad, { ...base, expectedSha: null }), (e: unknown) => e instanceof GitHubError && e.kind === "token");
});

test("end to end through a mocked fetch: read first, then PUT with the sha; a 409 between them is a conflict", async () => {
  const path = "poring-lab/ฟาร์ม.flow.json";
  const ok = fakeFetch(fileReply(path, "{}", sha("a")), { status: 200, body: { content: { sha: sha("b") }, commit: { sha: sha("c") } } });
  const client = new GitHubClient({ repository: REPO, token: "t", fetch: ok.fetch });
  const out = await saveFlow(client, { path, text: '{"a":"ไทย"}', message, expectedSha: sha("a"), replace: false });
  assert.equal(out.kind, "saved");
  assert.deepEqual(ok.calls.map((c) => c.init.method), ["GET", "PUT"]);
  assert.equal(JSON.parse(String(ok.calls[1].init.body)).sha, sha("a"));
  // someone saved between our read and our write
  const raced = fakeFetch(fileReply(path, "{}", sha("a")), { status: 409, body: { message: "is at abc but expected def" } });
  const c2 = new GitHubClient({ repository: REPO, token: "t", fetch: raced.fetch });
  assert.deepEqual(await saveFlow(c2, { path, text: "{}", message, expectedSha: sha("a"), replace: false }), { kind: "conflict", reason: "changed" });
  // a classmate's newer file: one GET, no PUT
  const newer = fakeFetch(fileReply(path, "{}", sha("d")));
  const c3 = new GitHubClient({ repository: REPO, token: "t", fetch: newer.fetch });
  assert.deepEqual(await saveFlow(c3, { path, text: "{}", message, expectedSha: sha("a"), replace: false }), { kind: "conflict", reason: "changed" });
  assert.deepEqual(newer.calls.map((c) => c.init.method), ["GET"]);
  // and the folder lists through the trees API as the Load dialog shows it
  const list = fakeFetch(repoReply(), treeReply([dir("poring-lab", sha("e"))]), treeReply([blob("ฟาร์ม.flow.json", 900, sha("d"))]));
  const listed = await listFlows(new GitHubClient({ repository: REPO, token: null, fetch: list.fetch }), "poring-lab");
  assert.deepEqual(listed.flows, [{ name: "ฟาร์ม", path, sha: sha("d"), size: 900 }]);
});

test("commit messages: the note or Add/Update, who saved it, and 'Saved from poring-lab.'", () => {
  assert.equal(commitMessage({ name: "Farm", created: true, note: "", author: "" }), "Add Farm\n\nSaved from poring-lab.");
  assert.equal(commitMessage({ name: "Farm", created: false, note: " faster\nloot ", author: " Ploy " }), "faster loot (saved by Ploy)\n\nSaved from poring-lab.");
  assert.equal(commitMessage({ name: "ฟาร์ม", created: false, note: "", author: "สมชาย" }), "Update ฟาร์ม (saved by สมชาย)\n\nSaved from poring-lab.");
  const long = commitMessage({ name: "x", created: true, note: "n".repeat(500), author: "a\u202eb" });
  assert.ok(long.startsWith(`${"n".repeat(100)} (saved by a b)`));
});

test("the next free name: 'name 2', 'name 3' ..., within 60 characters and 180 bytes", () => {
  assert.equal(nextFreeName("Farm", ["farm", "Farm 2"]), "Farm 3");
  assert.equal(nextFreeName("Farm 2", ["Farm", "Farm 2"]), "Farm 3");
  assert.equal(nextFreeName("x".repeat(60), []), `${"x".repeat(58)} 2`);
  const thai = nextFreeName("ก".repeat(60), []);
  assert.ok(utf8Bytes(thai) <= 180 && thai.endsWith(" 2"), thai);
  assert.equal(thai, `${"ก".repeat(58)} 2`); // the character cap binds: 58 + 2 = 60 characters, 176 bytes
  assert.equal(nextFreeName("🐷".repeat(45), []), `${"🐷".repeat(44)} 2`); // the byte cap binds: 4 x 44 + 2 = 178 bytes, 46 characters
  assert.equal(nextFreeName("ฟาร์ม", ["ฟาร์ม", "ฟาร์ม 2"]), "ฟาร์ม 3");
});

test("the words: errors with the time GitHub allows requests again, who saved a file, sizes", () => {
  const e = new GitHubError("rate-limit", "Wait.", 429, new Date("2027-01-15T08:00:00Z"));
  assert.match(describeGitHubError(e), /^Wait\. \(GitHub allows it again at .+\.\)$/);
  assert.equal(describeGitHubError(new GitHubError("token", "Bad token.")), "Bad token.");
  assert.equal(describeGitHubError(new Error("x")), "x");
  assert.equal(describeGitHubError("??"), "Something went wrong.");
  assert.equal(describeSaved("", ""), "");
  assert.equal(describeSaved("Ploy", "not a time"), "Ploy");
  assert.ok(describeSaved("Ploy", "2026-11-12T04:12:00Z").startsWith("Ploy, "));
  assert.deepEqual([describeSize(10), describeSize(2355), describeSize(1_700_000)], ["10 B", "2.3 KB", "1.6 MB"]);
});
