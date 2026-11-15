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
import { keepDropDownsInside, refreshPickers, setPickerSource } from "@/components/flows/blockly-pickers";
import { huntKey, inTick, register, registerHunt, setFlyoutNotes, syncExprWrap, syncLabelRows, syncSetting, syncStepPlace, themesOf, tickLock } from "@/components/flows/blockly-register";
import { registerSearch } from "@/components/flows/blockly-search";
import type { CatalogueDoc, Finding, LintDoc, Trace } from "@/lib/flow/api";
import { BADGE_TEXT, sitePath, warningText } from "@/lib/flow/api";
import { boxReplaced } from "@/lib/flow/box";
import { argsRowShown, defTooltip, SENTENCE_BY_TYPE, titleLines, type Toolbox, toolbox, toolboxCatalogue, type ToolboxScope, varTooltip } from "@/lib/flow/blockdefs";
import { type Defaults, placedIds, shelfItems, TAB_TOP_Y, type TabScope, tabFromWorkspace, tabToWorkspace, type Workspace } from "@/lib/flow/blocks";
import { defaultFields, HUNT_TYPE, huntTooltip, omitted } from "@/lib/flow/hunt";
import { canonical } from "@/lib/flow/ir";
import { personMoved, pushGrown, shelf, SHELF_LEFT, shelfWidth, STACK_GAP, type TopBox } from "@/lib/flow/layout";
import { firstDetector, monstersOf, notAdopted } from "@/lib/flow/models";
import type { MapsDoc, PickerData } from "@/lib/flow/pickers";
import { nodeById, type Project, type Tab, tabOf } from "@/lib/flow/project";
import { noteLines, SETTING_NOTE_ROWS, settingFallback, type SettingNote, settingOfType, settingTooltip } from "@/lib/flow/settings";
import { runLine } from "@/lib/flow/status";
import { injectFor } from "@/lib/flow/theme";
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
  /** matpilot round 20 #3, #4a: the lint's words per setting block (POST /flows/lint `settings`),
   * kept while a new lint runs (the rows would blink on every edit otherwise). */
  notes: Record<string, SettingNote> | null;
  trace: Trace | null;
  /** Round 21 (live-blocks.md 12.5): the map names the world knows (GET /flows/maps), the map
   * pickers' list; null while it loads or where the world is not here. */
  maps: MapsDoc | null;
  hidden: boolean;
  onProject: (project: Project) => void;
  onState: (state: EditorState) => void;
  onApi: (api: EditorApi | null) => void;
};

