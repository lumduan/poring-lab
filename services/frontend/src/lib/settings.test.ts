import assert from "node:assert/strict";
import { test } from "node:test";

import { auditText, diff, isForbidden, reasonText, validateEntry } from "./settings.ts";

const FORBIDDEN = ["kro-assit.ragnarok.co.kr", "*.ragnarok.co.kr", "49.229.28.99:3000", "49.229.28.13"];

test("a LAN server and a DNS name pass, normalised", () => {
  assert.deepEqual(validateEntry(" 192.168.1.13 ", "6900", FORBIDDEN), {
    host: "192.168.1.13",
    port: 6900,
    error: null,
  });
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
    ["300.1.1.1", "6900", "bad_host"],
    ["192.168.1.13", "0", "bad_port"],
    ["192.168.1.13", "70000", "bad_port"],
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

test("Save's diff lists what is added and removed", () => {
  const a = { host: "192.168.1.13", port: 6900 };
  const b = { host: "192.168.1.13", port: 5121 };
  const c = { host: "ro.example.net", port: 6900 };
  assert.deepEqual(diff([a, b], [b, c]), { added: ["ro.example.net:6900"], removed: ["192.168.1.13:6900"] });
});

test("refusals and audit lines are plain words", () => {
  assert.match(reasonText("forbidden_endpoint"), /official/);
  assert.match(reasonText("agent_network"), /bot can never/);
  assert.match(reasonText("something_new"), /something_new/);
  assert.match(
    auditText({
      t_wall: "2026-10-06T07:00:00+00:00", action: "add", env_id: "lab-rathena",
      entry: "192.168.1.13:6900", revision_before: 0, revision_after: 1, ok: true,
      reason: "saved", client: "192.168.1.50",
    }),
    /Allowed 192\.168\.1\.13:6900 in lab-rathena \(revision 0 → 1\) \[from 192\.168\.1\.50\]/,
  );
});
