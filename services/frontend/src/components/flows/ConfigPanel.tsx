"use client";

// THE SETTINGS of a map's flow (Batt 2026-11-13: "nothing is fixed, we only put the defaults";
// "a global config for every map's flow; a map's flow that sets them again overrides it"; "move
// them too"; "all of them"). Every setting of scripts/flow_config.py, by group: the everyday ones
// open, the rest under "all the other numbers". Each group edits EVERY MAP's values or THIS MAP's
// own; each change is saved at once on the bot server (PUT /flows/config, the Settings write gate)
// with an undo line (matpilot 2026-11-13: a child scrolls over these on a phone). A value equal to
// the level below is not stored: it keeps following that level. The blocks show what the next
// Run uses. Every value renders as text.
import { useCallback, useEffect, useRef, useState } from "react";

import { type ConfigDoc, type ConfigField, type ConfigFile, type ConfigValue, effectiveConfig, FIRST_GROUPS, fieldProblem, type Level, levelAfter, notInUseWhy, shownValue } from "@/lib/flow/config";
import { REFUSALS } from "@/lib/flow/liverun";
import { backendHttpBase } from "@/lib/ws";

export type ConfigState = { file: ConfigFile | null; err: string | null; busy: boolean; save: (scope: "global" | "map", group: string, values: Record<string, ConfigValue> | null) => Promise<boolean> };

