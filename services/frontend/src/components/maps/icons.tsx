// The Maps page's small icons, inline SVG (round 2, 2026-11-10: the media glyphs U+23EE and
// U+23F8 rendered as empty boxes in Chromium on Linux, which lacks them). Each is aria-hidden: its
// button keeps its words for screen readers. The folder, save and play paths are MatPilot's
// (src/components/blocks/BlocksApp.tsx at commit d639909; MIT License, Copyright (c) 2026 Sarat
// Sonsuk; the licence text is in studio.css and THIRD_PARTY.md), as /flows' FlowsApp.tsx has them.

type P = { className?: string };
const box = { viewBox: "0 0 16 16", width: 16, height: 16, "aria-hidden": true, focusable: false } as const;

export function FolderIcon({ className = "button-icon" }: P) {
  return (
    <svg className={className} {...box}>
      <path d="M1.75 4.25v8a1 1 0 0 0 1 1h10.5a1 1 0 0 0 1-1v-6a1 1 0 0 0-1-1H8L6.5 3.25H2.75a1 1 0 0 0-1 1z" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

export function SaveIcon({ className = "button-icon" }: P) {
  return (
    <svg className={className} {...box}>
      <path d="M8 2v7.5M4.75 6.5 8 9.75l3.25-3.25M2.5 10.5v2a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-2" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function PlayIcon({ className = "button-icon" }: P) {
  return (
    <svg className={className} {...box}>
      <path d="M5 3.5v9l7.5-4.5z" fill="currentColor" />
    </svg>
  );
}

export function PauseIcon({ className = "button-icon" }: P) {
  return (
    <svg className={className} {...box}>
      <path d="M4.5 3h2.5v10H4.5zM9 3h2.5v10H9z" fill="currentColor" />
    </svg>
  );
}

/** Back to the start: a bar, then a triangle pointing at it. */
export function ToStartIcon({ className = "button-icon" }: P) {
  return (
    <svg className={className} {...box}>
      <path d="M3 3h2v10H3zM13 3.5v9L6 8z" fill="currentColor" />
    </svg>
  );
}

export function StepBackIcon({ className = "button-icon" }: P) {
  return (
    <svg className={className} {...box}>
      <path d="M11 3.5v9L4 8z" fill="currentColor" />
    </svg>
  );
}

export function StepIcon({ className = "button-icon" }: P) {
  return (
    <svg className={className} {...box}>
      <path d="M5 3.5v9L12 8z" fill="currentColor" />
    </svg>
  );
}

export function CloseIcon({ className }: P) {
  return (
    <svg className={className} {...box}>
      <path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function CaretIcon({ className = "button-icon" }: P) {
  return (
    <svg className={className} {...box} width={10} height={10}>
      <path d="M3.5 6l4.5 4.5L12.5 6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
