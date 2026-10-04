"use client";

import { useRef, useState } from "react";

import {
  applyDrag,
  type Cls,
  type EditBox,
  hitTest,
  newBox,
  type Part,
  toImage,
} from "@/lib/qa_edit";

type Props = {
  boxes: EditBox[];
  size: [number, number];
  selected: number | null;
  newClass: Cls;
  onChange: (boxes: EditBox[]) => void;
  onSelect: (index: number | null) => void;
};

type Drag =
  | { kind: "edit"; index: number; part: Part; x0: number; y0: number; start: EditBox }
  | { kind: "add"; x0: number; y0: number; x: number; y: number };

const COLOURS: Record<Cls, string> = { player: "#fbbf24", monster: "#38bdf8", npc: "#4ade80" };

/** The B6 hand-check layer (Post-S2 round Part D): drag a box to move it, a corner to resize it,
 * empty space to add one (class: keys 1/2/3 in the viewer). Pure geometry lives in lib/qa_edit. */
export default function QaEditor({ boxes, size, selected, newClass, onChange, onSelect }: Props) {
  const ref = useRef<SVGSVGElement>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [w, h] = size;

  const point = (e: React.PointerEvent): [number, number] => {
    const rect = ref.current?.getBoundingClientRect();
    return rect ? toImage(e.clientX, e.clientY, rect, size) : [0, 0];
  };

  const onDown = (e: React.PointerEvent) => {
    const [x, y] = point(e);
    (e.target as Element).setPointerCapture?.(e.pointerId);
    const hit = hitTest(boxes, x, y);
    if (hit) {
      onSelect(hit.index);
      setDrag({ kind: "edit", index: hit.index, part: hit.part, x0: x, y0: y, start: boxes[hit.index] });
    } else {
      onSelect(null);
      setDrag({ kind: "add", x0: x, y0: y, x, y });
    }
  };

  const onMove = (e: React.PointerEvent) => {
    if (!drag) return;
    const [x, y] = point(e);
    if (drag.kind === "add") {
      setDrag({ ...drag, x, y });
      return;
    }
    const next = boxes.slice();
    next[drag.index] = applyDrag(drag.start, drag.part, x - drag.x0, y - drag.y0, size);
    onChange(next);
  };

  const onUp = () => {
    if (drag?.kind === "add") {
      const b = newBox(drag.x0, drag.y0, drag.x, drag.y, newClass, size);
      if (b) {
        onChange([...boxes, b]);
        onSelect(boxes.length);
      }
    }
    setDrag(null);
  };

  const preview = drag?.kind === "add" ? newBox(drag.x0, drag.y0, drag.x, drag.y, newClass, size) : null;
  return (
    <svg
      ref={ref}
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      className="absolute inset-0 h-full w-full cursor-crosshair touch-none select-none"
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerCancel={() => setDrag(null)}
    >
      {boxes.map((b, i) => (
        <g key={i}>
          <rect
            x={b.x1}
            y={b.y1}
            width={b.x2 - b.x1}
            height={b.y2 - b.y1}
            fill={i === selected ? "rgba(255,255,255,0.08)" : "none"}
            stroke={COLOURS[b.cls]}
            strokeWidth={i === selected ? 3 : 2}
            vectorEffect="non-scaling-stroke"
          />
          <text x={b.x1 + 2} y={b.y1 - 3} fill={COLOURS[b.cls]} fontSize={12} fontFamily="ui-monospace, monospace">
            {b.cls}
            {b.gid === null ? " +" : ` #${b.gid}`}
          </text>
          {i === selected &&
            [
              [b.x1, b.y1],
              [b.x2, b.y1],
              [b.x1, b.y2],
              [b.x2, b.y2],
            ].map(([cx, cy], k) => <rect key={k} x={cx - 4} y={cy - 4} width={8} height={8} fill="#fff" />)}
        </g>
      ))}
      {preview && (
        <rect
          x={preview.x1}
          y={preview.y1}
          width={preview.x2 - preview.x1}
          height={preview.y2 - preview.y1}
          fill="none"
          stroke={COLOURS[newClass]}
          strokeDasharray="6 4"
          strokeWidth={2}
          vectorEffect="non-scaling-stroke"
        />
      )}
    </svg>
  );
}
