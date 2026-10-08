"use client";

// The block editor (MW2 level 2): Blockly with its own `zelos` renderer (the MakeCode / Scratch
// look), one scope at a time (a map block's main + its map events, or the global events). Blockly
// is loaded lazily on /flows only. Its media are self-hosted (/blockly-media), sounds are off, and
// it needs neither eval nor an inline script (THIRD_PARTY.md, the nonce CSP is unchanged). The
// workspace converts to the IR with lib/flow/blocks.ts; nothing is applied while a field is wrong.
import "./flows.css";

import type * as BlocklyT from "blockly/core";
import { useEffect, useRef, useState } from "react";

import type { CatalogueDoc, LintDoc, Trace } from "@/lib/flow/api";
import { BADGE_TEXT } from "@/lib/flow/api";
import { BLOCK_DEFS, toolbox } from "@/lib/flow/blockdefs";
import { type Defaults, fromWorkspace, type Scope, toWorkspace, type Workspace } from "@/lib/flow/blocks";
import type { Flow } from "@/lib/flow/ir";
import { findingsByPath, runLine } from "@/lib/flow/status";

const PALETTE_BLOCK: Record<string, string> = {
  pl_walk_to: "walk_to",
  pl_talk_npc: "talk_npc",
  pl_choose_menu: "choose_menu",
  pl_open_window: "open_window",
  pl_use_item: "use_item",
};

let registered = false;

function register(B: typeof BlocklyT): void {
  // once per page load; Blockly's registries outlive a hot-reloaded copy of this module
  if (registered || B.Extensions.isRegistered("pl_state")) return;
  registered = true;
  // Every block keeps what it does not show (lossless): the converter's extraState. Blockly lets
  // only a mutator define the state hooks; these have no mutator UI.
  B.Extensions.registerMutator("pl_state", {
    saveExtraState(this: { plState_?: unknown }) {
      return this.plState_ ?? null;
    },
    loadExtraState(this: { plState_?: unknown }, state: unknown) {
      this.plState_ = state;
    },
  });
  // and / or: one value input per term (T0, T1, ...), rebuilt from the saved count.
  B.Extensions.registerMutator(
    "pl_logic",
    {
      saveExtraState(this: { n_?: number }) {
        return { n: this.n_ ?? 2 };
      },
      loadExtraState(this: BlocklyT.Block & { n_?: number }, state: { n?: number }) {
        const n = Math.max(2, Math.min(100, Number(state?.n ?? 2)));
        for (let i = this.n_ ?? 2; i < n; i++) this.appendValueInput(`T${i}`);
        this.n_ = Math.max(this.n_ ?? 2, n);
      },
    },
    function (this: BlocklyT.Block & { n_?: number }) {
      this.n_ = 2;
      this.appendValueInput("T0");
      this.appendValueInput("T1");
    },
  );
  B.common.defineBlocksWithJsonArray(BLOCK_DEFS as unknown as object[]);
}

function themeOf(B: typeof BlocklyT): BlocklyT.Theme {
  return B.Theme.defineTheme("poring-dark", {
    name: "poring-dark",
    base: B.Themes.Classic,
    componentStyles: {
      workspaceBackgroundColour: "#18181b",
      toolboxBackgroundColour: "#202024",
      toolboxForegroundColour: "#e5e5e5",
      flyoutBackgroundColour: "#26262b",
      flyoutForegroundColour: "#d4d4d4",
      flyoutOpacity: 0.95,
      scrollbarColour: "#52525b",
      insertionMarkerColour: "#ffffff",
      insertionMarkerOpacity: 0.3,
    },
  });
}

export type BlockEditorProps = {
  flow: Flow;
  scope: Scope;
  title: string;
  catalogue: CatalogueDoc | null;
  lint: LintDoc | null;
  trace: Trace | null;
  onApply: (flow: Flow, warnings: string[]) => void;
  onClose: () => void;
};

