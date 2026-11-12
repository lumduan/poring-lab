"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";

import {
  fmtC,
  fmtGB,
  fmtGiB,
  fmtPct,
  fmtW,
  fmtWallTime,
  groupTemps,
  type HardwareView,
  isStale,
  limitTone,
  naText,
  POLL_MS,
  type Sample,
  type SeriesName,
  share,
  sparkPath,
  sparkPoints,
  sparkSummary,
  staleAgeS,
  tempTone,
  type Tone,
  TONE_WORD,
  fmtVram,
  vramPct,
} from "@/lib/hardware";
import { backendHttpBase } from "@/lib/ws";

const TONE_TEXT: Record<Tone, string> = {
  ok: "text-neutral-100",
  warn: "text-amber-300",
  crit: "text-red-300",
};
const TONE_FILL: Record<Tone, string> = {
  ok: "bg-sky-500",
  warn: "bg-amber-500",
  crit: "bg-red-500",
};

/** A value, or the backend's reason it is missing ("n/a: root only"), as plain text. */
function Val({ text, sample, na, tone = "ok" }: { text: string | null; sample: Sample | null; na: string[]; tone?: Tone }) {
  if (text == null) return <span className="text-neutral-500">{naText(sample, ...na)}</span>;
  return (
    <span className={TONE_TEXT[tone]}>
      {text}
      {TONE_WORD[tone] && <span className="ml-1 text-xs font-semibold uppercase">({TONE_WORD[tone]})</span>}
    </span>
  );
}

/** A thin meter: a use against a whole or a limit. The track is a lighter step of the fill. */
function Meter({ pct, tone = "ok", label }: { pct: number | null; tone?: Tone; label: string }) {
  if (pct == null) return null;
  const width = Math.min(100, Math.max(0, pct));
  return (
    <div className="h-1.5 w-full rounded-full bg-neutral-800" role="meter" aria-label={label} aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
      <div className={`h-1.5 rounded-full ${TONE_FILL[tone]}`} style={{ width: `${width}%` }} />
    </div>
  );
}

/** A captioned 10-minute sparkline (inline SVG, no script): the history in the de-emphasis grey,
 * the newest point in the accent. Its accessible name gives the range, so it is never colour alone. */
function Spark({
  view,
  name,
  caption,
  unit,
  min,
  max,
}: {
  view: HardwareView | null;
  name: SeriesName;
  caption: string;
  unit: string;
  min?: number;
  max?: number;
}) {
  const values = view?.history.series[name] ?? [];
  const t = view?.history.t_s ?? [];
  const opts = { width: 120, height: 28, min, max };
  const d = sparkPath(t, values, opts);
  const tail = sparkPoints(t, values, opts).at(-1);
  const summary = `${caption}, ${sparkSummary(values, unit)}`;
  return (
    <figure className="mt-2">
      <figcaption className="flex justify-between text-xs text-neutral-500">
        <span>{caption}</span>
        <span>10 min</span>
      </figcaption>
      <svg viewBox="-2 -2 124 32" preserveAspectRatio="none" className="h-8 w-full" role="img" aria-label={summary}>
        <title>{summary}</title>
        <path d={d} fill="none" className="stroke-neutral-500" strokeWidth={1.5} strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
        {tail && <circle cx={tail.x} cy={tail.y} r={2} className="fill-sky-400" />}
      </svg>
    </figure>
  );
}

