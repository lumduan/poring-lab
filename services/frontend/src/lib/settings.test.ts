import assert from "node:assert/strict";
import { test } from "node:test";

import {
  auditText,
  badgeText,
  cdnWarning,
  DECLARE_WARNING,
  declaredText,
  declareReady,
  describeServer,
  groupSuggestions,
  isForbidden,
  notReadyText,
  parseForbidden,
  reasonText,
  toInputs,
  unblockReady,
  validateEntry,
  withDeclaration,
  type Declaration,
  type EnvView,
  type ServerView,
} from "./settings.ts";

const FORBIDDEN = ["kro-assit.ragnarok.co.kr", "*.ragnarok.co.kr", "49.229.28.99:3000", "49.229.28.13"];

function server(host: string, port: number | null, extra: Partial<ServerView> = {}): ServerView {
  return {
    host, port, key: port === null ? host : `${host}:${port}`, note: "", source: "manual",
    added_at: "", added_by: "", resolved: [], forbidden: false, ...extra,
  };
}

test("a LAN server and a DNS name pass, normalised", () => {
  assert.deepEqual(validateEntry(" 192.168.1.13 ", "6900", FORBIDDEN), { host: "192.168.1.13", port: 6900, error: null });
  assert.equal(validateEntry("RO.Example.NET.", "5121", FORBIDDEN).host, "ro.example.net");
});

test("the backend's refusals are mirrored", () => {
  const cases: [string, string, string][] = [
    ["", "6900", "empty_host"],
    ["*.example.com", "6900", "wildcard"],
    ["0.0.0.0", "6900", "unspecified_address"],
    ["127.0.0.1", "6900", "loopback"],
    ["localhost", "6900", "loopback"],
    ["169.254.1.1", "6900", "link_local"],
    ["224.0.0.1", "6900", "not_unicast"],
    ["::1", "6900", "ipv6_not_supported"],
    ["a b.example", "6900", "bad_host"],
    ["<script>alert(1)</script>", "6900", "bad_host"],
    ["300.1.1.1", "6900", "bad_host"],
    ["192.168.1.13", "0", "bad_port"],
    ["192.168.1.13", "x", "bad_port"],
    ["KRO-ASSIT.ragnarok.co.kr", "3000", "forbidden_endpoint"],
    ["anything.ragnarok.co.kr", "6900", "forbidden_endpoint"],
    ["49.229.28.99", "3000", "forbidden_endpoint"],
    ["49.229.28.13", "6900", "forbidden_endpoint"],
  ];
  for (const [host, port, reason] of cases) {
    assert.equal(validateEntry(host, port, FORBIDDEN).error, reason, `${host}:${port}`);
  }
  assert.equal(validateEntry("49.229.28.99", "6900", FORBIDDEN).error, null); // port-specific
});

test("forbidden domains match the domain and every name under it, nothing else", () => {
  assert.equal(isForbidden("ragnarok.co.kr", 1, FORBIDDEN), true);
  assert.equal(isForbidden("notragnarok.co.kr", 1, FORBIDDEN), false);
});

test("servers and badges are plain words", () => {
  assert.equal(describeServer({ host: "thro-acc3.gnjoy.in.th", port: null }), "thro-acc3.gnjoy.in.th : every port");
  assert.equal(describeServer({ host: ".gnjoy.in.th", port: null }), "gnjoy.in.th and every name under it");
  assert.equal(describeServer({ host: "49.229.28.99", port: 3000 }), "49.229.28.99 : 3000");
  assert.equal(badgeText({ type: "allowed", servers: [] }), "Allowed · 0 servers");
  assert.equal(badgeText({ type: "allowed", servers: [server("a.example", 1)] }), "Allowed · 1 server");
  assert.equal(badgeText({ type: "forbidden", servers: [server("a.example", null), server(".b", null)] }), "Forbidden · 2 blocked");
});

test("why the bot cannot act yet, in one sentence", () => {
  assert.match(notReadyText({ type: "allowed", servers: [], signals: ["session"] }) ?? "", /confirm at least one server/);
  const flagged = [server("192.168.1.13", 6900, { forbidden: true })];
  assert.match(notReadyText({ type: "allowed", servers: flagged, signals: ["session"] }) ?? "", /forbidden list/);
  assert.match(notReadyText({ type: "allowed", servers: [server("a.example", 1)], signals: [] }) ?? "", /no way to check/);
  assert.equal(notReadyText({ type: "allowed", servers: [server("a.example", 1)], signals: ["session"] }), null);
  assert.equal(notReadyText({ type: "forbidden", servers: [], signals: [] }), null);
});

test("suggestions of one server are grouped for Confirm all", () => {
  assert.deepEqual(
    groupSuggestions([{ host: "192.168.1.13", port: 6900 }, { host: "192.168.1.13", port: 6121 },
      { host: "192.168.1.13", port: 5121 }, { host: "10.0.0.2", port: 6900 }]),
    [{ host: "192.168.1.13", ports: [6900, 6121, 5121] }, { host: "10.0.0.2", ports: [6900] }],
  );
});

test("the request carries user fields only", () => {
  const env: EnvView = { id: "lab", name: "Lab", type: "allowed", summary: "s", why: "w",
    servers: [server("192.168.1.13", 6900)], suggestions: [], ready: true, signals: ["session"], declared: null };
  assert.deepEqual(toInputs({ environments: [env] }), [{ id: "lab", name: "Lab", type: "allowed", summary: "s",
    why: "w", servers: [{ host: "192.168.1.13", port: 6900, note: "" }], declared: null }]);
});

// --- ADR-0023 decision 1: a person's declaration (Batt 2026-11-12: a warning, not a lock) ----------

