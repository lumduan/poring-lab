// "Find servers from a game file": every fixture is SYNTHETIC and built here (no client data is
// committed). Every dropped file is treated as hostile: crafted GRFs, XSS hostnames, a
// decompression bomb, an oversized table, ReDoS-shaped strings, a public-internet endpoint.

import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { deflateSync } from "node:zlib";

import { ignorable, isLan, parseEndpoint, printableRuns, scanText, validHost, validPort } from "./endpoint.ts";
import { entropy, exeProtection } from "./extract.ts";
import { inflateCapped } from "./inflate.ts";
import { allowWarning, applyFound, defaultTarget, initialTicks, targetOptions, unusable } from "./plan.ts";
import { checked, scanInWorker, type WorkerLike } from "./run.ts";
import { bytesReader, LIMITS, NOT_KNOWN, PROTECTED, scanSource, type Limits, type ScanResult } from "./scan.ts";
import type { SettingsView } from "../settings.ts";

const enc = new TextEncoder();
const CONTROL = /[\u0000-\u001f\u007f-\u009f]/;

// ---- synthetic GRF builder (version 0x200) --------------------------------------------------

type Entry = { name: string | Uint8Array; data?: Uint8Array; flags?: number; size?: number; zdata?: Uint8Array; offset?: number };

function u32le(n: number): Uint8Array {
  const b = new Uint8Array(4);
  new DataView(b.buffer).setUint32(0, n >>> 0, true);
  return b;
}

function concat(parts: Uint8Array[]): Uint8Array {
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let at = 0;
  for (const p of parts) {
    out.set(p, at);
    at += p.length;
  }
  return out;
}

function grf(entries: Entry[], opts: { version?: number; table?: Uint8Array; tableSize?: number; tableOffset?: number } = {}): Uint8Array {
  const body: Uint8Array[] = [];
  const records: Uint8Array[] = [];
  let at = 0;
  for (const e of entries) {
    const z = e.zdata ?? deflateSync(e.data ?? new Uint8Array());
    const name = typeof e.name === "string" ? enc.encode(e.name) : e.name;
    records.push(concat([name, new Uint8Array([0]), u32le(z.length), u32le(z.length), u32le(e.size ?? (e.data?.length ?? 0)),
      new Uint8Array([e.flags ?? 0x01]), u32le(e.offset ?? at)]));
    body.push(z);
    at += z.length;
  }
  const rawTable = concat(records);
  const table = opts.table ?? deflateSync(rawTable);
  const header = concat([enc.encode("Master of Magic\0"), new Uint8Array(14), u32le(opts.tableOffset ?? at), u32le(0),
    u32le(entries.length + 7), u32le(opts.version ?? 0x200)]);
  return concat([header, ...body, u32le(table.length), u32le(opts.tableSize ?? rawTable.length), table]);
}

const CLIENTINFO = `<?xml version="1.0" encoding="euc-kr" ?>
<clientinfo>
  <servicetype>korea</servicetype>
  <connection>
    <display>Lab rAthena</display>
    <address>192.168.1.13</address>
    <port>6900</port>
    <version>55</version>
    <registrationweb>http://www.example.com/join</registrationweb>
  </connection>
</clientinfo>`;

/** A stand-in for a compiled externalsettings lub: the Lua signature, then NUL-separated strings. */
function lub(...strings: string[]): Uint8Array {
  return concat([enc.encode("\x1bLuaQ\0"), ...strings.map((s) => enc.encode(`${s}\0`))]);
}

const scan = (bytes: Uint8Array, name = "data.grf", limits: Limits = LIMITS): Promise<ScanResult> =>
  scanSource(bytesReader(bytes), name, bytes.length, limits);

