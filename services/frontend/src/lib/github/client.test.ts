// The GitHub client against a MOCKED fetch (no network): the request shape, the tree listing, the
// size checks, Base64 with Thai, and the errors. Ported from MatPilot's src/lib/github/client.test.ts
// at 4022c87 (MIT, Copyright (c) 2026 Sarat Sonsuk), in node:test, plus ours.
import assert from "node:assert/strict";
import { test } from "node:test";

import { GitHubClient, GitHubError, MAX_READ_BYTES } from "./client.ts";
import { blob, dir, fakeFetch, fileReply, type Reply, repoReply, sha, treeReply } from "./testkit.ts";

const REPO = { owner: "teacher-class", repo: "flows" };
const API = "https://api.github.com/repos/teacher-class/flows";

const rejects = async (p: Promise<unknown>, kind: string, msg?: RegExp): Promise<GitHubError> => {
  const e = await p.then(
    () => assert.fail("expected an error"),
    (x: unknown) => x,
  );
  assert.ok(e instanceof GitHubError, String(e));
  assert.equal(e.kind, kind, e.message);
  if (msg) assert.match(e.message, msg);
  return e;
};

test("every request: the token only as Bearer, the API version, no cache, no cookies, no referrer", async () => {
  const { fetch, calls } = fakeFetch(repoReply({ private: true, permissions: { push: true } }));
  const client = new GitHubClient({ repository: REPO, token: " github_pat_x ", fetch });
  assert.equal(calls.length, 0); // a client makes no request until it is asked
  assert.deepEqual(await client.getRepository(), { fullName: "teacher-class/flows", private: true, canPush: true, defaultBranch: "main" });
  assert.equal(calls[0].url, API);
  const init = calls[0].init;
  assert.deepEqual(
    { method: init.method, cache: init.cache, credentials: init.credentials, referrerPolicy: init.referrerPolicy, body: init.body },
    { method: "GET", cache: "no-store", credentials: "omit", referrerPolicy: "no-referrer", body: undefined },
  );
  assert.deepEqual(init.headers, { Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", Authorization: "Bearer github_pat_x" });
});

test("no token, no Authorization header: public repositories load without one", async () => {
  const { fetch, calls } = fakeFetch(repoReply({ permissions: { push: false } }));
  const client = new GitHubClient({ repository: REPO, token: "  ", fetch });
  assert.equal(client.hasToken, false);
  assert.deepEqual(await client.getRepository(), { fullName: "teacher-class/flows", private: false, canPush: null, defaultBranch: "main" });
  assert.ok(!("Authorization" in (calls[0].init.headers as Record<string, string>)));
});

test("the folder is listed with the Git Trees API: the branch's tree, then the folder's sub-tree", async () => {
  const { fetch, calls } = fakeFetch(
    repoReply(),
    treeReply([blob("README.md"), dir("poring-lab", sha("c")), dir("other")]),
    treeReply([
      blob("ฟาร์ม.flow.json", 812, sha("f")),
      blob("notes.md", 3),
      dir("old"),
      { path: "link.flow.json", mode: "120000", type: "blob", sha: sha("9"), size: 9 }, // a symlink
      { path: "sub", mode: "160000", type: "commit", sha: sha("8") }, // a submodule
      { path: "..", mode: "100644", type: "blob", sha: sha("7"), size: 1 },
      { path: "a/b.flow.json", mode: "100644", type: "blob", sha: sha("6"), size: 1 },
      { path: "bad.flow.json", mode: "100644", type: "blob", sha: "zzz", size: 1 },
    ]),
  );
  const client = new GitHubClient({ repository: REPO, token: null, fetch });
  assert.deepEqual(await client.listFolder("poring-lab"), {
    entries: [
      { name: "ฟาร์ม.flow.json", path: "poring-lab/ฟาร์ม.flow.json", sha: sha("f"), size: 812 },
      { name: "notes.md", path: "poring-lab/notes.md", sha: sha("b"), size: 3 },
    ],
    truncated: false,
  });
  assert.deepEqual(
    calls.map((c) => c.url),
    [API, `${API}/git/trees/main`, `${API}/git/trees/${sha("c")}`],
  );
  assert.ok(calls.every((c) => c.init.method === "GET" && c.init.cache === "no-store"));
});

test("a nested Thai folder walks one sub-tree a level; the branch saved by Check and save skips a request", async () => {
  const { fetch, calls } = fakeFetch(treeReply([dir("ห้อง 1", sha("1"))]), treeReply([dir("นักเรียน", sha("2"))]), treeReply([blob("a.flow.json")]));
  const client = new GitHubClient({ repository: REPO, token: null, branch: "trunk", fetch });
  const out = await client.listFolder("ห้อง 1/นักเรียน");
  assert.deepEqual(out.entries.map((e) => e.path), ["ห้อง 1/นักเรียน/a.flow.json"]);
  assert.deepEqual(calls.map((c) => c.url), [`${API}/git/trees/trunk`, `${API}/git/trees/${sha("1")}`, `${API}/git/trees/${sha("2")}`]);
});

test("TRUNCATED is said plainly: never a partial list that looks complete", async () => {
  const last = fakeFetch(repoReply(), treeReply([dir("poring-lab", sha("c"))]), treeReply([blob("a.flow.json"), blob("b.flow.json")], true));
  assert.deepEqual(await new GitHubClient({ repository: REPO, token: null, fetch: last.fetch }).listFolder("poring-lab"), { entries: [], truncated: true });
  // the root was cut and the folder is not in the part we got: we cannot say it is missing
  const root = fakeFetch(repoReply(), treeReply([blob("x")], true));
  assert.deepEqual(await new GitHubClient({ repository: REPO, token: null, fetch: root.fetch }).listFolder("poring-lab"), { entries: [], truncated: true });
});

test("a folder not made yet, and an empty repository, list as empty; a missing repository says so", async () => {
  const missing = fakeFetch(repoReply(), treeReply([blob("README.md")]));
  assert.deepEqual(await new GitHubClient({ repository: REPO, token: null, fetch: missing.fetch }).listFolder("poring-lab"), { entries: [], truncated: false });
  const empty = fakeFetch(repoReply(), { status: 409, body: { message: "Git Repository is empty." } }, repoReply());
  assert.deepEqual(await new GitHubClient({ repository: REPO, token: "t", fetch: empty.fetch }).listFolder("poring-lab"), { entries: [], truncated: false });
  const gone = fakeFetch({ status: 404 });
  await rejects(new GitHubClient({ repository: REPO, token: "t", fetch: gone.fetch }).listFolder("poring-lab"), "not-found", /no repository teacher-class\/flows that this token can open/);
  const renamed = fakeFetch({ status: 404 }, repoReply({ default_branch: "main" }), treeReply([blob("a.flow.json")]));
  const c = new GitHubClient({ repository: REPO, token: null, branch: "master", fetch: renamed.fetch });
  assert.deepEqual((await c.listFolder("")).entries.map((e) => e.path), ["a.flow.json"]); // a renamed branch: asked again
  assert.deepEqual(renamed.calls.map((x) => x.url), [`${API}/git/trees/master`, API, `${API}/git/trees/main`]);
});

test("no '.' or '..' ever reaches a URL: unsafe paths are refused before any request", async () => {
  const { fetch, calls } = fakeFetch();
  const client = new GitHubClient({ repository: REPO, token: "t", fetch });
  for (const path of ["../secrets", "a/../../b", "./a", "a//b", "a\\b", "", "a/\u0000"]) {
    await rejects(client.readFile(path), "invalid");
    await rejects(client.writeFile({ path, text: "x", message: "m", sha: null }), "invalid");
  }
  await rejects(client.listFolder("a/../b"), "invalid");
  assert.equal(calls.length, 0);
});

test("a file is read as UTF-8 (Thai in GitHub's wrapped Base64), or null when it is missing", async () => {
  const text = '{"name":"ฟาร์ม 🐷"}\n';
  const { fetch, calls } = fakeFetch(fileReply("poring-lab/ฟาร์ม.flow.json", text), { status: 404 });
  const client = new GitHubClient({ repository: REPO, token: null, fetch });
  assert.deepEqual(await client.readFile("poring-lab/ฟาร์ม.flow.json"), { path: "poring-lab/ฟาร์ม.flow.json", sha: sha("1"), text });
  assert.equal(calls[0].url, `${API}/contents/poring-lab/%E0%B8%9F%E0%B8%B2%E0%B8%A3%E0%B9%8C%E0%B8%A1.flow.json`);
  assert.equal(await client.readFile("poring-lab/gone.flow.json"), null);
});

test("the size is checked BEFORE the content is read: GitHub's size, then the Base64's length", async () => {
  const big = { status: 200, body: { type: "file", path: "a.flow.json", sha: sha("2"), size: MAX_READ_BYTES + 1, encoding: "base64", content: "" } };
  const one = fakeFetch(big);
  await rejects(new GitHubClient({ repository: REPO, token: null, fetch: one.fetch }).readFile("a.flow.json"), "too-large");
  assert.equal(one.left(), 0);
  // a size that lies: the Base64 itself is measured before it is decoded
  const content = Buffer.from("x".repeat(3000)).toString("base64");
  const lying = fakeFetch({ status: 200, body: { type: "file", path: "a", sha: sha("2"), size: 10, encoding: "base64", content } });
  await rejects(new GitHubClient({ repository: REPO, token: null, fetch: lying.fetch }).readFile("a", 2000), "too-large");
  const notUtf8 = fakeFetch({ status: 200, body: { type: "file", path: "a", sha: sha("2"), size: 3, encoding: "base64", content: Buffer.from([0xff, 0xfe, 0]).toString("base64") } });
  await rejects(new GitHubClient({ repository: REPO, token: null, fetch: notUtf8.fetch }).readFile("a"), "invalid", /not a text file/);
});

test("a file of 1 to 2 MB comes raw (Accept: raw), keeping the sha of the first answer", async () => {
  const text = `{"name":"ใหญ่"}${" ".repeat(1_100_000)}`;
  const { fetch, calls } = fakeFetch(
    { status: 200, body: { type: "file", path: "a.flow.json", sha: sha("3"), size: Buffer.byteLength(text), encoding: "none", content: "" } },
    { status: 200, raw: text },
  );
  const client = new GitHubClient({ repository: REPO, token: "t", fetch });
  assert.deepEqual(await client.readFile("a.flow.json"), { path: "a.flow.json", sha: sha("3"), text });
  assert.deepEqual(
    calls.map((c) => (c.init.headers as Record<string, string>).Accept),
    ["application/vnd.github+json", "application/vnd.github.raw+json"],
  );
  // larger than our cap: refused before the raw request
  const huge = fakeFetch({ status: 200, body: { type: "file", path: "a", sha: sha("3"), size: 13_000_000, encoding: "none", content: "" } });
  await rejects(new GitHubClient({ repository: REPO, token: "t", fetch: huge.fetch }).readFile("a"), "too-large");
  assert.equal(huge.calls.length, 1);
});

test("a folder or a symlink where a file is expected is refused; a file where the folder should be lists nothing", async () => {
  const { fetch } = fakeFetch({ status: 200, body: [] }, { status: 200, body: { type: "symlink", path: "x", sha: sha("4") } });
  const client = new GitHubClient({ repository: REPO, token: null, fetch });
  await rejects(client.readFile("x"), "invalid", /not a file/);
  await rejects(client.readFile("x"), "invalid", /not a file/);
  const asFile = fakeFetch(repoReply(), treeReply([blob("poring-lab")]));
  assert.deepEqual(await new GitHubClient({ repository: REPO, token: null, fetch: asFile.fetch }).listFolder("poring-lab"), { entries: [], truncated: false });
});

test("writing: one PUT, Thai content as UTF-8 Base64, the sha it replaces; the commit link is built, not taken", async () => {
  const { fetch, calls } = fakeFetch({
    status: 200,
    body: { content: { sha: sha("5") }, commit: { sha: sha("6"), html_url: "https://evil.example/phish" } },
  });
  const client = new GitHubClient({ repository: REPO, token: "t", fetch });
  const saved = await client.writeFile({ path: "poring-lab/ฟาร์ม 2.flow.json", text: "ฟาร์ม", message: "Update ฟาร์ม", sha: sha("a") });
  assert.deepEqual(saved, { sha: sha("5"), commitUrl: `https://github.com/teacher-class/flows/commit/${sha("6")}` });
  assert.equal(calls[0].url, `${API}/contents/poring-lab/%E0%B8%9F%E0%B8%B2%E0%B8%A3%E0%B9%8C%E0%B8%A1%202.flow.json`);
  assert.equal(calls[0].init.method, "PUT");
  assert.equal((calls[0].init.headers as Record<string, string>)["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(String(calls[0].init.body)), { message: "Update ฟาร์ม", content: Buffer.from("ฟาร์ม").toString("base64"), sha: sha("a") });
  // a new file: no sha
  const created = fakeFetch({ status: 201, body: { content: { sha: sha("5") }, commit: {} } });
  await new GitHubClient({ repository: REPO, token: "t", fetch: created.fetch }).writeFile({ path: "a.flow.json", text: "{}", message: "Add a", sha: null });
  assert.ok(!("sha" in JSON.parse(String(created.calls[0].init.body))));
});

test("saving needs a token; no request is made without one", async () => {
  const { fetch, calls } = fakeFetch();
  await rejects(new GitHubClient({ repository: REPO, token: null, fetch }).writeFile({ path: "a", text: "", message: "m", sha: null }), "token");
  assert.equal(calls.length, 0);
});

test("errors map as MatPilot's: 401, 403, 404, 409, 422 (sha or not), 429, the rate limit, the network", async () => {
  const cases: [string, Reply | Error, string][] = [
    ["network", new TypeError("Failed to fetch"), "network"],
    ["401", { status: 401, body: { message: "Bad credentials" } }, "token"],
    ["403 rate limit", { status: 403, headers: { "x-ratelimit-remaining": "0", "x-ratelimit-reset": "1800000000" } }, "rate-limit"],
    ["403 secondary limit", { status: 403, headers: { "retry-after": "60" }, body: { message: "You have exceeded a secondary rate limit" } }, "rate-limit"],
    ["429", { status: 429 }, "rate-limit"],
    ["403", { status: 403, body: { message: "Resource not accessible by personal access token" } }, "forbidden"],
    ["409", { status: 409, body: { message: "x does not match y" } }, "conflict"],
    ["422 sha", { status: 422, body: { message: "Invalid request.\n\n\"sha\" wasn't supplied." } }, "conflict"],
    ["422", { status: 422, body: { message: "path is invalid" } }, "invalid"],
    ["500", { status: 500 }, "other"],
  ];
  for (const [label, reply, kind] of cases) {
    const { fetch } = fakeFetch(reply);
    const client = new GitHubClient({ repository: REPO, token: "x", fetch });
    const e = await rejects(client.writeFile({ path: "a", text: "", message: "m", sha: null }), kind);
    assert.ok(e.message.length > 0 && !e.message.includes("\n"), label);
  }
});

test("the rate limit says when GitHub allows requests again (x-ratelimit-reset)", async () => {
  const { fetch } = fakeFetch({ status: 403, headers: { "x-ratelimit-remaining": "0", "x-ratelimit-reset": "1800000000" } });
  const e = await rejects(new GitHubClient({ repository: REPO, token: null, fetch }).getRepository(), "rate-limit", /without a token/);
  assert.equal(e.retryAt?.toISOString(), "2027-01-15T08:00:00.000Z");
  const withToken = fakeFetch({ status: 429, headers: { "x-ratelimit-reset": "1800000000" } });
  await rejects(new GitHubClient({ repository: REPO, token: "t", fetch: withToken.fetch }).getRepository(), "rate-limit", /too many requests/);
});
