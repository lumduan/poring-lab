/**
 * The Settings page's "Who may play a Run" (Batt 2026-11-19, ADR-0020 Amendment R): the mode and
 * the characters remembered on this install (GET / PUT /settings/run-identity, POST
 * /settings/run-identity/remember; the backend's routes_identity.py). Pure helpers, no React.
 */

export type RunIdentityMode = "any" | "known" | "mine";

export type RememberedCharacter = {
  id: string;
  name: string;
  remembered: string; // ISO time (UTC)
  w: number;
  h: number;
  rgb: string; // base64 of h*w*3 bytes, row by row: the name line the bot compares
};

export type RunIdentityView = {
  store: "ok" | "default" | "unreadable";
  problem: string | null;
  revision: number;
  mode: RunIdentityMode;
  default_mode: RunIdentityMode;
  modes: RunIdentityMode[];
  characters: RememberedCharacter[];
  max_characters: number;
  max_name: number;
  helper_alive: boolean;
  saved?: boolean;
  changes?: { action: string; text: string }[];
  remembered?: string;
};

export const MODE_CHOICES: { mode: RunIdentityMode; title: string; help: string }[] = [
  {
    mode: "any",
    title: "Any character (the default)",
    help: "A Run does not check who plays: any name, any job. Each learner makes their own character.",
  },
  {
    mode: "known",
    title: "Only the characters remembered here",
    help:
      "The character's name line must match one remembered below. A character of another server " +
      "(or anyone not remembered) is refused at the first line of the check, before any key is pressed.",
  },
  {
    mode: "mine",
    title: "Only the lab's own character (advanced)",
    help:
      "The lab's setup: the name and the job against the reference pictures crusader.py cut. " +
      "An install without them refuses every Run.",
  },
];

/** The name a person types (the bot compares the name line's PICTURE, so any script works). */
export function nameProblem(name: string, maxName: number, taken: string[]): string | null {
  if (!name.trim()) return "Type the character's name.";
  if (name !== name.trim()) return "No spaces at the start or the end.";
  if ([...name].length > maxName) return `At most ${maxName} characters.`;
  if (/\p{C}/u.test(name)) return "The name holds a control character.";
  const low = name.toLocaleLowerCase();
  if (taken.some((t) => t.toLocaleLowerCase() === low)) return "That name is in the list already.";
  return null;
}

/** The name line's RGB bytes as canvas pixels (RGBA), or null when they do not fit w x h. */
export function plateRgba(rgb: string, w: number, h: number): Uint8ClampedArray | null {
  let bin: string;
  try {
    bin = atob(rgb);
  } catch {
    return null;
  }
  if (bin.length !== w * h * 3) return null;
  const out = new Uint8ClampedArray(w * h * 4);
  for (let i = 0, j = 0; i < bin.length; i += 3, j += 4) {
    out[j] = bin.charCodeAt(i);
    out[j + 1] = bin.charCodeAt(i + 1);
    out[j + 2] = bin.charCodeAt(i + 2);
    out[j + 3] = 255;
  }
  return out;
}

const REASONS: Record<string, string> = {
  helper_not_running: "The Run helper is not running (poring-lab-flowrun.service), so nothing can read the game screen.",
  helper_busy: "The Run helper has a request waiting: try again in a moment.",
  plate_timeout: "The Run helper did not answer in time: nothing was remembered.",
  plate_failed: "The name line could not be read",
  already_remembered: "This character is remembered already, as",
  name_taken: "That name is in the list already.",
  too_many_characters: "The list is full.",
  revision_conflict: "The settings changed in another tab: the page was reloaded, try again.",
  store_unreadable: "The saved file does not parse: choose a mode and Save first (with no character).",
  store_unreadable_characters: "The saved file does not parse: save with no character first.",
  unknown_character: "A character in the page is no longer in the list: reload the page.",
  character_twice: "A character is in the page twice: reload the page.",
  settings_store_missing: "The settings folder is not mounted into the backend.",
  read_back_failed: "The file did not read back the same: nothing is trusted, reload the page.",
  name_missing: "Type the character's name.",
  name_empty: "Type the character's name.",
  name_spaces_at_ends: "No spaces at the start or the end.",
  name_too_long: "The name is too long.",
  name_control_character: "The name holds a control character.",
  csrf_invalid: "The page's token expired: reload the page.",
  lab_host_peer: "Settings cannot be changed from the lab computer itself (its programs include the bot): use another computer on the LAN.",
  windows_host_peer: "Settings cannot be changed from the Windows game PC (the bot drives it): use another computer on the LAN.",
  rate_limited: "Too many saves in a minute: wait a moment.",
};

/** A refusal in words: the reason, with its detail where the backend gave one. */
export function identityReasonText(reason: string, detail?: unknown): string {
  const base = REASONS[reason] ?? `Refused (${reason}).`;
  if (reason === "plate_failed" && detail) return `${base}: ${String(detail)}.`;
  if (reason === "already_remembered" && detail) return `${base} “${String(detail)}”.`;
  if (reason === "too_many_characters" && detail) return `The list is full (at most ${String(detail)}).`;
  return reason === "plate_failed" ? `${base}.` : base;
}