function noHostileText(r: ScanResult): void {
  for (const f of r.found) {
    assert.ok(parseEndpoint(f.port === null ? f.host : f.host.includes(":") ? `[${f.host}]:${f.port}` : `${f.host}:${f.port}`), f.host);
    for (const s of [f.host, ...f.sources]) assert.ok(!CONTROL.test(s) && !s.includes("<") && !s.includes(">"), s);
  }
  for (const s of [...r.notes, r.error ?? "", r.display ?? "", r.file]) assert.ok(!CONTROL.test(s), s);
}

// ---- the endpoint grammar -------------------------------------------------------------------

test("the grammar accepts IPv4, IPv6 and RFC hostnames with a port 1-65535, nothing else", () => {
  assert.deepEqual(parseEndpoint("192.168.1.13:6900"), { host: "192.168.1.13", port: 6900 });
  assert.deepEqual(parseEndpoint("Kro-Assit.Example.COM:3000"), { host: "kro-assit.example.com", port: 3000 });
  assert.deepEqual(parseEndpoint("[2001:db8::1]:6900"), { host: "2001:db8::1", port: 6900 });
  assert.deepEqual(parseEndpoint("2001:db8::1"), { host: "2001:db8::1", port: null });
  assert.equal(validHost(`${"a".repeat(63)}.example.com`), `${"a".repeat(63)}.example.com`);
  for (const bad of [
    "<script>alert(1)</script>", "javascript:alert(1)", "javascript://evil.com:80", "\"evil.com\":80",
    "evil.com/x:80", "evil .com:80", "evil.com:0", "evil.com:65536", "evil.com:6900x", "evil.com:+80",
    `${"a".repeat(64)}.example.com:80`, `${"a.".repeat(130)}com:80`, "1.2.3:80", "-evil.com:80", "evil-.com:80",
    "evil.com\u0000:80", "evil.com\n:80", "evil.com:80:81", "300.1.1.1:80", "[::1:80", "a_b.example.com:80",
  ]) {
    assert.equal(parseEndpoint(bad), null, bad);
  }
  assert.equal(validPort("65535"), 65535);
  assert.equal(validPort(" 1 "), 1);
});

test("LAN, this-computer and public addresses are told apart", () => {
  assert.equal(isLan("192.168.1.13"), true);
  assert.equal(isLan("10.210.96.6"), true);
  assert.equal(isLan("172.31.0.1"), true);
  assert.equal(isLan("203.0.113.7"), false);
  assert.equal(isLan("lab.example.com"), false); // a NAME is never assumed to be on the LAN
  assert.equal(ignorable("127.0.0.1"), true);
  assert.equal(ignorable("0.0.0.0"), true);
  assert.equal(ignorable("localhost"), true);
  assert.equal(ignorable("192.168.1.13"), false);
});

test("scanning is linear: ReDoS-shaped strings finish fast and yield no fragments", () => {
  const evil = [
    "a".repeat(2_000_000),
    `${"a.".repeat(1_000_000)}:`,
    `${"1.".repeat(1_000_000)}1:80`,
    `${"a-".repeat(1_000_000)}!`,
    `${"x".repeat(1_000)}.example.com:6900`, // an overlong token: skipped whole, not cut
    "[".repeat(1_000_000),
    ":".repeat(1_000_000),
  ];
  for (const s of evil) {
    const t0 = performance.now();
    const out = scanText(s);
    const ms = performance.now() - t0;
    assert.ok(ms < 1500, `${s.slice(0, 12)}… took ${ms.toFixed(0)} ms`);
    assert.deepEqual(out, [], s.slice(0, 12));
  }
  assert.deepEqual(scanText("AssistAddr = \"kro-assit.example.com:3000\", url=http://web.example.com:8080/x"),
    [{ host: "kro-assit.example.com", port: 3000 }, { host: "web.example.com", port: 8080 }]);
  const long = new Uint8Array(4_000_000).fill(0x61);
  const t0 = performance.now();
  assert.equal([...printableRuns(long)].length, 0); // one overlong run, dropped whole
  assert.ok(performance.now() - t0 < 1500);
});

// ---- clientinfo / XSS -----------------------------------------------------------------------

