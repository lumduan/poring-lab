"use client";

// Save and Load for /flows and /maps, one component both pages render (flows-save-load.md
// section 5): the Save dialog, the Load dialog, and GitHub settings opened from either (closing it
// goes back to the dialog it came from). The page keeps the flow, its undo notice and its file meta;
// this keeps nothing of its own but which dialog is showing.
//
// The dialogs are ported from MatPilot (MIT), src/components/blocks/{Save,Load,GitHubSettings}
// Dialog.tsx at 4022c87 (https://github.com/lumduan/matpilot, Copyright (c) 2026 Sarat Sonsuk; the
// licence text is in flowfile.css and THIRD_PARTY.md); this wrapper and the shortcuts hook are ours.
import { useEffect, useRef, useState } from "react";

import { type FileMeta, fileShortcut } from "@/lib/flow/file";
import type { Flow } from "@/lib/flow/ir";

import GitHubSettingsDialog from "./GitHubSettingsDialog";
import LoadDialog, { type Opened } from "./LoadDialog";
import SaveDialog from "./SaveDialog";
import { useGitHub } from "./useGitHub";

export type { Opened } from "./LoadDialog";
export type FileDialog = "save" | "load" | null;

export type FlowFileDialogsProps = {
  readonly open: FileDialog;
  readonly onClose: () => void;
  readonly meta: FileMeta;
  readonly onMeta: (meta: FileMeta) => void;
  readonly getFlow: () => Flow;
  readonly pythonCached: (flow: Flow) => string | null;
  readonly pythonFor: (flow: Flow) => Promise<string>;
  /** A flow that passed every check: the page replaces its flow as ONE undo step. */
  readonly onOpened: (o: Opened) => void;
};

export default function FlowFileDialogs({ open, onClose, meta, onMeta, getFlow, pythonCached, pythonFor, onOpened }: FlowFileDialogsProps) {
  const github = useGitHub();
  const [settings, setSettings] = useState(false);
  if (!open) return null;
  const close = () => {
    setSettings(false);
    onClose();
  };
  if (settings) return <GitHubSettingsDialog github={github} onClose={() => setSettings(false)} />;
  if (open === "save") {
    return <SaveDialog github={github} meta={meta} getFlow={getFlow} pythonCached={pythonCached} pythonFor={pythonFor} onMeta={onMeta} onClose={close} onSetUpGitHub={() => setSettings(true)} />;
  }
  return (
    <LoadDialog
      github={github}
      onClose={close}
      onOpened={(o) => {
        setSettings(false);
        onOpened(o);
      }}
      onSetUpGitHub={() => setSettings(true)}
    />
  );
}

/** Ctrl/⌘+S opens Save and Ctrl/⌘+O opens Load (not while typing in a field, not while a dialog
 * shows; the browser's own Save page and Open file are kept from opening). */
export function useFileShortcuts(onOpen: (d: "save" | "load") => void, open: FileDialog, enabled = true): void {
  const latest = useRef({ onOpen, open, enabled });
  useEffect(() => {
    latest.current = { onOpen, open, enabled };
  });
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const which = fileShortcut(e);
      const now = latest.current;
      if (!which || !now.enabled || now.open !== null) return;
      e.preventDefault();
      now.onOpen(which);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
