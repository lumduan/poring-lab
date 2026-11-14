"use client";

// THE NODE INSPECTOR (docs/planning/project-model.md; /maps' side panel, and /flows shows it too):
// one project node -- its id and kind; for a map node its map, entries (name, cell, radius), targets
// and ignored species, resume_here and its zones reference; for the login and character nodes what
// their main says in words (a server and a credential BY NAME, the slot); for every node its tabs
// and their names, marked where a node's name OVERRIDES Global's, and for Global's names the nodes
// that override them. Every change is a new project through `onChange` (lib/maps/edit.ts,
// session.ts); nothing here saves, runs or reaches the game. Every value is rendered as text.
//
// Props: project, nodeId, lint (the engine's LintDoc or null), onChange(project), onOpen(nodeId)
// ("Open flow": the node's tabs on /flows). Optional: credentials (the catalogue's names), onZones
// (the zones editor for a map node), onSimulate (Simulate from this node), onRules (the world
// rules' editor), onRenamed (the page follows a rename), canOpen (false on /flows' own node).
import "./inspector.css";

import { useState } from "react";

import type { LintDoc } from "@/lib/flow/api";
import { boxNameWords } from "@/lib/flow/box";
import type { Entry, MobRef } from "@/lib/flow/ir";
import { nodeById, type MapNode, type PNode, type Project, sessionPath } from "@/lib/flow/project";
import { lintLine } from "@/lib/flow/status";
import { type Edit, removeNode, renameNode, renameProblem, setStart, setZones, updateMapNode } from "@/lib/maps/edit";
import { entryCaption, nodeLinks } from "@/lib/maps/links";
import { cappedFindings, findingWhere, KIND_TITLE, nodeLint, nodeTitle, runnerSpecies, SEVERITY_WORDS, tabRows, tabSummary } from "@/lib/maps/nodewords";
import { readRules, wingText } from "@/lib/maps/rules";
import { characterOf, characterWords, CHAR_NAME, CREDENTIAL_NAME, CREDENTIALS, credentialOf, loginOf, loginWords, MAX_SLOT, SERVERS, setCharacter, setLogin } from "@/lib/maps/session";

export type NodeInspectorProps = {
  project: Project;
  nodeId: string;
  lint: LintDoc | null;
  onChange: (project: Project) => void;
  onOpen: (nodeId: string) => void;
  credentials?: readonly string[];
  onZones?: (nodeId: string) => void;
  onSimulate?: (nodeId: string) => void;
  onRules?: () => void;
  onRenamed?: (from: string, to: string) => void;
  canOpen?: boolean;
  /** "Start here": the page's own (its notice); else the edit is applied as any other */
  onStart?: (id: string) => void;
};

const MAX_FINDINGS = 6;

