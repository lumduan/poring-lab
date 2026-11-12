import assert from "node:assert/strict";
import { test } from "node:test";

import {
  cleanFlowName,
  cleanSavedBy,
  DEFAULT_FLOW_NAME,
  downloadText,
  type DownloadDeps,
  fileShortcut,
  FLOW_FILE_MAX_BYTES,
  flowFileName,
  flowNameFromFileName,
  isFlowFileName,
  type KeyLike,
  NAME_MAX_BYTES,
  NAME_MAX_CHARS,
  newFileMeta,
  parseFlowFile,
  readFileMeta,
  REVOKE_AFTER_MS,
  serializeFlowFile,
  utf8Bytes,
  writeFileMeta,
} from "./file.ts";
import { exportText } from "./importer.ts";
import { canonical, type Flow } from "./ir.ts";
import { KEYS, type StorageLike } from "./prefs.ts";
import { FIXTURES, fixture } from "./testkit.ts";

const SAVED_AT = "2026-11-12T04:12:00.000Z";
const parts = (flow: Flow, over: Partial<{ name: string; savedBy: string; python: string }> = {}) => ({
  name: "ฟาร์มโพริง farm 1",
  savedBy: " Ploy ",
  savedAt: SAVED_AT,
  python: "from poring import *\n\ndef main():\n    pass\n",
  flow,
  ...over,
});

test("a flow file round-trips exactly: seven fields, the Python as lines, the flow in canonical key order", () => {
  for (const name of FIXTURES) {
    const flow = fixture(name);
    const text = serializeFlowFile(parts(flow));
    assert.ok(text.endsWith("}\n"));
    const data = JSON.parse(text) as Record<string, unknown>;
    assert.deepEqual(Object.keys(data), ["format", "version", "name", "savedBy", "savedAt", "python", "flow"]);
    assert.equal(data.format, "poring-lab-flow");
    assert.equal(data.version, 1);
    assert.equal(data.savedBy, "Ploy");
    assert.deepEqual(data.python, ["from poring import *", "", "def main():", "    pass"]);
    assert.deepEqual(Object.keys(data.flow as object), Object.keys(data.flow as object).slice().sort());
    const r = parseFlowFile(text, "ignored.flow.json");
    assert.ok(r.ok, JSON.stringify(r));
    if (!r.ok) continue;
    assert.equal(canonical(r.flow), canonical(flow));
    assert.equal(r.name, "ฟาร์มโพริง farm 1");
    assert.equal(r.savedBy, "Ploy");
    assert.equal(r.savedAt, SAVED_AT);
    assert.equal(r.bare, false);
    assert.equal(serializeFlowFile({ ...parts(r.flow), name: r.name }), text); // stable: saving again changes nothing
  }
  assert.deepEqual(JSON.parse(serializeFlowFile(parts(fixture("farm_loop"), { python: "" }))).python, []);
});

test("the static data (the world) never goes into a file, whatever the caller hands over", () => {
  const sneaky = { ...parts(fixture("farm_loop")), world: { maps: { prt_fild08: { spawns: [1002] } } }, sample: "sheets" };
  const text = serializeFlowFile(sneaky as unknown as Parameters<typeof serializeFlowFile>[0]);
  assert.ok(!text.includes("world") && !text.includes("prt_fild08") && !text.includes("sheets"));
  assert.deepEqual(Object.keys(JSON.parse(text)), ["format", "version", "name", "savedBy", "savedAt", "python", "flow"]);
});

test("a bare IR file (a download from before 2026-11-12) still opens, named after its file", () => {
  const flow = fixture("visit_and_choose");
  const r = parseFlowFile(exportText(flow), flowNameFromFileName("Downloads/visit_and_choose.flow.json"));
  assert.ok(r.ok && r.bare && canonical(r.flow) === canonical(flow));
  if (r.ok) assert.deepEqual([r.name, r.savedBy, r.savedAt], ["visit_and_choose", "", ""]);
  const noName = parseFlowFile(exportText(flow), "");
  assert.ok(noName.ok && noName.name === flow.name);
  const bad = parseFlowFile(JSON.stringify({ ...flow, name: "Bad Name" }), "x"); // the IR's own checks apply
  assert.ok(!bad.ok && /name:/.test(bad.errors.join(" ")));
});

