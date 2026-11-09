// The studio's READY-MADE STARTER program (what a learner sees first, as on matpilot.org/blocks):
// one tab, "main", with three blocks: wait 1 second, wait until the v1 detector sees a monster
// (at most 30 s), stop. Kept minimal. Its canonical JSON is fixtures/starter.json, which the
// flow engine's tests check is canonical and lints without an error (poring_flow
// tests/test_models.py); starter.test.ts checks this object equals it.
import { type Flow, IR_VERSION, RUNTIME_DEFAULT_S, WHERE_BUDGET_DEFAULT } from "./ir.ts";

export const STARTER_NAME = "my_first_flow";

export function starterFlow(): Flow {
  return {
    ir: IR_VERSION,
    name: STARTER_NAME,
    description: "",
    target: { client: "kro-20211103-prere", server: "lab-rathena", locale: "en", path: "s2" },
    assumes: [],
    max_runtime_s: RUNTIME_DEFAULT_S,
    where_budget: WHERE_BUDGET_DEFAULT,
    stop_when: null,
    variables: {},
    procedures: {},
    handlers: [],
    main: [
      { kind: "wait_until", cond: { kind: "lit", value: false }, timeout_s: 1, outcome_to: null },
      {
        kind: "wait_until",
        cond: { kind: "sense", sensor: "detector_sees", args: { label: { kind: "lit", value: "monster" }, model: { kind: "lit", value: "v1" } } },
        timeout_s: 30,
        outcome_to: null,
      },
      { kind: "stop", reason: "done" },
    ],
    workflow: null,
  };
}
