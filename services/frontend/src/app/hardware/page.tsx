import type { Metadata } from "next";
import { connection } from "next/server";

import HardwareMonitor from "@/components/HardwareMonitor";
import NavBar from "@/components/NavBar";

export const metadata: Metadata = {
  title: "poring-lab hardware",
  description: "CPU, memory, GPU, temperatures and power of the lab host (read-only)",
};

/** Hardware (Batt, 2026-11-08): the lab host's CPU, RAM, GPU, temperatures and power, from the
 * backend's GET /hardware (public listener only; the agent never gets it). Nothing here sends input. */
export default async function Page() {
  // Dynamic rendering, as the console: BACKEND_PUBLIC_URL is read at request time.
  await connection();
  const backendUrl = process.env.BACKEND_PUBLIC_URL ?? null;
  return (
    <>
      <NavBar backendUrl={backendUrl} />
      <HardwareMonitor backendUrl={backendUrl} />
    </>
  );
}
