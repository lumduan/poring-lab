"use client";

// A modal dialog (the browser's own <dialog>): it opens when rendered, keeps keyboard focus inside,
// and closes with ×, Escape, or a click outside it. Render it only while it is open.
//
// Ported from MatPilot (MIT), src/components/Dialog.tsx at 4022c87 (https://github.com/lumduan/matpilot,
// Copyright (c) 2026 Sarat Sonsuk; the licence text is in flowfile.css and THIRD_PARTY.md).
import "./flowfile.css";

import { type ReactNode, useEffect, useId, useRef } from "react";

export default function Dialog({ title, onClose, children, testId }: { title: string; onClose: () => void; children: ReactNode; testId?: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      className="dialog"
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(e) => {
        // a click on the backdrop lands on the <dialog> itself, outside its content
        if (e.target === e.currentTarget) e.currentTarget.close();
      }}
      data-testid={testId}
    >
      <div className="dialog-inner">
        <div className="dialog-header">
          <h2 id={titleId}>{title}</h2>
          <button type="button" className="icon-button" onClick={() => ref.current?.close()} title="Close">
            <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
              <path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
            <span className="visually-hidden">Close</span>
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}
