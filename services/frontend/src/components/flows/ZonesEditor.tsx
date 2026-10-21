"use client";

// The ZONES layer of a map node (docs/planning/blocks-from-hunt-flow.md section 3, B2; ADR-0020
// Amendment A 4, DRAFT). SIMULATE only: nothing here reaches the bot, the mux or any input path.
// - Draw on the map's walk grid: a no-cross line (click cells, double-click to end) or a no-enter
//   area (click corners, close on the first). Each item asks for its id and note.
// - Check: the backend runs the RUNNER'S OWN loader on the YAML text and returns its error as it
//   is, the sha256, the cells each item closes and the search-area preview; the browser draws them
//   and computes no cell itself.
// - Export only (Batt D6, 2026-10-21): the YAML, its sha256 and the diff against
//   config/map_zones/<map>.yaml; a PERSON commits the file and git is the review record.
// - reviewed_by names a person and is NEVER filled by the editor (the file's own review is shown
//   as a reference only). The agent never approves a zone.
// Text only: every value from a file or the backend is rendered as React text.
import { useEffect, useMemo, useState } from "react";

import PathMap, { type ZonesLayer } from "@/components/flows/PathMap";
import { ApiError, type FlowsApi, type WorldSource } from "@/lib/flow/api";
import type { ZonesRef } from "@/lib/flow/ir";
import {
  addItem,
  addPoint,
  type Cell,
  checkLines,
  commentLines,
  type Draft,
  emptyReview,
  emptyZones,
  finished,
  modelFrom,
  removeItem,
  type Review,
  startDraft,
  suggestId,
  undoPoint,
  type ZoneKind,
  type ZonesCheck,
  type ZonesFile,
  type ZonesModel,
  zonesYaml,
} from "@/lib/flow/zones";

const btn = "rounded bg-neutral-800 px-2.5 py-1 text-xs hover:bg-neutral-700 disabled:opacity-50";
const input = "w-full rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-xs";
const TONE: Record<string, string> = { ok: "text-emerald-300", error: "text-red-300", info: "text-neutral-300" };
const KIND_TEXT: Record<ZoneKind, string> = { no_cross: "no-cross line", no_enter: "no-enter area" };

export type ZonesEditorProps = {
  api: FlowsApi;
  world: WorldSource;
  server: string;
  map: string;
  block: string;
  zonesRef: ZonesRef | null;
  onReference: (ref: ZonesRef | null) => void;
  onClose: () => void;
};

