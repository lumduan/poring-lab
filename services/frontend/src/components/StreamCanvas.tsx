"use client";

import { type ReactNode, type RefObject, useEffect, useRef } from "react";

import {
  buttonName,
  normalizePointer,
  shouldPreventDefault,
  WheelAccumulator,
} from "@/lib/input";
import { browserNowNs, type BrowserToBackend, type MouseButton } from "@/lib/protocol";

type Props = {
  videoRef: RefObject<HTMLCanvasElement | null>;
  frameIdRef: RefObject<number>;
  send: (message: BrowserToBackend) => void;
  children?: ReactNode;
};

// PointerEvent.buttons bit for each PointerEvent.button value (left, middle, right).
const BUTTON_BITS: Record<MouseButton["button"], number> = { left: 1, middle: 4, right: 2 };

/** The video canvas plus input capture. Every event carries the id of the frame on screen when
 * it happened, so human reaction latency can be measured later. */
export default function StreamCanvas({ videoRef, frameIdRef, send, children }: Props) {
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const box = boxRef.current;
    const video = videoRef.current;
    if (!box || !video) return;

    const stamp = () => ({ t_mono_ns: browserNowNs(), frame_id: frameIdRef.current });
    const at = (e: MouseEvent) => normalizePointer(e, video.getBoundingClientRect());
    const wheel = new WheelAccumulator();
    let pendingMove: { x: number; y: number } | null = null;
    let raf = 0;

    // Moves are coalesced to one per animation frame (~16 ms). Anything else flushes a pending
    // move first, so the backend always sees events in the order they happened.
    const flushMove = () => {
      raf = 0;
      if (pendingMove) send({ type: "mouse_move", ...stamp(), ...pendingMove });
      pendingMove = null;
    };
    const flushNow = () => {
      if (raf) cancelAnimationFrame(raf);
      flushMove();
    };
    const sendButton = (e: PointerEvent, action: "down" | "up") => {
      const button = buttonName(e.button);
      if (!button) return;
      flushNow();
      send({ type: "mouse_button", ...stamp(), button, action, ...at(e) });
    };

    const onPointerMove = (e: PointerEvent) => {
      if (e.button >= 0) {
        // A second button pressed/released while another is held arrives as a move ("chord").
        const button = buttonName(e.button);
        if (button) sendButton(e, e.buttons & BUTTON_BITS[button] ? "down" : "up");
        return;
      }
      pendingMove = at(e);
      if (!raf) raf = requestAnimationFrame(flushMove);
    };
    const onPointerDown = (e: PointerEvent) => {
      e.preventDefault();
      box.focus();
      box.setPointerCapture(e.pointerId); // the matching "up" arrives even outside the box
      sendButton(e, "down");
    };
    const onPointerUp = (e: PointerEvent) => {
      e.preventDefault();
      sendButton(e, "up");
    };
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const dy = wheel.push(e);
      if (dy !== 0) send({ type: "wheel", ...stamp(), dy });
    };
    const onKey = (action: "down" | "up") => (e: KeyboardEvent) => {
      if (shouldPreventDefault(e)) e.preventDefault();
      if (e.repeat || !e.code) return; // Windows runs its own key repeat for a held key
      flushNow();
      send({ type: "key", ...stamp(), code: e.code, action });
    };
    const onKeyDown = onKey("down");
    const onKeyUp = onKey("up");
    const onBlur = () => {
      flushNow();
      send({ type: "release_all", ...stamp() });
    };
    const onContextMenu = (e: Event) => e.preventDefault(); // right-click belongs to the game

    box.addEventListener("pointermove", onPointerMove);
    box.addEventListener("pointerdown", onPointerDown);
    box.addEventListener("pointerup", onPointerUp);
    box.addEventListener("wheel", onWheel, { passive: false });
    box.addEventListener("keydown", onKeyDown);
    box.addEventListener("keyup", onKeyUp);
    box.addEventListener("blur", onBlur);
    box.addEventListener("contextmenu", onContextMenu);
    return () => {
      if (raf) cancelAnimationFrame(raf);
      box.removeEventListener("pointermove", onPointerMove);
      box.removeEventListener("pointerdown", onPointerDown);
      box.removeEventListener("pointerup", onPointerUp);
      box.removeEventListener("wheel", onWheel);
      box.removeEventListener("keydown", onKeyDown);
      box.removeEventListener("keyup", onKeyUp);
      box.removeEventListener("blur", onBlur);
      box.removeEventListener("contextmenu", onContextMenu);
    };
  }, [videoRef, frameIdRef, send]);

  return (
    <div
      ref={boxRef}
      tabIndex={0}
      role="application"
      aria-label="Remote game screen. Click to control it."
      className="relative cursor-crosshair select-none overflow-hidden rounded-md border border-neutral-800 bg-black outline-none focus:border-sky-500"
    >
      <canvas ref={videoRef} width={1280} height={720} className="block h-auto w-full" />
      {children}
    </div>
  );
}