export default function BlockEditor({ flow, scope, title, catalogue, lint, trace, onApply, onClose }: BlockEditorProps) {
  const host = useRef<HTMLDivElement | null>(null);
  const ws = useRef<BlocklyT.WorkspaceSvg | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [ready, setReady] = useState(false);
  const defaults: Defaults = Object.fromEntries(
    Object.entries(catalogue?.blocks ?? {}).map(([n, b]) => [n, { concept: b.spec.concept, timeout_s: b.spec.timeout_s }]),
  );

  // The catalogue may arrive after the editor opened: the toolbox follows it (effect below).
  const catRef = useRef<CatalogueDoc | null>(catalogue);
  useEffect(() => {
    catRef.current = catalogue;
  }, [catalogue]);

  // The workspace is created for ONE flow and scope; a new lint or run only re-decorates it, so
  // edits not applied yet are never lost to a background lint.
  useEffect(() => {
    let disposed = false;
    void (async () => {
      const B = await import("blockly/core");
      const En = await import("blockly/msg/en");
      if (disposed || !host.current) return;
      B.setLocale(En as unknown as Record<string, string>);
      register(B);
      const w = B.inject(host.current, {
        renderer: "zelos",
        theme: themeOf(B),
        media: "/blockly-media/",
        sounds: false,
        trashcan: true,
        toolbox: toolboxOf(catRef.current, scope),
        zoom: { controls: true, wheel: true, startScale: 0.8, maxScale: 2, minScale: 0.3 },
        move: { scrollbars: true, drag: true, wheel: false },
        grid: { spacing: 24, length: 2, colour: "#2f2f35", snap: false },
      });
      ws.current = w;
      B.serialization.workspaces.load(toWorkspace(flow, scope) as unknown as object, w);
      setReady(true);
    })();
    return () => {
      disposed = true;
      ws.current?.dispose();
      ws.current = null;
      setReady(false);
    };
  }, [flow, scope]);

  useEffect(() => {
    if (!ready || !ws.current) return;
    ws.current.updateToolbox(toolboxOf(catalogue, scope));
    decorate(ws.current, catalogue, lint, trace);
  }, [ready, catalogue, lint, trace, scope]);

  const apply = async () => {
    if (!ws.current) return;
    const B = await import("blockly/core");
    const json = B.serialization.workspaces.save(ws.current) as unknown as Workspace;
    const r = fromWorkspace(flow, scope, json, defaults);
    if (!r.ok) {
      setErrors(r.errors);
      return;
    }
    setErrors([]);
    onApply(r.flow, r.warnings);
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-neutral-950/95" data-testid="block-editor">
      <div className="flex items-center gap-3 border-b border-neutral-800 px-4 py-2">
        <span className="font-semibold">{title}</span>
        <span className="text-xs text-neutral-400">
          Badges: each skill block shows its L1 verification (verified RDP / S2 / unverified). Hover a ⚠ for its lint finding.
        </span>
        <div className="ml-auto flex gap-2">
          <button className="rounded bg-emerald-700 px-3 py-1 text-sm hover:bg-emerald-600 disabled:opacity-50" disabled={!ready} onClick={() => void apply()}>
            Apply to the flow
          </button>
          <button className="rounded bg-neutral-800 px-3 py-1 text-sm hover:bg-neutral-700" onClick={onClose}>
            Close without applying
          </button>
        </div>
      </div>
      {errors.length > 0 && (
        <ul className="max-h-32 overflow-auto border-b border-red-900 bg-red-950/60 px-4 py-1 text-xs text-red-200">
          {errors.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      )}
      <div ref={host} className="min-h-0 flex-1" />
    </div>
  );
}

function toolboxOf(catalogue: CatalogueDoc | null, scope: Scope): BlocklyT.utils.toolbox.ToolboxDefinition {
  const cat = Object.fromEntries(
    Object.entries(catalogue?.blocks ?? {})
      .filter(([, b]) => b.spec.kind !== "core" || b.name === "assert_save_point")
      .map(([n, b]) => [n, { concept: b.spec.concept, timeout_s: b.spec.timeout_s, badge: b.badge }]),
  );
  return toolbox(cat, scope.kind) as unknown as BlocklyT.utils.toolbox.ToolboxDefinition;
}

/** Badges (L1 verification), lint warnings and the last run on each block, after loading. */
function decorate(w: BlocklyT.WorkspaceSvg, catalogue: CatalogueDoc | null, lint: LintDoc | null, trace: Trace | null): void {
  const byPath = findingsByPath(lint);
  for (const b of w.getAllBlocks(false)) {
    const name = PALETTE_BLOCK[b.type] ?? (b.type === "pl_action" || b.type === "pl_do" ? String(b.getFieldValue("BLOCK")) : null);
    const badgeField = b.getField("BADGE");
    if (name && badgeField) {
      const doc = catalogue?.blocks[name];
      const badge = doc?.badge ?? "unknown";
      badgeField.setValue(`● ${BADGE_TEXT[badge]}`);
      const svg = (badgeField as unknown as { getSvgRoot?: () => SVGElement | null }).getSvgRoot?.();
      svg?.classList.add(`pl-badge-${badge}`);
      const runs = doc?.verified_on.map((v) => `${v.path} ${v.rule} ${v.date}`).join("; ");
      b.setTooltip(`${name}: ${doc?.purpose ?? ""}\nL1: ${BADGE_TEXT[badge]}${runs ? ` (${runs})` : ""}`);
    }
    if (!b.id.startsWith("n:")) continue;
    const path = b.id.slice(2).split("#")[0];
    const runField = b.getField("RUN");
    if (runField) runField.setValue(trace ? runLine(trace.nodes[path]) || "not run" : "");
    const own = byPath.get(path);
    b.setWarningText(own?.length ? own.map((f) => `${f.severity}: ${f.text}`).join("\n") : null);
  }
}