export default function BlockEditor(p: BlockEditorProps) {
  const { scope, scopeKey, epoch, catalogue, lint, notes, trace, hidden } = p;
  const host = useRef<HTMLDivElement | null>(null);
  const ws = useRef<BlocklyT.WorkspaceSvg | null>(null);
  const blockly = useRef<typeof BlocklyT | null>(null);
  const paths = useRef<Record<string, string>>({}); // block id -> its node path, as converted last
  const issues = useRef<Issue[]>([]); // round 21: the tab's problems as converted last (marked on their blocks)
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
    let unfit: (() => void) | null = null;
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
      // round 25: the places of the blocks a person put (dragged, or the tab's layout placed) are saved
      const r = tabFromWorkspace(project, latest.current.scope, json, defaults(), placedOf.get(w));
      issues.current = r.ok ? [] : r.issues;
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
      decorate(B, w, latest.current.catalogue, latest.current.lint, latest.current.notes, latest.current.trace, paths.current, latest.current.scope, r.ok ? r.project : project, issues.current);
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
        // round 21: what the pickers list when one opens -- the project as converted last, this tab,
        // the catalogue, the map list, and the functions written here and not converted yet
        setPickerSource((): PickerData => ({
          project: latest.current.getProject(),
          node: latest.current.scope.node,
          tab: latest.current.scope.tab,
          catalogue: latest.current.catalogue,
          maps: latest.current.maps,
          extraDefs: (ws.current?.getBlocksByType("pl_def", false) ?? []).map((b) => String(b.getFieldValue("NAME") ?? "").trim()),
        }));
        const cat = latest.current.catalogue;
        const hunt = registerHunt(B, cat?.hunt_rules ?? null) ? (cat?.hunt_rules ?? null) : null;
        const th = themesOf(B);
        tbRef.current = toolboxOf(cat, latest.current.toolboxScope);
        // matpilot round 18 #4: a phone starts smaller (more of each row shows beside the toolbox)
        const phone = typeof window !== "undefined" && !!window.matchMedia && window.matchMedia("(max-width: 48rem)").matches;
        // round 21: the Settings flyout and the search grey a setting this node's box replaces
        setFlyoutNotes((name) => boxReplaced(latest.current.lint?.box?.[latest.current.scope.node]).get(name) ?? null);
        const w = B.inject(host.current, {
          ...injectFor(phone),
          theme: media?.matches ? th.dark : th.light,
          toolbox: tbRef.current as unknown as BlocklyT.utils.toolbox.ToolboxDefinition,
        } as unknown as BlocklyT.BlocklyOptions);
        ws.current = w;
        B.Events.disable();
        try {
          // round 25: a remembered block where the person put it, the others left to right while
          // they fit this canvas at its scale (a phone: one column)
          const opened = latest.current.getProject();
          const json = tabToWorkspace(opened, scope, { hunt, width: canvasWidth(w) });
          placedOf.set(w, placedIds(json, tabAt(opened, scope)));
          modelWidths.set(w, new Map(shelfItems(json.blocks.blocks, tabAt(opened, scope)).map((i) => [i.id, i.w])));
          B.serialization.workspaces.load(json as unknown as object, w);
          for (const b of w.getBlocksByType("pl_main", false)) {
            const [one, two] = titleLines(latest.current.title);
            b.getField("TITLE")?.setValue(one);
            b.getField("TITLE2")?.setValue(two);
            if (!two) b.getInput("ROW_TITLE2")?.setVisible(false); // one row: no empty second
          }
        } finally {
          B.Events.enable();
        }
        w.clearUndo();
        w.addChangeListener(B.Events.disableOrphans);
        w.addChangeListener(followModel(B, w, () => latest.current.catalogue?.models ?? null));
        w.addChangeListener((e: BlocklyT.Events.Abstract) => {
          if (e.isUiEvent) return;
          remember(B, w, e); // round 25: a block a person put somewhere keeps its place
          settle(B, w); // round 23: a block whose height changed pushes the ones under it down
          if (timer) clearTimeout(timer);
          timer = setTimeout(() => {
            timer = null;
            convert();
          }, CONVERT_MS);
        });
        // round 23: Blockly's own menus (on / off, the choices) stay inside the blocks area
        unfit = keepDropDownsInside(B, () => w.getInjectionDiv()?.getBoundingClientRect() ?? null);
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
      unfit?.();
      if (onMedia) media?.removeEventListener("change", onMedia);
      blockly.current?.DropDownDiv.hideWithoutAnimation(); // a picker open on this tab closes with it
      setPickerSource(null);
      setFlyoutNotes(null);
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
    // matpilot round 15 #3: a re-render (the Run panel's 2 s poll) must not re-send an equal toolbox:
    // updateToolbox closes an open flyout. Only a CHANGED toolbox is sent.
    const next = toolboxOf(catalogue, p.toolboxScope);
    if (JSON.stringify(next) !== JSON.stringify(tbRef.current)) {
      tbRef.current = next;
      ws.current.updateToolbox(tbRef.current as unknown as BlocklyT.utils.toolbox.ToolboxDefinition);
    }
    if (blockly.current) decorate(blockly.current, ws.current, catalogue, lint, notes, trace, paths.current, scope, p.getProject(), issues.current);
    // the scopes as plain values: their objects are new on every render of the page
  }, [ready, catalogue, lint, notes, trace, p.maps, scope.node, scope.tab, p.toolboxScope.node, p.toolboxScope.main, p.toolboxScope.tab, p.toolboxScope.model]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <div ref={host} className="blocks-workspace" data-testid="blocks-workspace" data-status={failed ? "failed" : ready ? "ready" : "loading"} inert={hidden} />
      {failed && <p className="notice notice-error blocks-failed">The block editor could not be loaded. Reload the page to try again.</p>}
    </>
  );
}

