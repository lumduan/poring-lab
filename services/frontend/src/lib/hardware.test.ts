import assert from "node:assert/strict";
import { test } from "node:test";

import {
  fmtC,
  fmtGB,
  fmtGiB,
  fmtMHz,
  fmtPct,
  fmtW,
  fmtWallTime,
  groupTemps,
  isStale,
  limitTone,
  naText,
  type Sample,
  share,
  sparkPath,
  sparkPoints,
  sparkRange,
  sparkSummary,
  staleAgeS,
  tempTone,
  type Temp,
} from "./hardware.ts";

function sample(na: Record<string, string> = {}): Sample {
  return {
    seq: 1, t_mono_ns: 1, t_wall: 0, read_ms: 1,
    cpu: { model: null, cores: null, busy_pct: null, core_pct: [], core_mhz: [], mhz_source: null, load: null },
    memory: { total_b: null, available_b: null, used_b: null, swap_total_b: null, swap_used_b: null, shmem_b: null },
    shm: null, disk: null, gpu: null, temps: [],
    power: { server_w: null, server_avg_s: null, gpu_w: null, gpu_max_w: null, cpu_pkg_w: null },
    na,
  };
}

test("a null sensor says why, in the backend's words", () => {
  const s = sample({ "power.cpu_pkg_w": "root only", "gpu.power_w": "warming up" });
  assert.equal(naText(s, "power.cpu_pkg_w"), "n/a: root only");
  assert.equal(naText(s, "gpu.temp_c", "gpu.power_w"), "n/a: warming up"); // the first key with a reason
  assert.equal(naText(s, "nothing"), "n/a");
  assert.equal(naText(null, "power.cpu_pkg_w"), "n/a");
});

test("formatting: units stated, null stays null (never a fake zero)", () => {
  assert.equal(fmtPct(12.345), "12.3 %");
  assert.equal(fmtPct(0), "0.0 %");
  assert.equal(fmtGiB(16089124864), "15.0 GiB");
  assert.equal(fmtGB(83376840704), "83.4 GB"); // decimal, as the disk floors are stated
  assert.equal(fmtW(16.94), "16.9 W");
  assert.equal(fmtC(50.4), "50 °C");
  assert.equal(fmtMHz(1197.3), "1197 MHz");
  for (const f of [fmtPct, fmtGiB, fmtGB, fmtW, fmtC, fmtMHz]) {
    assert.equal(f(null), null);
    assert.equal(f(undefined), null);
    assert.equal(f(Number.NaN), null);
  }
  assert.equal(typeof fmtWallTime(1794109691), "string");
  assert.equal(fmtWallTime(null), null);
  assert.equal(share(1, 4), 25);
  assert.equal(share(1, 0), null);
  assert.equal(share(null, 4), null);
});

test("staleness: the backend's age at fetch plus this tab's time since, over 6 s", () => {
  assert.equal(staleAgeS(0.5, 10_000, 12_000), 2.5);
  assert.equal(staleAgeS(0.5, 10_000, 9_000), 0.5); // a clock step back never makes it younger
  assert.equal(staleAgeS(null, 10_000, 12_000), null);
  assert.equal(staleAgeS(0.5, null, 12_000), null);
  assert.equal(isStale(2.5), false);
  assert.equal(isStale(6), false);
  assert.equal(isStale(6.1), true);
  assert.equal(isStale(null), true); // nothing yet is not fresh
  // a backend that stopped answering: the last good sample ages on this tab's clock
  assert.equal(isStale(staleAgeS(0.2, 1_000, 8_000)), true);
});

test("tones: a temperature against its own max/crit; a use against its limit", () => {
  assert.equal(tempTone(35, 78, 88), "ok");
  assert.equal(tempTone(78, 78, 88), "warn");
  assert.equal(tempTone(88, 78, 88), "crit");
  assert.equal(tempTone(101, null, 110), "warn"); // no max: within 10 °C of crit
  assert.equal(tempTone(99, null, 110), "ok");
  assert.equal(tempTone(90, null, null), "ok"); // no limits: no judgement
  assert.equal(limitTone(380e6, 4e9), "ok");
  assert.equal(limitTone(3.1e9, 4e9), "warn");
  assert.equal(limitTone(4.2e9, 4e9), "crit");
  assert.equal(limitTone(null, 4e9), "ok");
});

test("temperatures group by chip in the backend's order", () => {
  const t = (chip: string, label: string): Temp => ({ chip, label, c: 40, max_c: null, crit_c: null });
  const groups = groupTemps([t("coretemp", "Package id 0"), t("coretemp", "Core 0"), t("tg3", "eno1"), t("tg3", "eno2"), t("i915", "i915")]);
  assert.deepEqual(groups.map((g) => [g.chip, g.items.length]), [["coretemp", 2], ["tg3", 2], ["i915", 1]]);
});

test("sparkline: newest at the right edge, y by value, a null is a gap", () => {
  const opts = { width: 100, height: 10, windowS: 600, min: 0, max: 100 };
  assert.equal(sparkPath([-600, -300, 0], [0, 50, 100], opts), "M0 10 L50 5 L100 0");
  assert.equal(sparkPath([-4, -2, 0], [10, null, 30], { ...opts, windowS: 4 }), "M0 9 M100 7");
  assert.equal(sparkPath([-700, 0], [50, 50], opts), "M100 5"); // older than the window: left out
  assert.equal(sparkPath([-2, 0], [150, -5], opts), "M99.7 0 L100 10"); // clamped to the bounds
  assert.equal(sparkPath([], [], opts), "");
  assert.deepEqual(sparkPoints([-300, 0], [50, null], opts).at(-1), { x: 50, y: 5, move: true }); // the newest drawn point
});

test("sparkline bounds: fixed, else from the data, padded when flat", () => {
  assert.deepEqual(sparkRange([5, 7], { min: 0, max: 100 }), [0, 100]);
  assert.deepEqual(sparkRange([16.9, 17.2], {}), [16.9, 17.2]);
  assert.deepEqual(sparkRange([100, 100], {}), [95, 105]);
  assert.deepEqual(sparkRange([null, null], {}), [0, 1]);
  assert.deepEqual(sparkRange([0, 0], { min: 0 }), [0, 1]);
  assert.equal(sparkSummary([3.21, null, 41], " %"), "last 10 min: min 3.2 %, max 41.0 %");
  assert.equal(sparkSummary([null], " W"), "no history yet");
});