test("the python field is IGNORED on load: never read, never trusted", () => {
  const flow = fixture("farm_loop");
  const data = JSON.parse(serializeFlowFile(parts(flow)));
  for (const python of [12345, { evil: true }, ["import os", "os.system('rm -rf /')"], "x".repeat(50_000), null]) {
    const r = parseFlowFile(JSON.stringify({ ...data, python }), "x");
    assert.ok(r.ok, String(python));
    if (r.ok) {
      assert.equal(canonical(r.flow), canonical(flow));
      assert.ok(!("python" in r));
    }
  }
  const without = { ...data };
  delete without.python;
  assert.ok(parseFlowFile(JSON.stringify(without), "x").ok);
});

test("a newer version is refused with a plain message; a damaged version too", () => {
  const data = JSON.parse(serializeFlowFile(parts(fixture("farm_loop"))));
  const newer = parseFlowFile(JSON.stringify({ ...data, version: 2 }), "x");
  assert.ok(!newer.ok);
  if (!newer.ok) assert.equal(newer.errors[0], "this flow was saved by a newer poring-lab: pull the update, then open it again");
  for (const version of [0, -1, 1.5, "1", null, undefined]) {
    const r = parseFlowFile(JSON.stringify({ ...data, version }), "x");
    assert.ok(!r.ok && /version: a whole number/.test(r.errors[0]), String(version));
  }
});

test("hostile files are refused with a message before anything changes: size, depth, shape, the IR", () => {
  const data = JSON.parse(serializeFlowFile(parts(fixture("farm_loop"))));
  const big = JSON.stringify({ ...data, python: ["x".repeat(FLOW_FILE_MAX_BYTES)] });
  const cases: [string, RegExp][] = [
    [big, /bytes; a flow file is at most 2000000/],
    ["[".repeat(300) + "]".repeat(300), /nested deeper/],
    ["{not json", /not JSON/],
    ["[1, 2]", /a JSON object/],
    ['{"hello": 1}', /not a poring-lab flow/],
    [JSON.stringify({ ...data, format: "matpilot-blocks" }), /not a poring-lab flow/],
    [JSON.stringify({ ...data, name: 7 }), /name: text/],
    [JSON.stringify({ ...data, savedBy: ["x"] }), /savedBy: text/],
    [JSON.stringify({ ...data, flow: null }), /flow: missing/],
    [JSON.stringify({ ...data, flow: [] }), /flow: missing/],
    [JSON.stringify({ ...data, flow: { ...data.flow, ir: 3 } }), /flow: ir: IR version 3 is not supported/],
    [JSON.stringify({ ...data, flow: { ...data.flow, main: [] } }), /flow: a flow has exactly one of main and workflow/],
    // the IR inside keeps its own 1 MiB cap (importFlow), under the file's 2 MB
    [JSON.stringify({ ...data, flow: { ...data.flow, description: "y".repeat((1 << 20) + 10) } }), /flow: the file is \d+ bytes; at most 1048576/],
  ];
  for (const [text, msg] of cases) {
    const r = parseFlowFile(text, "x");
    assert.equal(r.ok, false, String(msg));
    if (!r.ok) assert.match(r.errors.join("; "), msg);
  }
});

test("saved-by and saved-at are cleaned: one short line, a time that parses", () => {
  const data = JSON.parse(serializeFlowFile(parts(fixture("farm_loop"))));
  const r = parseFlowFile(JSON.stringify({ ...data, savedBy: "Ploy\n\u202eevil\u0000" + "z".repeat(100), savedAt: "yesterday" }), "x");
  assert.ok(r.ok);
  if (r.ok) {
    assert.ok(r.savedBy.startsWith("Ploy evil") && r.savedBy.length <= 40 && !/[\u0000-\u001f\u202e]/.test(r.savedBy));
    assert.equal(r.savedAt, "");
  }
  assert.equal(cleanSavedBy("  สมชาย   ใจดี  "), "สมชาย ใจดี");
});