function toolboxOf(catalogue: CatalogueDoc | null, scope: ToolboxScope): Toolbox {
  const cat = toolboxCatalogue(catalogue); // round 27: blockdefs.ts (the tick's steps offered)
  const rules = catalogue?.hunt_rules ?? null;
  const models = catalogue?.models ?? null;
  const first = firstDetector(models);
  return toolbox(
    cat,
    scope,
    rules && huntKey() ? defaultFields(rules) : null,
    rules && huntKey() ? omitted(rules) : {},
    { model: first.model, label: first.label, notes: notAdopted(models) },
    monstersOf(models, scope.model ?? null),
  );
}

/** Badges (L1 verification), lint warnings and the last run on each block. `paths`: block id ->
 * node path, as converted last (edits move blocks; their ids stay). The labels change with events
 * off: a decoration is not an edit (no undo step, no conversion). */
function decorate(B: typeof BlocklyT, w: BlocklyT.WorkspaceSvg, catalogue: CatalogueDoc | null, lint: LintDoc | null, notes: Record<string, SettingNote> | null, trace: Trace | null, paths: Record<string, string>, scope: TabScope, project: Project | null, issues: readonly Issue[] = []): void {
  const was = B.Events.isEnabled();
  if (was) B.Events.disable();
  try {
    paint(B, w, catalogue, lint, notes, trace, paths, scope, project, issues);
    // round 21: a reference that became known (a function written since, the map list arrived)
    // loses its ⚠, one that is gone gains it
    refreshPickers(w);
  } finally {
    if (was) B.Events.enable();
  }
  // a block that gained rows (a setting's warning, the lint's note, a wrapped condition, the badge)
  // pushes the blocks under it down once Blockly has drawn it (its height is known only then)
  settle(B, w);
}

/** Each workspace's top blocks' sizes at its last settle (none yet: the tab just opened). */
const settledSizes = new WeakMap<BlocklyT.WorkspaceSvg, Map<string, { w: number; h: number }>>();
/** A settle waiting for Blockly's renders (true: asked again meanwhile, so it runs once more). */
const settling = new WeakMap<BlocklyT.WorkspaceSvg, boolean>();
/** Round 25: each workspace's top blocks a PERSON placed (their ids): the ones the tab's layout put
 * where they were, and every block dragged since (or arranged by Blockly's "Clean up Blocks", a
 * person's own choice). Their places are saved with the project (tabFromWorkspace `placed`). */
const placedOf = new WeakMap<BlocklyT.WorkspaceSvg, Set<string>>();
/** Round 25: each workspace's top blocks' widths as the shelf placed them when the tab opened (the
 * model's, with room for the widest badge): the first settle keeps those columns. */
const modelWidths = new WeakMap<BlocklyT.WorkspaceSvg, Map<string, number>>();

/** The tab of a scope (round 25: its layout). */
function tabAt(p: Project, scope: TabScope): Tab | undefined {
  const n = nodeById(p, scope.node);
  return n ? tabOf(n, scope.tab) : undefined;
}

/** The shelf's width for this canvas (layout.ts shelfWidth: its visible width at its scale). */
function canvasWidth(w: BlocklyT.WorkspaceSvg): number {
  try {
    return shelfWidth(w.getMetricsManager().getViewMetrics(false).width, w.scale);
  } catch {
    return 0; // not measurable (hidden): one column
  }
}

