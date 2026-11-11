import type { Metadata } from "next";
import { connection } from "next/server";

import EconomyDashboard from "@/components/EconomyDashboard";
import NavBar from "@/components/NavBar";

export const metadata: Metadata = {
  title: "poring-lab economy",
  description: "A run's business results at fixed NPC prices: income, kills, drops, consumables and the P&L per hour (read-only)",
};

/** Economy (Batt, 2026-11-11: "a dashboard page of business results (P&L)", course material too):
 * the exports of scripts/econ_dash.py from the backend's GET /economy/* (read-only, public listener
 * only). Edited prices stay in the browser. Nothing here sends input. */
export default async function Page() {
  // Dynamic rendering, as the console: BACKEND_PUBLIC_URL is read at request time.
  await connection();
  const backendUrl = process.env.BACKEND_PUBLIC_URL ?? null;
  return (
    <>
      <NavBar backendUrl={backendUrl} />
      <EconomyDashboard backendUrl={backendUrl} />
    </>
  );
}
