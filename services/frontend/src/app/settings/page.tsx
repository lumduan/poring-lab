import { connection } from "next/server";

import NavBar from "@/components/NavBar";
import RunIdentitySettings from "@/components/RunIdentitySettings";
import RunLogSettings from "@/components/RunLogSettings";
import ServerSettings from "@/components/ServerSettings";

/** Settings (Batt, 2026-10-06): the servers the bot may act on, confirmed by a human. Only this
 * page (a browser on the LAN, the console's own origin) can change them; the bot can only read.
 * Since 2026-11-19 (ADR-0020 Amendment R) also who may play a Run: the mode and the characters
 * remembered here. Since 2026-11-21 (Batt) also the Run log: "What she does" kept as history. */
export default async function Page() {
  // Dynamic rendering, as the console: BACKEND_PUBLIC_URL is read at request time.
  await connection();
  const backendUrl = process.env.BACKEND_PUBLIC_URL ?? null;
  return (
    <>
      <NavBar backendUrl={backendUrl} />
      <RunIdentitySettings backendUrl={backendUrl} />
      <RunLogSettings backendUrl={backendUrl} />
      <ServerSettings backendUrl={backendUrl} />
    </>
  );
}
