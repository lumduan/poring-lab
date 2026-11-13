"use client";

// The block editor of the /flows studio (2026-11-09, docs/planning/flows-studio.md; MW2 level 2
// before it): Blockly with its `zelos` renderer in MatPilot's theme (lib/flow/theme.ts), EMBEDDED in
// the page's canvas, one tab (scope) at a time: a map block's main + its map events, the global
// events, or a plain flow's main. Every non-UI change is converted to the IR at once
// (lib/flow/blocks.ts, coalesced) and handed up, so the Python beside the blocks follows; a block
// that cannot become the IR is reported ("Fix before simulating") and nothing of the tab is applied
// until it is fixed. Blockly is loaded lazily on /flows only; its media are self-hosted, sounds are
// off, and it needs neither eval nor an inline script (THIRD_PARTY.md: the nonce CSP is unchanged).
// B2 (blocks-from-hunt-flow.md): the HUNT block's type is built from the catalogue's lists.
import "./flows.css";

import type * as BlocklyT from "blockly/core";
import { useEffect, useRef, useState } from "react";

import { followModel, registerDetectorMenus } from "@/components/flows/blockly-fields";
import { huntKey, register, registerHunt, themesOf } from "@/components/flows/blockly-register";
import { registerSearch } from "@/components/flows/blockly-search";
import type { CatalogueDoc, Finding, LintDoc, Trace } from "@/lib/flow/api";
import { BADGE_TEXT, sitePath } from "@/lib/flow/api";
import { SENTENCE_BY_TYPE, type Toolbox, toolbox, type ToolboxScope } from "@/lib/flow/blockdefs";
import { type Defaults, type TabScope, tabFromWorkspace, tabToWorkspace, type Workspace } from "@/lib/flow/blocks";
import { defaultFields, HUNT_TYPE, huntTooltip, omitted } from "@/lib/flow/hunt";
import { canonical } from "@/lib/flow/ir";
import { firstDetector, notAdopted } from "@/lib/flow/models";
import type { Project } from "@/lib/flow/project";
import { runLine } from "@/lib/flow/status";
import { INJECT } from "@/lib/flow/theme";
import type { Issue, Loose } from "@/lib/flow/words";

const PALETTE_BLOCK: Record<string, string> = {
  pl_walk_to: "walk_to",
  pl_talk_npc: "talk_npc",
  pl_choose_menu: "choose_menu",
  pl_open_window: "open_window",
  pl_use_item: "use_item",
  pl_press_key: "press_key",
  pl_dungeon_hunt: "dungeon_hunt",
  pl_login: "login",
  pl_choose_character: "choose_character",
  ...SENTENCE_BY_TYPE, // the shop / Kafra / storage sentences (2026-11-09 pm)
};
const CONVERT_MS = 120; // a drag fires many events: convert once they settle

const darkQuery = () => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null);

export type EditorApi = {
  /** Select and show the block at a node path (a lint finding's); false when this tab has none. */
  showPath: (path: string) => boolean;
  /** Select and show a block by its id (a problem's). */
  showBlock: (id: string) => boolean;
  undo: (redo: boolean) => void;
};
export type EditorState = { ready: boolean; failed: boolean; issues: Issue[]; loose: Loose[]; canUndo: boolean; canRedo: boolean };

export type BlockEditorProps = {
  /** One tab of one node (the project model, 2026-11-13). */
  scope: TabScope;
  /** Which blocks its toolbox offers (the node's kind, its main or another tab). */
  toolboxScope: ToolboxScope;
  /** The main tab's start block's words, e.g. "when she arrives on xmas_dun02". */
  title: string;
  /** The tab: a new key, or a new `epoch` (the project was replaced from outside), reloads it. */
  scopeKey: string;
  epoch: number;
  getProject: () => Project;
  catalogue: CatalogueDoc | null;
  lint: LintDoc | null;
  trace: Trace | null;
  hidden: boolean;
  onProject: (project: Project) => void;
  onState: (state: EditorState) => void;
  onApi: (api: EditorApi | null) => void;
};