test("clientinfo.xml gives the login server, a LAN one, with its display name", async () => {
  const r = await scan(enc.encode(CLIENTINFO), "clientinfo.xml");
  assert.equal(r.kind, "clientinfo");
  assert.equal(r.error, null);
  assert.deepEqual(r.found.map((f) => [f.host, f.port, f.role, f.lan]), [
    ["192.168.1.13", 6900, "login", true],
    ["www.example.com", null, "other", false],
  ]);
  assert.equal(r.display, "Lab rAthena");
  assert.deepEqual(r.found[0].sources, ["clientinfo.xml"]);
});

test("XSS payloads in a clientinfo never become endpoints or markup", async () => {
  const xml = `<clientinfo>
    <connection><display><img src=x onerror=alert(1)>"'&</display>
      <address><script>alert(1)</script></address><port>6900</port></connection>
    <connection><address>javascript:alert(document.cookie)</address><port>6900</port></connection>
    <connection><address>evil.example.com"onmouseover="alert(1)</address><port>6900</port></connection>
    <connection><address>evil.example.com</address><port>6900<script></port></connection>
    <connection><address>ok.example.com</address><port>6900</port>
      <registrationweb>javascript:alert(1)//evil.example.com</registrationweb></connection>
  </clientinfo>`;
  const r = await scan(enc.encode(xml), "clientinfo.xml");
  assert.deepEqual(r.found.map((f) => `${f.host}:${f.port}`), ["ok.example.com:6900"]);
  assert.equal(r.display, null); // the crafted display name is cut at its first "<": nothing left
  const named = await scan(enc.encode("<connection><display>Test server <img src=x onerror=alert(1)></display></connection>"), "clientinfo.xml");
  assert.equal(named.display, "Test server");
  noHostileText(r);
});

test("a crafted file with a public-internet endpoint: blocking is the default, allowing warns", async () => {
  const xml = "<clientinfo><connection><address>203.0.113.7</address><port>6900</port></connection></clientinfo>";
  const r = await scan(enc.encode(xml), "sclientinfo.xml");
  assert.equal(r.found.length, 1);
  const f = r.found[0];
  assert.equal(f.lan, false);
  const view: SettingsView = {
    revision: 3, store: "ok", seeded_from: null, config: "ok", forbidden: [],
    environments: [
      { id: "official-th", name: "Official Thai", type: "forbidden", summary: "", why: "", servers: [], suggestions: [], ready: false, signals: [] },
      { id: "lab", name: "Lab", type: "allowed", summary: "", why: "", servers: [], suggestions: [], ready: false, signals: ["session"] },
    ],
  };
  const options = targetOptions(view);
  assert.equal(options[0].value, "new-forbidden"); // the first (default) option blocks
  assert.deepEqual(defaultTarget(), { kind: "new-forbidden" });
  assert.ok(options.filter((o) => o.loosens).every((o) => o.label.startsWith("Allow:")));
  assert.ok(options.findIndex((o) => o.loosens) > options.findLastIndex((o) => !o.loosens)); // Allowed last
  // Blocking pre-ticks; allowing pre-ticks NOTHING (a deliberate choice, never automatic).
  assert.equal(initialTicks(r.found, defaultTarget(), []).size, 1);
  assert.equal(initialTicks(r.found, { kind: "allowed", envId: "lab" }, []).size, 0);
  // Allowing warns, naming the outside endpoint; blocking needs no warning.
  assert.match(allowWarning([f], { kind: "allowed", envId: "lab" }) ?? "", /203\.0\.113\.7:6900 is OUTSIDE your network\. The bot will act/);
  assert.equal(allowWarning([f], defaultTarget()), null);
  // The default action makes a FORBIDDEN environment holding it, marked as found in the file.
  const envs = applyFound(view, defaultTarget(), [f], "Found in sclientinfo.xml");
  const added = envs[envs.length - 1];
  assert.equal(added.type, "forbidden");
  assert.deepEqual(added.servers.map((s) => [s.host, s.port, s.source]), [["203.0.113.7", 6900, "file"]]);
  assert.match(added.servers[0].note, /^found in sclientinfo\.xml$/);
  assert.equal(envs.find((e) => e.id === "lab")?.servers.length, 0); // the allowed list is untouched
});

