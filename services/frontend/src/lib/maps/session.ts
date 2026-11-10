// The Maps page's SESSION: Login and Choose character, the two steps before the first map (Batt
// 2026-11-10: "start from login and character selection; make it a MOCK for now -- we already have
// the Python code for this part, the bot uses it"). docs/planning/world-map-flows.md section 3.
//
// A MOCK, and only a mock: nothing here logs in, types or sends anything. The simulator plays these
// steps with fixed times before the flow's first map; the Python pane shows the bot's REAL calls
// they stand for (scripts/ro_agent.py: `to_char_select(agent, screen, which)`,
// `enter_game(agent, screen, which, char=None)`, `login` = both, `session(name)`).
//
// - NO credential anywhere: the account is ro_agent's `which` ("gm" | "player"), whose id and
//   password the bot reads from the server's .env (`account(which)`); the page never asks for,
//   stores or shows them.
// - The SERVER list mirrors config/environments.yaml (ADR-0006, the interlock of ADR-0016): only the
//   lab's rAthena can be chosen; every other entry is shown disabled with why (session.test.ts reads
//   the YAML and fails on any difference in ids or statuses).
// - The CHARACTER: the bot enters the slot the client REMEMBERS (Enter on the selected slot:
//   enter_game); `char` names the character that slot holds when it is not the account's .env one
//   (enter_game checks it against the account's characters in the database). A numbered slot is a
//   mock choice: ro_agent has no slot click (a person, or the caller, selects it first).
import type { StorageLike } from "../flow/prefs.ts";

export type ServerStatus = "allowed" | "pending" | "forbidden";
export type ServerChoice = { id: string; title: string; status: ServerStatus; automatable: boolean; why: string };

/** config/environments.yaml's environments, in its order; only `automatable` ones can be chosen. */
export const SERVERS: readonly ServerChoice[] = [
  {
    id: "lab-rathena",
    title: "Lab rAthena (this lab's server)",
    status: "allowed",
    automatable: true,
    why: "the lab's own rAthena on this network: the only server the bot may act on, and only while the interlock attests it (ADR-0006 environment 1, ADR-0016)",
  },
  {
    id: "lab-rathena-th",
    title: "Lab rAthena, Thai data (stopped)",
    status: "allowed",
    automatable: false,
    why: "its client copy was removed from the Windows PC on 2026-10-06 (ADR-0019), so ro_agent refuses its profile; the server itself is normally stopped",
  },
  {
    id: "official-ro-thai",
    title: "Official Thai RO",
    status: "forbidden",
    automatable: false,
    why: "an official server: forbidden for every component, in every mode (ADR-0006)",
  },
  {
    id: "official-ro-korea",
    title: "Official Korean RO (kRO)",
    status: "forbidden",
    automatable: false,
    why: "an official server: forbidden for every component, in every mode (ADR-0006)",
  },
  {
    id: "community-bot-testing",
    title: "Community bot-testing server",
    status: "pending",
    automatable: false,
    why: "the owner's written permission is still pending and no session there can be verified (packet capture is not allowed): no automation; Batt may play it by hand (ADR-0006 environment 2)",
  },
];

export type Account = "gm" | "player";
/** ro_agent's `which`: account(which) reads <prefix>_GM_* / <prefix>_AGENT_* from .env. */
export const ACCOUNTS: readonly { id: Account; title: string; env: string }[] = [
  { id: "gm", title: "the lab GM account", env: "RATHENA_GM_USER / _PASSWORD / _CHAR in the server's .env" },
  { id: "player", title: "the lab agent account", env: "RATHENA_AGENT_USER / _PASSWORD / _CHAR in the server's .env" },
];

export const MAX_SLOT = 15;
/** A character name as the page accepts one (letters, digits, spaces, _; at most 23: rAthena's). */
export const CHAR_NAME = /^[A-Za-z0-9_][A-Za-z0-9 _]{0,22}$/;

/** `slot` null: the slot the client remembers (what the bot enters); `char` "": the account's own. */
export type Session = { server: string; account: Account; slot: number | null; char: string };
export const DEFAULT_SESSION: Session = { server: "lab-rathena", account: "gm", slot: null, char: "" };
export const SESSION_KEY = "poring-lab.maps.session.v1";

export function serverOf(id: string): ServerChoice | null {
  return SERVERS.find((s) => s.id === id) ?? null;
}

