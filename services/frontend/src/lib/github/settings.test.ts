// THE TOKEN STORE (flows-save-load.md section 3): this tab only (sessionStorage) by default,
// localStorage ONLY when a person ticks "Remember on this computer", memory when storage refuses,
// and "Forget the token" removes it everywhere.
import assert from "node:assert/strict";
import { test } from "node:test";

import type { StorageLike } from "../flow/prefs.ts";
import { DEFAULT_GITHUB_SETTINGS, GITHUB_KEYS, GitHubSettingsStore, parseSettings, tokenProblem } from "./settings.ts";

function memoryStore(): StorageLike & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return { data, getItem: (k) => data.get(k) ?? null, setItem: (k, v) => void data.set(k, v), removeItem: (k) => void data.delete(k) };
}
const blocked: StorageLike = {
  getItem: () => {
    throw new Error("blocked");
  },
  setItem: () => {
    throw new Error("blocked");
  },
  removeItem: () => {
    throw new Error("blocked");
  },
};
const setup = () => {
  const local = memoryStore();
  const session = memoryStore();
  return { local, session, store: new GitHubSettingsStore({ local: () => local, session: () => session }) };
};
const SETTINGS = { ...DEFAULT_GITHUB_SETTINGS, repository: "teacher-class/flows", author: "Ploy" };
const TOKEN = "github_pat_11ABCDEF0123456789";

test("by default the token stays in THIS TAB (sessionStorage), never in localStorage", () => {
  const { local, session, store } = setup();
  assert.equal(DEFAULT_GITHUB_SETTINGS.remember, false);
  store.save(SETTINGS, TOKEN);
  assert.equal(session.data.get(GITHUB_KEYS.token), TOKEN);
  assert.ok(!local.data.has(GITHUB_KEYS.token));
  assert.ok(![...local.data.values()].some((v) => v.includes(TOKEN)), "the settings never carry the token");
  assert.deepEqual(store.snapshot(), { settings: SETTINGS, token: TOKEN, where: "session" });
  assert.deepEqual(parseSettings(local.data.get(GITHUB_KEYS.settings) ?? null), SETTINGS);
});

test("localStorage ONLY when a person ticks Remember; unticking moves it back to this tab", () => {
  const { local, session, store } = setup();
  store.save({ ...SETTINGS, remember: true }, ` ${TOKEN} `);
  assert.equal(local.data.get(GITHUB_KEYS.token), TOKEN);
  assert.ok(!session.data.has(GITHUB_KEYS.token));
  assert.equal(store.snapshot().where, "local");
  store.save({ ...SETTINGS, remember: false }, null); // null keeps the token
  assert.ok(!local.data.has(GITHUB_KEYS.token));
  assert.equal(session.data.get(GITHUB_KEYS.token), TOKEN);
  assert.equal(store.snapshot().where, "session");
});

test("Forget the token removes it from memory, this tab and this computer; '' forgets it too", () => {
  const { local, session, store } = setup();
  store.save({ ...SETTINGS, remember: true }, TOKEN);
  local.setItem(GITHUB_KEYS.token, TOKEN);
  session.setItem(GITHUB_KEYS.token, TOKEN);
  store.forgetToken();
  assert.ok(!local.data.has(GITHUB_KEYS.token) && !session.data.has(GITHUB_KEYS.token));
  assert.equal(store.snapshot().token, null);
  assert.equal(store.snapshot().settings.repository, "teacher-class/flows"); // the settings stay
  store.save(SETTINGS, TOKEN);
  store.save(SETTINGS, "");
  assert.equal(store.snapshot().token, null);
});

test("storage that refuses (a private window, blocked site data) keeps the token in the page's memory only", () => {
  const store = new GitHubSettingsStore({ local: () => blocked, session: () => blocked });
  store.save({ ...SETTINGS, remember: true }, TOKEN);
  assert.deepEqual(store.snapshot(), { settings: { ...SETTINGS, remember: true }, token: TOKEN, where: "memory" });
  store.forgetToken();
  assert.equal(store.snapshot().token, null);
  const none = new GitHubSettingsStore({ local: () => null, session: () => null });
  assert.deepEqual(none.snapshot(), { settings: DEFAULT_GITHUB_SETTINGS, token: null, where: null });
});

test("the snapshot is the same object until something changes; listeners hear every save and forget", () => {
  const { store } = setup();
  let heard = 0;
  const off = store.subscribe(() => heard++);
  const a = store.snapshot();
  assert.equal(store.snapshot(), a);
  store.save(SETTINGS, TOKEN);
  assert.notEqual(store.snapshot(), a);
  store.forgetToken();
  off();
  store.save(SETTINGS, TOKEN);
  assert.equal(heard, 2);
});

test("a stored token that is not one (spaces, line breaks) is not used; stored settings are checked", () => {
  const { session, store } = setup();
  session.setItem(GITHUB_KEYS.token, "two words");
  assert.equal(store.snapshot().token, null);
  assert.equal(tokenProblem(""), null);
  assert.equal(tokenProblem(TOKEN), null);
  assert.match(tokenProblem("ghp_abc\ndef") ?? "", /copy it again/);
  assert.match(tokenProblem("x".repeat(300)) ?? "", /too long/);
  assert.deepEqual(parseSettings("{broken"), DEFAULT_GITHUB_SETTINGS);
  assert.deepEqual(parseSettings('{"repository": 5, "remember": "yes", "folder": "x"}'), { ...DEFAULT_GITHUB_SETTINGS, folder: "x" });
});