const DECLARED: Declaration = {
  at: "2026-11-12T07:03:41.123456+00:00", peer: "192.168.1.50",
  statement: "The class server's owner (our teacher) runs it for bots.",
};

function allowedEnv(extra: Partial<EnvView> = {}): EnvView {
  return { id: "class", name: "Class server", type: "allowed", summary: "", why: "",
    servers: [server("203.0.113.7", 6900)], suggestions: [], ready: false, signals: [], ...extra };
}

test("the declaration warning is Batt's wording, in full", () => {
  assert.equal(DECLARE_WARNING,
    "Declare only for a server whose owner permits bots. The lab cannot check this: once you declare, " +
    "the bot will act there on your word. Official servers stay blocked by default; lifting that block " +
    "can get your account banned and is your own responsibility. Never collect other players' data.");
});

test("declaring needs the person's own words, as the backend's minimum", () => {
  assert.equal(declareReady(""), false);
  assert.equal(declareReady("   ok it is   "), false); // 8 characters after trim
  assert.equal(declareReady("123456789"), false); // 9 characters
  assert.equal(declareReady(" 1234567890 "), true); // 10 after trim
  assert.equal(declareReady("x".repeat(501)), false); // over the backend's maximum
});

test("a declaration is shown as declared by a person, never as verified", () => {
  const text = declaredText(DECLARED);
  assert.equal(text, "Declared by a person, not verified — 2026-11-12 07:03 UTC, from 192.168.1.50");
  assert.doesNotMatch(text.replace("not verified", ""), /verified/);
});

test("a kept declaration is sent back as its statement; declare and withdraw change only one", () => {
  const view = { environments: [allowedEnv({ declared: DECLARED }), allowedEnv({ id: "other", name: "Other" })] };
  const envs = toInputs(view);
  assert.deepEqual(envs.map((e) => e.declared), [DECLARED.statement, null]);
  const declared = withDeclaration(envs, "other", "  The owner said so on their Discord.  ");
  assert.deepEqual(declared.map((e) => e.declared), [DECLARED.statement, "The owner said so on their Discord."]);
  const withdrawn = withDeclaration(envs, "class", null);
  assert.deepEqual(withdrawn.map((e) => e.declared), [null, null]);
  assert.deepEqual(envs.map((e) => e.declared), [DECLARED.statement, null]); // the input is untouched
});

test("an allowed environment without a packet check can be declared; a declared one is ready", () => {
  assert.match(notReadyText(allowedEnv()) ?? "", /no way to check.*declare it below/);
  assert.equal(notReadyText(allowedEnv({ declared: DECLARED })), null);
  assert.match(notReadyText(allowedEnv({ declared: DECLARED, servers: [] })) ?? "", /confirm at least one server/);
});

test("declare and withdraw history lines quote the person's statement", () => {
  const base = { t_wall: "2026-11-12T07:03:41+00:00", env_id: "class", entry: "Class server",
    revision_before: 4, revision_after: 5, ok: true, reason: "page", client: "192.168.1.50" };
  const declare = auditText({ ...base, action: "declare", kind: "declare", note: DECLARED.statement });
  assert.match(declare, /^Declared the owner's permission \(not verified\): Class server — statement: "The class server's owner/);
  assert.match(declare, /\[from 192\.168\.1\.50\]$/);
  const withdraw = auditText({ ...base, action: "withdraw", kind: "easy", note: DECLARED.statement });
  assert.match(withdraw, /^Withdrew the declaration: Class server — withdrawn statement: "/);
  assert.match(reasonText("statement_required"), /own words \(at least 10 characters\)/);
  assert.match(reasonText("declaration_not_importable"), /cannot come from a file/);
});

test("a CDN address gets the firewall warning; a plain one does not", () => {
  assert.match(cdnWarning({ resolved: [{ ip: "104.18.20.108", cdn: "cloudflare" }] }) ?? "", /Cloudflare/);
  assert.equal(cdnWarning({ resolved: [{ ip: "49.229.28.13", cdn: null }] }), null);
});

test("forbidden entries parse like the backend's", () => {
  assert.equal(parseForbidden(" New-Assist.Example.com:3000 "), "new-assist.example.com:3000");
  assert.equal(parseForbidden(".Gnjoy.in.th"), ".gnjoy.in.th");
  assert.equal(parseForbidden("49.229.28.13"), "49.229.28.13");
  for (const bad of ["*.example.com", "a b.example", "x.example.com:99999", "", "300.1.1.1"]) {
    assert.equal(parseForbidden(bad), null, bad);
  }
});

test("a hard change needs a reason and the subject typed again", () => {
  const e = "49.229.28.99:3000";
  assert.equal(unblockReady(e, "too short", e), false);
  assert.equal(unblockReady(e, "the stage server was retired", "49.229.28.99"), false);
  assert.equal(unblockReady(e, "the stage server was retired", ` ${e} `), true);
});

test("refusals and history lines are plain words", () => {
  assert.match(reasonText("forbidden_endpoint"), /official/);
  assert.match(reasonText("one_hard_change_at_a_time"), /one forbidden thing at a time/);
  assert.match(reasonText("something_new"), /something_new/);
  const base = { t_wall: "2026-10-06T07:00:00+00:00", env_id: "lab", revision_before: 0,
    revision_after: 1, ok: true, reason: "page", client: "192.168.1.50" };
  assert.match(auditText({ ...base, action: "server_add", kind: "normal", entry: "192.168.1.13:6900",
    note: "added 192.168.1.13:6900 to 'Lab'" }), /^Added: 192\.168\.1\.13:6900/);
  assert.match(auditText({ ...base, action: "server_remove", kind: "hard", entry: "49.229.28.99:3000",
    note: "the stage server was retired" }), /^LOOSENED a forbidden list — Removed: .*reason: "the stage server was retired"/);
});
