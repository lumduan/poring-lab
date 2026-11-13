"use client";

// THE FLOWS ROW (Batt 2026-11-13: "why, when I open /flows, don't I see this flow's name at all?"):
// every flow /flows can show, by name, always in view under the header -- the person's own flow
// (the studio's: the one this browser last had open) and each map's flow (the runner flows, named
// after their maps). One press switches; nothing is replaced or lost (the studio keeps its flow in
// this browser, and a map flow is read only). Names render as text only.
import { RUNNERS } from "@/lib/flow/runners";

export type FlowPick = { kind: "mine" } | { kind: "map"; id: string };

export default function FlowSwitcher({ current, myName, onMine, onMap }: { current: FlowPick; myName: string; onMine: () => void; onMap: (id: string) => void }) {
  const mine = current.kind === "mine";
  return (
    <nav className="flow-switcher" aria-label="Flows" data-testid="flow-switcher">
      <span className="flow-switcher-label">Flows</span>
      <button type="button" className="flow-switcher-item" aria-pressed={mine} onClick={mine ? undefined : onMine} title="Your own flow: the blocks you edit (Simulate only)" data-testid="flow-switch-mine">
        <span className="flow-switcher-name">{myName.slice(0, 60) || "my flow"}</span>
        <span className="flow-switcher-kind">your flow</span>
      </button>
      {RUNNERS.map((r) => {
        const on = current.kind === "map" && current.id === r.id;
        return (
          <button
            key={r.id}
            type="button"
            className="flow-switcher-item"
            aria-pressed={on}
            onClick={on ? undefined : () => onMap(r.id)}
            title={`${r.subtitle ?? r.title}: Simulate, or Run in the game`}
            data-testid={`flow-switch-${r.id}`}
          >
            <span className="flow-switcher-name">{r.title}</span>
            <span className="flow-switcher-kind">map flow · Run</span>
          </button>
        );
      })}
    </nav>
  );
}
