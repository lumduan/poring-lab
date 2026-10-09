// Scroll boxes that never jump (Batt 2026-10-09 14:24): the HUD's decision log and the Packet
// timeline have a FIXED height and their own scroll. New lines never move the box, and they move
// what the reader sees only when the reader is already at the newest line. Pure, unit tested with
// `node --test` (src/lib/scroll.test.ts); the components apply the numbers.

/** Within this many px of an edge counts as AT it (sub-pixel layout, zoom rounding). */
export const AT_EDGE_PX = 4;

export type ScrollBox = { scrollTop: number; scrollHeight: number; clientHeight: number };

/** Newest line at the BOTTOM (the HUD log): the reader is at it, so it follows new lines. */
export function atBottom(box: ScrollBox, slack = AT_EDGE_PX): boolean {
  return box.scrollHeight - box.scrollTop - box.clientHeight <= slack;
}

/** Newest line at the TOP (the packet list): the reader is at it, so new rows simply appear. */
export function atTop(box: Pick<ScrollBox, "scrollTop">, slack = AT_EDGE_PX): boolean {
  return box.scrollTop <= slack;
}

/** The reader scrolled away from the newest rows: the scrollTop that keeps the row they look at
 * (`anchorOffset` px below the box's top edge when they last scrolled) where it was, after rows
 * were added above it (its offsetTop is now `anchorTop`). */
export function keepAnchor(anchorTop: number, anchorOffset: number): number {
  return Math.max(0, anchorTop - anchorOffset);
}
