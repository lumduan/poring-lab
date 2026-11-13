"use client";

// THE WORLD RULES' editor (Batt 2026-11-13; lib/maps/rules.ts): the save point, stated once for the
// run, and what happens on a map none of the project's map nodes is on. Both are written into the
// PROJECT as ordinary code -- the save point as the START map's first statement, the unknown-map
// rule as Global's event `unexpected_map` -- so /flows shows them (that node's main, Global's tab)
// and the engine lints them.
import { useState } from "react";

import { mapNodes, nodeById, type Project } from "@/lib/flow/project";
import { knownMaps, savePointNode } from "@/lib/maps/links";
import { MAX_PER_RUN, readRules, type RuleEdit, ruleMaps, setSavePoint, setUnknownMap, wingText } from "@/lib/maps/rules";

export default function RulesPanel({ project, onEdit, onOpen }: { project: Project; onEdit: (r: RuleEdit) => void; onOpen: (id: string) => void }) {
  const r = readRules(project);
  const sp = savePointNode(project);
  const maps = knownMaps(project);
  const spMap = sp.node ? nodeById(project, sp.node) : undefined;
  const [form, setForm] = useState(() => ({
    map: r.savePoint.cell?.map ?? (spMap?.kind === "map" ? spMap.map.map : (maps[0] ?? "")),
    x: r.savePoint.cell ? String(r.savePoint.cell.x) : "",
    y: r.savePoint.cell ? String(r.savePoint.cell.y) : "",
  }));
  const x = Number(form.x);
  const y = Number(form.y);
  const cellOk = /^[a-z0-9_@-]{1,40}$/i.test(form.map) && form.x !== "" && form.y !== "" && Number.isInteger(x) && Number.isInteger(y);
  const count = mapNodes(project).length;
  return (
    <div className="stack" data-testid="rules-panel">
      <h3 className="mp-panel-title">World rules</h3>
      <p className="muted">For every map of this project. They are written into the project as ordinary code (the start map&apos;s first step, a Global event), so /flows shows them and the linter checks them.</p>

      <section className="mp-rule" aria-label="The save point">
        <h4>1. The save point</h4>
        <p className="muted">Where a Butterfly Wing lands, and where a death respawns.</p>
        <p data-testid="rules-save-now">
          {!r.startMap
            ? "The session path does not reach a map yet (login → character → a map): the save point is stated on the START map, so connect one first."
            : r.savePoint.cell
              ? `Stated: ${r.savePoint.cell.map} (${r.savePoint.cell.x}, ${r.savePoint.cell.y}), the first step of ${r.startMap}'s main.`
              : spMap?.kind === "map"
                ? `Not stated. The project sets it at a Kafra on ${spMap.map.map} (${spMap.id}), but only from that step on.`
                : "Not stated, and nothing in the project sets it: a wing or a death lands where the character's save point happens to be."}
        </p>
        <form
          className="mp-rule-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (cellOk) onEdit(setSavePoint(project, { kind: "cell", map: form.map, x, y }));
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
          <button type="submit" className="button button-small button-primary" disabled={!cellOk || !r.startMap} data-testid="rules-save-set">
            {r.savePoint.cell ? "Change it" : "State it"}
          </button>
          {r.savePoint.cell && (
            <button type="button" className="button button-small" onClick={() => onEdit(setSavePoint(project, null))} data-testid="rules-save-clear">
              Clear
            </button>
          )}
        </form>
        <p className="muted">
          It is the character&apos;s save point as YOU know it (set at a Kafra in the game). The project cannot read it from the screen, so it stays a visible warning at approval, as every assertion
          does.
        </p>
      </section>

      <section className="mp-rule" aria-label="An unknown map">
        <h4>2. Any other map</h4>
        <p className="muted">A map none of the {count} map node{count === 1 ? " is" : "s are"} on: a teleport walked into by accident, a warp that led somewhere else.</p>
        {r.custom ? (
          <div className="stack">
            <p>Global writes its own unexpected_map event (its tab {r.tab}, on /flows). It is left as it is.</p>
            <div className="button-row">
              <button type="button" className="button button-small" onClick={() => onOpen("global")}>
                Open Global ↗
              </button>
              <button type="button" className="button button-small" onClick={() => onEdit(setUnknownMap(project, "wing", true))}>
                Replace it with the wing-home rule
              </button>
            </div>
          </div>
        ) : (
          <div className="mp-rule-choice" role="radiogroup" aria-label="On an unknown map">
            <label>
              <input type="radio" name="unknown-map" checked={r.unknownMap === "stop"} onChange={() => onEdit(setUnknownMap(project, "stop"))} data-testid="rules-unknown-stop" />
              Stop the run there <span className="muted">(the built-in default)</span>
            </label>
            <label>
              <input type="radio" name="unknown-map" checked={r.unknownMap === "wing"} onChange={() => onEdit(setUnknownMap(project, "wing"))} data-testid="rules-unknown-wing" />
              Use a Butterfly Wing back to the save point, then carry on there
            </label>
          </div>
        )}
        {r.unknownMap === "wing" && (
          <ul className="mp-rule-list">
            <li>
              The Global event unexpected_map (its tab {r.tab}): on a map that is not {ruleMaps(project).join(", ")}, {wingText(r.wingItem)}. The list follows the map nodes by itself.
            </li>
            <li>At most {MAX_PER_RUN} times a run; then the run stops.</li>
            <li>After the wing the bot carries on with the save point&apos;s map node; with none there, the run stops in that town.</li>
            {!r.savePoint.cell && <li className="mp-rule-warn">State the save point above: without it the linter refuses a wing (it would fly to an unknown place).</li>}
          </ul>
        )}
        {r.overriddenOn.length > 0 && (
          <p className="muted" data-testid="rules-overridden">
            {r.overriddenOn.join(", ")} {r.overriddenOn.length === 1 ? "has its" : "have their"} own unexpected_map: there it runs instead of Global&apos;s (never changed here).
          </p>
        )}
      </section>
    </div>
  );
}
