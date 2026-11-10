import type { Metadata } from "next";
import { connection } from "next/server";

import FlowsClient from "@/components/flows/FlowsClient";
import NavBar from "@/components/NavBar";

export const metadata: Metadata = {
  title: "poring-lab flows",
  description: "The block programming studio: blocks with their Python side by side, lint and SIMULATE over the flow IR",
};

/** Flows (MW2, Batt 2026-10-08; the studio layout of matpilot.org/blocks since 2026-11-09):
 * edit, lint and SIMULATE block programs. No live run: nothing on this page reaches the executor,
 * the mux or any input path. The column gives the studio the window's height under the NavBar.
 * `?block=<name>` opens that map block's tab (the Maps page's "Open flow", 2026-11-10). */
export default async function Page(props: PageProps<"/flows">) {
  // Dynamic rendering, as the console: BACKEND_PUBLIC_URL is read at request time.
  await connection();
  const backendUrl = process.env.BACKEND_PUBLIC_URL ?? null;
  const block = (await props.searchParams).block;
  return (
    <div className="flex h-dvh flex-col">
      <NavBar backendUrl={backendUrl} />
      <FlowsClient backendUrl={backendUrl} initialBlock={typeof block === "string" && block.length <= 48 ? block : null} />
    </div>
  );
}
