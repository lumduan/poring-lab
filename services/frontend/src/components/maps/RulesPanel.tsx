"use client";

// THE WORLD RULES' editor (Batt 2026-11-13; lib/maps/rules.ts): the save point, stated once for the
// run, and what happens on a map none of the flow's map nodes is on. Both are written into the
// flow as the engine's own blocks, so /flows shows them (the start block's first step, the events
// tab) and the linter checks them.
import { useState } from "react";

import { type EditResult, savePointBlock } from "@/lib/flow/canvas";
import type { Flow } from "@/lib/flow/ir";
import { knownMaps } from "@/lib/maps/links";
import { MAX_PER_RUN, readRules, ruleMaps, setSavePoint, setUnknownMap } from "@/lib/maps/rules";

export default function RulesPanel({ flow, onEdit }: { flow: Flow; onEdit: (r: EditResult) => void }) {
  const r = readRules(flow);
  const sp = savePointBlock(flow);
  const maps = knownMaps(flow);
  const wf = flow.workflow;
  const [form, setForm] = useState(() => ({
    map: r.savePoint.cell?.map ?? (sp.block ? (wf?.blocks.find((b) => b.name === sp.block)?.map.map ?? "") : (maps[0] ?? "")),
    x: r.savePoint.cell ? String(r.savePoint.cell.x) : "",
    y: r.savePoint.cell ? String(r.savePoint.cell.y) : "",
  }));
  if (!wf) {
    return (
      <div className="stack" data-testid="rules-panel">
        <h3 className="mp-panel-title">World rules</h3>
        <p>A plain flow has no maps, so it has no world rules. Load ▸ the two-map starter, or One map from the lab data, to place maps.</p>
      </div>
    );
  }
  const x = Number(form.x);
  const y = Number(form.y);
  const cellOk = /^[a-z0-9_@-]{1,40}$/i.test(form.map) && form.x !== "" && form.y !== "" && Number.isInteger(x) && Number.isInteger(y);
  return (
    <div className="stack" data-testid="rules-panel">
      <h3 className="mp-panel-title">World rules</h3>
      <p className="muted">For every map of this flow. They are written into the flow as ordinary blocks, so /flows shows them and the linter checks them.</p>

      <section className="mp-rule" aria-label="The save point">
        <h4>1. The save point</h4>
        <p className="muted">Where a Butterfly Wing lands, and where a death respawns.</p>
        <p data-testid="rules-save-now">
          {r.savePoint.cell
            ? `Stated: ${r.savePoint.cell.map} (${r.savePoint.cell.x}, ${r.savePoint.cell.y}), the first step of ${wf.start_block}.`
            : sp.block
              ? `Not stated. The flow sets it at a Kafra on ${wf.blocks.find((b) => b.name === sp.block)?.map.map} (${sp.block}), but only from that step on.`
              : "Not stated, and nothing in the flow sets it: a wing or a death lands where the character's save point happens to be."}
        </p>
        <form
          className="mp-rule-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (cellOk) onEdit(setSavePoint(flow, { kind: "cell", map: form.map, x, y }));
          }}
        >
          <label>
            map
            <input value={form.map} onChange={(e) => setForm({ ...form, map: e.target.value })} list="rules-maps" maxLength={40} data-testid="rules-save-map" />
          </label>
          <datalist id="rules-maps">
            {maps.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
          <label>
            x
            <input value={form.x} onChange={(e) => setForm({ ...form, x: e.target.value })} inputMode="numeric" maxLength={4} size={4} data-testid="rules-save-x" />
          </label>
          <label>
            y
            <input value={form.y} onChange={(e) => setForm({ ...form, y: e.target.value })} inputMode="numeric" maxLength={4} size={4} data-testid="rules-save-y" />
          </label>
          <button type="submit" className="button button-small button-primary" disabled={!cellOk} data-testid="rules-save-set">
            {r.savePoint.cell ? "Change it" : "State it"}
          </button>
          {r.savePoint.cell && (
            <button type="button" className="button button-small" onClick={() => onEdit(setSavePoint(flow, null))} data-testid="rules-save-clear">
              Clear
            </button>
          )}
        </form>
        <p className="muted">
          It is the character&apos;s save point as YOU know it (set at a Kafra in the game). The flow cannot read it from the screen, so it stays a visible warning at approval, as every assertion
          does.
        </p>
      </section>

      <section className="mp-rule" aria-label="An unknown map">
        <h4>2. Any other map</h4>
        <p className="muted">A map none of the {wf.blocks.length} map nodes is on: a teleport walked into by accident, a warp that led somewhere else.</p>
        {r.custom ? (
          <div className="stack">
            <p>This flow writes its own unexpected_map event (/flows, the events tab). It is left as it is.</p>
            <button type="button" className="button button-small" onClick={() => onEdit(setUnknownMap(flow, "wing", true))}>
              Replace it with the wing-home rule
            </button>
          </div>
        ) : (
          <div className="mp-rule-choice" role="radiogroup" aria-label="On an unknown map">
            <label>
              <input type="radio" name="unknown-map" checked={r.unknownMap === "stop"} onChange={() => onEdit(setUnknownMap(flow, "stop"))} data-testid="rules-unknown-stop" />
              Stop the run there <span className="muted">(the built-in, always on)</span>
            </label>
            <label>
              <input type="radio" name="unknown-map" checked={r.unknownMap === "wing"} onChange={() => onEdit(setUnknownMap(flow, "wing"))} data-testid="rules-unknown-wing" />
              Use a Butterfly Wing back to the save point, then carry on there
            </label>
          </div>
        )}
        {r.unknownMap === "wing" && (
          <ul className="mp-rule-list">
            <li>Known maps (no wing there): {ruleMaps(flow).join(", ")}. The list follows the map nodes by itself.</li>
            <li>At most {MAX_PER_RUN} times a run; then the run stops.</li>
            <li>After the wing the bot carries on with the save point&apos;s map node; with none there, the run stops in that town.</li>
            {!r.savePoint.cell && <li className="mp-rule-warn">State the save point above: without it the linter refuses a wing (it would fly to an unknown place).</li>}
          </ul>
        )}
      </section>
    </div>
  );
}
