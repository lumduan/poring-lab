// The /flows studio's colours, as MatPilot's /blocks has them (Batt 2026-11-09: "use matpilot's
// colour theme", so learners who know matpilot.org/blocks recognise every category). Pure data, no
// Blockly: the block editor (components/flows/BlockEditor.tsx) builds its two Blockly themes from
// these, and theme.test.ts checks them in node.
//
// The category colours, the block / category style names, the font and the light / dark component
// styles are copied from MatPilot (https://github.com/lumduan/matpilot at commit d639909,
// src/lib/blocks/colours.ts and src/lib/blocks/theme.ts; THIRD_PARTY.md), under its licence:
//
//   MIT License
//
//   Copyright (c) 2026 Sarat Sonsuk
//
//   Permission is hereby granted, free of charge, to any person obtaining a copy
//   of this software and associated documentation files (the "Software"), to deal
//   in the Software without restriction, including without limitation the rights
//   to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
//   copies of the Software, and to permit persons to whom the Software is
//   furnished to do so, subject to the following conditions:
//
//   The above copyright notice and this permission notice shall be included in all
//   copies or substantial portions of the Software.
//
//   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
//   IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
//   FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
//   AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
//   LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
//   OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
//   SOFTWARE.
//
// OUR part is the mapping of poring-lab's block types onto MatPilot's categories (BLOCK_STYLE and
// the toolbox in blockdefs.ts): walking and hunting are Movement, the NPC / item / window actions
// are output blue ("Actions"), waits and loops are Flow ("Control"), the model blocks are Sensors.

/** MatPilot's block category colours: each is dark enough for white block text (>= 4.5:1). */
export const CATEGORY_COLOURS = {
  setup: "#4b5563",
  output: "#1d4ed8",
  input: "#0e7490",
  flow: "#b45309",
  data: "#15803d",
  variables: "#be185d",
  sharedVariables: "#e10089",
  other: "#6d28d9",
  movement: "#a21caf",
  light: "#7e22ce",
  sound: "#9f1239",
  controller: "#3f6212",
  functions: "#4338ca",
} as const;

export type BlockStyle = { colourPrimary: string; hat?: "cap" };

/** Blockly block styles, keyed as MatPilot's (start / hat blocks get the round cap). */
export const BLOCK_STYLES: Record<string, BlockStyle> = {
  mp_setup_blocks: { colourPrimary: CATEGORY_COLOURS.setup },
  mp_start_blocks: { colourPrimary: CATEGORY_COLOURS.flow, hat: "cap" },
  mp_output_blocks: { colourPrimary: CATEGORY_COLOURS.output },
  mp_input_blocks: { colourPrimary: CATEGORY_COLOURS.input },
  mp_other_blocks: { colourPrimary: CATEGORY_COLOURS.other },
  mp_movement_blocks: { colourPrimary: CATEGORY_COLOURS.movement },
  mp_motor_blocks: { colourPrimary: CATEGORY_COLOURS.output },
  mp_light_blocks: { colourPrimary: CATEGORY_COLOURS.light },
  mp_sound_blocks: { colourPrimary: CATEGORY_COLOURS.sound },
  mp_sensor_blocks: { colourPrimary: CATEGORY_COLOURS.input },
  mp_controller_blocks: { colourPrimary: CATEGORY_COLOURS.controller },
  mp_function_blocks: { colourPrimary: CATEGORY_COLOURS.functions },
  mp_function_define_blocks: { colourPrimary: CATEGORY_COLOURS.functions, hat: "cap" },
  loop_blocks: { colourPrimary: CATEGORY_COLOURS.flow },
  logic_blocks: { colourPrimary: CATEGORY_COLOURS.flow },
  math_blocks: { colourPrimary: CATEGORY_COLOURS.data },
  text_blocks: { colourPrimary: CATEGORY_COLOURS.data },
  variable_blocks: { colourPrimary: CATEGORY_COLOURS.variables },
  mp_shared_variable_blocks: { colourPrimary: CATEGORY_COLOURS.sharedVariables },
};

/** Blockly category styles (the toolbox rows), keyed as MatPilot's. */
export const CATEGORY_STYLES: Record<string, { colour: string }> = {
  mp_setup_category: { colour: CATEGORY_COLOURS.setup },
  mp_output_category: { colour: CATEGORY_COLOURS.output },
  mp_input_category: { colour: CATEGORY_COLOURS.input },
  loop_category: { colour: CATEGORY_COLOURS.flow },
  math_category: { colour: CATEGORY_COLOURS.data },
  variable_category: { colour: CATEGORY_COLOURS.variables },
  mp_other_category: { colour: CATEGORY_COLOURS.other },
  mp_movement_category: { colour: CATEGORY_COLOURS.movement },
  mp_motor_category: { colour: CATEGORY_COLOURS.output },
  mp_light_category: { colour: CATEGORY_COLOURS.light },
  mp_sound_category: { colour: CATEGORY_COLOURS.sound },
  mp_sensor_category: { colour: CATEGORY_COLOURS.input },
  mp_controller_category: { colour: CATEGORY_COLOURS.controller },
  mp_function_category: { colour: CATEGORY_COLOURS.functions },
};