function Tile({ title, children, footer, wide = false }: { title: string; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  return (
    <section
      className={`flex flex-col rounded-lg border border-neutral-800 bg-neutral-900/60 p-4 ${wide ? "xl:col-span-2" : ""}`}
      aria-label={title}
    >
      <h2 className="mb-2 text-sm font-semibold text-neutral-300">{title}</h2>
      <div className="flex flex-1 flex-col gap-1 text-sm">{children}</div>
      {footer && <div className="mt-2 text-xs text-neutral-500">{footer}</div>}
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-3 font-mono text-xs">
      <span className="text-neutral-500">{label}</span>
      <span className="text-right tabular-nums">{children}</span>
    </div>
  );
}

function Headline({ children }: { children: ReactNode }) {
  return <div className="font-mono text-2xl font-semibold tabular-nums">{children}</div>;
}

/** Hardware (Batt 2026-11-08): CPU, RAM, GPU, temperatures and power of the lab host, from the
 * backend's GET /hardware every 2 s while this tab is visible. Read-only: this page sends nothing. */
export default function HardwareMonitor({ backendUrl }: { backendUrl: string | null }) {
  const [view, setView] = useState<HardwareView | null>(null);
  const [fetchedAt, setFetchedAt] = useState<number | null>(null);
  const [now, setNow] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [hidden, setHidden] = useState(false);
  const inFlight = useRef(false);

  useEffect(() => {
    let alive = true;
    const base = backendHttpBase(backendUrl);
    const tick = async () => {
      const visible = document.visibilityState === "visible";
      setHidden(!visible);
      if (!visible) return; // paused while the tab is hidden: no request at all
      setNow(Date.now());
      if (inFlight.current) return; // a slow answer is never overtaken by the next poll
      inFlight.current = true;
      try {
        const r = await fetch(`${base}/hardware`, { cache: "no-store" });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const body = (await r.json()) as HardwareView;
        if (alive) {
          setView(body);
          setFetchedAt(Date.now());
          setNow(Date.now());
          setError(null);
        }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      } finally {
        inFlight.current = false;
      }
    };
    const onVisibility = () => void tick();
    const first = setTimeout(() => void tick(), 0);
    const timer = setInterval(() => void tick(), POLL_MS);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      alive = false;
      clearTimeout(first);
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [backendUrl]);

  const s = view?.current ?? null;
  const age = staleAgeS(view?.age_s ?? null, fetchedAt, now);
  const stale = isStale(age);
  const cpu = s?.cpu;
  const mem = s?.memory;
  const gpu = s?.gpu ?? null;
  const power = s?.power;
  const memPct = share(mem?.used_b, mem?.total_b);
  const shmTone = limitTone(s?.shm?.used_b ?? null, s?.shm?.limit_b ?? null);
  const gpuPowerTone = limitTone(gpu?.power_w ?? null, gpu?.power_max_w ?? null);
  const pkg = s?.temps.find((t) => t.chip === "coretemp" && t.label.toLowerCase().startsWith("package"));
  const sampledAt = fmtWallTime(s?.t_wall);

  return (
    <main className="mx-auto flex max-w-[1600px] flex-col gap-3 p-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold tracking-tight">Hardware</h1>
        <div className="flex flex-wrap items-center gap-3 font-mono text-xs text-neutral-400">
          {hidden && <span>paused (tab hidden)</span>}
          {error && <span className="text-red-300">backend: {error}</span>}
          {s && (
            <span>
              sample #{s.seq} at {sampledAt ?? "–"} · read {s.read_ms.toFixed(1)} ms
            </span>
          )}
          <span
            className={`rounded-md px-2 py-0.5 font-semibold ${stale ? "bg-amber-500 text-neutral-950" : "bg-neutral-800 text-neutral-200"}`}
          >
            {age == null ? "waiting for data" : stale ? `STALE: ${age.toFixed(0)} s old` : `live (${age.toFixed(1)} s)`}
          </span>
        </div>
      </header>

      <div className={`grid gap-3 md:grid-cols-2 xl:grid-cols-3 ${stale && s ? "opacity-60" : ""}`}>
        <Tile title="CPU" footer={cpu?.model ?? undefined}>
          <Headline>
            <Val text={fmtPct(cpu?.busy_pct)} sample={s} na={["cpu.busy_pct"]} />
          </Headline>
          <Meter pct={cpu?.busy_pct ?? null} label="CPU busy" />
          <Row label="load 1 / 5 / 15">
            {cpu?.load ? cpu.load.map((v) => v.toFixed(2)).join(" / ") : <Val text={null} sample={s} na={["cpu.load"]} />}
          </Row>
          <Row label="cores">{cpu?.cores ?? "–"}</Row>
          <div className="mt-1 grid grid-cols-4 gap-x-3 gap-y-0.5 font-mono text-xs tabular-nums">
            {(cpu?.core_pct ?? []).map((pct, i) => (
              <div key={i} className="flex justify-between gap-1" title={`cpu${i}`}>
                <span className="text-neutral-500">{i}</span>
                <span>{pct == null ? "–" : `${pct.toFixed(0)}%`}</span>
                <span className="text-neutral-500">{cpu?.core_mhz[i] ?? "–"}</span>
              </div>
            ))}
          </div>
          {cpu?.mhz_source && <p className="text-xs text-neutral-500">per core: busy %, MHz ({cpu.mhz_source})</p>}
          <Spark view={view} name="cpu_pct" caption="busy %" unit=" %" min={0} max={100} />
        </Tile>

        <Tile title="Memory" footer="used = total - available (/proc/meminfo)">
          <Headline>
            <Val text={fmtGiB(mem?.used_b)} sample={s} na={["memory"]} />
            <span className="ml-2 text-sm text-neutral-400">of {fmtGiB(mem?.total_b) ?? "–"}</span>
          </Headline>
          <Meter pct={memPct} label="memory used" />
          <Row label="available">
            <Val text={fmtGiB(mem?.available_b)} sample={s} na={["memory"]} />
          </Row>
          <Row label="swap used">
            <Val text={fmtGiB(mem?.swap_used_b)} sample={s} na={["memory"]} /> of {fmtGiB(mem?.swap_total_b) ?? "–"}
          </Row>
          <Row label="shmem (host, all tmpfs)">
            <Val text={fmtGiB(mem?.shmem_b)} sample={s} na={["memory"]} />
          </Row>
          <Row label="/dev/shm (limit 4 GB)">
            <Val text={s?.shm ? `${fmtGB(s.shm.used_b, 2)} of 4 GB` : null} sample={s} na={["shm"]} tone={shmTone} />
          </Row>
          {s?.shm && <Meter pct={share(s.shm.used_b, s.shm.limit_b)} tone={shmTone} label="/dev/shm against its 4 GB limit" />}
          <Row label="root disk free">
            <Val text={s?.disk ? `${fmtGB(s.disk.free_b)} of ${fmtGB(s.disk.total_b)}` : null} sample={s} na={["disk"]} />
          </Row>
          {s?.disk && <p className="truncate text-xs text-neutral-500" title={s.disk.path}>statvfs {s.disk.path}</p>}
          <Spark view={view} name="mem_pct" caption="used %" unit=" %" min={0} max={100} />
        </Tile>

        <Tile
          title="GPU"
          footer={gpu ? `${gpu.name ?? gpu.pci_id ?? "GPU"} · ${gpu.driver} ${gpu.card}` : undefined}
        >
          <Headline>
            <Val text={gpu ? fmtPct(gpu.busy_pct) : null} sample={s} na={gpu ? ["gpu.busy_pct"] : ["gpu"]} />
          </Headline>
          <p className="text-xs text-neutral-500">busy (from RC6 residency)</p>
          <Meter pct={gpu?.busy_pct ?? null} label="GPU busy (from RC6 residency)" />
          <Row label="temperature">
            <Val text={fmtC(gpu?.temp_c)} sample={s} na={["gpu.temp_c", "gpu"]} />
          </Row>
          <Row label="power">
            <Val text={fmtW(gpu?.power_w)} sample={s} na={["gpu.power_w", "gpu"]} tone={gpuPowerTone} />
            {gpu?.power_max_w != null && ` of ${fmtW(gpu.power_max_w)} limit`}
          </Row>
          <Row label="frequency act / cur / max">
            {gpu ? [gpu.freq_act_mhz, gpu.freq_cur_mhz, gpu.freq_max_mhz].map((v) => (v == null ? "–" : String(v))).join(" / ") + " MHz" : <Val text={null} sample={s} na={["gpu"]} />}
          </Row>
          <Row label="fan">
            <Val text={gpu?.fan_rpm != null ? `${gpu.fan_rpm} RPM` : null} sample={s} na={["gpu.fan_rpm", "gpu"]} />
          </Row>
          <Row label="VRAM used">
            <Val text={fmtVram(gpu?.vram_used_b, gpu?.vram_total_b)} sample={s} na={["gpu.vram_used_b", "gpu"]} />
          </Row>
          <Meter pct={vramPct(gpu?.vram_used_b, gpu?.vram_total_b)} label="VRAM used" />
          <Spark view={view} name="gpu_busy_pct" caption="busy % (RC6)" unit=" %" min={0} max={100} />
          <Spark view={view} name="gpu_temp_c" caption="temperature °C" unit=" °C" />
        </Tile>

        <Tile title="Power" footer={power?.server_avg_s ? `server: the iLO meter's average over ${power.server_avg_s.toFixed(0)} s` : undefined}>
          <Headline>
            <Val text={fmtW(power?.server_w)} sample={s} na={["power.server_w"]} />
            <span className="ml-2 text-sm text-neutral-400">whole server (wall)</span>
          </Headline>
          <Spark view={view} name="server_w" caption="server W" unit=" W" min={0} />
          <Row label="GPU">
            <Val text={fmtW(power?.gpu_w)} sample={s} na={["power.gpu_w"]} tone={gpuPowerTone} />
          </Row>
          <Row label="CPU package (RAPL)">
            <Val text={fmtW(power?.cpu_pkg_w)} sample={s} na={["power.cpu_pkg_w"]} />
          </Row>
          <Spark view={view} name="gpu_w" caption="GPU W" unit=" W" min={0} />
        </Tile>

        <Tile title="Temperatures" wide footer="High / over limit: against each sensor's own max and crit.">
          <Headline>
            <Val text={fmtC(pkg?.c)} sample={s} na={["temps"]} tone={pkg ? tempTone(pkg.c, pkg.max_c, pkg.crit_c) : "ok"} />
            <span className="ml-2 text-sm text-neutral-400">CPU package</span>
          </Headline>
          <Spark view={view} name="cpu_temp_c" caption="CPU package °C" unit=" °C" />
          <div className="mt-1 grid gap-x-6 gap-y-2 sm:grid-cols-2">
            {s && s.temps.length === 0 && <span className="text-xs text-neutral-500">no temperature sensors</span>}
            {groupTemps(s?.temps ?? []).map((group, gi) => (
              <div key={`${gi}:${group.chip}`}>
                <p className="text-xs font-semibold text-neutral-400">{group.chip}</p>
                {group.items.map((t, ti) => {
                  const tone = tempTone(t.c, t.max_c, t.crit_c);
                  const limits = [t.max_c != null && `max ${t.max_c.toFixed(0)}`, t.crit_c != null && `crit ${t.crit_c.toFixed(0)}`].filter(Boolean).join(" · ");
                  return (
                    <Row key={`${ti}:${t.chip}:${t.label}`} label={t.label === t.chip ? "temp" : t.label}>
                      <Val text={fmtC(t.c)} sample={s} na={[]} tone={tone} />
                      {limits && <span className="ml-2 text-neutral-500">{limits}</span>}
                    </Row>
                  );
                })}
              </div>
            ))}
          </div>
        </Tile>
      </div>
      <p className="text-xs text-neutral-500">
        Every {view ? view.period_s : 2} s while this tab is visible; sparklines show the last 10 minutes,
        the dot is the newest point. Read-only: this page sends nothing.
      </p>
    </main>
  );
}
