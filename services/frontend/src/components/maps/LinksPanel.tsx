"use client";

// THE LINKS PANEL under the Maps graph (Batt 2026-11-13: "show which map links to which and how,
// with the information below"): the selected map's entries (how the character arrives) and exits
// (where each goes and how), or, with no map selected, every link of the flow. Clicking a map name
// selects that node; "Open flow" opens the map's blocks on /flows. Read-only: links are drawn on
// the graph or written in a map's flow.
import { EXIT_COLOURS } from "@/components/flows/FlowCanvas";
import type { Flow } from "@/lib/flow/ir";
import { arrivalText, blockLinks, EXIT_WORDS, worldLinks } from "@/lib/maps/links";
import { readRules } from "@/lib/maps/rules";

type P = { flow: Flow; block: string | null; onSelect: (id: string) => void; onOpenFlow: (block: string) => void; onRules: () => void };

const cell = (c: { x: number; y: number } | null) => (c ? `(${c.x}, ${c.y})` : "anywhere");

function MapButton({ flow, block, onSelect }: { flow: Flow; block: string; onSelect: P["onSelect"] }) {
  const b = flow.workflow?.blocks.find((x) => x.name === block);
  if (!b) return <span className="mp-rule-warn">{block} (not in this flow)</span>;
  return (
    <button type="button" className="mp-link-map" onClick={() => onSelect(`block:${b.name}`)} title={`Select ${b.map.map} (${b.name})`}>
      {b.map.map}
    </button>
  );
}

function RulesLine({ flow, onRules }: { flow: Flow; onRules: () => void }) {
  const r = readRules(flow);
  return (
    <p className="mp-links-rules" data-testid="links-rules">
      <strong>World rules:</strong> save point {r.savePoint.cell ? `${r.savePoint.cell.map} ${cell(r.savePoint.cell)}` : "not stated"} · any other map →{" "}
      {r.custom ? "the flow's own event" : r.unknownMap === "wing" ? "a Butterfly Wing home" : "the run stops"}{" "}
      <button type="button" className="mp-button" onClick={onRules} data-testid="links-rules-edit">
        Change
      </button>
    </p>
  );
}

export default function LinksPanel({ flow, block, onSelect, onOpenFlow, onRules }: P) {
  const wf = flow.workflow;
  if (!wf) {
    return (
      <div className="mp-links" data-testid="links-panel">
        <p>
          <strong>This flow is not bound to any map.</strong> A plain flow is ONE program (the tab “main” on /flows) that runs wherever the character stands, so there are no maps to link. Load ▸
          Starter: two maps, or One map from the lab data, to place maps.
        </p>
      </div>
    );
  }
  const links = block ? blockLinks(flow, block) : null;
  if (links) {
    return (
      <div className="mp-links" data-testid="links-panel">
        <div className="mp-links-head">
          <strong>{links.map}</strong>
          <span className="muted">its flow: the map node {links.block}</span>
          <button type="button" className="mp-button" onClick={() => onOpenFlow(links.block)} data-testid="links-open-flow">
            Open flow ↗
          </button>
        </div>
        <div className="mp-links-grid">
          <table className="mp-links-table" aria-label={`How the character arrives on ${links.map}`}>
            <caption>Entries: how the character arrives</caption>
            <thead>
              <tr>
                <th>entry</th>
                <th>cell</th>
                <th>arrives by</th>
              </tr>
            </thead>
            <tbody>
              {links.entries.map((e) => (
                <tr key={e.name}>
                  <td>{e.name}</td>
                  <td>
                    {cell(e.at)}
                    {e.at ? ` ±${e.radius}` : ""}
                  </td>
                  <td>
                    {e.arrivals.length === 0 && <span className="muted">nothing arrives here yet</span>}
                    {e.arrivals.map((a, i) => (
                      <span key={i} className="mp-arrival" style={{ color: a.kind === "start" ? undefined : EXIT_COLOURS[a.kind] }}>
                        {a.from ? (
                          <>
                            {arrivalText({ ...a, fromMap: null })} from <MapButton flow={flow} block={a.from} onSelect={onSelect} />
                          </>
                        ) : (
                          arrivalText(a)
                        )}
                      </span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <table className="mp-links-table" aria-label={`Where ${links.map}'s exits go`}>
            <caption>Exits: where the character leaves to</caption>
            <thead>
              <tr>
                <th>to</th>
                <th>how</th>
                <th>lands at</th>
              </tr>
            </thead>
            <tbody>
              {links.exits.length === 0 && !links.respawnTo && (
                <tr>
                  <td colSpan={3} className="muted">
                    no exit: the run ends on this map
                  </td>
                </tr>
              )}
              {links.exits.map((x) => (
                <tr key={x.path} style={{ color: EXIT_COLOURS[x.kind] }}>
                  <td>
                    <MapButton flow={flow} block={x.toBlock} onSelect={onSelect} />
                  </td>
                  <td>
                    {EXIT_WORDS[x.kind]}: {x.how}
                  </td>
                  <td>{x.entryKnown ? x.toEntry : <span className="mp-rule-warn">{x.toEntry} (no such entry)</span>}</td>
                </tr>
              ))}
              {links.respawnTo && links.respawnTo.block !== links.block && (
                <tr style={{ color: EXIT_COLOURS.death_respawn }}>
                  <td>
                    <MapButton flow={flow} block={links.respawnTo.block} onSelect={onSelect} />
                  </td>
                  <td>a death respawns at the save point (derived)</td>
                  <td>the save point</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <RulesLine flow={flow} onRules={onRules} />
      </div>
    );
  }
  const all = worldLinks(flow);
  return (
    <div className="mp-links" data-testid="links-panel">
      <div className="mp-links-head">
        <strong>Every link</strong>
        <span className="muted">
          {wf.blocks.length} map{wf.blocks.length === 1 ? "" : "s"}, {all.length} exit{all.length === 1 ? "" : "s"} · the run starts on <MapButton flow={flow} block={wf.start_block} onSelect={onSelect} /> ({wf.start_entry}) ·
          click a map for its entries and exits
        </span>
      </div>
      <table className="mp-links-table" aria-label="Every link of the flow">
        <thead>
          <tr>
            <th>from</th>
            <th>to</th>
            <th>how</th>
            <th>lands at</th>
          </tr>
        </thead>
        <tbody>
          {all.length === 0 && (
            <tr>
              <td colSpan={4} className="muted">
                no exits yet: drag from a map&apos;s “+” port onto another map
              </td>
            </tr>
          )}
          {all.map((x) => (
            <tr key={x.path} style={{ color: EXIT_COLOURS[x.kind] }}>
              <td>
                <MapButton flow={flow} block={x.fromBlock} onSelect={onSelect} />
              </td>
              <td>
                <MapButton flow={flow} block={x.toBlock} onSelect={onSelect} />
              </td>
              <td>
                {EXIT_WORDS[x.kind]}: {x.how}
              </td>
              <td>{x.toEntry}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <RulesLine flow={flow} onRules={onRules} />
    </div>
  );
}