export function useConfig(backendUrl: string | null, map: string): ConfigState {
  const base = backendHttpBase(backendUrl);
  const [file, setFile] = useState<ConfigFile | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const csrf = useRef<string | null>(null);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const r = await fetch(`${base}/flows/config`, { cache: "no-store" });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const body = (await r.json()) as ConfigFile;
        if (alive) setFile(body);
      } catch (e) {
        if (alive) setErr(`The settings could not be read (${e instanceof Error ? e.message : String(e)}): the blocks show the defaults.`);
      }
    })();
    return () => {
      alive = false;
    };
  }, [base]);

  const save = useCallback(
    async (scope: "global" | "map", group: string, values: Record<string, ConfigValue> | null): Promise<boolean> => {
      setBusy(true);
      setErr(null);
      let ok = false;
      try {
        for (let attempt = 0; attempt < 2; attempt++) {
          if (csrf.current === null) {
            const t = await fetch(`${base}/settings/csrf`, { cache: "no-store" });
            if (!t.ok) throw new Error(`the security token was refused (HTTP ${t.status})`);
            csrf.current = ((await t.json()) as { token: string }).token;
          }
          const r = await fetch(`${base}/flows/config`, {
            method: "PUT",
            cache: "no-store",
            headers: { "content-type": "application/json", "x-csrf-token": csrf.current },
            body: JSON.stringify({ scope, map: scope === "map" ? map : null, group, values }),
          });
          if (r.ok) {
            const body = (await r.json()) as ConfigFile;
            setFile({ global: body.global ?? {}, maps: body.maps ?? {} });
            ok = true;
            break;
          }
          const body = (await r.json().catch(() => ({}))) as { detail?: { reason?: string; detail?: string } | unknown[] };
          const det = !Array.isArray(body.detail) ? body.detail : undefined;
          const reason = det?.reason ?? `HTTP ${r.status}`;
          if (reason === "csrf_invalid" && attempt === 0) {
            csrf.current = null; // a backend restart invalidates every token: fetch a new one once
            continue;
          }
          setErr(det?.detail ? `Not saved: ${det.detail}` : (REFUSALS[reason] ?? `Not saved: ${reason}`));
          break;
        }
      } catch (e) {
        setErr(`Not saved: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        setBusy(false);
      }
      return ok;
    },
    [base, map],
  );
  return { file, err, busy, save };
}

const LEVEL_TAG: Record<Level, string> = { default: "", global: "every map", map: "this map" };
type Last = { scope: "global" | "map"; group: string; prev: Record<string, ConfigValue> | null; text: string };

export default function ConfigPanel({ d, map, cs, problem }: { d: ConfigDoc; map: string; cs: ConfigState; problem: string | null }) {
  const eff = effectiveConfig(d, cs.file, map);
  const [last, setLast] = useState<Last | null>(null);
  const [why, setWhy] = useState<string | null>(null);
  const [more, setMore] = useState(false);
  const nOther = d.fields.filter((f) => !FIRST_GROUPS.includes(f.group)).length;

  // what a level holds for a group now (null: nothing of its own), for the undo
  const held = (scope: "global" | "map", group: string): Record<string, ConfigValue> | null => {
    const lvl = scope === "map" ? cs.file?.maps?.[map] : cs.file?.global;
    const out = Object.fromEntries(Object.entries(lvl ?? {}).filter(([k]) => d.fields.some((f) => f.name === k && f.group === group)));
    return Object.keys(out).length ? out : null;
  };
  const saveUndoable = (scope: "global" | "map", group: string, values: Record<string, ConfigValue> | null, text: string) => {
    const prev = held(scope, group);
    void cs.save(scope, group, values).then((ok) => setLast(ok ? { scope, group, prev, text } : null));
  };
  const change = (scope: "global" | "map", f: ConfigField, v: ConfigValue) => {
    const p = fieldProblem(f, v, d);
    setWhy(p);
    if (p !== null || v === eff.values[f.name]) return;
    const values = levelAfter(d, cs.file, scope, map, f.group, f.name, v);
    saveUndoable(scope, f.group, values, `${f.words} ${shownOf(f, eff.values[f.name])} → ${shownOf(f, v)}, for ${scope === "map" ? `${map} only` : "every map"}`);
  };

  const group = (g: ConfigDoc["groups"][number]) => {
    const fields = d.fields.filter((f) => f.group === g.id);
    return <GroupRow key={g.id} g={g} fields={fields} d={d} map={map} eff={eff} cs={cs} onChange={change} onClear={(scope) => saveUndoable(scope, g.id, null, `${g.title}: ${scope === "map" ? `${map} uses every map's values again` : "every map is back to the defaults"}`)} />;
  };
  return (
    <section className="config-panel" aria-label="The settings" data-testid="config-panel">
      {d.groups.filter((g) => FIRST_GROUPS.includes(g.id)).map(group)}
      <details className="config-more" open={more} onToggle={(e) => setMore(e.currentTarget.open)} data-testid="config-more">
        <summary>
          all the other numbers <span className="muted">({nOther}: the start, the fight, aiming, loot, walking, safety, the loop)</span>
        </summary>
        {more && d.groups.filter((g) => !FIRST_GROUPS.includes(g.id)).map(group)}
      </details>
      {last && (
        <p className="config-line" role="status" data-testid="config-saved">
          saved on the bot server: {last.text}{" "}
          <button type="button" className="mb-link" disabled={cs.busy} onClick={() => void cs.save(last.scope, last.group, last.prev).then((ok) => ok && setLast(null))} data-testid="config-undo">
            undo
          </button>
        </p>
      )}
      {(why || cs.err || problem || cs.file?.broken) && (
        <p className="config-line mb-warn" role="status" data-testid="config-problem">
          {why ?? cs.err ?? problem ?? `The settings file on the bot server cannot be used (${cs.file?.broken}): a person looks at settings/flowrun/config.json first (Run refuses until then).`}
        </p>
      )}
    </section>
  );
}

const shownOf = (f: ConfigField, v: ConfigValue) => `${shownValue(f, v)}${f.kind === "share" ? " %" : f.unit ? ` ${f.unit}` : ""}`;

function GroupRow({
  g,
  fields,
  d,
  map,
  eff,
  cs,
  onChange,
  onClear,
}: {
  g: ConfigDoc["groups"][number];
  fields: ConfigField[];
  d: ConfigDoc;
  map: string;
  eff: ReturnType<typeof effectiveConfig>;
  cs: ConfigState;
  onChange: (scope: "global" | "map", f: ConfigField, v: ConfigValue) => void;
  onClear: (scope: "global" | "map") => void;
}) {
  const ownMap = fields.some((f) => eff.source[f.name] === "map");
  const ownGlobal = fields.some((f) => cs.file?.global?.[f.name] !== undefined);
  // the person's pick; until they pick, the group follows the file: this map's own values = "map"
  // (matpilot 2026-11-13: set before the file had loaded, it showed "every map" after a reload)
  const [picked, setScope] = useState<"global" | "map" | null>(null);
  const scope = picked ?? (ownMap ? "map" : "global");
  // switches and choices first (what runs), then its numbers
  const ordered = [...fields].sort((a, b) => Number(!["switch", "choice"].includes(a.kind)) - Number(!["switch", "choice"].includes(b.kind)));
  const off = cs.busy || cs.file === null || Boolean(cs.file?.broken);
  return (
    <div className="map-binding run-settings config-group" data-kind="block" data-testid={`config-group-${g.id}`}>
      <span className="mb-part" title={g.note}>
        <span className="mb-key">{g.title}</span>
      </span>
      <span className="mb-part config-scope" role="radiogroup" aria-label={`${g.title}: a change goes to`}>
        <span className="muted">change for:</span>{" "}
        <label title="Edit the values every map's flow uses">
          <input type="radio" name={`scope-${g.id}`} checked={scope === "global"} onChange={() => setScope("global")} data-testid={`config-scope-${g.id}-global`} /> every map
        </label>{" "}
        <label title={`Edit ${map}'s own values: they override every map's`}>
          <input type="radio" name={`scope-${g.id}`} checked={scope === "map"} onChange={() => setScope("map")} data-testid={`config-scope-${g.id}-map`} /> {map} only
        </label>
      </span>
      {ordered.map((f) => (
        <FieldInput key={f.name} f={f} d={d} v={eff.values[f.name]} level={eff.source[f.name]} off={off} why={notInUseWhy(d, eff.values, f.name)} onChange={(v) => onChange(scope, f, v)} />
      ))}
      {scope === "map" && ownMap && (
        <button
          type="button"
          className="mb-link"
          disabled={off}
          onClick={() => {
            onClear("map");
            setScope(null); // matpilot: the radio stayed on "map only" until a reload
          }}
          data-testid={`config-clear-${g.id}-map`}
        >
          {map}: use every map&apos;s values again
        </button>
      )}
      {scope === "global" && ownGlobal && (
        <button
          type="button"
          className="mb-link"
          disabled={off}
          onClick={() => {
            onClear("global");
            setScope(null);
          }}
          data-testid={`config-clear-${g.id}-global`}
        >
          every map back to the defaults
        </button>
      )}
    </div>
  );
}

function FieldInput({ f, d, v, level, off, why, onChange }: { f: ConfigField; d: ConfigDoc; v: ConfigValue; level: Level; off: boolean; why: string | null; onChange: (v: ConfigValue) => void }) {
  const [draft, setDraft] = useState<string | null>(null); // a number or a point while it is typed
  const tag = LEVEL_TAG[level];
  const label = (
    <>
      {f.words}
      {tag && <span className="config-tag"> ({tag})</span>}
      {why && <span className="config-tag"> (not in use: {why})</span>}{" "}
    </>
  );
  const id = `config-${f.name}`;
  if (f.kind === "switch") {
    return (
      <label className="mb-part" data-unused={why ? "true" : "false"}>
        <input type="checkbox" checked={v === true} disabled={off} onChange={(e) => onChange(e.target.checked)} data-testid={id} /> {label}
        {v === false && f.warn && <span className="config-warn"> {f.warn}</span>}
      </label>
    );
  }
  if (f.kind === "choice") {
    return (
      <label className="mb-part" data-unused={why ? "true" : "false"}>
        {label}
        <select value={String(v)} disabled={off} onChange={(e) => onChange(e.target.value)} data-testid={id}>
          {(f.options ?? []).map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </label>
    );
  }
  if (f.kind === "key") {
    return (
      <label className="mb-part">
        {label}
        <select value={String(v)} disabled={off} onChange={(e) => onChange(e.target.value)} data-testid={id}>
          {d.keys.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </label>
    );
  }
  if (f.kind === "point" || f.kind === "point_or_none") {
    const none = v === "none";
    const text = draft ?? (none ? "" : String(v));
    return (
      <span className="mb-part">
        {f.kind === "point_or_none" && (
          <input type="checkbox" checked={!none} disabled={off} onChange={(e) => onChange(e.target.checked ? String(f.default !== "none" ? f.default : "714,405") : "none")} aria-label={`${f.words}: this server asks`} data-testid={`${id}-on`} />
        )}{" "}
        {label}
        <input
          className="run-settings-point"
          value={text}
          disabled={off || none}
          onChange={(e) => setDraft(e.target.value.replace(/[^\d,]/g, "").slice(0, 9))}
          onBlur={() => {
            if (draft !== null) onChange(draft);
            setDraft(null);
          }}
          placeholder="x,y"
          size={8}
          aria-label={`${f.words} (x,y in the game picture)`}
          data-testid={id}
        />
      </span>
    );
  }
  const pct = f.kind === "share";
  const shown = draft ?? shownValue(f, v);
  return (
    <label className="mb-part">
      {label}
      <input
        className="run-settings-num"
        type="number"
        min={pct ? f.lo * 100 : f.lo}
        max={pct ? f.hi * 100 : f.hi}
        step={pct ? f.step * 100 : f.step}
        value={shown}
        disabled={off}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => {
          if (draft !== null && draft !== "") onChange(pct ? Math.round(Number(draft) * 100) / 10000 : Number(draft));
          setDraft(null);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        }}
        aria-label={f.words}
        data-testid={id}
      />
      {pct ? " %" : f.unit ? ` ${f.unit}` : ""}
    </label>
  );
}
