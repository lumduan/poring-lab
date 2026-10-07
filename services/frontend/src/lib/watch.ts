// What the console may send while a person only watches. Pure, unit tested with `node --test`
// (src/lib/watch.test.ts).
//
// Batt, 2026-10-07: in ASSIST every human event takes the mux's lease, and the bot lets go of
// whatever it holds (mux.py). Two things took leases nobody meant:
//  A) the tab sent release_all on every blur / hidden tab / screen paste, even with nothing held;
//  B) a mouse resting over the stream sends moves. "Watch only" forwards no input at all; the mux
//     stays ASSIST, and turning it off restores instant takeover.

import type { BrowserToBackend } from "./protocol.ts";

type MessageType = BrowserToBackend["type"];

/** Every message the browser can send, as input (reaches the mux) or control (never does).
 * A Record over the union: a new message type fails typecheck until it is classified here. */
const KIND: Record<MessageType, "input" | "control"> = {
  mouse_move: "input",
  mouse_button: "input",
  wheel: "input",
  key: "input",
  release_all: "input",
  clipboard_paste: "input",
  set_mode: "control",
  secret_input: "control",
  ping: "control",
  viewer_timing: "control",
};

export function isHumanInput(type: MessageType): boolean {
  return KIND[type] !== "control";
}

/** The backstop under the handlers: in watch-only mode, input never leaves the tab. A release_all
 * still may, because the console only sends one while this tab holds something (A), and letting
 * go is always safe (releases always pass the mux). Control messages (mode switch, secret
 * typing, ping, timing) always pass: watching never blocks switching to HUMAN. */
export function mayForward(type: MessageType, watchOnly: boolean): boolean {
  return !watchOnly || !isHumanInput(type) || type === "release_all";
}

/** Whether leaving the screen (blur, a hidden tab, a paste) must send release_all: only while this
 * tab holds a key or a mouse button (A). */
export function releaseNeeded(keys: ReadonlySet<string>, buttons: ReadonlySet<string>): boolean {
  return keys.size > 0 || buttons.size > 0;
}

/** The toggle's button text and its tooltip. */
export function watchToggle(on: boolean): { label: string; title: string } {
  return on
    ? {
        label: "Watch only ON",
        title:
          "Nothing you do on the screen is sent: no mouse, keys, wheel or paste. The mux mode is " +
          "unchanged, and switching to HUMAN still works. Click to take control again.",
      }
    : {
        label: "Watch only",
        title:
          "Watch without taking over: no input from this tab reaches Windows, so the bot keeps " +
          "control in ASSIST. Turn it off to get instant takeover back.",
      };
}
