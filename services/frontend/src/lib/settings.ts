// The Settings page's server allowlist (Batt, 2026-10-06; backend routes_settings.py). The backend
// decides; this file only mirrors its checks so a typo is caught before Save, and turns its refusal
// reasons into plain words.

export type EnvType = "allowed" | "forbidden" | "pending";

export interface ResolvedIp {
  ip: string;
  cdn: string | null;
}

export interface ServerView {
  host: string; // a name, an IPv4 address, or ".domain" (forbidden/pending lists)
  port: number | null; // null: every port
  key: string;
  note: string;
  source: "default" | "manual" | "discovered" | "import";
  added_at: string;
  added_by: string;
  resolved: ResolvedIp[];
  forbidden: boolean; // an allowed server now on a forbidden list: shown, and ignored by the bot
}

export interface Suggestion {
  host: string;
  port: number;
}

export interface EnvView {
  id: string;
  name: string;
  type: EnvType;
  summary: string;
  why: string;
  servers: ServerView[];
  suggestions: Suggestion[];
  ready: boolean;
  signals: string[];
}

export interface SettingsView {
  revision: number | null;
  store: string;
  seeded_from: string | null;
  config: string;
  environments: EnvView[];
  forbidden: string[];
  saved?: boolean;
  read_back?: boolean;
  changes?: { kind: "easy" | "normal" | "hard"; text: string }[];
}

/** One environment as the PUT body carries it (user fields only). */
export interface EnvInput {
  id: string | null;
  name: string;
  type: EnvType;
  summary: string;
  why: string;
  servers: { host: string; port: number | null; note: string; source?: string }[];
}

export interface AuditRecord {
  t_wall: string;
  action: string;
  kind?: "easy" | "normal" | "hard" | null;
  env_id: string | null;
  entry: string | null;
  revision_before: number | null;
  revision_after: number | null;
  ok: boolean;
  reason: string;
  client: string | null;
  note?: string | null;
}

const LABEL = "[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?";
const DNS_NAME = new RegExp(`^(?=.{1,253}$)${LABEL}(?:\\.${LABEL})*$`);
const IPV4 = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/;

export const REASON_TEXT: Record<string, string> = {
  empty_host: "Type a server address.",
  wildcard: "Wildcards (*) are not allowed: name one server.",
  unspecified_address: "0.0.0.0 is not a server address.",
  loopback: "This computer's own address (localhost / 127.x) is not a game server.",
  link_local: "169.254.x.x is not a game server address.",
  not_unicast: "That address is not a single server.",
  ipv6_not_supported: "Use an IPv4 address or a name.",
  bad_host: "That does not look like a server address (an IP like 192.168.1.13, or a name).",
  bad_port: "The port must be a number from 1 to 65535.",
  forbidden_endpoint: "That is an official game server: automation is never allowed there.",
  duplicate: "That server is already in the list.",
  stale_revision: "Someone else saved in the meantime. Reload and try again.",
  origin_required: "This page must be opened from the lab console.",
  origin_not_allowed: "This page must be opened from the lab console.",
  not_public_listener: "Settings can only be changed from the lab console.",
  compose_peer: "Settings can only be changed from a browser on your network.",
  not_a_lan_viewer: "Settings can only be changed from a browser on your network.",
  agent_network: "The bot can never change settings.",
  lab_host_peer: "Settings cannot be changed from the lab computer itself: use your own computer's browser.",
  windows_host_peer: "Settings cannot be changed from the game PC (the bot controls it): use your own computer's browser.",
  environment_pending: "This environment is not approved yet: servers cannot be added.",
  environment_forbidden: "Automation is forbidden here: servers cannot be added.",
  unknown_environment: "Unknown environment.",
  settings_store_missing: "The settings store is not mounted on the backend.",
  settings_store_corrupt: "The saved settings file is damaged: nothing was changed.",
  write_failed: "Saving failed: nothing was changed.",
  config_missing: "The lab's environment list is missing on the backend.",
  config_invalid: "The lab's environment list is invalid on the backend.",
  invalid: "The request was not understood.",
  too_large: "Too many servers in one save.",
  reason_required: "This loosens a forbidden list: give a reason (at least 10 characters).",
  port_required: "A server the bot may use needs a port (for example 6900).",
  domain_not_allowed_here: "A whole domain can only be blocked, never allowed: name one server.",
  duplicate_name: "Another environment already has that name.",
  duplicate_environment: "That environment appears twice.",
  one_hard_change_at_a_time: "Loosen one forbidden thing at a time (each needs its own reason).",
  environments_store_missing: "The saved environments are missing on the backend: the bot is blocked until this is fixed.",
  environments_store_invalid: "The saved environments are damaged on the backend: the bot is blocked until this is fixed.",
  environments_store_unseeded: "The environments have not been set up yet on the backend.",
  confirm_mismatch: "Type the blocked server exactly as shown to confirm.",
  bad_forbidden_entry: "Write a server (name or IP), optionally with :port, or .domain for a whole domain.",
  not_blocked: "That server is not on the blocked list.",
  not_a_forbidden_environment: "Blocked servers belong to the forbidden (official) environments.",
};