/** Round 25: a top block a person moved -- a drag (mouse, touch or the keyboard's move mode: all
 * Blockly's "drag"), or "Clean up Blocks" -- keeps its place from now on. Blockly's own moves (a
 * bump, a snap, a connection) and the editor's (settle: events off) are not a person's. Undo moves
 * the block back and the place saved follows (the conversion after it). */
function remember(B: typeof BlocklyT, w: BlocklyT.WorkspaceSvg, e: BlocklyT.Events.Abstract): void {
  if (e.type !== B.Events.BLOCK_MOVE) return;
  const id = personMoved(e as BlocklyT.Events.BlockMove);
  if (!id) return;
  let set = placedOf.get(w);
  if (!set) placedOf.set(w, (set = new Set()));
  set.add(id);
}

/** Round 23 (the survival tab's event blocks overlapped and hid 8 fields), ➡️ round 25 (Batt
 * 2026-11-15: the places a person chose WIN): once Blockly has drawn the tab, its top blocks are
 * placed with the sizes Blockly MEASURED (getHeightWidth).
 * - The first time (the tab just opened): the blocks no person placed go left to right while they
 *   fit the canvas (layout.ts shelf, STACK_GAP apart), around the placed ones, which stay.
 * - Afterwards, whenever a block's height changed (a picker's value, a note, a warning row, a
 *   wrapped condition, a block plugged in or taken out): only the blocks the growth now REACHES in
 *   its column go down (layout.ts pushGrown), placed or not; a block a person dropped onto another
 *   stays where it was dropped (it overlapped before).
 * A move, never an edit: no event, no undo step; not while a person drags. The places saved are
 * the placed blocks' (tabFromWorkspace), so a block pushed down keeps the place it was pushed to. */
function settle(B: typeof BlocklyT, w: BlocklyT.WorkspaceSvg): void {
  if (settling.has(w)) {
    settling.set(w, true);
    return;
  }
  settling.set(w, false);
  void B.renderManagement.finishQueuedRenders().then(
    () => {
      const again = settling.get(w);
      settling.delete(w);
      settleNow(B, w);
      if (again) settle(B, w);
    },
    () => settling.delete(w),
  );
}