export default function ZonesEditor({ api, world, server, map, block, zonesRef, onReference, onClose }: ZonesEditorProps) {
  const [rows, setRows] = useState<string[] | null>(null);
  const [file, setFile] = useState<ZonesFile | null>(null);
  const [model, setModel] = useState<ZonesModel>(() => emptyZones(map));
  const [comment, setComment] = useState("");
  const [review, setReview] = useState<Review>(emptyReview);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [pending, setPending] = useState<Draft | null>(null);
  const [itemId, setItemId] = useState("");
  const [itemNote, setItemNote] = useState("");
  const [check, setCheck] = useState<{ doc: ZonesCheck; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "info" | "error"; text: string } | null>(null);
  const [zoom, setZoom] = useState(2);
  const [selected, setSelected] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .world(world, server, [map], true)
      .then((w) => alive && setRows(w.walk?.[map] ?? null))
      .catch(() => alive && setRows(null));
    api
      .zonesFile(map, world, server)
      .then((f) => alive && setFile(f))
      .catch((e) => alive && setMsg({ tone: "error", text: `The zones file cannot be read: ${e instanceof ApiError ? e.reason : String(e)}` }));
    return () => {
      alive = false;
    };
  }, [api, world, server, map]);

  const full: ZonesModel = useMemo(() => ({ ...model, comment: commentLines(comment) }), [model, comment]);
  const yaml = useMemo(() => zonesYaml(full, review), [full, review]);
  const text = yaml.ok ? yaml.text : null;
  const fresh = check !== null && text !== null && check.doc.ok && check.text === text ? check.doc : null;

  const layer: ZonesLayer = useMemo(
    () => ({
      area: fresh?.area?.rows ?? null,
      closed: (fresh?.items ?? []).map((it) => ({ kind: it.kind, cells: it.cells })),
      items: model.items.map((it, i) => ({ kind: it.kind, points: it.points, selected: i === selected })),
      draft,
    }),
    [fresh, model, selected, draft],
  );

  const tool = (kind: ZoneKind) => {
    setDraft(startDraft(kind));
    setPending(null);
    setMsg({ tone: "info", text: kind === "no_cross" ? "Click the line's cells; double-click to end it." : "Click the corners; click the FIRST corner again to close the area." });
  };

  const onCell = (c: Cell, double: boolean) => {
    if (!draft) return;
    if (double) {
      if (draft.kind === "no_cross" && finished(draft)) finish(draft);
      return;
    }
    const r = addPoint(draft, c);
    if (r.error) setMsg({ tone: "error", text: r.error });
    if (r.closed) finish(r.draft);
    else setDraft(r.draft);
  };

  const finish = (d: Draft) => {
    setDraft(null);
    setPending(d);
    setItemId(suggestId(model, d.kind));
    setItemNote("");
    setMsg({ tone: "info", text: `Give the ${KIND_TEXT[d.kind]} its id and a short note.` });
  };

  const add = () => {
    if (!pending) return;
    const r = addItem(model, pending, itemId, itemNote);
    if (!r.ok) return setMsg({ tone: "error", text: r.error });
    setModel(r.model);
    setPending(null);
    setMsg(null);
  };

  const startFromFile = () => {
    const m = modelFrom(file?.model, map);
    if (!m) return setMsg({ tone: "error", text: "The committed file is not one the editor can read: start empty, or fix it by hand." });
    setModel({ ...m, comment: [] });
    setComment(m.comment.join("\n"));
    setReview(emptyReview()); // the review is typed for the file being exported: never carried over
    setCheck(null);
    setMsg({ tone: "info", text: "Started from the committed file. Its review is shown as a reference; type the review of what you export." });
  };

  const runCheck = async () => {
    if (text === null) return;
    setBusy(true);
    try {
      const doc = await api.zonesCheck(map, text, world, server);
      setCheck({ doc, text });
      setMsg(null);
    } catch (e) {
      setMsg({ tone: "error", text: `Check failed: ${e instanceof ApiError ? e.message : String(e)}` });
    } finally {
      setBusy(false);
    }
  };

  const download = () => {
    if (text === null) return;
    const url = URL.createObjectURL(new Blob([text], { type: "application/yaml" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${map}.yaml`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const f = file?.file;
  const cellsOf = (i: number) => fresh?.items?.[i];
  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-neutral-950/95" data-testid="zones-editor">
      <div className="flex flex-wrap items-center gap-3 border-b border-neutral-800 px-4 py-2 text-sm">
        <span className="font-semibold">Zones of {map} (map node {block})</span>
        <span className="rounded bg-amber-900/60 px-2 py-0.5 text-xs text-amber-200">SIMULATE only · EXPORT only: a person commits config/map_zones/{map}.yaml</span>
        <div className="ml-auto flex items-center gap-2">
          <label className="text-xs text-neutral-400">
            zoom{" "}
            <select className="rounded border border-neutral-700 bg-neutral-900 px-1 py-0.5 text-xs" value={zoom} onChange={(e) => setZoom(Number(e.target.value))}>
              {[1, 2, 3, 4, 6, 8].map((z) => (
                <option key={z} value={z}>{z} px / cell</option>
              ))}
            </select>
          </label>
          <button className={btn} onClick={onClose}>Close</button>
        </div>
      </div>
      {msg && <div className={`border-b border-neutral-900 px-4 py-1 text-xs ${msg.tone === "error" ? "text-red-300" : "text-sky-300"}`}>{msg.text}</div>}
      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 overflow-auto p-3">
          <div className="mb-2 flex flex-wrap gap-2 text-xs">
            <button className={btn} onClick={() => tool("no_cross")}>Draw a no-cross line</button>
            <button className={btn} onClick={() => tool("no_enter")}>Draw a no-enter area</button>
            <button className={btn} disabled={!draft?.points.length} onClick={() => draft && setDraft(undoPoint(draft))}>Undo point</button>
            <button className={btn} disabled={!draft || draft.kind !== "no_cross" || !finished(draft)} onClick={() => draft && finish(draft)}>End the line</button>
            <button className={btn} disabled={!draft && !pending} onClick={() => { setDraft(null); setPending(null); setMsg(null); }}>Cancel</button>
            <span className="text-neutral-400">
              {fresh ? "Showing the cells the loader closes (red: lines, orange: areas), sealed pieces (purple) and the search area (green)." : "Check to see the cells the loader closes."}
            </span>
          </div>
          <PathMap name={map} rows={rows} sheet={null} paths={[]} marks={[]} zones={layer} zoom={zoom} onCell={onCell} />
        </div>
        <aside className="w-[480px] shrink-0 space-y-3 overflow-auto border-l border-neutral-800 p-3 text-xs">
          {pending && (
            <div className="space-y-1 rounded border border-cyan-800 p-2">
              <div className="font-semibold">New {KIND_TEXT[pending.kind]} ({pending.points.length} points)</div>
              <label>id<input className={input} value={itemId} onChange={(e) => setItemId(e.target.value)} /></label>
              <label>note (a short reason, in your words)<input className={input} value={itemNote} onChange={(e) => setItemNote(e.target.value)} /></label>
              <button className="rounded bg-cyan-800 px-2.5 py-1 text-xs hover:bg-cyan-700" onClick={add}>Add</button>
            </div>
          )}
          <div className="space-y-1">
            <div className="font-semibold">Items ({model.items.length})</div>
            <ul className="space-y-1">
              {model.items.map((it, i) => (
                <li key={`${it.kind}:${it.id}`} className={`rounded border p-1.5 ${i === selected ? "border-yellow-600" : "border-neutral-800"}`} onMouseEnter={() => setSelected(i)} onMouseLeave={() => setSelected(null)}>
                  <div className="flex items-center gap-2">
                    <b>{it.id}</b> <span className="text-neutral-400">{KIND_TEXT[it.kind]} · {it.points.length} points{cellsOf(i) ? ` · closes ${cellsOf(i)!.cell_count} cells` : ""}</span>
                    <button className={`${btn} ml-auto`} onClick={() => { setModel(removeItem(model, i)); setSelected(null); }}>Delete</button>
                  </div>
                  <div className="text-neutral-300">{it.note}</div>
                  <div className="text-neutral-500">{it.points.map(([x, y]) => `(${x}, ${y})`).join(" ")}</div>
                </li>
              ))}
              {!model.items.length && <li className="text-neutral-500">none yet</li>}
            </ul>
          </div>
          <div className="space-y-1 rounded border border-neutral-800 p-2">
            <div className="font-semibold">config/map_zones/{map}.yaml (the checkout the backend sees)</div>
            {!f && <div className="text-neutral-500">loading…</div>}
            {f && !f.exists && <div className="text-neutral-400">No file: no zones on this map (the runner changes nothing).</div>}
            {f?.exists && (
              <>
                <div className={f.ok ? "text-neutral-300" : "text-red-300"}>
                  sha256 {f.sha256} · {f.ok ? "the loader accepts it" : `the loader refuses it: ${f.error}`}
                </div>
                {f.review && (
                  <div className="text-neutral-400">
                    Its review (a reference; never copied into your export): {f.review.reviewed_by}, {f.review.reviewed}
                    {f.review.delegation ? ` · delegation: ${f.review.delegation}` : ""}
                  </div>
                )}
                {(file?.notes ?? []).map((n) => (
                  <div key={n} className="text-amber-300">{n}</div>
                ))}
                <button className={btn} disabled={!file?.model} onClick={startFromFile}>Start from this file</button>
              </>
            )}
          </div>
          <div className="space-y-1 rounded border border-neutral-800 p-2">
            <div className="font-semibold">Map node {block}: its zones reference (part of the flow; approval binds it)</div>
            <div className="text-neutral-300">{zonesRef ? `names ${zonesRef.map} ${zonesRef.sha256.slice(0, 12)}…` : "names no zones file"}</div>
            {zonesRef && f?.sha256 && zonesRef.sha256 !== f.sha256 && <div className="text-amber-300">The file is now {f.sha256.slice(0, 12)}…: lint says zones_changed until a person reviews and references it again.</div>}
            <div className="flex gap-2">
              <button className={btn} disabled={!f?.exists || !f.ok || !f.sha256 || zonesRef?.sha256 === f.sha256} onClick={() => f?.sha256 && onReference({ map, sha256: f.sha256 })}>
                Reference the committed file
              </button>
              <button className={btn} disabled={!zonesRef} onClick={() => onReference(null)}>Remove the reference</button>
            </div>
          </div>
          <div className="space-y-1 rounded border border-neutral-800 p-2">
            <div className="font-semibold">Review of THIS export (typed by the person who reviewed it)</div>
            <label>reviewed_by<input className={input} value={review.reviewed_by} placeholder="the PERSON who reviewed this file" onChange={(e) => setReview({ ...review, reviewed_by: e.target.value })} /></label>
            <label>reviewed<input className={input} type="date" value={review.reviewed} onChange={(e) => setReview({ ...review, reviewed: e.target.value })} /></label>
            <label>delegation (only under a person&apos;s recorded delegation; the loader checks it)<input className={input} value={review.delegation} onChange={(e) => setReview({ ...review, delegation: e.target.value })} /></label>
            <label>comment lines at the top (# …)<textarea className={`${input} h-20 font-mono`} value={comment} onChange={(e) => setComment(e.target.value)} /></label>
          </div>
          <div className="space-y-1 rounded border border-neutral-800 p-2">
            <div className="flex items-center gap-2">
              <span className="font-semibold">Check and export</span>
              <button className="rounded bg-sky-800 px-2.5 py-1 text-xs hover:bg-sky-700 disabled:opacity-50" disabled={text === null || busy} onClick={() => void runCheck()}>
                {busy ? "Checking…" : "Check with the loader"}
              </button>
              <button className={btn} disabled={text === null} onClick={download}>Download {map}.yaml</button>
            </div>
            {!yaml.ok && (
              <ul className="text-amber-300">
                {yaml.errors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            )}
            {check && (
              <div className={check.text === text ? "" : "opacity-60"} data-testid="zones-check">
                {check.text !== text && <div className="text-amber-300">STALE: the zones changed since this check.</div>}
                <ul>
                  {checkLines(check.doc).map((l, i) => (
                    <li key={i} className={TONE[l.tone]}>{l.text}</li>
                  ))}
                </ul>
                {check.doc.diff !== undefined && (
                  <details open={!!check.doc.diff}>
                    <summary className="cursor-pointer">diff against the committed file</summary>
                    <pre className="max-h-64 overflow-auto rounded bg-neutral-950 p-2 text-[11px]">{check.doc.diff || "(no difference)"}</pre>
                  </details>
                )}
              </div>
            )}
            {text !== null && (
              <details>
                <summary className="cursor-pointer">the YAML ({new TextEncoder().encode(text).length} bytes{fresh ? `, sha256 ${fresh.sha256}` : ""})</summary>
                <pre className="max-h-64 overflow-auto rounded bg-neutral-950 p-2 text-[11px]" data-testid="zones-yaml">{text}</pre>
              </details>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
