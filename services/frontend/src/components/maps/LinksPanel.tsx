"use client";

// THE LINKS PANEL under the Maps graph (Batt 2026-11-13: "show which map links to which and how,
// with the information below"): the selected map node's entries (how the character arrives) and
// exits (where each goes and how, in which tab), or, with no map selected, every link of the
// project. Clicking a map selects its node; "Open flow" opens the node's tabs on /flows. Read-only:
// links are drawn on the graph or written in a map node's tabs.
import { EXIT_COLOURS } from "@/components/maps/colours";
import { mapNodes, nodeById, type Project, sessionPath } from "@/lib/flow/project";
import { arrivalText, EXIT_WORDS, nodeLinks, worldLinks } from "@/lib/maps/links";
import { readRules, wingText } from "@/lib/maps/rules";

type P = { project: Project; node: string | null; onSelect: (id: string) => void; onOpen: (id: string) => void; onRules: () => void };

const cell = (c: { x: number; y: number } | null) => (c ? `(${c.x}, ${c.y})` : "anywhere");

function MapButton({ project, node, onSelect }: { project: Project; node: string; onSelect: P["onSelect"] }) {
  const n = nodeById(project, node);
  if (!n) return <span className="mp-rule-warn">{node} (not in this project)</span>;
  return (
    <button type="button" className="mp-link-map" onClick={() => onSelect(n.id)} title={`Select ${n.id}`}>
      {n.kind === "map" ? n.map.map : n.id}
    </button>
  );
}

function RulesLine({ project, onRules }: { project: Project; onRules: () => void }) {
  const r = readRules(project);
  return (
    <p className="mp-links-rules" data-testid="links-rules">
      <strong>World rules:</strong> save point {r.savePoint.cell ? `${r.savePoint.cell.map} ${cell(r.savePoint.cell)}` : "not stated"} · any other map →{" "}
      {r.custom ? "Global's own event" : r.unknownMap === "wing" ? `${wingText(r.wingItem)} home` : "the run stops"}{" "}
      <button type="button" className="mp-button" onClick={onRules} data-testid="links-rules-edit">
        Change
      </button>
    </p>
  );
}

export default function LinksPanel({ project, node, onSelect, onOpen, onRules }: P) {
  const links = node ? nodeLinks(project, node) : null;
  if (links) {
    return (
      <div className="mp-links" data-testid="links-panel">
        <div className="mp-links-head">
          <strong>{links.map}</strong>
          <span className="muted">the map node {links.node}</span>
          <button type="button" className="mp-button" onClick={() => onOpen(links.node)} data-testid="links-open-flow">
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
                        {a.from && a.kind !== "start" ? (
                          <>
                            {arrivalText({ ...a, fromMap: null })} from <MapButton project={project} node={a.from} onSelect={onSelect} />
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
                    <MapButton project={project} node={x.toNode} onSelect={onSelect} />
                  </td>
                  <td>
                    {EXIT_WORDS[x.kind]}: {x.how}
                    {x.tab !== "main" ? <span className="muted"> (tab {x.tab})</span> : null}
                  </td>
                  <td>{x.entryKnown ? x.toEntry : <span className="mp-rule-warn">{x.toEntry} (no such entry)</span>}</td>
                </tr>
              ))}
              {links.respawnTo && links.respawnTo.node !== links.node && (
                <tr style={{ color: EXIT_COLOURS.death_respawn }}>
                  <td>
                    <MapButton project={project} node={links.respawnTo.node} onSelect={onSelect} />
                  </td>
                  <td>a death respawns at the save point (derived)</td>
                  <td>the save point</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <RulesLine project={project} onRules={onRules} />
      </div>
    );
  }
  const all = worldLinks(project);
  const sp = sessionPath(project);
  const count = mapNodes(project).length;
  return (
    <div className="mp-links" data-testid="links-panel">
      <div className="mp-links-head">
        <strong>Every link</strong>
        <span className="muted">
          {count} map{count === 1 ? "" : "s"}, {all.length} exit{all.length === 1 ? "" : "s"} ·{" "}
          {sp.map ? (
            <>
              the session enters on <MapButton project={project} node={sp.map.id} onSelect={onSelect} /> ({sp.entry ?? "no entry"})
            </>
          ) : (
            "the session path does not reach a map yet"
          )}{" "}
          · click a map for its entries and exits
        </span>
      </div>
      <table className="mp-links-table" aria-label="Every link of the project">
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
                <MapButton project={project} node={x.fromNode} onSelect={onSelect} />
              </td>
              <td>
                <MapButton project={project} node={x.toNode} onSelect={onSelect} />
              </td>
              <td>
                {EXIT_WORDS[x.kind]}: {x.how}
                {x.tab !== "main" ? <span className="muted"> (tab {x.tab})</span> : null}
              </td>
              <td>{x.toEntry}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <RulesLine project={project} onRules={onRules} />
    </div>
  );
}
