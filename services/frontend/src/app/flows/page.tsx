import type { Metadata } from "next";
import { connection } from "next/server";

import FlowsClient from "@/components/flows/FlowsClient";
import NavBar from "@/components/NavBar";

export const metadata: Metadata = {
  title: "poring-lab flows",
  description: "The block programming studio: one node of the project at a time, its tabs as blocks with their Python side by side; lint, SIMULATE, and Run on a map with the runner",
};

/** Flows (MW2, Batt 2026-10-08; the studio layout of matpilot.org/blocks since 2026-11-09):
 * edit, lint and SIMULATE block programs. No live run: nothing on this page reaches the executor,
 * the mux or any input path. The column gives the studio the window's height under the NavBar.
 * `?node=<id>` opens that node of the project (the Maps page's double-click; the project model,
 * 2026-11-13: one node's tabs, one main); `?block=<id>` is the older spelling of the same.
 * `?runner=<id or map>` opens a RUNNER FLOW (2026-11-12): the generated description of a live
 * runner, e.g. `?runner=xmas_dun02` (the Rogue's dungeon_hunt.py); display + SIMULATE only. */
export default async function Page(props: PageProps<"/flows">) {
  // Dynamic rendering, as the console: BACKEND_PUBLIC_URL is read at request time.
  await connection();
  const backendUrl = process.env.BACKEND_PUBLIC_URL ?? null;
  const { block, node, runner } = await props.searchParams;
  const want = typeof node === "string" ? node : block;
  return (
    <div className="flex h-dvh flex-col">
      <NavBar backendUrl={backendUrl} />
      <FlowsClient
        backendUrl={backendUrl}
        initialBlock={typeof want === "string" && want.length <= 48 ? want : null}
        initialRunner={typeof runner === "string" && runner.length <= 64 ? runner : null}
      />
    </div>
  );
}
