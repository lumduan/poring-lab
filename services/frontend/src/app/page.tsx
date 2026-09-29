import { connection } from "next/server";

import Console from "@/components/Console";

export default async function Page() {
  // Dynamic rendering: BACKEND_PUBLIC_URL is read at request time, so one image works on any host.
  // Unset -> the browser derives ws://<this page's hostname>:8000.
  await connection();
  return <Console backendUrl={process.env.BACKEND_PUBLIC_URL ?? null} />;
}
