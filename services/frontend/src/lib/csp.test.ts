import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import { backendSources, cspHeader, GITHUB_API_ORIGIN } from "./csp.ts";
import { GITHUB_API } from "./github/client.ts";

const directive = (csp: string, name: string): string =>
  csp.split("; ").find((d) => d.startsWith(`${name} `)) ?? "";

test("production: scripts by nonce only, no inline script, no eval, no plugins, no framing", () => {
  const csp = cspHeader({ nonce: "abc", dev: false, backend: ["http://192.168.1.13:8000", "ws://192.168.1.13:8000"], host: "192.168.1.13:3000" });
  const script = directive(csp, "script-src");
  assert.equal(script, "script-src 'self' 'nonce-abc' 'strict-dynamic'");
  assert.ok(!csp.includes("unsafe-eval"));
  assert.ok(!script.includes("unsafe-inline"));
  assert.equal(directive(csp, "object-src"), "object-src 'none'");
  assert.equal(directive(csp, "frame-ancestors"), "frame-ancestors 'none'");
  assert.equal(directive(csp, "base-uri"), "base-uri 'self'");
  assert.equal(directive(csp, "worker-src"), "worker-src 'self' blob:");
  assert.equal(directive(csp, "connect-src"), "connect-src 'self' http://192.168.1.13:8000 ws://192.168.1.13:8000 https://api.github.com");
});

test("development adds only what next dev needs: eval for React's debugging, the HMR socket", () => {
  const csp = cspHeader({ nonce: "n", dev: true, backend: [], host: "192.168.1.13:3001" });
  assert.match(directive(csp, "script-src"), /'unsafe-eval'$/);
  assert.equal(directive(csp, "connect-src"), "connect-src 'self' ws://192.168.1.13:3001 https://api.github.com");
});

test("the backend's address comes from the config, else the host; junk adds nothing", () => {
  assert.deepEqual(backendSources("http://192.168.1.13:8000/", null), ["http://192.168.1.13:8000", "ws://192.168.1.13:8000"]);
  assert.deepEqual(backendSources(null, "lab.local:3000"), ["http://lab.local:8000", "ws://lab.local:8000"]);
  for (const bad of ["javascript:alert(1)", "data:text/html,x"]) assert.deepEqual(backendSources(bad, null), []);
  for (const host of ["a b", "x'; script-src *", "evil.com/'unsafe-inline'", "a".repeat(400)]) {
    const out = backendSources(null, host);
    assert.ok(out.every((s) => !s.includes("'") && !s.includes(" ") && !s.includes(";")), `${host}: ${out}`);
  }
  const csp = cspHeader({ nonce: "n", dev: true, backend: [], host: "x; script-src *" });
  assert.equal(directive(csp, "connect-src"), "connect-src 'self' https://api.github.com");
});

test("GitHub's API is the ONE outside origin, in connect-src only (flows-save-load.md section 3)", () => {
  assert.equal(GITHUB_API_ORIGIN, "https://api.github.com");
  assert.equal(GITHUB_API, GITHUB_API_ORIGIN); // the client talks to exactly the origin the CSP allows
  for (const dev of [false, true]) {
    const csp = cspHeader({ nonce: "n", dev, backend: [], host: null });
    const outside = csp
      .split("; ")
      .flatMap((d) => d.split(" ").slice(1).map((src) => [d.split(" ")[0], src]))
      .filter(([, src]) => /^(https?|wss?):/.test(src));
    assert.deepEqual(outside, [["connect-src", "https://api.github.com"]], csp);
    assert.equal(directive(csp, "default-src"), "default-src 'self'");
    assert.equal(directive(csp, "img-src"), "img-src 'self' blob: data:");
    assert.equal(directive(csp, "form-action"), "form-action 'self'");
  }
});

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    if (statSync(p).isDirectory()) return sources(p);
    return /\.(ts|tsx)$/.test(n) && !n.endsWith(".test.ts") ? [p] : [];
  });
}

test("only lib/github/client.ts names GitHub's API (and the CSP that allows it): no other page code calls it", () => {
  const src = join(import.meta.dirname, "..");
  const naming = sources(src)
    .filter((f) => readFileSync(f, "utf8").includes("api.github.com"))
    .map((f) => f.slice(src.length + 1).split("\\").join("/"))
    .sort();
  assert.deepEqual(naming, ["lib/csp.ts", "lib/github/client.ts"]);
});
