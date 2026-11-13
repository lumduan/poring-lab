"use client";

// THE BINDING STRIP above a tab's blocks (Batt 2026-11-13: "the flows page should say which map
// this flow is bound to, and where each exit goes"): for a map block's tab, its map, how the
// character arrives (each entry) and where each exit leads, every map a link to its own tab; for
// the Map tab, the maps and the world rules; for a plain flow, why it has no map. Read-only: the
// links are made in the blocks (take exit) or on the Maps page.
import Link from "next/link";

import type { Flow } from "@/lib/flow/ir";
import { arrivalText, blockLinks, EXIT_WORDS, knownMaps } from "@/lib/maps/links";
import { readRules } from "@/lib/maps/rules";

import { EXIT_COLOURS } from "./FlowCanvas";

type P = { flow: Flow; tab: string; onTab: (key: string) => boolean; onLeave: () => void; onLoadStarter: () => void };

function Rules({ flow, onLeave }: { flow: Flow; onLeave: () => void }) {
  const r = readRules(flow);
  return (
    <span className="mb-part" data-testid="binding-rules">
      <span className="mb-key">world rules</span> save point {r.savePoint.cell ? `${r.savePoint.cell.map} (${r.savePoint.cell.x}, ${r.savePoint.cell.y})` : "not stated"} · any other map →{" "}
      {r.custom ? "this flow's own event" : r.unknownMap === "wing" ? "a Butterfly Wing home" : "the run stops"}{" "}
      <Link href="/maps?node=unknown" className="mb-link" onClick={onLeave}>
        change on Maps
      </Link>
    </span>
  );
}

export default function MapBinding({ flow, tab, onTab, onLeave, onLoadStarter }: P) {
  const wf = flow.workflow;
  if (!wf) {
    const n = flow.main?.length ?? 0;
    return (
      <div className="map-binding" data-kind="plain" data-testid="map-binding">
        <span className="mb-part">
          <strong>Not bound to a map.</strong> This is a PLAIN flow: one program (“main”, {n} step{n === 1 ? "" : "s"}) that runs wherever the character stands, so it has no entries, exits or
          map.
        </span>
        <span className="mb-part">
          To give each map its own flow:{" "}
          <button type="button" className="mb-link" onClick={onLoadStarter} data-testid="binding-load-starter">
            open the two-map starter
          </button>{" "}
          or start from{" "}
          <Link href="/maps" className="mb-link" onClick={onLeave}>
            the Maps page
          </Link>
          .
        </span>
      </div>
    );
  }
  const block = tab.startsWith("block:") ? tab.slice(6) : null;
  const links = block ? blockLinks(flow, block) : null;
  const go = (b: string) => (
    <button type="button" className="mb-map" onClick={() => onTab(`block:${b}`)} title={`Open ${b}'s tab`}>
      {wf.blocks.find((x) => x.name === b)?.map.map ?? `${b}?`}
    </button>
  );
  if (!links) {
    const maps = knownMaps(flow);
    return (
      <div className="map-binding" data-kind="all" data-testid="map-binding">
        <span className="mb-part">
          <span className="mb-key">{maps.length} map{maps.length === 1 ? "" : "s"}</span>
          {wf.blocks.map((b, i) => (
            <span key={b.name}>
              {i > 0 && ", "}
              {go(b.name)}
            </span>
          ))}{" "}
          · starts on {go(wf.start_block)}
        </span>
        <Rules flow={flow} onLeave={onLeave} />
      </div>
    );
  }
  return (
    <div className="map-binding" data-kind="block" data-testid="map-binding">
      <span className="mb-part">
        <span className="mb-key">bound to map</span> <strong>{links.map}</strong> <span className="muted">(its map block {links.block})</span>
      </span>
      <span className="mb-part" data-testid="binding-entries">
        <span className="mb-key">arrives</span>
        {links.entries.length === 0 && <span className="mb-warn">no entry</span>}
        {links.entries.map((e, i) => (
          <span key={e.name}>
            {i > 0 && " · "}
            {e.name}
            {e.at ? ` (${e.at.x}, ${e.at.y})` : ""}:{" "}
            {e.arrivals.length === 0 ? (
              <span className="muted">nothing arrives yet</span>
            ) : (
              e.arrivals.map((a, j) => (
                <span key={j}>
                  {j > 0 && ", "}
                  {a.from ? (
                    <>
                      {arrivalText({ ...a, fromMap: null })} from {go(a.from)}
                    </>
                  ) : (
                    arrivalText(a)
                  )}
                </span>
              ))
            )}
          </span>
        ))}
      </span>
      <span className="mb-part" data-testid="binding-exits">
        <span className="mb-key">exits</span>
        {links.exits.length === 0 && <span className="muted">none: the run ends on this map</span>}
        {links.exits.map((x, i) => (
          <span key={x.path} style={{ color: EXIT_COLOURS[x.kind] }}>
            {i > 0 && " · "}→ {go(x.toBlock)} <span className="mb-how">({EXIT_WORDS[x.kind]}: {x.how})</span>
          </span>
        ))}
      </span>
      <Rules flow={flow} onLeave={onLeave} />
    </div>
  );
}
