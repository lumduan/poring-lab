// Ported from MatPilot's src/lib/github/repository.test.ts at 4022c87 (MIT, Copyright (c) 2026
// Sarat Sonsuk), in node:test, plus ours: safePath, Windows-refused folder characters, commitUrl.
import assert from "node:assert/strict";
import { test } from "node:test";

import { cleanFolder, commitUrl, encodePath, folderUrl, historyUrl, joinPath, newTokenUrl, parseRepository, safePath } from "./repository.ts";

test("the repository: owner/name, links and SSH addresses", () => {
  const want = { owner: "teacher-class", repo: "flows" };
  for (const input of [
    "teacher-class/flows",
    " teacher-class/flows ",
    "https://github.com/teacher-class/flows",
    "https://github.com/teacher-class/flows.git",
    "github.com/teacher-class/flows/tree/main/poring-lab",
    "http://www.github.com/teacher-class/flows?tab=readme",
    "git@github.com:teacher-class/flows.git",
  ]) {
    assert.deepEqual(parseRepository(input), want, input);
  }
  assert.deepEqual(parseRepository("lumduan/my.repo_1"), { owner: "lumduan", repo: "my.repo_1" });
});

test("what cannot be a repository is refused (by regex, before any request)", () => {
  for (const input of ["", "teacher-class", "-team/x", "team-/x", "te--am/x", "a/..", "a/.", "a b/c", "a/b c", "ห้อง/flows", "a/b%2F..", "x".repeat(301), "https://gitlab.com/a/b"]) {
    assert.equal(parseRepository(input), null, input);
  }
});

test("folders: cleaned, NFC; '.', '..', backslashes, controls and what Windows refuses are refused", () => {
  assert.equal(cleanFolder(" poring-lab "), "poring-lab");
  assert.equal(cleanFolder("/class 1/ห้อง 2/"), "class 1/ห้อง 2");
  assert.equal(cleanFolder(""), "");
  assert.equal(cleanFolder("Café"), "Café");
  for (const bad of ["a/../b", "./a", "..", "a\\b", "a\u0000b", "a:b", "a*b", "a?b", 'a"b', "a<b", "a|b", "x".repeat(201)]) {
    assert.equal(cleanFolder(bad), null, bad);
  }
  assert.equal(joinPath("", "x.flow.json"), "x.flow.json");
  assert.equal(joinPath("a/b", "x.flow.json"), "a/b/x.flow.json");
});

test("no '.' / '..' segment ever reaches a URL; every segment is encodeURIComponent'd", () => {
  for (const ok of ["a", "a/b.flow.json", "ห้อง/ฟาร์ม.flow.json", "a b/%2e%2e"]) assert.ok(safePath(ok), ok);
  for (const bad of ["", ".", "..", "a/..", "../a", "a/./b", "a//b", "/a", "a/", "a\\b", "a/\u0007"]) assert.ok(!safePath(bad), bad);
  assert.equal(encodePath("ห้อง 1/a?b#c.flow.json"), "%E0%B8%AB%E0%B9%89%E0%B8%AD%E0%B8%87%201/a%3Fb%23c.flow.json");
  assert.equal(encodePath("a b/%2e%2e"), "a%20b/%252e%252e"); // an encoded dot-dot stays a plain name
  assert.equal(encodePath("a/../b"), null);
});

test("links to the folder, a file's history, a commit, and the prefilled token page", () => {
  const name = { owner: "teacher-class", repo: "flows" };
  assert.equal(folderUrl(name, ""), "https://github.com/teacher-class/flows");
  assert.equal(folderUrl(name, "class/room 1"), "https://github.com/teacher-class/flows/tree/HEAD/class/room%201");
  assert.equal(historyUrl(name, "poring-lab/รถ.flow.json"), "https://github.com/teacher-class/flows/commits/HEAD/poring-lab/%E0%B8%A3%E0%B8%96.flow.json");
  assert.equal(historyUrl(name, "../x"), "https://github.com/teacher-class/flows");
  assert.equal(commitUrl(name, "a".repeat(40)), `https://github.com/teacher-class/flows/commit/${"a".repeat(40)}`);
  assert.equal(commitUrl(name, "javascript:alert(1)"), null);
  const url = new URL(newTokenUrl("teacher-class"));
  assert.equal(url.origin + url.pathname, "https://github.com/settings/personal-access-tokens/new");
  assert.deepEqual(Object.fromEntries(url.searchParams), {
    name: "poring-lab flows",
    description: "Save and load poring-lab flows",
    target_name: "teacher-class",
    expires_in: "366",
    contents: "write",
  });
  assert.ok(!new URL(newTokenUrl(null)).searchParams.has("target_name"));
  assert.ok(!new URL(newTokenUrl("a b&x=1")).searchParams.has("target_name"));
});
