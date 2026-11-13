"use client";

// THE LINT LIST of the Maps page (matpilot round 16 #7, 2026-11-14): the lint chip opens it in the
// side panel. The chip counts EVERY finding of the project lint; the cards show only a node's, so
// a finding on the project itself ("a death returns to the save point on geffen, where no block
// is") was counted and shown nowhere on the page. Here: the project's own first, then each node's,
// grouped by lib/maps/nodewords.ts lintGroups (the cards' own rule), so what this list shows adds
// up to the chip. Text only: every finding is rendered as React text.
import "./inspector.css";

import type { Finding, LintDoc } from "@/lib/flow/api";
import { sitePath } from "@/lib/flow/api";
import { nodeById, type Project } from "@/lib/flow/project";
import { lintLine } from "@/lib/flow/status";
import { lintGroups, nodeTitle } from "@/lib/maps/nodewords";

const SEVERITY_WORDS: Record<Finding["severity"], string> = { error: "error", warning: "warning", info: "info", readiness: "not ready" };

/** Where a finding is inside its node ("main main.0: "), or "" for the node or the project itself. */
function whereText(f: Finding): string {
  if (!f.tab) return "";
  const site = sitePath(f);
  return `${f.tab}${site && site !== f.path ? ` ${site}` : ""}: `;
}

export default function LintList({ lint, project, stale, onSelect }: { lint: LintDoc | null; project: Project; stale: boolean; onSelect: (id: string) => void }) {
  if (!lint) return <p className="ni-muted">The lint has not answered yet.</p>;
  const groups = lintGroups(lint, project);
  return (
    <div className="stack" data-testid="maps-lint">
      <h3 className="mp-panel-title">
        Lint: {lintLine(lint.counts).text}
        {stale ? " (checking…)" : ""}
      </h3>
      <p className="muted">Every finding the lint chip counts: the project&apos;s own (on no node, so no card shows it) first, then each node&apos;s, as its card counts them. /flows&apos; Lint pane lists the same beside the blocks.</p>
      {groups.length === 0 && <p className="ni-ok">No findings.</p>}
      {groups.map((g) => {
        const n = g.node !== null ? nodeById(project, g.node) : undefined;
        return (
          <section key={g.node ?? ""} className="ni-section" aria-label={g.node === null ? "The project's own findings" : `The findings on ${g.node}`} data-testid={`maps-lint-${g.node ?? "project"}`}>
            <h4>
              {g.node === null ? (
                "The project (on no node)"
              ) : (
                <button type="button" className="problem-link" onClick={() => onSelect(g.node as string)} title={`Select ${g.node} (its card and its inspector)`}>
                  {n ? nodeTitle(n) : g.node}
                  {n && n.id !== (n.kind === "map" ? n.map.map : n.kind) ? ` (node ${n.id})` : ""}
                </button>
              )}{" "}
              · {lintLine(g.counts).text}
            </h4>
            <ul className="ni-findings">
              {g.findings.map((f, i) => (
                <li key={`${f.path}-${f.rule}-${i}`} data-level={f.severity}>
                  <strong>{SEVERITY_WORDS[f.severity]}</strong> · {whereText(f)}
                  {f.text || f.message}
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