export default function NodeInspector(props: NodeInspectorProps) {
  const { project, nodeId, lint, onChange, onOpen, onSimulate, onRules, canOpen = true } = props;
  const [error, setError] = useState<{ for: string; text: string } | null>(null);
  const n = nodeById(project, nodeId);
  if (!n) return <p className="ni-muted">There is no node {nodeId} in this project.</p>;
  const apply = (r: Edit | { ok: true; project: Project } | { ok: false; error: string }) => {
    if (r.ok) {
      setError(null);
      onChange(r.project);
    } else setError({ for: n.id, text: r.error });
  };
  const nl = nodeLint(lint, n.id);
  const ll = lint ? lintLine(nl.counts) : null;
  const capped = cappedFindings(nl.findings, MAX_FINDINGS);
  const sp = sessionPath(project);
  return (
    <div className="ni" data-testid="node-inspector">
      <div className="ni-head">
        <h3 className="ni-title">{nodeTitle(n)}</h3>
        {/* the kind when the title is not it (a map's title is its map); the id when it says more */}
        {nodeTitle(n) !== KIND_TITLE[n.kind] && <span className="ni-kind">{KIND_TITLE[n.kind]}</span>}
        {n.id !== (n.kind === "map" ? n.map.map : n.kind) ? <span className="ni-muted">node {n.id}</span> : null}
      </div>
      <p className="ni-muted">{whereText(n, project, sp)}</p>
      <div className="button-row">
        {canOpen && (
          <button type="button" className="button button-small button-primary" onClick={() => onOpen(n.id)} data-testid="inspector-open">
            Open flow ↗
          </button>
        )}
        {onSimulate && (n.kind === "map" || n.kind === "login") && (
          <button type="button" className="button button-small" onClick={() => onSimulate(n.id)} data-testid="inspector-simulate">
            Simulate from here
          </button>
        )}
        {(n.kind === "map" || n.kind === "login") && project.start !== n.id && (
          <button
            type="button"
            className="button button-small"
            onClick={() => (props.onStart ? props.onStart(n.id) : apply(setStart(project, n.id)))}
            title={n.kind === "map" ? `The run starts on ${n.id}, where a person puts her (no login, no character): START moves here` : "The run starts with this login node (the session path: login → character → a map)"}
            data-testid="inspector-start-here"
          >
            Start here
          </button>
        )}
      </div>
      {error && error.for === n.id && (
        <p className="ni-error" role="alert" data-testid="inspector-error">
          {error.text}
        </p>
      )}
      {ll && (
        <section className="ni-section" aria-label="Lint">
          <h4>
            Lint: <span className={ll.level === "ok" ? "ni-ok" : undefined}>{ll.text}</span>
          </h4>
          {capped.shown.length > 0 && (
            // matpilot round 17 N2: the most serious first, each line labelled; the rest in words
            <ul className="ni-findings" data-testid="inspector-findings">
              {capped.shown.map((f, i) => (
                <li key={`${f.path}-${f.rule}-${i}`} data-level={f.severity}>
                  <strong>{SEVERITY_WORDS[f.severity]}</strong> · {findingWhere(f)}
                  {f.text || f.message}
                </li>
              ))}
              {capped.more && <li data-testid="inspector-findings-more">{capped.more}</li>}
            </ul>
          )}
        </section>
      )}
      {n.kind !== "global" && <RenameRow key={`rename-${n.id}`} project={project} node={n} apply={apply} onRenamed={props.onRenamed} />}
      {n.kind === "login" && <LoginSection project={project} node={n} credentials={props.credentials} apply={apply} />}
      {n.kind === "character" && <CharacterSection key={`ch-${n.id}-${characterOf(n).name}`} project={project} node={n} apply={apply} />}
      {n.kind === "map" && <MapSection key={`map-${n.id}-${JSON.stringify([n.map, n.entries, n.targets, n.ignore, n.resume_here])}`} project={project} node={n} lint={lint} apply={apply} onZones={props.onZones} />}
      {n.kind === "global" && (
        <section className="ni-section" aria-label="Shared by every node">
          <h4>Shared by every node</h4>
          <p className="ni-muted">Every node imports Global&apos;s tabs, and main imports its own node&apos;s tabs. A node&apos;s own function, event or variable of the same name OVERRIDES Global&apos;s on that node (everywhere there, Global&apos;s own functions included).</p>
          <GlobalRule project={project} onRules={onRules} />
        </section>
      )}
      <TabsSection project={project} node={n} lint={lint} />
      {n.kind === "map" && <DeleteRow key={`del-${n.id}`} project={project} node={n} apply={apply} />}
    </div>
  );
}

function whereText(n: PNode, p: Project, sp: ReturnType<typeof sessionPath>): string {
  if (n.kind === "login") return p.start === n.id ? "Simulate starts here: the session logs in, then the character node chooses, then the start map." : "Not the project's start (START is elsewhere): its session is not played.";
  if (n.kind === "character") return sp.character?.id === n.id && sp.map ? `The session enters the game on ${sp.map.id}${sp.entry ? ` (entry ${sp.entry})` : ""}.` : "Not connected to a map yet: drag from its right port onto a map's entry.";
  if (n.kind === "global") return "Global has no main and no connections: the user makes its tabs.";
  if (p.start === n.id) return `START: the run starts here, where a person put her${sp.entry ? ` (the entry ${sp.entry})` : ""}; no login, no character. Run on /maps plays from here, box by box.`;
  return sp.map?.id === n.id ? `The session enters the game here${sp.entry ? `, at the entry ${sp.entry}` : ""}: the first map.` : "A map the run reaches by an exit (or none yet).";
}

