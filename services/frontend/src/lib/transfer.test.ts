import assert from "node:assert/strict";
import { test } from "node:test";

import {
  checkPaste,
  describePaste,
  describeTransferError,
  fileUrl,
  formatBytes,
  PASTE_MAX_BYTES,
  TransferError,
  utf8Bytes,
} from "./transfer.ts";

test("the paste cap counts UTF-8 bytes: Thai is 3 bytes per character", () => {
  assert.equal(utf8Bytes("abc"), 3);
  assert.equal(utf8Bytes("สวัสดี"), 18);
  const thai = "ส".repeat(Math.floor(PASTE_MAX_BYTES / 3));
  assert.equal(checkPaste(thai).ok, true);
  const over = checkPaste(thai + "ส");
  assert.equal(over.ok, false);
  assert.match(over.message ?? "", /Too large to paste: 64 KiB.*limit 64 KiB/);
  assert.equal(checkPaste("a".repeat(PASTE_MAX_BYTES)).ok, true);
  assert.equal(checkPaste("a".repeat(PASTE_MAX_BYTES + 1)).ok, false);
});

test("an empty paste is not sendable but is not an error either", () => {
  assert.deepEqual(checkPaste(""), { ok: false, bytes: 0, message: null });
});

test("byte sizes read naturally", () => {
  assert.equal(formatBytes(37), "37 B");
  assert.equal(formatBytes(64 * 1024), "64 KiB");
  assert.equal(formatBytes(512 * 1024 * 1024), "512 MiB");
  assert.equal(formatBytes(1536 * 1024), "1.5 MiB");
  assert.equal(formatBytes(Number.NaN), "?");
});

test("paste outcomes explain themselves, including mode refusal", () => {
  assert.match(describePaste("mode_bot"), /BOT mode/);
  assert.match(describePaste("no_data_request"), /Click a text field/);
  assert.equal(describePaste("something_new"), "Paste failed: something_new.");
});

test("transfer errors: the size cap points at other channels for large files", () => {
  const message = describeTransferError(413, {
    reason: "too_large",
    size: 3 * 1024 ** 3,
    max_bytes: 512 * 1024 ** 2,
  });
  assert.match(message, /3 GiB/);
  assert.match(message, /512 MiB/);
  assert.match(message, /SMB or a direct download/);
  assert.match(describeTransferError(409, { reason: "exists", name: "a.txt" }), /"a.txt" already/);
  assert.match(describeTransferError(503, { reason: "transfer_disabled" }), /RDP_DRIVES/);
  assert.equal(describeTransferError(500, null), "Transfer failed (HTTP 500).");
});

test("TransferError keeps the status and the machine-readable reason", () => {
  const error = new TransferError(409, { reason: "exists", name: "x" });
  assert.equal(error.status, 409);
  assert.equal(error.reason, "exists");
  assert.equal(new TransferError(502, "Bad Gateway").reason, null);
});

test("file URLs encode names, Thai and separators included", () => {
  assert.equal(
    fileUrl("http://h:8000", "รายงาน 1.txt"),
    "http://h:8000/transfer/files/%E0%B8%A3%E0%B8%B2%E0%B8%A2%E0%B8%87%E0%B8%B2%E0%B8%99%201.txt",
  );
  assert.equal(fileUrl("http://h:8000", "a/b"), "http://h:8000/transfer/files/a%2Fb");
  assert.equal(fileUrl("http://h:8000", "a", true), "http://h:8000/transfer/files/a?overwrite=true");
});