function settleNow(B: typeof BlocklyT, w: BlocklyT.WorkspaceSvg): void {
  try {
    if (!w.rendered || !w.getParentSvg()?.isConnected) return; // the tab was closed meanwhile
  } catch {
    return;
  }
  if (B.Gesture.inProgress()) {
    setTimeout(() => settle(B, w), 250); // after the drag
    return;
  }
  const tops = w.getTopBlocks(false).filter((b) => !b.isDisposed() && !b.isInFlyout);
  const boxes: TopBox[] = tops.map((b) => {
    const at = b.getRelativeToSurfaceXY();
    const hw = b.getHeightWidth();
    return { id: b.id, x: at.x, y: at.y, w: hw.width, h: hw.height };
  });
  const last = settledSizes.get(w);
  settledSizes.set(w, new Map(boxes.map((b) => [b.id, { w: b.w, h: b.h }])));
  let moves: Map<string, [number, number]>;
  if (!last) {
    // the tab just opened: the shelf again, with the measured sizes, in the tab's order
    const placed = placedOf.get(w) ?? new Set<string>();
    const model = modelWidths.get(w);
    moves = shelf(
      boxes.map((b, i) => ({ id: b.id, w: Math.max(b.w, model?.get(b.id) ?? 0), h: b.h, at: placed.has(b.id) ? ([b.x, b.y] as const) : null, alone: tops[i].type === "pl_main" })),
      canvasWidth(w),
      STACK_GAP,
      TAB_TOP_Y,
      SHELF_LEFT,
    );
  } else {
    moves = pushGrown(boxes, last, STACK_GAP);
  }
  const was = B.Events.isEnabled();
  if (was) B.Events.disable();
  try {
    for (const b of tops) {
      const to = moves.get(b.id);
      if (!to) continue;
      const at = b.getRelativeToSurfaceXY();
      if (Math.abs(to[0] - at.x) > 0.5 || Math.abs(to[1] - at.y) > 0.5) b.moveBy(to[0] - at.x, to[1] - at.y);
    }
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

/** The style a setting block takes while the lint says it is not used in a Run (greyed: a colour of
 * its own, never Blockly's disabled state, which would drop it from the project). */
export const UNUSED_STYLE = "pl_unused_blocks";
const SETTING_STYLE = "mp_setup_blocks";

function paint(B: typeof BlocklyT, w: BlocklyT.WorkspaceSvg, catalogue: CatalogueDoc | null, lint: LintDoc | null, notes: Record<string, SettingNote> | null, trace: Trace | null, paths: Record<string, string>, scope: TabScope, project: Project | null, issues: readonly Issue[] = []): BlocklyT.BlockSvg[] {
  const byPath = tabFindings(lint, scope);
  // round 21 (the re-measure of round 20): a problem that keeps the tab from becoming the project is
  // marked on ITS block -- a setting block's rows say it (⚠ "already set in tab knife; ..."), any
  // other block shows Blockly's warning with the words under the canvas
  const issueOf = new Map<string, Issue[]>();
  for (const it of issues) if (it.id) issueOf.set(it.id, [...(issueOf.get(it.id) ?? []), it]);
  const prefix = `${scope.node}/${scope.tab}/`;
  const grew: BlocklyT.BlockSvg[] = [];
  const hasGlobal = Boolean(project?.nodes.some((n) => n.kind === "global"));
  for (const b of w.getAllBlocks(false)) {
    // round 22: a long condition wraps onto rows of its own (loaded ones too); its stack moves down
    if (b.type === "pl_expr" && !b.isInFlyout && syncExprWrap(B, b)) grew.push(b);
    // round 26: a block inside hunt_tick() is dragged out alone, a locked step not at all (tickLock)
    if (!b.isInFlyout && inTick(b)) tickLock(B, b);
    // round 28: a step's padlock and WHY rows follow its place (an extra or a misplaced copy says why)
    if (!b.isInFlyout && syncStepPlace(B, b)) grew.push(b);
    // round 27: a function's and a variable's tooltip names Global only in a project that has one;
    // hunt_tick's and hunt_loop's carry their ABOUT words
    if (b.type === "pl_def") b.setTooltip(defTooltip(String(b.getFieldValue("NAME") ?? "").trim(), hasGlobal));
    if (b.type === "pl_vardecl") b.setTooltip(varTooltip(hasGlobal));
    // round 26 (the reviewer: find_target's empty "( )" opened a picker saying "This block takes no
    // inputs"): a hunt loop block whose catalogue entry takes no inputs hides its inputs' row while
    // it holds none
    if ((b.type === "pl_hunt_take" || b.type === "pl_hunt_step") && !b.isInFlyout) {
      const spec = catalogue?.blocks[String(b.getFieldValue("BLOCK") ?? "")]?.spec;
      const row = b.getInput("ROW_ARGS");
      const show = argsRowShown(spec?.params, String(b.getFieldValue("ARGS") ?? ""));
      if (row && row.isVisible() !== show) {
        row.setVisible(show);
        grew.push(b);
        void b.queueRender();
      }
    }
    // a SETTING block (live-blocks.md 12): a safety switch shows its warning rows while it is off;
    // matpilot round 20 #4a: the lint's "not used" words on rows of its own, the block greyed; the
    // tooltip says what deleting the block falls back to (Global's block, else the default)
    const setting = settingOfType(b.type);
    if (setting && !b.isInFlyout) {
      const note = notes?.[`${prefix}${setting.var}`] ?? null;
      const problem = issueOf.get(b.id)?.[0] ?? null;
      const lines = problem ? noteLines(problem.note ?? problem.text, "⚠") : noteLines(note?.unused ?? "");
      b.getSvgRoot()?.classList.toggle("pl-setting-problem", problem !== null);
      for (let i = 0; i < SETTING_NOTE_ROWS; i++) b.getField(`NOTE${i}`)?.setValue(lines[i] ?? "");
      const unused = Boolean(note?.unused);
      if (b.getStyleName() !== (unused ? UNUSED_STYLE : SETTING_STYLE)) b.setStyle(unused ? UNUSED_STYLE : SETTING_STYLE);
      b.getSvgRoot()?.classList.toggle("pl-setting-unused", unused);
      if (syncSetting(B, b)) grew.push(b);
      if (project) b.setTooltip(settingTooltip(setting, { fallback: settingFallback(project, scope.node, setting), global: hasGlobal, note }));
    }
    const name =
      b.type === HUNT_TYPE ? "hunt" : (PALETTE_BLOCK[b.type] ?? (b.type === "pl_action" || b.type === "pl_do" ? String(b.getFieldValue("BLOCK")) : null));
    const badgeField = b.getField("BADGE");
    if (name && badgeField) {
      const doc = catalogue?.blocks[name];
      const badge = doc?.badge ?? "unknown";
      // matpilot round 16 #11: a block the live player plays says so (its L1 status stays in the tooltip)
      const plays = (doc?.spec as { live?: boolean } | undefined)?.live === true;
      badgeField.setValue(plays ? "● plays live" : `● ${BADGE_TEXT[badge]}`);
      const svg = (badgeField as unknown as { getSvgRoot?: () => SVGElement | null }).getSvgRoot?.();
      svg?.classList.add(`pl-badge-${badge}`);
      const runs = doc?.verified_on.map((v) => `${v.path} ${v.rule} ${v.date}`).join("; ");
      b.setTooltip(`${name}: ${doc?.purpose ?? ""}\nL1: ${BADGE_TEXT[badge]}${runs ? ` (${runs})` : ""}${plays ? "\nplays live: the live block player plays it in the game (Run)" : ""}`);
      const rules = catalogue?.hunt_rules ?? null;
      const ev = b.getField("EVIDENCE");
      if (b.type === HUNT_TYPE && rules) {
        // D8's hunting evidence BESIDE the L1 badge (one path, one map, an immune GM)
        ev?.setValue(rules.evidence.badges.length ? `◆ ${rules.evidence.badges.join(", ")}` : "");
        b.setTooltip(huntTooltip(rules, BADGE_TEXT[badge]));
      }
    }
    const path = paths[b.id] ?? (b.id.startsWith("n:") ? b.id.slice(2).split("#")[0] : null);
    if (path === null || b.isInFlyout) {
      if (!b.isInFlyout) {
        if (syncLabelRows(B, b)) grew.push(b); // round 21: the badge row once it says something
        if (!settingOfType(b.type) && !b.outputConnection) b.setWarningText(warningText(issueOf.get(b.id) ?? [], []));
      }
      continue;
    }
    const runField = b.getField("RUN");
    if (runField) runField.setValue(trace ? runLine(trace.nodes[prefix + path] ?? trace.nodes[path]) || "not run" : "");
    if (syncLabelRows(B, b)) grew.push(b); // round 21: the run line's row shows while it says something
    if (b.outputConnection) continue; // findings sit on the statement that holds the value
    // round 26 (the reviewer: find_target's ⚠ bubble said "info: ... unsupported here: L2 binding
    // ...", twice): an INFO never shows Blockly's warning triangle (the Lint pane lists it), and
    // each line shows once
    if (!settingOfType(b.type)) b.setWarningText(warningText(issueOf.get(b.id) ?? [], byPath.get(path) ?? []));
  }
  return grew;
}
