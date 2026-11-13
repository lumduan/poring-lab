// The Maps page's SESSION: the project's Login and Choose character NODES (docs/planning/
// project-model.md sections 2 and 5): a login node's main is `login(server, credential)`, a
// character node's `choose_character(slot?, name?)`. They are real project nodes, but this round
// they are NOT run live (section 1): Simulate plays them, and until the engine's trace names
// them (play kinds "login" / "character") the page plays them as the fixed MOCK timeline below,
// standing for the bot's REAL calls (scripts/ro_agent.py: `to_char_select(agent, screen, which)`,
// `enter_game(agent, screen, which, char=None)`, `login` = both, `session(name)`).
//
// - NO secret anywhere: a CREDENTIAL is a NAME (n8n's way; section 5). This round's are the lab's
//   two accounts as ro_agent knows them (`lab_gm`, `lab_player`); their ids and passwords stay in
//   the server's .env (`account(which)`). The page never asks for, stores or shows them.
// - The SERVER list mirrors config/environments.yaml (ADR-0006, the interlock of ADR-0016): only the
//   lab's rAthena can be chosen; every other entry is shown disabled with why (packages/poring_flow
//   tests/test_maps_page.py reads the YAML and fails on any difference in ids or statuses).
// - The CHARACTER: the bot enters the slot the client REMEMBERS (Enter on the selected slot:
//   enter_game); a name names the character that slot holds when it is not the account's own. A
//   numbered slot is a choice ro_agent cannot click yet (a person, or the caller, selects it).
import { type ActionStmt, clone, type Expr } from "../flow/ir.ts";
import { type CharacterNode, characterMain, type LoginNode, loginMain, MAIN_TAB, nodeById, type PNode, type Project, sessionPath } from "../flow/project.ts";

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
/** The lab's credentials BY NAME (project-model.md section 5) -> ro_agent's `which`, whose id and
 * password the bot reads from .env (<prefix>_GM_* / <prefix>_AGENT_*). Names only. */
export const CREDENTIALS: readonly { name: string; account: Account; title: string; env: string }[] = [
  { name: "lab_gm", account: "gm", title: "the lab GM account", env: "RATHENA_GM_USER / _PASSWORD / _CHAR in the server's .env" },
  { name: "lab_player", account: "player", title: "the lab agent account", env: "RATHENA_AGENT_USER / _PASSWORD / _CHAR in the server's .env" },
];
/** A credential NAME as a project may hold one: a name, never a secret (no spaces, no symbols). */
export const CREDENTIAL_NAME = /^[a-z][a-z0-9_]{0,31}$/;

export const MAX_SLOT = 15;
/** A character name as the page accepts one (letters, digits, spaces, _; at most 23: rAthena's). */
export const CHAR_NAME = /^[A-Za-z0-9_][A-Za-z0-9 _]{0,22}$/;

/** What the session nodes say. `slot` null: the slot the client remembers; `char` "": the account's own. */
export type Session = { server: string; credential: string; slot: number | null; char: string; login: string; character: string };

export function serverOf(id: string): ServerChoice | null {
  return SERVERS.find((s) => s.id === id) ?? null;
}

export function credentialOf(name: string): (typeof CREDENTIALS)[number] | null {
  return CREDENTIALS.find((c) => c.name === name) ?? null;
}

const litStr = (e: Expr | undefined): string | null => (e?.kind === "lit" && typeof e.value === "string" ? e.value : null);
const litInt = (e: Expr | undefined): number | null => (e?.kind === "lit" && typeof e.value === "number" && Number.isInteger(e.value) ? e.value : null);

function actionIn(n: PNode | undefined, block: string): ActionStmt | null {
  const main = n?.tabs.find((t) => t.name === MAIN_TAB)?.main ?? [];
  for (const s of main) if (s.kind === "action" && s.block === block) return s;
  return null;
}

/** A login node's main, read: its server and credential (null: not a literal / no login block),
 * and whether the main is exactly the one login block (the inspector edits only that form). */
export function loginOf(n: PNode | undefined): { server: string | null; credential: string | null; plain: boolean; found: boolean } {
  const a = actionIn(n, "login");
  const main = n?.tabs.find((t) => t.name === MAIN_TAB)?.main ?? [];
  return { server: litStr(a?.params.server), credential: litStr(a?.params.credential), plain: main.length === 1 && a !== null, found: a !== null };
}

/** A character node's main, read: its slot and name (null / "": the remembered slot, the account's own). */
export function characterOf(n: PNode | undefined): { slot: number | null; name: string; plain: boolean; found: boolean } {
  const a = actionIn(n, "choose_character");
  const main = n?.tabs.find((t) => t.name === MAIN_TAB)?.main ?? [];
  return { slot: litInt(a?.params.slot), name: litStr(a?.params.name) ?? "", plain: main.length === 1 && a !== null, found: a !== null };
}

/** The session the project's path says: its login and character nodes (the ready-mades' defaults
 * where a node or a value is missing). */
export function sessionOf(p: Project): Session {
  const sp = sessionPath(p);
  const l = loginOf(sp.login ?? undefined);
  const c = characterOf(sp.character ?? undefined);
  return { server: l.server ?? p.target.server, credential: l.credential ?? "lab_gm", slot: c.slot, char: c.name, login: sp.login?.id ?? p.start, character: sp.character?.id ?? "character" };
}

export type SessionEdit = { ok: true; project: Project } | { ok: false; error: string };

/** Set a login node's server and credential (names only): the first login block of its main, or a
 * new one at its start. */
