"use client";

// THE FLOWS ROW (Batt 2026-11-13: "why, when I open /flows, don't I see this flow's name at all?"),
// round 2 the same evening (Batt: "why is the xmas_dun02 flow separate? make it like my_first_flow"):
// every flow here is an ORDINARY flow of the studio, by name -- the one open now, the ones kept in
// this browser while another is open, and the ready-made ones (my_first_workflow, xmas_dun02). One
// press switches; the flow left is KEPT (lib/flow/prefs.ts `shelf`), so nothing is replaced or lost.
// Names render as text only.

export type FlowItem = { name: string; state: "open" | "kept" | "starter"; run: boolean };

const KIND: Record<FlowItem["state"], string> = { open: "open", kept: "kept here", starter: "ready-made" };

export default function FlowSwitcher({ items, onPick }: { items: FlowItem[]; onPick: (name: string) => void }) {
  return (
    <nav className="flow-switcher" aria-label="Flows" data-testid="flow-switcher">
      <span className="flow-switcher-label">Flows</span>
      {items.map((it) => {
        const on = it.state === "open";
        return (
          <button
            key={it.name}
            type="button"
            className="flow-switcher-item"
            aria-pressed={on}
            onClick={on ? undefined : () => onPick(it.name)}
            title={on ? "The flow open now" : it.state === "kept" ? "A flow kept in this browser while another is open: press to open it again" : "A ready-made flow: press to open it (the flow open now is kept)"}
            data-testid={`flow-switch-${it.name}`}
          >
            <span className="flow-switcher-name">{it.name.slice(0, 60)}</span>
            <span className="flow-switcher-kind">
              {KIND[it.state]}
              {it.run ? " · Run" : ""}
            </span>
          </button>
        );
      })}
    </nav>
  );
}
