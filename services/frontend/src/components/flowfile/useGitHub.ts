"use client";

// The GitHub settings and the client, for the Save, Load and GitHub dialogs: React's view of
// lib/github/settings.ts (the token rules live and are tested there). NOTHING here talks to GitHub
// on its own: a request is made only when a dialog calls check / list / read / write, which a person
// starts by opening GitHub settings, Save or Load (flows-save-load.md section 3).
//
// Ported from MatPilot (MIT), src/hooks/useGitHub.ts at 4022c87 (https://github.com/lumduan/matpilot,
// Copyright (c) 2026 Sarat Sonsuk; the licence text is in flowfile.css and THIRD_PARTY.md). Ours: the
// token store (this tab by default), the saved default branch, the truncated listing.
import { useCallback, useMemo, useSyncExternalStore } from "react";

import { GitHubClient, type RemoteFile, type RepositoryInfo } from "@/lib/github/client";
import { type FlowListing, listFlows, saveFlow, type SaveOutcome } from "@/lib/github/flows";
import { cleanFolder, parseRepository, type RepositoryName } from "@/lib/github/repository";
import { DEFAULT_GITHUB_SETTINGS, type GitHubSettings, GitHubSettingsStore, type GitHubSnapshot, type TokenPlace } from "@/lib/github/settings";

let shared: GitHubSettingsStore | null = null;
function store(): GitHubSettingsStore {
  shared ??= new GitHubSettingsStore({
    local: () => {
      try {
        return typeof window === "undefined" ? null : window.localStorage;
      } catch {
        return null;
      }
    },
    session: () => {
      try {
        return typeof window === "undefined" ? null : window.sessionStorage;
      } catch {
        return null;
      }
    },
  });
  return shared;
}

const SERVER: GitHubSnapshot = { settings: DEFAULT_GITHUB_SETTINGS, token: null, where: null };
function subscribe(listener: () => void): () => void {
  const off = store().subscribe(listener);
  window.addEventListener("storage", listener); // another tab saved or forgot
  return () => {
    off();
    window.removeEventListener("storage", listener);
  };
}
const getSnapshot = (): GitHubSnapshot => store().snapshot();
const getServerSnapshot = (): GitHubSnapshot => SERVER;

export type GitHubApi = {
  readonly settings: GitHubSettings;
  readonly hasToken: boolean;
  /** Where the token is kept: this tab, this computer, or the page's memory. */
  readonly where: TokenPlace | null;
  readonly repository: RepositoryName | null;
  /** The folder, cleaned; null when it cannot be used. */
  readonly folder: string | null;
  /** A repository and a usable folder are set. */
  readonly configured: boolean;
  readonly save: (settings: GitHubSettings, token: string | null) => void;
  readonly forgetToken: () => void;
  /** Reads a repository with a token (the new one, else the kept one) before the settings are kept. */
  readonly check: (repository: RepositoryName, token: string | null) => Promise<RepositoryInfo>;
  readonly list: () => Promise<FlowListing>;
  readonly read: (path: string) => Promise<RemoteFile | null>;
  readonly write: (args: Parameters<typeof saveFlow>[1]) => Promise<SaveOutcome>;
};

const notConfigured = () => Promise.reject(new Error("GitHub is not set up."));

export function useGitHub(): GitHubApi {
  const { settings, token, where } = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const repository = useMemo(() => parseRepository(settings.repository), [settings.repository]);
  const folder = cleanFolder(settings.folder);
  const client = useMemo(() => (repository ? new GitHubClient({ repository, token, branch: settings.branch || null }) : null), [repository, token, settings.branch]);

  const save = useCallback((s: GitHubSettings, t: string | null) => store().save(s, t), []);
  const forgetToken = useCallback(() => store().forgetToken(), []);
  const check = useCallback((name: RepositoryName, candidate: string | null) => new GitHubClient({ repository: name, token: candidate ?? getSnapshot().token }).getRepository(), []);
  const list = useCallback(() => (client && folder !== null ? listFlows(client, folder) : notConfigured()), [client, folder]);
  const read = useCallback((path: string) => (client ? client.readFile(path) : notConfigured()), [client]);
  const write = useCallback((args: Parameters<typeof saveFlow>[1]) => (client ? saveFlow(client, args) : notConfigured()), [client]);

  return { settings, hasToken: token !== null, where, repository, folder, configured: repository !== null && folder !== null, save, forgetToken, check, list, read, write };
}
