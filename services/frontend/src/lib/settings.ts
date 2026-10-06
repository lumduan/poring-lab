// The Settings page's server allowlist (Batt, 2026-10-06; backend routes_settings.py). The backend
// decides; this file only mirrors its checks so a typo is caught before Save, and turns its refusal
// reasons into plain words.

export interface EntryView {
  host: string;
  port: number;
  source: "manual" | "discovered";
  added_at: string;
  added_by: string;
  resolved: string[];
}

export interface Suggestion {
  host: string;
  port: number;
  from: string;
}

export interface EnvView {
  id: string;
  status: "allowed" | "pending" | "forbidden";
  adr: string;
  editable: boolean;
  entries: EntryView[];
  discovered: Suggestion[];
}

export interface SettingsView {
  revision: number | null;
  store: string;
  config: string;
  environments: EnvView[];
  forbidden: string[];
  saved?: boolean;
  read_back?: boolean;
}

export interface Draft {
  host: string;
  port: number;
  source: "manual" | "discovered";
}

export interface AuditRecord {
  t_wall: string;
  action: "add" | "remove" | "refused";
  env_id: string | null;
  entry: string | null;
  revision_before: number | null;
  revision_after: number | null;
  ok: boolean;
  reason: string;
  client: string | null;
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

export function keyOf(e: { host: string; port: number }): string {
  return `${e.host}:${e.port}`;
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

export function auditText(r: AuditRecord): string {
  const who = r.client ?? "unknown";
  if (r.action === "refused") {
    return `Refused${r.entry ? ` ${r.entry}` : ""}${r.env_id ? ` (${r.env_id})` : ""}: ${reasonText(r.reason)} [from ${who}]`;
  }
  const verb = r.action === "add" ? "Allowed" : "Removed";
  return `${verb} ${r.entry} in ${r.env_id} (revision ${r.revision_before} → ${r.revision_after}) [from ${who}]`;
}
