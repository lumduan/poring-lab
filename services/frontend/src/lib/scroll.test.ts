import assert from "node:assert/strict";
import { test } from "node:test";

import { atBottom, atTop, keepAnchor } from "./scroll.ts";

test("the HUD log follows new lines only when the reader is at the newest (bottom) line", () => {
  assert.equal(atBottom({ scrollTop: 0, scrollHeight: 192, clientHeight: 192 }), true); // no overflow
  assert.equal(atBottom({ scrollTop: 100, scrollHeight: 300, clientHeight: 198 }), true); // 2 px off
  assert.equal(atBottom({ scrollTop: 40, scrollHeight: 300, clientHeight: 192 }), false); // reading older lines
});

test("the packet list keeps the reader's row in place when rows arrive above it", () => {
  assert.equal(atTop({ scrollTop: 0 }), true);
  assert.equal(atTop({ scrollTop: 3 }), true);
  assert.equal(atTop({ scrollTop: 120 }), false);
  // the row was 8 px below the top edge at offsetTop 128; 40 px of new rows arrived above it
  assert.equal(keepAnchor(168, 8), 160);
  assert.equal(keepAnchor(5, 8), 0); // never negative
});