export default function BlockEditor(p: BlockEditorProps) {
  const { scope, scopeKey, epoch, catalogue, lint, trace, hidden } = p;
  const host = useRef<HTMLDivElement | null>(null);
  const ws = useRef<BlocklyT.WorkspaceSvg | null>(null);
  const blockly = useRef<typeof BlocklyT | null>(null);
  const paths = useRef<Record<string, string>>({}); // block id -> its node path, as converted last
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  // the latest props, read by Blockly's listeners (they outlive a render)
  const latest = useRef(p);
  const tbRef = useRef<Toolbox | null>(null);
  useEffect(() => {
    latest.current = p;
  });
  const huntReady = Boolean(catalogue?.hunt_rules);

  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let resize: ResizeObserver | null = null;
    const media = darkQuery();
    let onMedia: (() => void) | null = null;

    const defaults = (): Defaults =>
      Object.fromEntries(Object.entries(latest.current.catalogue?.blocks ?? {}).map(([n, b]) => [n, { concept: b.spec.concept, timeout_s: b.spec.timeout_s }]));

    const convert = (announce = true) => {
      const B = blockly.current;
      const w = ws.current;
      if (!B || !w) return;
      const json = B.serialization.workspaces.save(w) as unknown as Workspace;
      const project = latest.current.getProject();
      const r = tabFromWorkspace(project, latest.current.scope, json, defaults());
      if (r.ok) {
        paths.current = r.paths;
        if (announce && canonical(r.project) !== canonical(project)) latest.current.onProject(r.project);
      }
      latest.current.onState({
        ready: true,
        failed: false,
        issues: r.ok ? [] : r.issues,
        loose: r.loose,
        canUndo: w.getUndoStack().length > 0,
        canRedo: w.getRedoStack().length > 0,
      });
      decorate(B, w, latest.current.catalogue, latest.current.lint, latest.current.trace, paths.current, latest.current.scope);
    };

    const api: EditorApi = {
      showBlock: (id) => {
        const B = blockly.current;
        const w = ws.current;
        const b = w?.getBlockById(id) as BlocklyT.BlockSvg | null | undefined;
        if (!B || !w || !b) return false;
        w.centerOnBlock(id);
        try {
          B.getFocusManager().focusNode(b);
        } catch {
          b.select();
        }
        return true;
      },
      showPath: (path) => {
        const id = Object.entries(paths.current).find(([, v]) => v === path)?.[0] ?? (ws.current?.getBlockById(`n:${path}`) ? `n:${path}` : null);
        return id ? api.showBlock(id) : false;
      },
      undo: (redo) => {
        ws.current?.undo(redo);
      },
    };

    void (async () => {
      try {
        const B = await import("blockly/core");
        const En = await import("blockly/msg/en");
        if (disposed || !host.current) return;
        B.setLocale(En as unknown as Record<string, string>);
        register(B);
        registerSearch(B, () => tbRef.current);
        registerDetectorMenus(B, () => latest.current.catalogue?.models ?? null);
        blockly.current = B;
        const cat = latest.current.catalogue;
        const hunt = registerHunt(B, cat?.hunt_rules ?? null) ? (cat?.hunt_rules ?? null) : null;
        const th = themesOf(B);
        tbRef.current = toolboxOf(cat, latest.current.toolboxScope);
        const w = B.inject(host.current, {
          ...INJECT,
          theme: media?.matches ? th.dark : th.light,
          toolbox: tbRef.current as unknown as BlocklyT.utils.toolbox.ToolboxDefinition,
        } as unknown as BlocklyT.BlocklyOptions);
        ws.current = w;
        B.Events.disable();
        try {
          B.serialization.workspaces.load(tabToWorkspace(latest.current.getProject(), scope, { hunt }) as unknown as object, w);
          for (const b of w.getBlocksByType("pl_main", false)) b.getField("TITLE")?.setValue(latest.current.title);
        } finally {
          B.Events.enable();
        }
        w.clearUndo();
        w.addChangeListener(B.Events.disableOrphans);
        w.addChangeListener(followModel(B, w, () => latest.current.catalogue?.models ?? null));
        w.addChangeListener((e: BlocklyT.Events.Abstract) => {
          if (e.isUiEvent) return;
          if (timer) clearTimeout(timer);
          timer = setTimeout(() => {
            timer = null;
            convert();
          }, CONVERT_MS);
        });
        resize = new ResizeObserver(() => B.svgResize(w));
        resize.observe(host.current);
        onMedia = () => w.setTheme(media?.matches ? th.dark : th.light);
        media?.addEventListener("change", onMedia);
        convert(false);
        setReady(true);
        latest.current.onApi(api);
      } catch (e) {
        console.warn("the block editor could not be loaded", e);
        setFailed(true);
        latest.current.onState({ ready: false, failed: true, issues: [], loose: [], canUndo: false, canRedo: false });
      }
    })();
    return () => {
      disposed = true;
      if (timer) {
        clearTimeout(timer);
        convert(); // an edit not converted yet still lands in the flow
      }
      resize?.disconnect();
      if (onMedia) media?.removeEventListener("change", onMedia);
      ws.current?.dispose();
      ws.current = null;
      latest.current.onApi(null);
      setReady(false);
    };
    // the workspace is created for ONE tab and the flow as it was: a lint, a run or the flow
    // changing by its own edits only re-decorates it (an edit in progress is never lost)
  }, [scopeKey, epoch, huntReady]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!ready || !ws.current) return;
    // the lists may arrive after the workspace: the type is defined before the toolbox names it
    if (blockly.current) registerHunt(blockly.current, catalogue?.hunt_rules ?? null);
    tbRef.current = toolboxOf(catalogue, p.toolboxScope);
    ws.current.updateToolbox(tbRef.current as unknown as BlocklyT.utils.toolbox.ToolboxDefinition);
    if (blockly.current) decorate(blockly.current, ws.current, catalogue, lint, trace, paths.current, scope);
  }, [ready, catalogue, lint, trace, scope, p.toolboxScope]);

  return (
    <>
      <div ref={host} className="blocks-workspace" data-testid="blocks-workspace" data-status={failed ? "failed" : ready ? "ready" : "loading"} inert={hidden} />
      {failed && <p className="notice notice-error blocks-failed">The block editor could not be loaded. Reload the page to try again.</p>}
    </>
  );
}

