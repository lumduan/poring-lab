// Where on GitHub this browser keeps flows, and the token to save them
// (docs/planning/flows-save-load.md section 3). A plain store (no React; components/flowfile/
// useGitHub.ts wraps it), so its rules are unit-tested.
//
// THE TOKEN, stricter than MatPilot's default (ported from MatPilot (MIT), src/hooks/useAiHelper.ts
// at 4022c87, its key-storage pattern; src/hooks/useGitHub.ts for the rest:
// https://github.com/lumduan/matpilot, Copyright (c) 2026 Sarat Sonsuk; the licence text is in
// components/flowfile/flowfile.css and THIRD_PARTY.md):
// - by default it lives in THIS BROWSER TAB only (sessionStorage), gone when the tab closes;
// - it goes to localStorage ONLY when a person ticks "Remember on this computer";
// - storage that refuses it (a private window, blocked site data) keeps it in the page's memory;
// - "Forget the token" removes it from all three.
// The settings (repository, folder, your name) are not secret and stay in localStorage. Nothing here
// talks to GitHub: client.ts does, and only when a person asks.
import type { StorageLike } from "../flow/prefs.ts";
import { DEFAULT_FOLDER } from "./repository.ts";

export type GitHubSettings = {
  /** As typed: `owner/name`, a github.com link or git@github.com:... (repository.ts parses it). */
  readonly repository: string;
  readonly folder: string;
  /** The name put in commit messages ("saved by ..."); may be empty. */
  readonly author: string;
  /** Keep the token in localStorage (only when a person ticked it). */
  readonly remember: boolean;
  /** The default branch "Check and save" found ("" unknown): one request fewer for each listing. */
  readonly branch: string;
};

export const DEFAULT_GITHUB_SETTINGS: GitHubSettings = { repository: "", folder: DEFAULT_FOLDER, author: "", remember: false, branch: "" };
export const GITHUB_KEYS = { settings: "poring-lab.github.v1", token: "poring-lab.github.token.v1" } as const;

export type Areas = { readonly local: () => StorageLike | null; readonly session: () => StorageLike | null };
export type TokenPlace = "memory" | "session" | "local";
export type GitHubSnapshot = { readonly settings: GitHubSettings; readonly token: string | null; readonly where: TokenPlace | null };

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const text = (v: unknown, max: number, d: string): string => (typeof v === "string" && v.length <= max ? v : d);

export function parseSettings(raw: string | null): GitHubSettings {
  if (raw === null) return DEFAULT_GITHUB_SETTINGS;
  try {
    const d: unknown = JSON.parse(raw);
    if (!isObj(d)) return DEFAULT_GITHUB_SETTINGS;
    return {
      repository: text(d.repository, 300, ""),
      folder: text(d.folder, 300, DEFAULT_FOLDER),
      author: text(d.author, 100, ""),
      remember: d.remember === true,
      branch: text(d.branch, 255, ""),
    };
  } catch {
    return DEFAULT_GITHUB_SETTINGS;
  }
}

/** What is wrong with a pasted token, or null (an empty one is "none"). A token goes into an HTTP
 * header: visible ASCII only. */
export function tokenProblem(token: string): string | null {
  const t = token.trim();
  if (t === "") return null;
  if (t.length > 255) return "That is too long to be a GitHub token: copy it again.";
  if (!/^[\x21-\x7e]+$/.test(t)) return "The token has spaces, line breaks or other letters in it: copy it again.";
  return null;
}

const usable = (t: string | null): string | null => (t !== null && t.trim() !== "" && tokenProblem(t) === null ? t.trim() : null);

export class GitHubSettingsStore {
  private readonly areas: Areas;
  /** What storage refused, kept in this page's memory instead. */
  private memoryToken: string | null = null;
  private memorySettings: string | null = null;
  private cache: { key: string; snap: GitHubSnapshot } | null = null;
  private readonly listeners = new Set<() => void>();

  constructor(areas: Areas) {
    this.areas = areas;
  }

  private read(area: keyof Areas, key: string): string | null {
    try {
      return this.areas[area]()?.getItem(key) ?? null;
    } catch {
      return null;
    }
  }

  private write(area: keyof Areas, key: string, value: string | null): boolean {
    try {
      const s = this.areas[area]();
      if (!s) return false;
      if (value === null) s.removeItem(key);
      else s.setItem(key, value);
      return true;
    } catch {
      return false;
    }
  }

  /** The settings and the token (the same object while nothing changed: useSyncExternalStore). */
  snapshot(): GitHubSnapshot {
    const raw = this.memorySettings ?? this.read("local", GITHUB_KEYS.settings);
    const session = usable(this.read("session", GITHUB_KEYS.token));
    const local = usable(this.read("local", GITHUB_KEYS.token));
    const token = this.memoryToken ?? session ?? local;
    const where: TokenPlace | null = this.memoryToken !== null ? "memory" : session !== null ? "session" : local !== null ? "local" : null;
    const key = JSON.stringify([raw, token, where]);
    if (this.cache?.key !== key) this.cache = { key, snap: { settings: parseSettings(raw), token, where } };
    return this.cache.snap;
  }

  /** Stores the settings; `token` replaces the token, null keeps it, "" forgets it. The token goes
   * to localStorage only when `settings.remember`, else to this tab (sessionStorage). */
  save(settings: GitHubSettings, token: string | null): void {
    const raw = JSON.stringify(settings);
    this.memorySettings = this.write("local", GITHUB_KEYS.settings, raw) ? null : raw;
    const current = this.snapshot().token;
    const next = token === null ? current : usable(token);
    this.clearToken();
    if (next !== null && !this.write(settings.remember ? "local" : "session", GITHUB_KEYS.token, next)) this.memoryToken = next;
    this.notify();
  }

  /** "Forget the token": from memory, this tab and this computer. */
  forgetToken(): void {
    this.clearToken();
    this.notify();
  }

  private clearToken(): void {
    this.write("local", GITHUB_KEYS.token, null);
    this.write("session", GITHUB_KEYS.token, null);
    this.memoryToken = null;
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  notify(): void {
    for (const l of [...this.listeners]) l();
  }
}
