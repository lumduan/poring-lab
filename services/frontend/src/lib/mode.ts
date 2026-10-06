// The always-visible mode badge (Batt, 2026-10-06): like a camera's recording LED, so a person who
// sees the bot clicking the wrong window knows at a glance that the bot is the one acting.

import type { Mode } from "./protocol.ts";

export type Tone = "bot" | "assist" | "human" | "unknown";

export interface Badge {
  label: string;
  detail: string;
  tone: Tone;
  pulse: boolean;
  className: string;
}

/** The interlock's state as /health and Status report it (only the fields the badge reads). */
export interface InterlockLike {
  state?: string | null;
  reason?: string | null;
  window?: string | null;
}

const TONE_CLASS: Record<Tone, string> = {
  bot: "bg-red-600 text-white ring-2 ring-red-300",
  assist: "bg-amber-500 text-neutral-950 ring-2 ring-amber-200",
  human: "bg-sky-700 text-white",
  unknown: "bg-neutral-700 text-neutral-200",
};

/** The active colour of each mode, shared by the badge and the mode switch. */
export const MODE_ACTIVE_CLASS: Record<Mode, string> = {
  BOT: "bg-red-600 text-white",
  ASSIST: "bg-amber-500 text-neutral-950",
  HUMAN: "bg-sky-700 text-white",
};

function interlockText(env: InterlockLike | null | undefined): string {
  if (!env?.state) return "";
  if (env.state === "green") return " Lab session verified.";
  if (env.state === "window") return ` Operator window open (${env.window ?? "?"}).`;
  return ` Bot input is blocked (${env.reason ?? "no reason given"}).`;
}

export function modeBadge(mode: Mode | null | undefined, env?: InterlockLike | null): Badge {
  if (mode === "BOT") {
    return {
      label: "BOT IN CONTROL",
      detail: "The bot is acting on the game; your input is ignored. Switch to HUMAN to stop it." +
        interlockText(env),
      tone: "bot",
      pulse: true,
      className: TONE_CLASS.bot,
    };
  }
  if (mode === "ASSIST") {
    return {
      label: "ASSIST",
      detail: "The bot may act; anything you do takes over for a few seconds." + interlockText(env),
      tone: "assist",
      pulse: false,
      className: TONE_CLASS.assist,
    };
  }
  if (mode === "HUMAN") {
    return {
      label: "HUMAN",
      detail: "You are in control. The bot cannot act.",
      tone: "human",
      pulse: false,
      className: TONE_CLASS.human,
    };
  }
  return {
    label: "NO STATUS",
    detail: "The backend is not answering: the mode is unknown.",
    tone: "unknown",
    pulse: false,
    className: TONE_CLASS.unknown,
  };
}
