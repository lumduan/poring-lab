// Ported from MatPilot's src/lib/github/base64.test.ts at 4022c87 (MIT, Copyright (c) 2026 Sarat
// Sonsuk), in node:test, plus base64Bytes.
import assert from "node:assert/strict";
import { test } from "node:test";

import { base64Bytes, decodeBase64Utf8, encodeBase64Utf8 } from "./base64.ts";

test("encodes UTF-8 as Node does (Thai, emoji, more than one 32 KB chunk), and decodes GitHub's wrapped lines", () => {
  const text = `ฟาร์มโพริง น้ำ 🐷 farm\n${"x".repeat(70_000)}`;
  const encoded = encodeBase64Utf8(text);
  assert.equal(encoded, Buffer.from(text, "utf8").toString("base64"));
  const wrapped = encoded.replace(/(.{60})/g, "$1\n");
  assert.equal(decodeBase64Utf8(wrapped), text);
  assert.equal(base64Bytes(wrapped), Buffer.byteLength(text));
  for (const s of ["", "a", "ab", "abc", "ก"]) assert.equal(base64Bytes(encodeBase64Utf8(s)), Buffer.byteLength(s), s);
});

test("refuses bytes that are not UTF-8, and Base64 that is not Base64", () => {
  assert.throws(() => decodeBase64Utf8(Buffer.from([0xff, 0xfe, 0x00]).toString("base64")));
  assert.throws(() => decodeBase64Utf8("***"));
});
