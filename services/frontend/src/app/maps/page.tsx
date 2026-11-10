import type { Metadata } from "next";
import { connection } from "next/server";

import MapsClient from "@/components/maps/MapsClient";
import NavBar from "@/components/NavBar";

export const metadata: Metadata = {
  title: "poring-lab maps",
  description: "The flow as a graph of maps (login, character, the maps and their exits), each map bound to its flow, and a simulator that walks the bot on the maps",
};

/** Maps (Batt 2026-11-10, docs/planning/world-map-flows.md): START -> Login -> Choose character
 * (MOCKS) -> the flow's map nodes, each bound to its flow, and SIMULATE on the maps' walk grids. No
 * live run: nothing on this page reaches the executor, the mux or any input path. `?node=` selects
 * a node (block:<name>, login, character) when the page opens. */
export default async function Page(props: PageProps<"/maps">) {
  // Dynamic rendering, as the console: BACKEND_PUBLIC_URL is read at request time.
  await connection();
  const backendUrl = process.env.BACKEND_PUBLIC_URL ?? null;
  const node = (await props.searchParams).node;
  return (
    <div className="flex h-dvh flex-col">
      <NavBar backendUrl={backendUrl} />
      <MapsClient backendUrl={backendUrl} initialNode={typeof node === "string" && node.length <= 64 ? node : null} />
    </div>
  );
}
