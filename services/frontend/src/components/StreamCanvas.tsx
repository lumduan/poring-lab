"use client";

import { type ReactNode, type RefObject, useEffect, useRef, useState } from "react";

import { BUTTON_BITS, type ButtonName, buttonName, WheelAccumulator } from "@/lib/input";
import { type HeldKeys, type KeyStep, shouldForwardPhysical } from "@/lib/keys";
import { browserNowNs, type BrowserToBackend } from "@/lib/protocol";
import { drawRect, normalizePoint, type Size, type ViewMode } from "@/lib/view";

type Props = {
  videoRef: RefObject<HTMLCanvasElement | null>;
  frameIdRef: RefObject<number>;
  frameSize: Size;
  mode: ViewMode;
  held: HeldKeys;
  send: (message: BrowserToBackend) => void;
  onFocusChange?: (focused: boolean) => void;
  children?: ReactNode;
};

/** The remote screen and its input capture (a Proxmox-console-like view).
 *
 * Coordinates are normalized against the drawn image, never the letterbox around it. Every event
 * carries the id of the frame on screen when it happened, for reaction-latency measurement. */
export default function StreamCanvas({
  videoRef,
  frameIdRef,
  frameSize,
  mode,
  held,
  send,
  onFocusChange,
  children,
}: Props) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [viewport, setViewport] = useState<Size>({ width: 0, height: 0 });

  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setViewport({ width, height });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const box = viewportRef.current;
    const video = videoRef.current;
    if (!box || !video) return;

    const stamp = () => ({ t_mono_ns: browserNowNs(), frame_id: frameIdRef.current });
    const at = (e: MouseEvent) => {
      const r = video.getBoundingClientRect();
      return normalizePoint(e.clientX, e.clientY, { x: r.left, y: r.top, width: r.width, height: r.height });
    };
    const wheel = new WheelAccumulator();
    const buttons = new Set<ButtonName>();
    let pendingMove: { x: number; y: number } | null = null;
    let raf = 0;

    // Moves are coalesced to one per animation frame (~16 ms); anything else flushes a pending
    // move first so the backend sees events in the order they happened.
    const flushMove = () => {
      raf = 0;
      if (pendingMove) send({ type: "mouse_move", ...stamp(), ...pendingMove });
      pendingMove = null;
    };
    const flushNow = () => {
      if (raf) cancelAnimationFrame(raf);
      flushMove();
    };
    const sendKey = (step: KeyStep) => {
      if (!held.apply(step)) return;
      flushNow();
      send({ type: "key", ...stamp(), code: step.code, action: step.action });
    };
    const releaseAll = () => {
      flushNow();
      held.clear();
      buttons.clear();
      send({ type: "release_all", ...stamp() });
    };
    const buttonDown = (e: PointerEvent, button: ButtonName) => {
      const p = at(e);
      if (!p.inside) return; // presses in the letterbox are not clicks on the remote screen
      flushNow();
      buttons.add(button);
      send({ type: "mouse_button", ...stamp(), button, action: "down", x: p.x, y: p.y });
    };
    const buttonUp = (e: PointerEvent, button: ButtonName) => {
      if (!buttons.delete(button)) return; // only release what we pressed
      const p = at(e);
      flushNow();
      send({ type: "mouse_button", ...stamp(), button, action: "up", x: p.x, y: p.y });
    };

    const onPointerMove = (e: PointerEvent) => {
      if (e.button >= 0) {
        const button = buttonName(e.button);
        if (button) {
          if (e.buttons & BUTTON_BITS[button]) buttonDown(e, button);
          else buttonUp(e, button);
        }
        return;
      }
      const p = at(e);
      // Outside the image only drags continue (clamped to the edge); hovering sends nothing.
      if (!p.inside && buttons.size === 0) return;
      pendingMove = { x: p.x, y: p.y };
      if (!raf) raf = requestAnimationFrame(flushMove);
    };
    const onPointerDown = (e: PointerEvent) => {
      e.preventDefault();
      box.focus();
      const button = buttonName(e.button);
      if (!button) return;
      box.setPointerCapture(e.pointerId); // the matching up arrives even outside the viewport
      buttonDown(e, button);
    };
    const onPointerUp = (e: PointerEvent) => {
      e.preventDefault();
      const button = buttonName(e.button);
      if (button) buttonUp(e, button);
    };
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      if (!at(e).inside) return;
      const dy = wheel.push(e);
      if (dy !== 0) {
        flushNow();
        send({ type: "wheel", ...stamp(), dy });
      }
    };
    const onKey = (action: "down" | "up") => (e: KeyboardEvent) => {
      if (e.metaKey) return; // Cmd/Win combos stay with the viewer's own OS
      if (!shouldForwardPhysical(e.code)) return;
      e.preventDefault(); // F-keys, Tab, Esc, Backspace, arrows... belong to the remote session
      if (e.repeat) return; // Windows runs its own key repeat for a held key
      sendKey({ code: e.code, action });
    };
    const onKeyDown = onKey("down");
    const onKeyUp = onKey("up");
    const onVisibility = () => {
      if (document.hidden) releaseAll();
    };
    const onFocus = () => onFocusChange?.(true);
    const onBlur = () => {
      releaseAll();
      onFocusChange?.(false);
    };
    const onContextMenu = (e: Event) => e.preventDefault(); // right-click belongs to the game

    box.addEventListener("pointermove", onPointerMove);
    box.addEventListener("pointerdown", onPointerDown);
    box.addEventListener("pointerup", onPointerUp);
    box.addEventListener("wheel", onWheel, { passive: false });
    box.addEventListener("keydown", onKeyDown);
    box.addEventListener("keyup", onKeyUp);
    box.addEventListener("focus", onFocus);
    box.addEventListener("blur", onBlur);
    box.addEventListener("contextmenu", onContextMenu);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      if (raf) cancelAnimationFrame(raf);
      box.removeEventListener("pointermove", onPointerMove);
      box.removeEventListener("pointerdown", onPointerDown);
      box.removeEventListener("pointerup", onPointerUp);
      box.removeEventListener("wheel", onWheel);
      box.removeEventListener("keydown", onKeyDown);
      box.removeEventListener("keyup", onKeyUp);
      box.removeEventListener("focus", onFocus);
      box.removeEventListener("blur", onBlur);
      box.removeEventListener("contextmenu", onContextMenu);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [videoRef, frameIdRef, held, send, onFocusChange]);

  const rect = drawRect(viewport, frameSize, mode);
  const stageStyle =
    mode === "fit"
      ? { position: "absolute" as const, left: rect.x, top: rect.y, width: rect.width, height: rect.height }
      : { position: "relative" as const, width: frameSize.width, height: frameSize.height };

  return (
    <div
      ref={viewportRef}
      tabIndex={0}
      role="application"
      aria-label="Remote Windows desktop. Click to control it."
      className={`relative h-[calc(100vh-15rem)] min-h-64 w-full cursor-crosshair select-none rounded-md border border-neutral-800 bg-black outline-none focus:ring-2 focus:ring-sky-500 ${
        mode === "fit" ? "overflow-hidden" : "overflow-auto"
      }`}
    >
      <div style={stageStyle}>
        <canvas
          ref={videoRef}
          width={frameSize.width}
          height={frameSize.height}
          className="block h-full w-full"
        />
        {children}
      </div>
    </div>
  );
}
