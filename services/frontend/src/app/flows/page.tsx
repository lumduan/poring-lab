import type { Metadata } from "next";
import { connection } from "next/server";

import FlowsClient from "@/components/flows/FlowsClient";
import NavBar from "@/components/NavBar";

export const metadata: Metadata = {
  title: "poring-lab flows",
  description: "The block programming studio: one node of the project at a time, its tabs as blocks with their Python side by side; every runner setting a block; lint, SIMULATE, and Run on a map with the runner",
};

/** The old runner page's flow ids, each the map whose node it opens now (2026-11-14). */
const RUNNER_IDS: Record<string, string> = { xmas_dun02_rogue: "xmas_dun02" };

/** Flows (MW2, Batt 2026-10-08; the studio layout of matpilot.org/blocks since 2026-11-09):
 * edit, lint and SIMULATE block programs, and Run a map node in the game (the live block player).
 * The column gives the studio the window's height under the NavBar. `?node=<id>` opens that node
 * of the project (the Maps page's double-click; the project model, 2026-11-13: one node's tabs,
 * one main); `?block=<id>` is the older spelling of the same. ➡️ 2026-11-14 (Batt: "there should be
 * no runner [page]"; live-blocks.md 12): `?runner=<id or map>` opened the runner's description; it
 * opens that MAP's node now (`?runner=xmas_dun02` -> the node on xmas_dun02), never a 404. */
export default async function Page(props: PageProps<"/flows">) {
  // Dynamic rendering, as the console: BACKEND_PUBLIC_URL is read at request time.
  await connection();
  const backendUrl = process.env.BACKEND_PUBLIC_URL ?? null;
  const { block, node, runner } = await props.searchParams;
  const old = typeof runner === "string" && runner.length <= 64 ? (RUNNER_IDS[runner] ?? runner) : undefined;
  const want = typeof node === "string" ? node : typeof block === "string" ? block : old;
  return (
    <div className="flex h-dvh flex-col">
      <NavBar backendUrl={backendUrl} />
      <FlowsClient backendUrl={backendUrl} initialBlock={typeof want === "string" && want.length <= 48 ? want : null} />
    </div>
  );
}