test("names: letters in any script and spaces stay; what file systems refuse goes (MatPilot's cases + ours)", () => {
  assert.equal(cleanFlowName("  Farm   loop  "), "Farm loop");
  assert.equal(cleanFlowName("ฟาร์ม โพริง"), "ฟาร์ม โพริง");
  assert.equal(cleanFlowName('a/b\\c:d*e?f"g<h>i|j'), "a b c d e f g h i j");
  assert.equal(cleanFlowName("..hidden"), "hidden");
  assert.equal(cleanFlowName("line\none\ttab"), "line one tab");
  assert.equal(cleanFlowName(" / "), "");
  assert.equal(cleanFlowName("x".repeat(100)).length, NAME_MAX_CHARS);
  assert.equal(cleanFlowName("evil\u202etxt.exe"), "evil txt.exe"); // a bidi override would show another name
  assert.equal(cleanFlowName("a\u0085b\u009fc"), "a b c"); // C1 controls
  assert.equal(cleanFlowName("x\ud800y"), "xy"); // a lone surrogate is not UTF-8
  assert.equal(cleanFlowName("CON"), "CON_"); // Windows refuses CON.flow.json: a clone would fail
  assert.equal(cleanFlowName("lpt1"), "lpt1_");
  assert.equal(cleanFlowName("console"), "console");
});

test("names are NFC, and capped by BYTES as well as characters (Thai is 3 bytes a letter)", () => {
  // SARA AM (U+0E33) is NOT changed by NFC (it is by NFKC): Thai stays as typed
  assert.equal(cleanFlowName("น้ำ"), "น้ำ");
  assert.equal(cleanFlowName("น้ำ").length, 3);
  // a decomposed é becomes the composed one
  assert.equal(cleanFlowName("Cafe\u0301"), "Caf\u00e9");
  const thai = "ก".repeat(100); // 100 letters, 300 bytes
  const cut = cleanFlowName(thai);
  assert.equal(cut, "ก".repeat(NAME_MAX_BYTES / 3)); // 60 letters is 180 bytes: the byte cap and the character cap meet
  const marks = "กิ่".repeat(40); // base + vowel + tone: 3 code points, 9 bytes a grapheme
  const m = cleanFlowName(marks);
  assert.ok(utf8Bytes(m) <= NAME_MAX_BYTES && Array.from(m).length <= NAME_MAX_CHARS);
  assert.equal(m, "กิ่".repeat(20)); // cut between graphemes: no letter loses its marks
  for (const s of [thai, marks, "Cafe\u0301 ".repeat(30), "ฟาร์ม/โพริง..", "  .x. "]) {
    assert.equal(cleanFlowName(cleanFlowName(s)), cleanFlowName(s), s); // idempotent
    assert.ok(utf8Bytes(cleanFlowName(s)) <= NAME_MAX_BYTES);
  }
});

test("file names and the names read back from them", () => {
  assert.equal(flowFileName("Farm loop"), "Farm loop.flow.json");
  assert.equal(flowFileName("  ", "farm_loop"), "farm_loop.flow.json");
  assert.equal(flowFileName("", ""), `${DEFAULT_FLOW_NAME}.flow.json`);
  assert.equal(flowNameFromFileName("ฟาร์ม.flow.json"), "ฟาร์ม");
  assert.equal(flowNameFromFileName("Farm.FLOW.JSON"), "Farm");
  assert.equal(flowNameFromFileName("downloads/Farm (1).json"), "Farm (1)");
  assert.equal(flowNameFromFileName("C:\\Users\\x\\Farm.flow.json"), "Farm");
  assert.equal(flowNameFromFileName(".flow.json"), "flow");
  assert.ok(isFlowFileName("a.flow.json") && !isFlowFileName(".flow.json") && !isFlowFileName("a.json"));
});

/** A Storage in a Map. */
function memoryStore(): StorageLike & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return { data, getItem: (k) => data.get(k) ?? null, setItem: (k, v) => void data.set(k, v), removeItem: (k) => void data.delete(k) };
}

