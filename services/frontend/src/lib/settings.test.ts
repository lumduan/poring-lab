import assert from "node:assert/strict";
import { test } from "node:test";

import {
  auditText,
  badgeText,
  cdnWarning,
  describeServer,
  groupSuggestions,
  isForbidden,
  notReadyText,
  parseForbidden,
  reasonText,
  toInputs,
  unblockReady,
  validateEntry,
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
    servers: [server("192.168.1.13", 6900)], suggestions: [], ready: true, signals: ["session"] };
  assert.deepEqual(toInputs({ environments: [env] }), [{ id: "lab", name: "Lab", type: "allowed", summary: "s",
    why: "w", servers: [{ host: "192.168.1.13", port: 6900, note: "" }] }]);
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
