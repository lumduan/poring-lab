"use client";

import { useState, type ClipboardEvent, type KeyboardEvent } from "react";

import type { Mode, PasteResult } from "@/lib/protocol";
import { checkPaste, describePaste, formatBytes, PASTE_MAX_BYTES } from "@/lib/transfer";

type Props = {
  enabled: boolean; // the backend offers clipboard paste (Status.clipboard_enabled)
  connected: boolean;
  /** Watch only is on in this tab: nothing is sent (Batt, 2026-10-07). */
  watchOnly?: boolean;
  mode: Mode | null;
  pending: boolean;
  result: PasteResult | null;
  /** Send the text; returns false when the input socket is down. */
  onSend: (text: string) => boolean;
};

const button =
  "rounded-md border border-neutral-700 bg-neutral-900 px-2.5 py-1 text-sm hover:bg-neutral-800 disabled:opacity-40";

/** "Paste to Windows" (ADR-0004). A plain HTTP page is not a secure context, so the async
 * Clipboard API is unavailable -- but a real paste into a focused textarea works everywhere: the
 * user presses Cmd+V here, checks the text, and sends it. The backend then pastes it into
 * whichever Windows window has focus (click the target field in the remote screen first). */
export default function PastePanel({
  enabled,
  connected,
  watchOnly = false,
  mode,
  pending,
  result,
  onSend,
}: Props) {
  const [text, setText] = useState("");
  const [sentText, setSentText] = useState<string | null>(null);
  const check = checkPaste(text);

  // A successful paste clears the box: the text should not linger in the page.
  if (!pending && result?.ok && sentText !== null && text === sentText) {
    setText("");
    setSentText(null);
  }

  const blocked = !enabled
    ? "Clipboard paste is off on the backend (RDP_CLIPBOARD=text-to-remote)."
    : !connected
      ? "Input channel disconnected."
      : watchOnly
        ? "Watch only is on: nothing is sent. Turn it off to paste."
        : mode === "BOT"
        ? "The mux is in BOT mode: switch to HUMAN or ASSIST to paste."
        : null;

  const send = () => {
    if (blocked || pending || !check.ok) return;
    if (onSend(text)) setSentText(text);
  };

  const onPaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const pasted = event.clipboardData.getData("text/plain");
    if (!pasted) return; // not text (an image, say): let the browser do nothing
    event.preventDefault();
    setText(pasted); // one paste = one thing to send; edit it here if needed
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      send();
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-neutral-400">
        Quickest: click the target field in the remote screen, then just press ⌘V there. Or: paste
        into the box below (⌘V), check it, and Send (⌘Enter). Text only, up to{" "}
        {formatBytes(PASTE_MAX_BYTES)}; Thai is fine.
      </p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onPaste={onPaste}
        onKeyDown={onKeyDown}
        rows={4}
        spellCheck={false}
        placeholder="Paste here (⌘V)…"
        className="w-full resize-y rounded-md border border-neutral-700 bg-neutral-950 p-2 font-mono text-sm text-neutral-100 outline-none focus:ring-2 focus:ring-sky-500"
        aria-label="Text to paste into Windows"
      />
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <button
          type="button"
          className={button}
          onClick={send}
          disabled={!!blocked || pending || !check.ok}
        >
          {pending ? "Pasting…" : "Send to Windows"}
        </button>
        <span className="font-mono text-neutral-400">
          {text.length} chars · {formatBytes(check.bytes)} / {formatBytes(PASTE_MAX_BYTES)}
        </span>
        {text && (
          <button type="button" className={button} onClick={() => setText("")}>
            Clear
          </button>
        )}
      </div>
      {blocked && <p className="text-xs text-amber-300">{blocked}</p>}
      {check.message && <p className="text-xs text-red-400">{check.message}</p>}
      {result && !pending && (
        <p className={`text-xs ${result.ok ? "text-emerald-400" : "text-red-400"}`} role="status">
          {result.ok
            ? `Pasted ${result.chars} characters into the focused Windows window.`
            : describePaste(result.reason)}
        </p>
      )}
    </div>
  );
}