test("what can't go where: IPv6, port-less and forbidden endpoints are never allowed", () => {
  const base = { role: "login" as const, sources: ["x"], lan: false };
  const allow = { kind: "allowed" as const, envId: "lab" };
  assert.match(unusable({ ...base, host: "2001:db8::1", port: 6900 }, allow, []) ?? "", /IPv6/);
  assert.match(unusable({ ...base, host: "www.example.com", port: null }, allow, []) ?? "", /needs one/);
  assert.match(unusable({ ...base, host: "a.ragnarok.co.kr", port: 3000 }, allow, ["*.ragnarok.co.kr"]) ?? "", /forbidden list/);
  assert.equal(unusable({ ...base, host: "www.example.com", port: null }, defaultTarget(), []), null);
});

// ---- GRF ------------------------------------------------------------------------------------

test("a GRF: only the settings entries are read; encrypted ones are reported, not decrypted", async () => {
  const decoy = new Uint8Array(200_000).fill(0x41);
  const file = grf([
    { name: "data\\texture\\decoy.bmp", data: decoy },
    { name: "data\\clientinfo.xml", data: enc.encode(CLIENTINFO) },
    { name: "data\\luafiles514\\lua files\\service_korea\\externalsettings_kr.lub",
      data: lub("ExternalSettings", "AssistAddr", "kro-assit.example.com:3000", "WebAddr", "127.0.0.1:3000") },
    { name: "data\\luafiles514\\lua files\\service_korea\\externalsettings_kr_sak.lub", data: lub("x"), flags: 0x03 },
    { name: "DATA\\SClientInfo.XML", data: enc.encode(CLIENTINFO) },
  ]);
  const ranges: [number, number][] = [];
  const reader = bytesReader(file);
  const r = await scanSource(async (o, n) => (ranges.push([o, n]), reader(o, n)), "data.grf", file.length);
  assert.equal(r.kind, "grf");
  assert.equal(r.error, null);
  assert.equal(r.stats.entries, 5);
  assert.equal(r.stats.read, 3);
  assert.equal(r.stats.encrypted, 1);
  assert.deepEqual(r.found.map((f) => [f.host, f.port, f.role]), [
    ["192.168.1.13", 6900, "login"],
    ["kro-assit.example.com", 3000, "assist-web"],
    ["www.example.com", null, "other"],
  ]);
  assert.deepEqual(r.found[0].sources, ["data.grf: data\\clientinfo.xml", "data.grf: data\\sclientinfo.xml"]);
  assert.ok(r.notes.some((n) => /^Encrypted, can't read \(skipped\): data\\luafiles514.*_sak\.lub\.$/.test(n)), r.notes.join(" | "));
  assert.ok(r.notes.some((n) => /point to this computer/.test(n)));
  // The decoy's bytes (header 46 + its compressed data) were never read.
  const decoyEnd = 46 + deflateSync(decoy).length;
  assert.ok(ranges.every(([o, n]) => o === 0 || o >= decoyEnd || o + n <= 46), JSON.stringify(ranges));
  noHostileText(r);
});

test("a decompression bomb is refused, in an entry and in the table", async () => {
  const zeros = deflateSync(new Uint8Array(64 * 2 ** 20)); // 64 MB of zeros in ~64 KB
  // An entry that declares 1 KB and unpacks to 64 MB.
  const lying = await scan(grf([{ name: "data\\clientinfo.xml", zdata: zeros, size: 1024 }]));
  assert.ok(lying.notes.some((n) => /unpacks to more than it says.*decompression bomb/.test(n)), lying.notes.join(" | "));
  assert.ok(lying.stats.inflated <= 1024);
  // An entry that honestly declares 64 MB: over the per-entry limit, never inflated.
  const honest = await scan(grf([{ name: "data\\clientinfo.xml", zdata: zeros, size: 64 * 2 ** 20 }]));
  assert.ok(honest.notes.some((n) => /larger than 1 MB/.test(n)), honest.notes.join(" | "));
  assert.equal(honest.stats.inflated, 0);
  // A table that declares 1 KB and unpacks to 64 MB.
  const table = await scan(grf([], { table: zeros, tableSize: 1024 }));
  assert.match(table.error ?? "", /file table unpacks to more than it says/);
  // A table that declares more than the limit.
  const big = await scan(grf([], { table: zeros, tableSize: 512 * 2 ** 20 }));
  assert.match(big.error ?? "", /file table is too large/);
});

test("an oversized entry table is cut at the limit, and the walk stays bounded", async () => {
  const many: Entry[] = Array.from({ length: 5000 }, (_, i) => ({ name: `data\\x\\${i}.bmp`, data: new Uint8Array(0) }));
  many.push({ name: "data\\clientinfo.xml", data: enc.encode(CLIENTINFO) });
  const r = await scan(grf(many), "data.grf", { ...LIMITS, maxEntries: 1000 });
  assert.ok(r.notes.some((n) => /more than 1000 entries/.test(n)), r.notes.join(" | "));
  assert.equal(r.stats.entries, 1000);
  assert.equal(r.found.length, 0); // clientinfo was past the cut
  const targets: Entry[] = Array.from({ length: 10 }, () => ({ name: "data\\clientinfo.xml", data: enc.encode(CLIENTINFO) }));
  const t = await scan(grf(targets), "data.grf", { ...LIMITS, maxTargets: 3 });
  assert.ok(t.notes.some((n) => /more than 3 settings files/.test(n)));
  assert.equal(t.stats.read, 3);
});

test("bad offsets, a wrong version and a damaged table are refused in plain words", async () => {
  const ok = grf([{ name: "data\\clientinfo.xml", data: enc.encode(CLIENTINFO) }]);
  assert.match((await scan(grf([], { tableOffset: 0x7fff_ffff }))).error ?? "", /points outside the file/);
  assert.match((await scan(grf([], { version: 0x103 }))).error ?? "", /version 0x103/);
  assert.match((await scan(grf([], { table: enc.encode("not zlib at all") }))).error ?? "", /damaged/);
  const far = await scan(grf([{ name: "data\\clientinfo.xml", data: enc.encode(CLIENTINFO), offset: 0x7000_0000 }]));
  assert.ok(far.notes.some((n) => /points outside the file/.test(n)));
  // A name without its terminating NUL: the walk stops at the damage.
  const raw = enc.encode("data\\clientinfo.xml".repeat(20));
  const noNul = await scan(grf([], { table: deflateSync(raw), tableSize: raw.length }));
  assert.ok(noNul.notes.some((n) => /table is damaged/.test(n)));
  assert.equal((await scan(ok)).found[0].host, "192.168.1.13");
});

test("fuzzed GRFs never throw, never hang, and only ever yield grammatical endpoints", async () => {
  const base = grf([
    { name: "data\\clientinfo.xml", data: enc.encode(CLIENTINFO) },
    { name: "data\\luafiles514\\lua files\\service_korea\\externalsettings_kr.lub", data: lub("AssistAddr", "a.example.com:3000") },
  ]);
  let seed = 0x2026_1006;
  const rand = () => {
    seed ^= seed << 13;
    seed ^= seed >>> 17;
    seed ^= seed << 5;
    return (seed >>> 0) / 2 ** 32;
  };
  const t0 = performance.now();
  for (let i = 0; i < 400; i++) {
    let f = base.slice();
    const flips = 1 + Math.floor(rand() * 8);
    for (let k = 0; k < flips; k++) f[Math.floor(rand() * f.length)] = Math.floor(rand() * 256);
    if (rand() < 0.2) f = f.subarray(0, Math.floor(rand() * f.length));
    if (f.length >= 34 && rand() < 0.2) new DataView(f.buffer, f.byteOffset).setUint32(30, Math.floor(rand() * 2 ** 32), true);
    const r = await scan(f);
    noHostileText(r);
  }
  assert.ok(performance.now() - t0 < 20_000);
});

// ---- exe ------------------------------------------------------------------------------------

function pe(sections: { name: string; raw: Uint8Array; exec?: boolean }[], extra = new Uint8Array()): Uint8Array {
  const headerSize = 0x200;
  const head = new Uint8Array(headerSize);
  head.set(enc.encode("MZ"), 0);
  head.set(u32le(0x80), 0x3c);
  head.set(enc.encode("PE\0\0"), 0x80);
  new DataView(head.buffer).setUint16(0x80 + 6, sections.length, true);
  let at = headerSize;
  sections.forEach((s, i) => {
    const o = 0x80 + 24 + 40 * i;
    head.set(enc.encode(s.name.padEnd(8, "\0").slice(0, 8)), o);
    head.set(u32le(s.raw.length), o + 16);
    head.set(u32le(at), o + 20);
    head.set(u32le(s.exec ? 0x60000020 : 0x40000040), o + 36);
    at += s.raw.length;
  });
  return concat([head, ...sections.map((s) => s.raw), extra]);
}

function noise(n: number): Uint8Array {
  const b = new Uint8Array(n);
  let x = 12345;
  for (let i = 0; i < n; i++) {
    x = (x * 1103515245 + 12345) & 0x7fffffff;
    b[i] = x >>> 16;
  }
  return b;
}

test("an exe: a protected one says so plainly; a plain one gives its visible host:port strings", async () => {
  const themida = await scan(pe([{ name: ".themida", raw: new Uint8Array(1024) }]), "Ragexe.exe");
  assert.equal(themida.kind, "exe");
  assert.ok(themida.error?.startsWith(PROTECTED), themida.error ?? "");
  const blank = await scan(pe([{ name: "", raw: new Uint8Array(1024), exec: true }]), "game.exe");
  assert.match(blank.error ?? "", /blank names/);
  const packed = await scan(pe([{ name: ".text", raw: noise(256 * 1024), exec: true }]), "game.exe");
  assert.match(packed.error ?? "", /packed code/);
  assert.ok(entropy(noise(256 * 1024)) > 7.5);
  const code = new Uint8Array(128 * 1024).map((_, i) => [0x55, 0x8b, 0xec, 0x83, 0xc4, 0x08, 0xc3, 0x90][i % 8]);
  const ascii = enc.encode("\0<script>x.example.com:1</script>\0login.example.com:6900\0AssistAddr\0assist.example.com:3000\0\0");
  const pad = new Uint8Array(ascii.length % 2); // the wide string starts on an even offset
  const strings = concat([ascii, pad, enc.encode("w\0i\0d\0e\0.\0e\0x\0a\0m\0p\0l\0e\0.\0c\0o\0m\0:\x008\x000\0\0\0")]);
  const plain = await scan(pe([{ name: ".text", raw: code, exec: true }, { name: ".rdata", raw: strings }]), "game.exe");
  assert.equal(plain.error, null);
  assert.deepEqual(plain.found.map((f) => `${f.host}:${f.port} ${f.role}`).sort(), [
    "assist.example.com:3000 assist-web", "login.example.com:6900 other", "wide.example.com:80 other",
    "x.example.com:1 other",
  ]);
  assert.equal(exeProtection(enc.encode("MZ not really a program")).pe, false);
  noHostileText(plain);
});

test("an unknown or oversized file is refused before it is read", async () => {
  assert.equal((await scan(enc.encode("\x89PNG...."), "photo.png")).error, NOT_KNOWN);
  const big = await scanSource(async () => new Uint8Array(64), "huge.xml", 50 * 2 ** 20);
  assert.match(big.error ?? "", /larger than 1 MB/);
  const tooBig = await scanSource(async () => new Uint8Array(64), "data.grf", 6 * 2 ** 30);
  assert.match(tooBig.error ?? "", /too large/);
});

test("a lub in plain Lua text works too; a bare host is taken only after an ...Addr key", async () => {
  const text = enc.encode('ExternalSettings = {\n  AssistAddr = "kro-assit.example.com:3000",\n  LoginAddr = "\nlogin.example.com\n",\n  Title = "notes.txt"\n}\n');
  const r = await scan(text, "externalsettings_kr.lub");
  assert.deepEqual(r.found.map((f) => [f.host, f.port, f.role]), [
    ["kro-assit.example.com", 3000, "assist-web"], ["login.example.com", null, "other"],
  ]);
});

test("inflate stops a bomb after one chunk past the cap", async () => {
  const r = await inflateCapped(deflateSync(new Uint8Array(32 * 2 ** 20)), 100_000);
  assert.deepEqual(r, { ok: false, why: "too_big" });
  const ok = await inflateCapped(deflateSync(enc.encode("hello")), 5);
  assert.ok(ok.ok && new TextDecoder().decode(ok.bytes) === "hello");
  assert.deepEqual(await inflateCapped(enc.encode("junk"), 100), { ok: false, why: "corrupt" });
});

// ---- the page side: timeout, re-validation, no markup ---------------------------------------

test("a worker that never answers is terminated at the time limit", async () => {
  let terminated = false;
  const fake: WorkerLike = { postMessage() {}, terminate() { terminated = true; }, onmessage: null, onerror: null };
  const t0 = performance.now();
  const r = await scanInWorker({ name: "data.grf", size: 10 }, { timeoutMs: 50, makeWorker: () => fake });
  assert.ok(performance.now() - t0 < 1000);
  assert.equal(terminated, true);
  assert.match(r.error ?? "", /took longer than/);
});

test("the worker's reply is re-checked: bad endpoints dropped, text made safe", () => {
  const r = checked({
    file: "data\u0000.grf", kind: "grf", error: null, display: "<b>x</b>",
    notes: ["ok", "line\u001b[31mred"],
    found: [
      { host: "<script>alert(1)</script>", port: 6900, role: "login", sources: ["x"], lan: true },
      { host: "javascript:alert(1)", port: null, role: "login", sources: ["x"], lan: true },
      { host: "203.0.113.7", port: 6900, role: "login", sources: ["s\u0007"], lan: true }, // lan is recomputed
      { host: "a.example.com", port: 70000, role: "login", sources: [], lan: false },
      { host: "b.example.com", port: 80, role: "evil", sources: [], lan: false },
    ],
    stats: { entries: -5, read: "x" },
  }, "data.grf");
  assert.deepEqual(r.found.map((f) => [f.host, f.port, f.role, f.lan]), [
    ["203.0.113.7", 6900, "login", false], ["b.example.com", 80, "other", false],
  ]);
  noHostileText(r);
  assert.equal(r.stats.entries, 0);
  assert.equal(checked("nonsense", "f").error, "The finder stopped without an answer.");
});

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    if (statSync(p).isDirectory()) return sources(p);
    return /\.(ts|tsx)$/.test(n) && !n.endsWith(".test.ts") ? [p] : [];
  });
}

test("no page code renders HTML from strings, evaluates code, or links extracted values", () => {
  const src = join(import.meta.dirname, "..", "..");
  const files = sources(src);
  assert.ok(files.length > 20);
  for (const f of files) {
    const text = readFileSync(f, "utf8");
    for (const bad of ["dangerouslySetInnerHTML", ".innerHTML", ".outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"]) {
      assert.ok(!text.includes(bad), `${f}: ${bad}`);
    }
  }
  const finder = readFileSync(join(src, "components", "GameFileFinder.tsx"), "utf8");
  assert.ok(!finder.includes("href"), "the finder never makes a link");
});