test("the file meta (its saved name, its GitHub file) is kept beside the flow it belongs to", () => {
  const flow = fixture("farm_loop");
  const store = memoryStore();
  assert.deepEqual(readFileMeta(store, flow), newFileMeta(flow));
  const link = { repository: "teacher-class/flows", path: "poring-lab/ฟาร์ม.flow.json", sha: "a".repeat(40) };
  assert.ok(writeFileMeta(store, { name: "ฟาร์ม", link }, flow));
  assert.ok(store.data.has(KEYS.file));
  assert.deepEqual(readFileMeta(store, flow), { name: "ฟาร์ม", link });
  // another flow in storage: its meta is not this one's
  assert.deepEqual(readFileMeta(store, { ...flow, name: "other_flow" }), newFileMeta({ ...flow, name: "other_flow" }));
  for (const bad of [
    { ...link, path: "../../x" },
    { ...link, path: "a//b" },
    { ...link, sha: "not-a-sha" },
    { ...link, repository: "https://github.com/teacher-class/flows" }, // only the label form is stored
    { ...link, repository: "a b/c" },
  ]) {
    store.setItem(KEYS.file, JSON.stringify({ flow: flow.name, name: "x", link: bad }));
    assert.equal(readFileMeta(store, flow).link, null, JSON.stringify(bad));
  }
  store.setItem(KEYS.file, "{broken");
  assert.deepEqual(readFileMeta(store, flow), newFileMeta(flow));
  assert.deepEqual(readFileMeta(null, flow), newFileMeta(flow));
  const throwing: StorageLike = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); }, removeItem: () => undefined };
  assert.deepEqual(readFileMeta(throwing, flow), newFileMeta(flow));
  assert.equal(writeFileMeta(throwing, newFileMeta(flow), flow), false);
});

test("Save on this computer: a Blob download, the URL revoked 10 s later (not at once)", () => {
  const log: string[] = [];
  let later: { fn: () => void; ms: number } | null = null;
  const a = { href: "", download: "", rel: "", click: () => log.push("click"), remove: () => log.push("remove") };
  const deps: DownloadDeps = {
    make: () => a,
    attach: () => log.push("attach"),
    urls: {
      createObjectURL: (b: Blob) => (log.push(`blob ${b.type} ${b.size}`), "blob:x"),
      revokeObjectURL: (u: string) => log.push(`revoke ${u}`),
    },
    later: (fn, ms) => void (later = { fn, ms }),
  };
  downloadText("ฟาร์ม.flow.json", '{"a":"ไทย"}\n', deps);
  assert.deepEqual([a.href, a.download, a.rel], ["blob:x", "ฟาร์ม.flow.json", "noopener"]);
  assert.deepEqual(log, [`blob application/json ${utf8Bytes('{"a":"ไทย"}\n')}`, "attach", "click", "remove"]);
  assert.ok(later);
  const pending = later as { fn: () => void; ms: number };
  assert.equal(pending.ms, REVOKE_AFTER_MS);
  assert.equal(REVOKE_AFTER_MS, 10_000);
  pending.fn();
  assert.equal(log.at(-1), "revoke blob:x");
});

test("Ctrl/⌘+S opens Save and Ctrl/⌘+O opens Load, never while typing in a field", () => {
  const key = (over: Partial<KeyLike>): KeyLike => ({ key: "s", code: "KeyS", ctrlKey: true, metaKey: false, altKey: false, shiftKey: false, target: { tagName: "DIV" }, ...over });
  assert.equal(fileShortcut(key({})), "save");
  assert.equal(fileShortcut(key({ key: "S" })), "save");
  assert.equal(fileShortcut(key({ key: "o", code: "KeyO", ctrlKey: false, metaKey: true })), "load");
  assert.equal(fileShortcut(key({ key: "ห", code: "KeyS" })), "save"); // a Thai layout: the key's place
  assert.equal(fileShortcut(key({ key: "น", code: "KeyO" })), "load");
  for (const t of [{ tagName: "INPUT" }, { tagName: "textarea" }, { tagName: "SELECT" }, { tagName: "DIV", isContentEditable: true }]) {
    assert.equal(fileShortcut(key({ target: t })), null, JSON.stringify(t));
  }
  for (const over of [{ ctrlKey: false }, { altKey: true }, { shiftKey: true }, { isComposing: true }, { key: "z", code: "KeyZ" }, { key: "x", code: "KeyS" }]) {
    assert.equal(fileShortcut(key(over)), null, JSON.stringify(over));
  }
  assert.equal(fileShortcut(key({ target: null })), "save");
  assert.equal(fileShortcut(key({ key: undefined as unknown as string, code: undefined })), null); // Chrome's autofill
});