export function setLogin(p: Project, nodeId: string, v: { server: string; credential: string }): SessionEdit {
  if (!serverOf(v.server)?.automatable) return { ok: false, error: `${v.server}: the bot may not act on this server (${serverOf(v.server)?.why ?? "not in the environment list"})` };
  if (!CREDENTIAL_NAME.test(v.credential)) return { ok: false, error: "a credential is a NAME (lower-case letters, digits and _), never a secret" };
  const out = clone(p);
  const n = nodeById(out, nodeId);
  if (!n || n.kind !== "login") return { ok: false, error: `${nodeId} is not a login node` };
  const main = n.tabs.find((t) => t.name === MAIN_TAB);
  if (!main?.main) return { ok: false, error: `${nodeId} has no main tab` };
  const a = actionIn(n, "login");
  if (a) a.params = { ...a.params, server: { kind: "lit", value: v.server }, credential: { kind: "lit", value: v.credential } };
  else main.main.unshift(...loginMain(v.server, v.credential));
  return { ok: true, project: out };
}

/** Set a character node's slot (null: the remembered one) and name ("": the account's own). */
export function setCharacter(p: Project, nodeId: string, v: { slot: number | null; name: string }): SessionEdit {
  if (v.slot !== null && (!Number.isInteger(v.slot) || v.slot < 1 || v.slot > MAX_SLOT)) return { ok: false, error: `a slot is 1 to ${MAX_SLOT}, or the remembered one` };
  if (v.name !== "" && !CHAR_NAME.test(v.name)) return { ok: false, error: "the character name: letters, digits, spaces and _ only, at most 23" };
  const out = clone(p);
  const n = nodeById(out, nodeId);
  if (!n || n.kind !== "character") return { ok: false, error: `${nodeId} is not a character node` };
  const main = n.tabs.find((t) => t.name === MAIN_TAB);
  if (!main?.main) return { ok: false, error: `${nodeId} has no main tab` };
  let a = actionIn(n, "choose_character");
  if (!a) {
    a = characterMain()[0] as ActionStmt;
    main.main.unshift(a);
  }
  const params: ActionStmt["params"] = { ...a.params };
  delete params.slot;
  delete params.name;
  if (v.slot !== null) params.slot = { kind: "lit", value: v.slot };
  if (v.name !== "") params.name = { kind: "lit", value: v.name };
  a.params = params;
  return { ok: true, project: out };
}

/** What to tell a learner before the session runs (empty: nothing to say). */
export function sessionProblems(s: Session, projectServer: string): string[] {
  const out: string[] = [];
  const chosen = serverOf(s.server);
  if (!chosen?.automatable) out.push(`${s.server}: the bot may not act on this server (${chosen?.why ?? "not in the environment list"})`);
  if (projectServer !== s.server) out.push(`the project targets ${projectServer}, the login is ${s.server}: the run is checked against the project's server`);
  if (!credentialOf(s.credential)) out.push(`the credential ${s.credential} is not one the lab knows (${CREDENTIALS.map((c) => c.name).join(", ")})`);
  if (s.char !== "" && !CHAR_NAME.test(s.char)) out.push("the character name: letters, digits, spaces and _ only, at most 23");
  return out;
}

export function slotText(s: Pick<Session, "slot">): string {
  return s.slot === null ? "the remembered slot" : `slot ${s.slot}`;
}

// --- the simulated steps (the MOCK until the engine's trace names them) ---------------------------
export type SessionStepKind = "start" | "login" | "character";
/** `node`: the project node the step belongs to (the client's start belongs to the login node). */
export type SessionStep = { step: SessionStepKind; node: string; t0: number; t1: number; text: string; call: string };
/** MOCK seconds (illustrative: the real login waits on the client and the database). */
export const SESSION_S: Record<SessionStepKind, number> = { start: 1, login: 6, character: 4 };

export function sessionSteps(s: Session): SessionStep[] {
  const cred = credentialOf(s.credential);
  const which = cred?.account ?? "gm";
  const steps: Omit<SessionStep, "t0" | "t1">[] = [
    { step: "start", node: s.login, text: "Start: the Ragnarok client is open on its login screen", call: 'session("ro_agent")' },
    {
      step: "login",
      node: s.login,
      text: `Log in to ${s.server} with the credential ${s.credential}${cred ? ` (${cred.title}: its id and password come from the server's .env, typed as a sensitive batch)` : ""}; OK on the server list`,
      call: `to_char_select(agent, screen, "${which}")`,
    },
    {
      step: "character",
      node: s.character,
      text: `Choose ${slotText(s)}${s.char ? ` (${s.char})` : ""} and press Enter; the character comes online, the chat window is checked`,
      call: `enter_game(agent, screen, "${which}"${s.char ? `, char="${s.char}"` : ""})`,
    },
  ];
  let t = 0;
  return steps.map((st) => {
    const t0 = t;
    t += SESSION_S[st.step];
    return { ...st, t0, t1: t };
  });
}

export function sessionLength(): number {
  return SESSION_S.start + SESSION_S.login + SESSION_S.character;
}

/** The session nodes' words for a card or the inspector. */
export function loginWords(n: LoginNode | PNode | undefined): string {
  const l = loginOf(n);
  if (!l.found) return "no login block in its main yet";
  const srv = l.server ? (serverOf(l.server)?.title ?? l.server) : "a server that is not a plain name";
  const cred = l.credential ? `the credential ${l.credential}${credentialOf(l.credential) ? ` (${credentialOf(l.credential)?.title})` : ""}` : "a credential that is not a plain name";
  return `Log in to ${srv} with ${cred}${l.plain ? "" : ", among other steps"}.`;
}

export function characterWords(n: CharacterNode | PNode | undefined): string {
  const c = characterOf(n);
  if (!c.found) return "no choose-character block in its main yet";
  return `Enter ${slotText(c)}${c.name ? ` (${c.name})` : ", the account's own character"}${c.plain ? "" : ", among other steps"}.`;
}
