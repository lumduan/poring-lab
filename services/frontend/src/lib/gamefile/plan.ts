// What the finder's results can be turned into, under the page's normal rules (Batt, 2026-10-06):
//   * the DEFAULT is to block: a new Forbidden environment, or an existing one;
//   * adding to an Allowed environment is a separate, deliberate choice, with nothing pre-ticked,
//     and a warning for anything outside the LAN ("the bot will act on this server");
//   * nothing is ever added without the person pressing the button; the backend then applies its
//     usual checks (grammar, forbidden list, who may write).

import { isForbidden, toInputs, type EnvInput, type SettingsView } from "../settings.ts";
import type { Found } from "./endpoint.ts";

export type Target =
  | { kind: "new-forbidden" }
  | { kind: "forbidden"; envId: string }
  | { kind: "allowed"; envId: string };

export interface TargetOption {
  value: string;
  label: string;
  target: Target;
  loosens: boolean; // true: the bot could act on what is added
}

export function targetValue(t: Target): string {
  return t.kind === "new-forbidden" ? "new-forbidden" : `${t.kind}:${t.envId}`;
}

/** Blocking options first (the default is the first one); Allowed ones last, clearly marked. */
export function targetOptions(view: SettingsView): TargetOption[] {
  const out: TargetOption[] = [
    { value: "new-forbidden", label: "Block: create a new Forbidden environment", target: { kind: "new-forbidden" }, loosens: false },
  ];
  for (const e of view.environments) {
    if (e.type !== "forbidden") continue;
    const t: Target = { kind: "forbidden", envId: e.id };
    out.push({ value: targetValue(t), label: `Block: add to “${e.name}” (Forbidden)`, target: t, loosens: false });
  }
  for (const e of view.environments) {
    if (e.type !== "allowed") continue;
    const t: Target = { kind: "allowed", envId: e.id };
    out.push({ value: targetValue(t), label: `Allow: add to “${e.name}” (the bot may act there)`, target: t, loosens: true });
  }
  return out;
}

export function defaultTarget(): Target {
  return { kind: "new-forbidden" };
}

export function keyOfFound(f: { host: string; port: number | null }): string {
  return f.port === null ? f.host : `${f.host}:${f.port}`;
}

/** Why this endpoint cannot go to this target, in plain words; null when it can. */
export function unusable(f: Found, t: Target, forbidden: string[]): string | null {
  if (f.host.includes(":")) return "an IPv6 address: the lab's checks are IPv4 only, so it can't be allowed or blocked here";
  if (t.kind !== "allowed") return null;
  if (f.port === null) return "no port: an allowed server needs one";
  if (isForbidden(f.host, f.port, forbidden)) return "on a forbidden list: it can never be allowed";
  return null;
}

/** The ticks a result starts with: everything usable when BLOCKING; nothing when allowing. */
export function initialTicks(found: Found[], t: Target, forbidden: string[]): Set<string> {
  if (t.kind === "allowed") return new Set();
  return new Set(found.filter((f) => !unusable(f, t, forbidden)).map(keyOfFound));
}

/** The warning an Allowed addition needs before it is sent; null for blocking. */
export function allowWarning(chosen: Found[], t: Target): string | null {
  if (t.kind !== "allowed" || chosen.length === 0) return null;
  const outside = chosen.filter((f) => !f.lan).map(keyOfFound);
  const head = "The bot will act on these servers while the game is connected to them.";
  if (outside.length === 0) return `${head} Allow ${chosen.map(keyOfFound).join(", ")}?`;
  return `${outside.join(", ")} ${outside.length === 1 ? "is" : "are"} OUTSIDE your network. ${head} ` +
    "Only allow a server you run yourself or have permission to use. Are you sure?";
}

const NOTE_MAX = 300;

function noteOf(f: Found): string {
  const where = f.sources.join("; ");
  return `found in ${where}`.slice(0, NOTE_MAX);
}

/** The whole set after adding the chosen endpoints to the target (the PUT body). */
export function applyFound(
  view: SettingsView,
  t: Target,
  chosen: Found[],
  newName: string,
): EnvInput[] {
  const envs = toInputs(view);
  const servers = (have: EnvInput["servers"]) => {
    const keys = new Set(have.map((s) => keyOfFound(s)));
    const add = chosen
      .filter((f) => !unusable(f, t, view.forbidden) && !keys.has(keyOfFound(f)))
      .map((f) => ({ host: f.host, port: f.port, note: noteOf(f), source: "file" }));
    return [...have, ...add];
  };
  if (t.kind === "new-forbidden") {
    return [...envs, {
      id: null, name: newName.trim().slice(0, 80) || "Found in a game file", type: "forbidden",
      summary: "Servers found in a game file; the bot never acts on them.", why: "", servers: servers([]),
    }];
  }
  return envs.map((e) => {
    if (e.id !== t.envId) return e;
    if (t.kind === "allowed" && e.type !== "allowed") return e;
    if (t.kind === "forbidden" && e.type !== "forbidden") return e;
    return { ...e, servers: servers(e.servers) };
  });
}

export const ROLE_TEXT: Record<Found["role"], string> = {
  login: "login server",
  "assist-web": "assist / web service",
  other: "other",
};
