import assert from "node:assert/strict";
import test from "node:test";

import { exampleRunFolder, folderProblem, maxProblem, runLogReasonText } from "./runlog.ts";

test("the Run log's folder and size checks mirror the backend's (poring_env.runlog)", () => {
  assert.equal(folderProblem("logs/bot", 512), null);
  assert.equal(folderProblem("/mnt/nas/bot-logs", 512), null);
  assert.equal(folderProblem("  ", 512), "folder_empty");
  assert.equal(folderProblem("/", 512), "folder_root");
  assert.equal(folderProblem("logs/../../etc", 512), "folder_dotdot");
  assert.equal(folderProblem("x".repeat(600), 512), "folder_too_long");
  assert.equal(maxProblem(100, [1, 1_000_000]), null);
  assert.equal(maxProblem(0, [1, 1_000_000]), "max_out_of_range");
  assert.equal(maxProblem(1.5, [1, 1_000_000]), "max_not_a_whole_number");
  assert.match(runLogReasonText("folder_dotdot"), /whole path/);
});

test("a Run's folder is named by its start time, as the helper names it", () => {
  const at = new Date(2026, 10, 21, 11, 26, 42);
  assert.equal(exampleRunFolder("logs/bot/", at), "logs/bot/20261121-112642-<run>/");
});