/** A stored or imported session, checked field by field; anything unknown is the default. */
export function parseSession(text: string | null): Session {
  if (!text || text.length > 2000) return { ...DEFAULT_SESSION };
  let v: unknown;
  try {
    v = JSON.parse(text);
  } catch {
    return { ...DEFAULT_SESSION };
  }
  if (!v || typeof v !== "object" || Array.isArray(v)) return { ...DEFAULT_SESSION };
  const o = v as Record<string, unknown>;
  const server = typeof o.server === "string" && serverOf(o.server)?.automatable ? o.server : DEFAULT_SESSION.server;
  const account: Account = o.account === "player" ? "player" : "gm";
  const slot = typeof o.slot === "number" && Number.isInteger(o.slot) && o.slot >= 1 && o.slot <= MAX_SLOT ? o.slot : null;
  const char = typeof o.char === "string" && CHAR_NAME.test(o.char) ? o.char : "";
  return { server, account, slot, char };
}

export function readSession(store: StorageLike | null): Session {
  try {
    return parseSession(store?.getItem(SESSION_KEY) ?? null);
  } catch {
    return { ...DEFAULT_SESSION };
  }
}

export function writeSession(store: StorageLike | null, s: Session): void {
  try {
    store?.setItem(SESSION_KEY, JSON.stringify(s));
  } catch {
    // the page works on, unremembered
  }
}

/** What to tell a learner before the session runs (empty: nothing to say). */
export function sessionProblems(s: Session, flowServer: string): string[] {
  const out: string[] = [];
  const chosen = serverOf(s.server);
  if (!chosen?.automatable) out.push(`${s.server}: the bot may not act on this server (${chosen?.why ?? "not in the environment list"})`);
  if (flowServer !== s.server) out.push(`the flow targets ${flowServer}, the login is ${s.server}: the run is checked against the flow's server`);
  if (s.char !== "" && !CHAR_NAME.test(s.char)) out.push("the character name: letters, digits, spaces and _ only, at most 23");
  return out;
}

// --- the simulated steps --------------------------------------------------------------------------
export type SessionNode = "start" | "login" | "character";
export type SessionStep = { node: SessionNode; t0: number; t1: number; text: string; call: string };
/** MOCK seconds (illustrative: the real login waits on the client and the database). */
export const SESSION_S: Record<SessionNode, number> = { start: 1, login: 6, character: 4 };

export function slotText(s: Session): string {
  return s.slot === null ? "the remembered slot" : `slot ${s.slot}`;
}

export function sessionSteps(s: Session): SessionStep[] {
  const acc = ACCOUNTS.find((a) => a.id === s.account) ?? ACCOUNTS[0];
  const steps: Omit<SessionStep, "t0" | "t1">[] = [
    { node: "start", text: "Start: the Ragnarok client is open on its login screen", call: 'session("ro_agent")' },
    {
      node: "login",
      text: `Log in to ${s.server} with ${acc.title} (its id and password come from the server's .env, typed as a sensitive batch); OK on the server list`,
      call: `to_char_select(agent, screen, "${s.account}")`,
    },
    {
      node: "character",
      text: `Choose ${slotText(s)}${s.char ? ` (${s.char})` : ""} and press Enter; the character comes online, the chat window is checked`,
      call: `enter_game(agent, screen, "${s.account}"${s.char ? `, char="${s.char}"` : ""})`,
    },
  ];
  let t = 0;
  return steps.map((st) => {
    const t0 = t;
    t += SESSION_S[st.node];
    return { ...st, t0, t1: t };
  });
}

export function sessionLength(): number {
  return SESSION_S.start + SESSION_S.login + SESSION_S.character;
}

/** The session's Python pane: the bot's real calls this mock stands for, marked as a mock. Every
 * comment line is at most 42 characters (the side pane shows ~43, flows-studio.md section 9). */
export function sessionPython(s: Session): string {
  const slot =
    s.slot === null
      ? "    # Enter on the slot the client remembers"
      : `    # slot ${s.slot}: selected first (by hand;\n    # ro_agent has no slot click), then Enter`;
  const char = s.char ? `, char=${JSON.stringify(s.char)}` : "";
  return [
    "# A MOCK: the Maps page simulates it.",
    "# Nothing here runs from this page.",
    "# What the bot runs: scripts/ro_agent.py",
    `#   ro_agent.py login ${s.account}`,
    "from ro_agent import enter_game, session",
    "from ro_agent import to_char_select",
    "",
    "# --- Config -----------------------------",
    `SERVER = ${JSON.stringify(s.server)}  # the lab's own`,
    `ACCOUNT = ${JSON.stringify(s.account)}  # its id: the .env`,
    "",
    "# --- Main -------------------------------",
    'with session("ro_agent") as (agent, screen):',
    "    # the login dialog: the id and password",
    "    # from .env, typed as a sensitive batch;",
    "    # then OK on the server list (the lab",
    "    # client lists PoringLab LAN (rAthena))",
    "    to_char_select(agent, screen, ACCOUNT)",
    slot,
    `    enter_game(agent, screen, ACCOUNT${char})`,
    "    # then the map flow: the next file",
    "",
  ].join("\n");
}
