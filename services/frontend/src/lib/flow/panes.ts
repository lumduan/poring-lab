/** The drawer's panes in the order the person opened them (Batt 2026-11-21: "the layout opened
 * first is at the top, later ones below; close the top one and the ones below move up; open it
 * again and it goes to the bottom -- a simple way for a user to manage the layout"). PURE. */

/** `p` opened: at the bottom (already open: where it is). */
export function openPane<P extends string>(order: readonly P[], p: P): P[] {
  return order.includes(p) ? [...order] : [...order, p];
}

/** `p` closed: the panes below it move up. */
export function closePane<P extends string>(order: readonly P[], p: P): P[] {
  return order.filter((x) => x !== p);
}

export function setPaneOpen<P extends string>(order: readonly P[], p: P, open: boolean): P[] {
  return open ? openPane(order, p) : closePane(order, p);
}

/** A stored order (a JSON list): the known panes in it, each once; null when there is none or it
 * does not parse (the caller then reads the older per-pane choices). */
export function parsePaneOrder<P extends string>(text: string | null | undefined, known: readonly P[]): P[] | null {
  if (!text) return null;
  let v: unknown;
  try {
    v = JSON.parse(text);
  } catch {
    return null;
  }
  if (!Array.isArray(v)) return null;
  const out: P[] = [];
  for (const x of v) {
    if (typeof x === "string" && (known as readonly string[]).includes(x) && !out.includes(x as P)) out.push(x as P);
  }
  return out;
}

/** The blocks shown or hidden (Batt 2026-11-21: "while a Run plays, hide the coding blocks to see
 * the logs in full"). Hidden, the editor stays mounted (nothing is lost) and the panes take the
 * page's height. */
export const BLOCKS_CHOICES = ["shown", "hidden"] as const;
export type BlocksChoice = (typeof BLOCKS_CHOICES)[number];
