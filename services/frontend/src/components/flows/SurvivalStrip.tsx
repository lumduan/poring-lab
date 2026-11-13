"use client";

// THE SURVIVAL STRIP on a map flow (Batt 2026-11-13 ~14:2x: "the heal and escape numbers: a global
// config for every map's flow; a map's flow that sets them again overrides it"). It reads and
// writes the backend's /flows/survival (the human-only settings store, the Settings write gate:
// a LAN browser with the CSRF token); every change is saved at once, as the other Run settings
// are, and the Run helper reads the file at the next start. The blocks show what the next Run uses.
import { useCallback, useEffect, useRef, useState } from "react";

import { REFUSALS } from "@/lib/flow/liverun";
import { effectiveSurvival, groupLevel, type Survival, type SurvivalConfig, type SurvivalDoc, type SurvivalKey, survivalProblem } from "@/lib/flow/survival";
import { backendHttpBase } from "@/lib/ws";

export type SurvivalState = { cfg: SurvivalConfig | null; err: string | null; busy: boolean; save: (scope: "global" | "map", values: Survival | null) => Promise<void> };

export function useSurvival(backendUrl: string | null, map: string): SurvivalState {
  const base = backendHttpBase(backendUrl);
  const [cfg, setCfg] = useState<SurvivalConfig | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const csrf = useRef<string | null>(null);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const r = await fetch(`${base}/flows/survival`, { cache: "no-store" });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const body = (await r.json()) as SurvivalConfig;
        if (alive) setCfg(body);
      } catch (e) {
        if (alive) setErr(`The survival numbers could not be read (${e instanceof Error ? e.message : String(e)}): the blocks show the defaults.`);
      }
    })();
    return () => {
      alive = false;
    };
  }, [base]);

  const save = useCallback(
    async (scope: "global" | "map", values: Survival | null) => {
      setBusy(true);
      setErr(null);
      try {
        for (let attempt = 0; attempt < 2; attempt++) {
          if (csrf.current === null) {
            const t = await fetch(`${base}/settings/csrf`, { cache: "no-store" });
            if (!t.ok) throw new Error(`the security token was refused (HTTP ${t.status})`);
            csrf.current = ((await t.json()) as { token: string }).token;
          }
          const r = await fetch(`${base}/flows/survival`, {
            method: "PUT",
            cache: "no-store",
            headers: { "content-type": "application/json", "x-csrf-token": csrf.current },
            body: JSON.stringify({ scope, map: scope === "map" ? map : null, values }),
          });
          if (r.ok) {
            const body = (await r.json()) as SurvivalConfig;
            setCfg({ global: body.global ?? {}, maps: body.maps ?? {} });
            break;
          }
          const body = (await r.json().catch(() => ({}))) as { detail?: { reason?: string } | unknown[] };
          const reason = !Array.isArray(body.detail) && body.detail?.reason ? body.detail.reason : `HTTP ${r.status}`;
          if (reason === "csrf_invalid" && attempt === 0) {
            csrf.current = null; // a backend restart invalidates every token: fetch a new one once
            continue;
          }
          setErr(REFUSALS[reason] ?? `Not saved: ${reason}`);
          break;
        }
      } catch (e) {
        setErr(`Not saved: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        setBusy(false);
      }
    },
    [base, map],
  );

  return { cfg, err, busy, save };
}

const LEVEL_WORDS = { default: "the defaults", global: "every map's values", map: "this map's own values" } as const;

export default function SurvivalStrip({ d, map, sv }: { d: SurvivalDoc; map: string; sv: SurvivalState }) {
  const eff = effectiveSurvival(d, sv.cfg, map);
  const level = groupLevel(eff.source);
  const own = level === "map";
  const [rate, setRate] = useState<string | null>(null); // the fast fall's number while it is typed
  const scopeVals = (scope: "global" | "map"): Survival => (scope === "map" ? eff.values : effectiveSurvival(d, sv.cfg ? { global: sv.cfg.global, maps: {} } : null, map).values);
  const [why, setWhy] = useState<string | null>(null);

  const change = (k: SurvivalKey, v: number) => {
    const scope = own ? "map" : "global";
    const next = { ...scopeVals(scope), [k]: v };
    const p = survivalProblem(next, d);
    setWhy(p);
    if (p === null) void sv.save(scope, next);
  };
  const pick = (k: Exclude<SurvivalKey, "fly_rate">, label: string) => (
    <label className="mb-part" key={k}>
      {label}{" "}
      <select value={String(eff.values[k])} disabled={sv.busy || sv.cfg === null} onChange={(e) => change(k, Number(e.target.value))} data-testid={`survival-${k}`}>
        {d.choices[k].map((c) => (
          <option key={c} value={String(c)}>
            {Math.round(c * 100)} %
          </option>
        ))}
      </select>
    </label>
  );
  return (
    <div className="map-binding run-settings" data-kind={why || sv.err ? "plain" : "block"} data-testid="survival">
      <span className="mb-part">
        <span className="mb-key">heal and escape</span>
      </span>
      <span className="mb-part" role="radiogroup" aria-label="Whose numbers">
        <label title="The numbers every map's flow uses (a map with its own numbers uses those instead)">
          <input type="radio" name="survival-scope" checked={!own} disabled={sv.busy || sv.cfg === null} onChange={() => void sv.save("map", null)} data-testid="survival-scope-global" /> every map
        </label>{" "}
        <label title={`Numbers for ${map} only: they override every map's`}>
          <input type="radio" name="survival-scope" checked={own} disabled={sv.busy || sv.cfg === null} onChange={() => void sv.save("map", eff.values)} data-testid="survival-scope-map" /> {map} only
        </label>
      </span>
      {pick("potion_below", "heal at HP under")}
      {pick("fly_below", "Fly Wing at HP under")}
      <label className="mb-part" title="The fast-fall rule: a Fly Wing when the HP falls faster than this, while under the next number">
        or HP falling faster than{" "}
        <input
          className="run-settings-num"
          type="number"
          min={d.fly_rate[0]}
          max={d.fly_rate[1]}
          step={10}
          value={rate ?? String(eff.values.fly_rate)}
          disabled={sv.busy || sv.cfg === null}
          onChange={(e) => setRate(e.target.value)}
          onBlur={() => {
            if (rate !== null && rate !== "") change("fly_rate", Number(rate));
            setRate(null);
          }}
          aria-label="the fast fall, HP per second"
          data-testid="survival-fly_rate"
        />{" "}
        HP/s
      </label>
      {pick("fly_rate_below", "under")}
      <span className="mb-part muted" data-testid="survival-level">
        the next Run uses {LEVEL_WORDS[level]}
        {level === "global" ? " (set for every map)" : ""}
      </span>
      {level === "global" && (
        <button type="button" className="mb-link" disabled={sv.busy} onClick={() => void sv.save("global", null)} data-testid="survival-reset-global">
          every map back to the defaults
        </button>
      )}
      {(why || sv.err || sv.cfg?.broken) && (
        <span className="mb-part mb-warn" role="status">
          {why ?? sv.err ?? "The survival file on the bot server cannot be read: a person must look at settings/flowrun/survival.json (Run refuses until then)."}
        </span>
      )}
    </div>
  );
}