function RenameRow({ project, node, apply, onRenamed }: { project: Project; node: PNode; apply: (r: Edit) => void; onRenamed?: (from: string, to: string) => void }) {
  const [to, setTo] = useState(node.id);
  const why = to === node.id ? null : renameProblem(project, node.id, to);
  return (
    <form
      className="ni-row"
      onSubmit={(e) => {
        e.preventDefault();
        if (why || to === node.id) return;
        const r = renameNode(project, node.id, to);
        apply(r);
        if (r.ok) onRenamed?.(node.id, to);
      }}
    >
      <label>
        id
        <input value={to} onChange={(e) => setTo(e.target.value)} maxLength={48} aria-invalid={why !== null} data-testid="inspector-id" />
      </label>
      <button type="submit" className="button button-small" disabled={why !== null || to === node.id} title={why ?? "Rename: its connections and every exit that names it follow"}>
        Rename
      </button>
      {why && <span className="ni-error">{why}</span>}
    </form>
  );
}

function LoginSection({ project, node, credentials, apply }: { project: Project; node: PNode; credentials?: readonly string[]; apply: (r: Edit) => void }) {
  const l = loginOf(node);
  const names = [...new Set([...(credentials ?? CREDENTIALS.map((c) => c.name)), ...(l.credential ? [l.credential] : [])])].filter((c) => CREDENTIAL_NAME.test(c));
  const server = l.server ?? "lab-rathena";
  const credential = l.credential ?? names[0] ?? "lab_gm";
  return (
    <section className="ni-section" aria-label="The login">
      <h4>What its main says</h4>
      <p data-testid="inspector-login-words">{loginWords(node)}</p>
      <p className="ni-muted">
        A credential is a NAME (n8n&apos;s way): its id and password stay in the server&apos;s .env ({credentialOf(credential)?.env ?? "a credential the lab does not know"}). This page never asks for, stores or shows them. This round Simulate plays the login; the bot&apos;s real login is scripts/ro_agent.py.
      </p>
      <fieldset className="ni-section" style={{ border: 0, padding: 0 }}>
        <legend className="ni-muted">Server</legend>
        {SERVERS.map((s) => (
          <label key={s.id} className="ni-choice" data-disabled={!s.automatable}>
            <input type="radio" name={`server-${node.id}`} checked={server === s.id} disabled={!s.automatable} onChange={() => apply(setLogin(project, node.id, { server: s.id, credential }))} />
            <span>
              <strong>{s.title}</strong> <span className="ni-muted">· {s.status}</span>
              <span className="ni-why">{s.automatable ? s.why : `Not selectable: ${s.why}.`}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <label className="ni-field">
        Credential (a name)
        <select value={credential} onChange={(e) => apply(setLogin(project, node.id, { server, credential: e.target.value }))} data-testid="inspector-credential">
          {names.map((c) => (
            <option key={c} value={c}>
              {c}
              {credentialOf(c) ? ` (${credentialOf(c)?.title})` : ""}
            </option>
          ))}
        </select>
      </label>
    </section>
  );
}

function CharacterSection({ project, node, apply }: { project: Project; node: PNode; apply: (r: Edit) => void }) {
  const c = characterOf(node);
  const [name, setName] = useState(c.name);
  const bad = name !== "" && !CHAR_NAME.test(name);
  return (
    <section className="ni-section" aria-label="The character">
      <h4>What its main says</h4>
      <p data-testid="inspector-character-words">{characterWords(node)}</p>
      <label className="ni-field">
        Slot
        <select value={c.slot === null ? "" : String(c.slot)} onChange={(e) => apply(setCharacter(project, node.id, { slot: e.target.value === "" ? null : Number(e.target.value), name: c.name }))} data-testid="inspector-slot">
          <option value="">the remembered slot (as the bot does)</option>
          {Array.from({ length: MAX_SLOT }, (_, i) => i + 1).map((k) => (
            <option key={k} value={k}>
              slot {k} (selected first, by hand)
            </option>
          ))}
        </select>
      </label>
      <form
        className="ni-row"
        onSubmit={(e) => {
          e.preventDefault();
          if (!bad) apply(setCharacter(project, node.id, { slot: c.slot, name }));
        }}
      >
        <label>
          Character name (optional)
          <input value={name} maxLength={23} placeholder="the account's own character" onChange={(e) => setName(e.target.value)} aria-invalid={bad} />
        </label>
        <button type="submit" className="button button-small" disabled={bad || name === c.name}>
          Set
        </button>
      </form>
      <p className={bad ? "ni-error" : "ni-muted"}>{bad ? "Letters, digits, spaces and _ only, at most 23." : "The character that slot holds, when it is not the account's own: enter_game checks it is one of the account's characters."}</p>
    </section>
  );
}

type EntryForm = { name: string; x: string; y: string; radius: string };
const idsText = (ms: MobRef[]) => ms.map((m) => m.id).join(", ");

function parseIds(text: string): MobRef[] | null {
  const parts = text.split(/[\s,]+/).filter(Boolean);
  const out: MobRef[] = [];
  for (const p of parts) {
    if (!/^\d{1,6}$/.test(p)) return null;
    out.push({ kind: "mob", id: Number(p) });
  }
  return out;
}

function MapSection({ project, node, lint, apply, onZones }: { project: Project; node: MapNode; lint: LintDoc | null; apply: (r: Edit) => void; onZones?: (id: string) => void }) {
  const [map, setMap] = useState(node.map.map);
  const [entries, setEntries] = useState<EntryForm[]>(() => node.entries.map((e) => ({ name: e.name, x: e.at ? String(e.at.x) : "", y: e.at ? String(e.at.y) : "", radius: String(e.radius) })));
  const [targets, setTargets] = useState(idsText(node.targets));
  const [ignore, setIgnore] = useState(idsText(node.ignore));
  const [resume, setResume] = useState(node.resume_here);
  const links = nodeLinks(project, node.id);
  const rs = runnerSpecies(node, lint);
  const t = parseIds(targets);
  const ig = parseIds(ignore);
  const setEntry = (i: number, v: Partial<EntryForm>) => setEntries(entries.map((e, k) => (k === i ? { ...e, ...v } : e)));
  const submit = () => {
    if (!t || !ig) return;
    const out: Entry[] = [];
    for (const e of entries) {
      const anywhere = e.x.trim() === "" && e.y.trim() === "";
      const x = Number(e.x);
      const y = Number(e.y);
      out.push({ name: e.name.trim(), at: anywhere ? null : { kind: "cell", map, x: Number.isInteger(x) ? x : NaN, y: Number.isInteger(y) ? y : NaN }, radius: Number(e.radius) });
    }
    apply(updateMapNode(project, node.id, { map: { kind: "map", map: map.trim() }, entries: out, targets: t, ignore: ig, resume_here: resume }));
  };
  return (
    <section className="ni-section" aria-label="The map node">
      <h4>The map</h4>
      <form
        className="ni"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <label className="ni-field">
          map id
          <input value={map} onChange={(e) => setMap(e.target.value)} maxLength={40} data-testid="inspector-map" />
        </label>
        <div>
          <div className="ni-muted">Entries: how the character arrives (a cell and a radius; no cell = anywhere)</div>
          <table className="ni-entries">
            <thead>
              <tr>
                <th>name</th>
                <th>x</th>
                <th>y</th>
                <th>±</th>
                <th>
                  <span className="sr-only">remove</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e, i) => (
                <tr key={i}>
                  <td>
                    <input value={e.name} onChange={(ev) => setEntry(i, { name: ev.target.value })} maxLength={48} aria-label={`entry ${i + 1} name`} />
                  </td>
                  <td>
                    <input className="ni-num" value={e.x} onChange={(ev) => setEntry(i, { x: ev.target.value })} inputMode="numeric" maxLength={4} aria-label={`entry ${i + 1} x`} />
                  </td>
                  <td>
                    <input className="ni-num" value={e.y} onChange={(ev) => setEntry(i, { y: ev.target.value })} inputMode="numeric" maxLength={4} aria-label={`entry ${i + 1} y`} />
                  </td>
                  <td>
                    <input className="ni-num" value={e.radius} onChange={(ev) => setEntry(i, { radius: ev.target.value })} inputMode="numeric" maxLength={2} aria-label={`entry ${i + 1} radius`} />
                  </td>
                  <td>
                    <button type="button" className="button button-small" onClick={() => setEntries(entries.filter((_, k) => k !== i))} disabled={entries.length === 1} aria-label={`Remove the entry ${e.name || i + 1}`} title="Remove this entry">
                      ×
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button type="button" className="button button-small" onClick={() => setEntries([...entries, { name: `entry${entries.length + 1}`, x: "", y: "", radius: "2" }])}>
            + entry
          </button>
          {links && (
            <ul className="ni-names">
              {links.entries.map((e) => (
                <li key={e.name}>
                  {e.name}: {entryCaption(e)}
                </li>
              ))}
            </ul>
          )}
        </div>
        <label className="ni-field">
          targets (monster ids)
          <input value={targets} onChange={(e) => setTargets(e.target.value)} aria-invalid={t === null} placeholder="e.g. 1002, 1063" />
        </label>
        <label className="ni-field">
          ignore (monster ids)
          <input value={ignore} onChange={(e) => setIgnore(e.target.value)} aria-invalid={ig === null} />
        </label>
        {rs && (
          // matpilot round 17 N3: on a node that runs the runner these lists are not what it strikes
          <div className="ni-muted" data-testid="inspector-runner-targets">
            {rs.words}
            {rs.lines.length > 0 && (
              <ul className="ni-names">
                {rs.lines.map((l, i) => (
                  <li key={i}>{l}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        <label className="ni-field ni-check">
          <input type="checkbox" checked={resume} onChange={(e) => setResume(e.target.checked)} />
          resume here (a relocation onto this map carries on with this node)
        </label>
        <div className="button-row">
          <button type="submit" className="button button-small button-primary" disabled={!t || !ig} data-testid="inspector-apply">
            Apply
          </button>
        </div>
      </form>
      <div className="ni-field">
        zones
        <span data-testid="inspector-zones">{node.zones ? `config/map_zones/${node.zones.map}.yaml, sha256 ${node.zones.sha256.slice(0, 12)}…` : "none (the runner's whole-map defaults)"}</span>
        <div className="button-row">
          {onZones && (
            <button type="button" className="button button-small" onClick={() => onZones(node.id)}>
              {node.zones ? "Edit the zones…" : "Zones…"}
            </button>
          )}
          {node.zones && (
            <button type="button" className="button button-small" onClick={() => apply(setZones(project, node.id, null))}>
              Remove the reference
            </button>
          )}
        </div>
      </div>
    </section>
  );
}

function GlobalRule({ project, onRules }: { project: Project; onRules?: () => void }) {
  const r = readRules(project);
  return (
    <p>
      On any other map:{" "}
      {r.custom ? `Global's own unexpected_map event (its tab ${r.tab})` : r.unknownMap === "wing" ? `${wingText(r.wingItem)} back to the save point (the event unexpected_map, tab ${r.tab})` : "the run stops (the built-in)"}
      {r.overriddenOn.length ? `; overridden on ${r.overriddenOn.join(", ")}` : ""}.{" "}
      {onRules && (
        <button type="button" className="button button-small" onClick={onRules} data-testid="inspector-rules">
          World rules
        </button>
      )}
    </p>
  );
}

function TabsSection({ project, node, lint }: { project: Project; node: PNode; lint: LintDoc | null }) {
  const tabs = tabRows(project, node);
  const box = lint?.box?.[node.id] ?? null; // matpilot round 17 N1: what the box plays in a Run
  return (
    <section className="ni-section" aria-label="Tabs and names">
      <h4>Tabs and names</h4>
      {node.kind === "global" ? (
        <p className="ni-muted">“overridden on” lists the nodes whose own name of the same name runs there instead.</p>
      ) : (
        <p className="ni-muted">
          One namespace for the whole node; main imports every tab and Global. A FUNCTION is a named list of steps any tab of the node can call; an EVENT is a function with a trigger. “overrides Global” marks a name Global has too: this node&apos;s runs here. “presses” is the one key a function presses here.
        </p>
      )}
      {tabs.length === 0 && <p className="ni-muted">No tabs yet.</p>}
      {/* matpilot round 20 #6: 162 raw lines (about 10 screens): each tab FOLDS, folded by default,
          its line saying what it holds; a setting shows its value as its block does, and one that
          differs from our default comes first, marked */}
      {tabs.map((t) => (
        <details key={t.tab} className="ni-tab" data-testid={`inspector-tab-${t.tab}`}>
          <summary className="ni-tab-summary">
            <span className="ni-tab-name">{t.tab}</span>
            <span className="ni-muted"> · {tabSummary(t)}</span>
          </summary>
          {t.rows.length > 0 ? (
            <ul className="ni-names">
              {t.rows.map((x) => (
                <li key={x.name} data-setting={x.setting ? (x.setting.changed ? "changed" : "default") : undefined}>
                  {x.text}
                  {x.setting && <span className="ni-muted"> · {x.setting.var}</span>}
                  {x.setting?.changed && (
                    <span className="ni-mark" data-k="changed" title="Not our default: this block was set to another value">
                      changed
                    </span>
                  )}
                  {x.kind === "event" && <span className="ni-mark" data-k="event">event</span>}
                  {boxNameWords(box, `${node.id}/${t.tab}/${x.name}`) && (
                    <span className="ni-muted" data-testid={`inspector-box-${x.name}`}>
                      {" "}
                      · {boxNameWords(box, `${node.id}/${t.tab}/${x.name}`)}
                    </span>
                  )}
                  {x.key && (
                    <span className="ni-mark" data-k="key" title="The one key this function presses on this node">
                      presses {x.key}
                    </span>
                  )}
                  {x.clash.length > 0 && (
                    <span className="ni-mark" data-k="overrides" title="Two functions press the same key here">
                      {x.key} also {x.clash.join(", ")}
                    </span>
                  )}
                  {x.overrides && <span className="ni-mark" data-k="overrides">overrides Global</span>}
                  {x.overriddenOn.length > 0 && (
                    <span className="ni-mark" data-k="overridden">
                      overridden on {x.overriddenOn.join(", ")}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            !t.main && <div className="ni-muted">empty</div>
          )}
        </details>
      ))}
    </section>
  );
}

function DeleteRow({ project, node, apply }: { project: Project; node: MapNode; apply: (r: Edit) => void }) {
  const [asking, setAsking] = useState(false);
  const r = removeNode(project, node.id);
  const dangling = r.ok ? (r.dangling ?? 0) : 0;
  return (
    <section className="ni-section" aria-label="Delete">
      {asking ? (
        <div className="ni-row">
          <span>
            Delete {node.id} and its connections?{dangling ? ` ${dangling} exit${dangling === 1 ? "" : "s"} of other maps go${dangling === 1 ? "es" : ""} to it and will point nowhere.` : ""}
          </span>
          <button type="button" className="button button-small button-primary" onClick={() => apply(r)} data-testid="inspector-delete-yes">
            Delete
          </button>
          <button type="button" className="button button-small" onClick={() => setAsking(false)}>
            Keep it
          </button>
        </div>
      ) : (
        <button type="button" className="button button-small" onClick={() => setAsking(true)} disabled={!r.ok} data-testid="inspector-delete">
          Delete this map node…
        </button>
      )}
    </section>
  );
}
