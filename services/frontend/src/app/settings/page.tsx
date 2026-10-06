import { connection } from "next/server";

import NavBar from "@/components/NavBar";
import ServerSettings from "@/components/ServerSettings";

/** Settings (Batt, 2026-10-06): the servers the bot may act on, confirmed by a human. Only this
 * page (a browser on the LAN, the console's own origin) can change them; the bot can only read. */
export default async function Page() {
  // Dynamic rendering, as the console: BACKEND_PUBLIC_URL is read at request time.
  await connection();
  const backendUrl = process.env.BACKEND_PUBLIC_URL ?? null;
  return (
    <>
      <NavBar backendUrl={backendUrl} />
      <ServerSettings backendUrl={backendUrl} />
    </>
  );
}