export function reasonText(reason: string): string {
  return REASON_TEXT[reason] ?? `Refused (${reason}).`;
}

function ipRefusal(host: string): string | null {
  const m = IPV4.exec(host);
  if (!m) return null;
  const o = m.slice(1).map(Number);
  if (o.some((n) => n > 255)) return "bad_host";
  if (o.every((n) => n === 0)) return "unspecified_address";
  if (o[0] === 127) return "loopback";
  if (o[0] === 169 && o[1] === 254) return "link_local";
  if (o[0] >= 224) return "not_unicast";
  return "";
}

/** The forbidden list as /settings/servers sends it: "host", "host:port" or "*.domain". */
export function isForbidden(host: string, port: number, forbidden: string[]): boolean {
  for (const item of forbidden) {
    if (item.startsWith("*.")) {
      const domain = item.slice(2);
      if (host === domain || host.endsWith(`.${domain}`)) return true;
    } else if (item === host || item === `${host}:${port}`) {
      return true;
    }
  }
  return false;
}

/** The backend's checks (allowlist.validate), for a message before Save. */
export function validateEntry(
  hostText: string,
  portText: string,
  forbidden: string[],
): { host: string; port: number; error: string | null } {
  const host = hostText.trim().toLowerCase().replace(/\.$/, "");
  const port = Number(portText.trim());
  let error: string | null = null;
  if (!host) error = "empty_host";
  else if (host.includes("*") || host.includes("?")) error = "wildcard";
  else if (host.includes(":")) error = "ipv6_not_supported";
  else {
    const ip = ipRefusal(host);
    if (ip === null) {
      if (host === "localhost" || host.endsWith(".localhost")) error = "loopback";
      else if (!DNS_NAME.test(host) || /^[\d.]+$/.test(host)) error = "bad_host";
    } else if (ip) {
      error = ip;
    }
  }
  if (!error && (!Number.isInteger(port) || port < 1 || port > 65535)) error = "bad_port";
  if (!error && isForbidden(host, port, forbidden)) error = "forbidden_endpoint";
  return { host, port, error };
}

export function keyOf(e: { host: string; port: number | null }): string {
  return e.port === null ? e.host : `${e.host}:${e.port}`;
}

/** What Save would change, in the list's order. */
export function diff(before: { host: string; port: number }[], after: { host: string; port: number }[]) {
  const b = new Set(before.map(keyOf));
  const a = new Set(after.map(keyOf));
  return {
    added: after.map(keyOf).filter((k) => !b.has(k)),
    removed: before.map(keyOf).filter((k) => !a.has(k)),
  };
}

const ACTION_TEXT: Record<string, string> = {
  seed: "Started from the shipped settings",
  env_create: "Created",
  env_delete: "Deleted",
  env_rename: "Renamed",
  env_type: "Changed type",
  env_text: "Edited description",
  server_add: "Added",
  server_remove: "Removed",
};

export function auditText(r: AuditRecord): string {
  const who = r.client ? ` [from ${r.client}]` : "";
  if (r.action === "refused") {
    return `Refused${r.entry ? ` ${r.entry}` : ""}: ${reasonText(r.reason)}${who}`;
  }
  if (r.action === "seed") return `${ACTION_TEXT.seed} (${r.note ?? ""})`;
  const tag = r.kind === "hard" ? "LOOSENED a forbidden list — " : "";
  const what = r.kind === "hard" ? (r.note ? `reason: "${r.note}"` : "") : (r.note ?? "");
  const rev = `(revision ${r.revision_before} → ${r.revision_after})`;
  return `${tag}${ACTION_TEXT[r.action] ?? r.action}: ${r.entry ?? ""}${what ? ` — ${what}` : ""} ${rev}${who}`;
}

