import { connection } from "next/server";

import NavBar from "@/components/NavBar";
import QaViewer from "@/components/QaViewer";

/** Phase 2 label QA (docs/phase2-plan.md): recorded frames with their auto-labels, for a human
 * visual check, and the B6 hand-check editor that saves corrections to the backend. Reads the
 * dev-only /api/qa bundle route; nothing here reaches the agent. */
export default async function Page() {
  // Dynamic rendering, as the console: BACKEND_PUBLIC_URL is read at request time.
  await connection();
  const backendUrl = process.env.BACKEND_PUBLIC_URL ?? null;
  return (
    <>
      <NavBar backendUrl={backendUrl} />
      <QaViewer backendUrl={backendUrl} />
    </>
  );
}