export const FONT_STYLE = { family: 'system-ui, -apple-system, "Segoe UI", sans-serif', size: 12 };

export type ComponentStyles = {
  workspaceBackgroundColour: string;
  toolboxBackgroundColour: string;
  toolboxForegroundColour: string;
  flyoutBackgroundColour: string;
  flyoutForegroundColour: string;
  flyoutOpacity: number;
  scrollbarColour: string;
  insertionMarkerColour: string;
  insertionMarkerOpacity: number;
};

/** The workspace around the blocks; the block colours are the same in both. */
export const COMPONENT_STYLES: { light: ComponentStyles; dark: ComponentStyles } = {
  light: {
    workspaceBackgroundColour: "#f6f7f9",
    toolboxBackgroundColour: "#ffffff",
    toolboxForegroundColour: "#1b1f24",
    flyoutBackgroundColour: "#e9edf1",
    flyoutForegroundColour: "#1b1f24",
    flyoutOpacity: 1,
    scrollbarColour: "#b9c1ca",
    insertionMarkerColour: "#000000",
    insertionMarkerOpacity: 0.2,
  },
  dark: {
    workspaceBackgroundColour: "#111418",
    toolboxBackgroundColour: "#1a1f25",
    toolboxForegroundColour: "#e6e9ed",
    flyoutBackgroundColour: "#20262d",
    flyoutForegroundColour: "#e6e9ed",
    flyoutOpacity: 1,
    scrollbarColour: "#3d4650",
    insertionMarkerColour: "#ffffff",
    insertionMarkerOpacity: 0.3,
  },
};

/** Blockly's inject options for the studio (MatPilot's): the wheel SCROLLS, never zooms. */
export const INJECT = {
  renderer: "zelos",
  sounds: false,
  trashcan: true,
  zoom: { controls: true, wheel: false, startScale: 0.75, maxScale: 2, minScale: 0.4 },
  move: { scrollbars: true, drag: true, wheel: true },
  grid: { spacing: 24, length: 2, colour: "rgba(128, 128, 128, 0.25)", snap: false },
  media: "/blockly-media/", // self-hosted (no CDN: the CSP allows this origin only)
} as const;

/** Our block types onto MatPilot's styles (only words, colours and categories change; the
 * types, fields and the IR are unchanged). The run-time hunt type is Movement too. */
export const BLOCK_STYLE: Record<string, string> = {
  pl_walk_to: "mp_movement_blocks",
  pl_hunt: "mp_movement_blocks",
  pl_exit_walk: "mp_movement_blocks",
  pl_exit_npc: "mp_movement_blocks",
  pl_exit_item: "mp_movement_blocks",
  pl_talk_npc: "mp_output_blocks",
  pl_choose_menu: "mp_output_blocks",
  pl_use_item: "mp_output_blocks",
  pl_open_window: "mp_output_blocks",
  pl_wait: "loop_blocks",
  pl_wait_until: "loop_blocks",
  pl_repeat: "loop_blocks",
  pl_while: "loop_blocks",
  pl_if: "logic_blocks",
  pl_stop: "loop_blocks",
  pl_break: "loop_blocks",
  pl_continue: "loop_blocks",
  pl_compare: "logic_blocks",
  pl_logic: "logic_blocks",
  pl_not: "logic_blocks",
  pl_expr: "math_blocks",
  pl_set: "variable_blocks",
  pl_call: "mp_function_blocks",
  pl_main: "mp_start_blocks",
  pl_event: "mp_start_blocks",
  pl_extend: "mp_start_blocks",
  pl_disable: "mp_start_blocks",
  pl_detect_sees: "mp_sensor_blocks",
  pl_detect_count: "mp_sensor_blocks",
  pl_action: "mp_other_blocks",
  pl_do: "mp_other_blocks",
  pl_raw: "mp_setup_blocks",
  pl_raw_expr: "mp_setup_blocks",
};

/** WCAG contrast ratio of two #rrggbb colours (the theme test's 4.5:1 check). */
export function contrast(a: string, b: string): number {
  const lum = (hex: string) => {
    const [r, g, bl] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
  };
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
