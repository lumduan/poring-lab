// The model blocks' two menus (lib/flow/models.ts): "detector <model> sees <class>". Both menus are
// made when they open, from the catalogue the page has now: the model menu lists the LIVE models,
// the class menu that model's trained classes. A value from an imported flow that the menus would
// not offer (a not-adopted model, a class the model does not have) is KEPT and shown marked, never
// replaced: the converter stays lossless and the linter names the problem.
import type * as BlocklyT from "blockly/core";

import { CLASS_KEY, classFor, classOptions, MODEL_KEY, type Models, modelOptions } from "../../lib/flow/models.ts";

export const DETECTOR_EXTENSION = "pl_detector_menus";
const TYPES = new Set(["pl_detect_sees", "pl_detect_count"]);
let registered = false;

/** Register the extension once per page; `models` reads the catalogue the page has now. */
export function registerDetectorMenus(B: typeof BlocklyT, models: () => Models | null): void {
  if (registered || B.Extensions.isRegistered(DETECTOR_EXTENSION)) return;
  registered = true;

  /** A dropdown that accepts any well-formed key: a menu made on demand cannot know a loaded value.
   * Blockly finds the shown option in its CACHED menu, so the menu is made again (with the value
   * being set) before each value update: a loaded "cookie_xmas" shows as itself, not the default. */
  class KeyDropdown extends B.FieldDropdown {
    private readonly key: RegExp;
    pending: string | null = null;
    constructor(menu: BlocklyT.MenuGeneratorFunction, key: RegExp) {
      super(menu);
      this.key = key;
    }
    protected override doClassValidation_(newValue?: string): string | null {
      return typeof newValue === "string" && (this.key ?? /./).test(newValue) ? newValue : null;
    }
    protected override doValueUpdate_(newValue: string): void {
      this.pending = newValue;
      this.getOptions(false);
      this.pending = null;
      super.doValueUpdate_(newValue);
    }
  }
  /** The value a menu is made for: the one being set, else the field's own. */
  const valueOf = (f: BlocklyT.FieldDropdown): string | null => {
    const v = (f as unknown as { pending?: string | null }).pending ?? f.getValue();
    return typeof v === "string" ? v : null;
  };

  const modelMenu = function (this: BlocklyT.FieldDropdown): BlocklyT.MenuOption[] {
    const counting = this.getSourceBlock()?.type === "pl_detect_count";
    return modelOptions(models(), valueOf(this), counting);
  };
  const classMenu = function (this: BlocklyT.FieldDropdown): BlocklyT.MenuOption[] {
    const model = String(this.getSourceBlock()?.getFieldValue("MODEL") ?? "");
    return classOptions(models(), model, valueOf(this));
  };

  B.Extensions.register(DETECTOR_EXTENSION, function (this: BlocklyT.Block) {
    for (const [name, menu, key] of [
      ["MODEL", modelMenu, MODEL_KEY],
      ["CLASS", classMenu, CLASS_KEY],
    ] as const) {
      const old = this.getField(name);
      const input = old ? this.inputList.find((i) => i.fieldRow.includes(old)) : undefined;
      if (!old || !input) continue;
      const at = input.fieldRow.indexOf(old);
      const value = old.getValue();
      input.removeField(name, true);
      const field = new KeyDropdown(menu, key);
      input.insertFieldAt(at, field as unknown as BlocklyT.Field, name);
      if (typeof value === "string") field.setValue(value);
    }
  });
}

/** After a learner picks another model, the class follows (its first class) unless it still fits;
 * the class change joins the model change's undo group. */
export function followModel(B: typeof BlocklyT, ws: BlocklyT.WorkspaceSvg, models: () => Models | null) {
  return (e: BlocklyT.Events.Abstract) => {
    if (e.type !== B.Events.BLOCK_CHANGE) return;
    const ch = e as BlocklyT.Events.BlockChange;
    if (ch.element !== "field" || ch.name !== "MODEL" || !ch.blockId) return;
    const b = ws.getBlockById(ch.blockId);
    if (!b || !TYPES.has(b.type)) return;
    const cls = b.getField("CLASS");
    const cur = String(cls?.getValue() ?? "");
    const next = classFor(models(), String(ch.newValue ?? ""), cur);
    if (cls && next !== cur) {
      const group = B.Events.getGroup();
      B.Events.setGroup(ch.group || true);
      cls.setValue(next);
      B.Events.setGroup(group);
    }
  };
}
