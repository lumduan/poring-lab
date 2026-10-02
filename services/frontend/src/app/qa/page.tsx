import QaViewer from "@/components/QaViewer";

/** Phase 2 label QA (docs/phase2-plan.md): recorded frames with their auto-labels, for a human
 * visual check. Reads the dev-only /api/qa bundle route; nothing here reaches the agent. */
export default function Page() {
  return <QaViewer />;
}
