"use client";

import { type ReactNode, type RefObject, useEffect, useRef, useState } from "react";

import { BUTTON_BITS, type ButtonName, buttonName, WheelAccumulator } from "@/lib/input";
import {
  type HeldKeys,
  isMacPlatform,
  keyDecision,
  type KeyStep,
  shouldForwardPhysical,
} from "@/lib/keys";
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
  /** Text the viewer pasted onto the remote screen (Cmd+V / Ctrl+V / Shift+Insert, ADR-0004). */
  onPaste?: (text: string) => void;
  /** Drawn over the viewport (not the image): e.g. the paste toast. Never takes pointer events. */
  overlay?: ReactNode;
  children?: ReactNode;
};

/** The remote screen and its input capture (a Proxmox-console-like view).
 *
 * Coordinates are normalized against the drawn image, never the letterbox around it. Every event
 * carries the id of the frame on screen when it happened, for reaction-latency measurement.
 *
 * Keyboard focus lives in a visually hidden <textarea>, not the canvas (the technique web RDP clients
 * such as Guacamole use): an editable element is what lets the browser perform a native paste, so
 * Cmd+V on the screen pastes the viewer's clipboard into Windows (ADR-0004). Every other key is
 * prevented and forwarded by KeyboardEvent.code, and the textarea never keeps any text. */
export default function StreamCanvas({
  videoRef,
  frameIdRef,
  frameSize,
  mode,
  held,
  send,
  onFocusChange,
  onPaste,
  overlay,
  children,
}: Props) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
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
    const input = inputRef.current;
    if (!box || !video || !input) return;
    const nav = navigator as Navigator & { userAgentData?: { platform?: string } };
    const isMac = isMacPlatform(nav.userAgentData?.platform || nav.platform || "");

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
    // The default action of a press would move focus to <body> right after we focus the capture
    // textarea (the canvas is not focusable); it would also start a text selection.
    const onMouseDown = (e: MouseEvent) => e.preventDefault();
    const onPointerDown = (e: PointerEvent) => {
      e.preventDefault();
      input.focus({ preventScroll: true });
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
    const onKeyDown = (e: KeyboardEvent) => {
      // "paste": let the browser paste natively (-> onPasteEvent); never send the chord itself.
      // "local": Cmd/Win combos and keys the backend can't inject stay with the viewer's OS.
      if (keyDecision(e, isMac) !== "forward") return;
      e.preventDefault(); // F-keys, Tab, Esc, Backspace, arrows... belong to the remote session
      if (e.repeat) return; // Windows runs its own key repeat for a held key
      sendKey({ code: e.code, action: "down" });
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.metaKey || !shouldForwardPhysical(e.code)) return;
      e.preventDefault();
      // HeldKeys drops stray ups, e.g. the V of a paste chord, which was never sent down.
      sendKey({ code: e.code, action: "up" });
    };
    const onPasteEvent = (e: ClipboardEvent) => {
      e.preventDefault(); // nothing lands in the textarea
      const text = e.clipboardData?.getData("text/plain") ?? "";
      input.value = "";
      // A forwarded Ctrl/Shift still held on Windows would turn the backend's Ctrl+V into
      // Ctrl+Shift+V (or worse): release everything first, exactly as a blur does.
      releaseAll();
      onPaste?.(text);
    };
    // The textarea must never accumulate text: block every insertion, and clear what can't be
    // blocked (IME composition text is not cancelable).
    const onBeforeInput = (e: Event) => e.preventDefault();
    const clearInput = () => {
      input.value = "";
    };
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
    box.addEventListener("mousedown", onMouseDown);
    box.addEventListener("wheel", onWheel, { passive: false });
    box.addEventListener("contextmenu", onContextMenu);
    input.addEventListener("keydown", onKeyDown);
    input.addEventListener("keyup", onKeyUp);
    input.addEventListener("paste", onPasteEvent);
    input.addEventListener("beforeinput", onBeforeInput);
    input.addEventListener("input", clearInput);
    input.addEventListener("compositionend", clearInput);
    input.addEventListener("focus", onFocus);
    input.addEventListener("blur", onBlur);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      if (raf) cancelAnimationFrame(raf);
      box.removeEventListener("pointermove", onPointerMove);
      box.removeEventListener("pointerdown", onPointerDown);
      box.removeEventListener("pointerup", onPointerUp);
      box.removeEventListener("mousedown", onMouseDown);
      box.removeEventListener("wheel", onWheel);
      box.removeEventListener("contextmenu", onContextMenu);
      input.removeEventListener("keydown", onKeyDown);
      input.removeEventListener("keyup", onKeyUp);
      input.removeEventListener("paste", onPasteEvent);
      input.removeEventListener("beforeinput", onBeforeInput);
      input.removeEventListener("input", clearInput);
      input.removeEventListener("compositionend", clearInput);
      input.removeEventListener("focus", onFocus);
      input.removeEventListener("blur", onBlur);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [videoRef, frameIdRef, held, send, onFocusChange, onPaste]);

  const rect = drawRect(viewport, frameSize, mode);
  const stageStyle =
    mode === "fit"
      ? { position: "absolute" as const, left: rect.x, top: rect.y, width: rect.width, height: rect.height }
      : { position: "relative" as const, width: frameSize.width, height: frameSize.height };

  return (
    <div
      ref={viewportRef}
      role="application"
      aria-label="Remote Windows desktop. Click to control it."
      className={`relative h-[calc(100vh-15rem)] min-h-64 w-full cursor-crosshair select-none rounded-md border border-neutral-800 bg-black outline-none focus-within:ring-2 focus-within:ring-sky-500 ${
        mode === "fit" ? "overflow-hidden" : "overflow-auto"
      }`}
    >
      {/* The keyboard capture element: focusable (Tab lands here) and labelled, but invisible,
          click-through and never holding text. See the component comment. */}
      <textarea
        ref={inputRef}
        aria-label="Keyboard input for the remote desktop. Command+V pastes into Windows."
        rows={1}
        autoComplete="off"
        autoCorrect="off"
        autoCapitalize="off"
        spellCheck={false}
        className="pointer-events-none absolute top-0 left-0 m-0 h-px w-px resize-none overflow-hidden border-0 p-0 text-transparent caret-transparent opacity-0 outline-none"
      />
      <div style={stageStyle}>
        <canvas
          ref={videoRef}
          width={frameSize.width}
          height={frameSize.height}
          className="block h-full w-full"
        />
        {children}
      </div>
      {overlay && (
        <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center">
          {overlay}
        </div>
      )}
    </div>
  );
}