/** "Allowed · 3 servers", "Forbidden · 4 blocked", "Pending · 0 servers". */
export function badgeText(env: Pick<EnvView, "type" | "servers">): string {
  const n = env.servers.length;
  const type = env.type.charAt(0).toUpperCase() + env.type.slice(1);
  if (env.type === "forbidden") return `${type} · ${n} blocked`;
  return `${type} · ${n} server${n === 1 ? "" : "s"}`;
}

/** Why the bot cannot act in an allowed environment yet, in one sentence (null: it can). */
export function notReadyText(env: Pick<EnvView, "type" | "servers" | "signals">): string | null {
  if (env.type !== "allowed") return null;
  const usable = env.servers.filter((s) => !s.forbidden);
  if (env.servers.length === 0) return "The bot cannot act here yet: confirm at least one server below.";
  if (usable.length === 0) return "Every server here is on a forbidden list, so the bot ignores them.";
  if (env.signals.length === 0) {
    return "The bot cannot act here yet: the lab has no way to check a game session on these servers.";
  }
  return null;
}

/** Suggestions grouped by server address, for "Confirm all". */
export function groupSuggestions(list: Suggestion[]): { host: string; ports: number[] }[] {
  const by = new Map<string, number[]>();
  for (const s of list) by.set(s.host, [...(by.get(s.host) ?? []), s.port]);
  return [...by].map(([host, ports]) => ({ host, ports }));
}

/** The whole set as the PUT body carries it. */
export function toInputs(view: Pick<SettingsView, "environments">): EnvInput[] {
  return view.environments.map((e) => ({
    id: e.id,
    name: e.name,
    type: e.type,
    summary: e.summary,
    why: e.why,
    servers: e.servers.map((s) => ({ host: s.host, port: s.port, note: s.note })),
  }));
}

/** A server in plain words: "thro-acc3.gnjoy.in.th : every port", "gnjoy.in.th and every name
 * under it", "192.168.1.13 : 6900". */
export function describeServer(s: { host: string; port: number | null }): string {
  if (s.host.startsWith(".")) return `${s.host.slice(1)} and every name under it`;
  return s.port === null ? `${s.host} : every port` : `${s.host} : ${s.port}`;
}

// --- the forbidden list (Batt, 2026-10-06): asymmetric -- blocking is easy, unblocking is not ---

export const MIN_UNBLOCK_REASON = 10;

/** The firewall-layer warning: a name that resolves into a CDN's shared range. */
export function cdnWarning(b: { resolved: ResolvedIp[] }): string | null {
  const cdns = [...new Set(b.resolved.map((r) => r.cdn).filter((c): c is string => !!c))];
  if (!cdns.length) return null;
  const name = cdns.map((c) => c.charAt(0).toUpperCase() + c.slice(1)).join(", ");
  return (
    `Resolves to ${name} (shared addresses): blocking these IPs in a firewall could also block ` +
    "unrelated websites. The lab matches this server by its name instead."
  );
}

const IPV4_FULL = /^(\d{1,3}\.){3}\d{1,3}$/;

/** The backend's parse_forbidden: "host", "host:port" or ".domain"; null when it is not one. */
export function parseForbidden(text: string): string | null {
  const item = text.trim().toLowerCase().replace(/\.$/, "");
  if (!item || /[*? ]/.test(item)) return null;
  if (item.startsWith(".")) return DNS_NAME.test(item.slice(1)) ? item : null;
  let host = item;
  let port: number | null = null;
  const colon = item.lastIndexOf(":");
  if (colon >= 0) {
    host = item.slice(0, colon);
    const p = item.slice(colon + 1);
    if (!/^\d+$/.test(p) || Number(p) < 1 || Number(p) > 65535) return null;
    port = Number(p);
  }
  if (IPV4_FULL.test(host)) {
    if (host.split(".").some((o) => Number(o) > 255)) return null;
  } else if (!DNS_NAME.test(host) || /^[\d.]+$/.test(host)) {
    return null;
  }
  return port === null ? host : `${host}:${port}`;
}

/** Unblocking is ready only with a real reason AND the entry typed again exactly. */
export function unblockReady(entry: string, reason: string, confirm: string): boolean {
  return reason.trim().length >= MIN_UNBLOCK_REASON && confirm.trim().toLowerCase() === entry;
}