function toolboxOf(catalogue: CatalogueDoc | null, scope: ToolboxScope): Toolbox {
  const cat = Object.fromEntries(
    Object.entries(catalogue?.blocks ?? {})
      .filter(([, b]) => b.spec.kind !== "core" || b.name === "assert_save_point")
      .map(([n, b]) => [n, { concept: b.spec.concept, timeout_s: b.spec.timeout_s, badge: b.badge }]),
  );
  const rules = catalogue?.hunt_rules ?? null;
  const models = catalogue?.models ?? null;
  const first = firstDetector(models);
  return toolbox(cat, scope, rules && huntKey() ? defaultFields(rules) : null, rules && huntKey() ? omitted(rules) : {}, {
    model: first.model,
    label: first.label,
    notes: notAdopted(models),
  });
}

/** Badges (L1 verification), lint warnings and the last run on each block. `paths`: block id ->
 * node path, as converted last (edits move blocks; their ids stay). The labels change with events
 * off: a decoration is not an edit (no undo step, no conversion). */
function decorate(B: typeof BlocklyT, w: BlocklyT.WorkspaceSvg, catalogue: CatalogueDoc | null, lint: LintDoc | null, trace: Trace | null, paths: Record<string, string>, scope: TabScope): void {
  const was = B.Events.isEnabled();
  if (was) B.Events.disable();
  try {
    paint(w, catalogue, lint, trace, paths, scope);
  } finally {
    if (was) B.Events.enable();
  }
}

/** This tab's findings by their statement path inside the tab. */
function tabFindings(lint: LintDoc | null, scope: TabScope): Map<string, Finding[]> {
  const out = new Map<string, Finding[]>();
  for (const f of lint?.findings ?? []) {
    if (f.node !== scope.node || f.tab !== scope.tab) continue;
    const k = sitePath(f);
    out.set(k, [...(out.get(k) ?? []), f]);
  }
  return out;
}

function paint(w: BlocklyT.WorkspaceSvg, catalogue: CatalogueDoc | null, lint: LintDoc | null, trace: Trace | null, paths: Record<string, string>, scope: TabScope): void {
  const byPath = tabFindings(lint, scope);
  const prefix = `${scope.node}/${scope.tab}/`;
  for (const b of w.getAllBlocks(false)) {
    const name =
      b.type === HUNT_TYPE ? "hunt" : (PALETTE_BLOCK[b.type] ?? (b.type === "pl_action" || b.type === "pl_do" ? String(b.getFieldValue("BLOCK")) : null));
    const badgeField = b.getField("BADGE");
    if (name && badgeField) {
      const doc = catalogue?.blocks[name];
      const badge = doc?.badge ?? "unknown";
      badgeField.setValue(`● ${BADGE_TEXT[badge]}`);
      const svg = (badgeField as unknown as { getSvgRoot?: () => SVGElement | null }).getSvgRoot?.();
      svg?.classList.add(`pl-badge-${badge}`);
      const runs = doc?.verified_on.map((v) => `${v.path} ${v.rule} ${v.date}`).join("; ");
      b.setTooltip(`${name}: ${doc?.purpose ?? ""}\nL1: ${BADGE_TEXT[badge]}${runs ? ` (${runs})` : ""}`);
      const rules = catalogue?.hunt_rules ?? null;
      const ev = b.getField("EVIDENCE");
      if (b.type === HUNT_TYPE && rules) {
        // D8's hunting evidence BESIDE the L1 badge (one path, one map, an immune GM)
        ev?.setValue(rules.evidence.badges.length ? `◆ ${rules.evidence.badges.join(", ")}` : "");
        b.setTooltip(huntTooltip(rules, BADGE_TEXT[badge]));
      }
    }
    const path = paths[b.id] ?? (b.id.startsWith("n:") ? b.id.slice(2).split("#")[0] : null);
    if (path === null || b.isInFlyout) continue;
    const runField = b.getField("RUN");
    if (runField) runField.setValue(trace ? runLine(trace.nodes[prefix + path] ?? trace.nodes[path]) || "not run" : "");
    if (b.outputConnection) continue; // findings sit on the statement that holds the value
    const own = byPath.get(path);
    b.setWarningText(own?.length ? own.map((f) => `${f.severity}: ${f.text}`).join("\n") : null);
  }
}
