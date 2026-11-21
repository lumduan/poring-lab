/** Batt 2026-11-21: "the tooltip in the weight field -- why does it show HP?" The expression
 * block's tooltip said the same example for every expression (hp_percent() < 50). Now it says
 * what THIS expression means, in words, when it is a comparison it knows (joined by and / or);
 * the general help follows. PURE (blockly-register.ts sets it as the block's tooltip). */

export const EXPR_HELP = "An expression in the Python view's form, e.g. weight_percent() >= 75, hp_percent() < 50, sees(mob=mob(9109), within=15)";

const SENSOR_WORDS: Record<string, string> = {
  weight_percent: "the bag's weight (% of the most she can carry)",
  hp_percent: "her HP (%)",
  sp_percent: "her SP (%)",
  hp: "her HP",
  sp: "her SP",
};

const OP_WORDS: Record<string, string> = {
  ">=": "is at or over",
  ">": "is over",
  "<=": "is at or under",
  "<": "is under",
  "==": "is",
  "!=": "is not",
};

function partWords(part: string): string | null {
  const m = part.trim().match(/^([a-z_]+)\(\s*([A-Za-z0-9_]*)\s*\)\s*(>=|<=|==|!=|>|<)\s*(-?\d+(?:\.\d+)?)$/);
  if (!m) return null;
  const [, name, arg, op, num] = m;
  let what = SENSOR_WORDS[name];
  if (name === "hotbar_count" && arg) what = `the count on hotbar key ${arg}`;
  if (!what || (arg && name !== "hotbar_count")) return null;
  return `${what} ${OP_WORDS[op]} ${num}`;
}

/** The tooltip for an expression's text: its meaning when known, then the general help. */
export function exprTooltip(text: string | null | undefined): string {
  const t = (text ?? "").trim();
  if (!t) return EXPR_HELP;
  const joiner = / and /.test(t) && !/ or /.test(t) ? " and " : / or /.test(t) && !/ and /.test(t) ? " or " : null;
  const parts = joiner ? t.split(joiner) : [t];
  const said = parts.map(partWords);
  if (said.some((s) => s === null)) return `${t}\n${EXPR_HELP}`;
  return `On when ${said.join(joiner ?? "")}.\n(${t})\n${EXPR_HELP}`;
}
