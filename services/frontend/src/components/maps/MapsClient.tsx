"use client";

// Loads the Maps page in the browser only (it reads window.location for the backend's address and
// this browser's saved project, as /flows does) and keeps its code out of every other page's bundle.
import dynamic from "next/dynamic";

const MapsApp = dynamic(() => import("@/components/maps/MapsApp"), {
  ssr: false,
  loading: () => <div className="flex-1 p-4 text-sm text-neutral-400">Loading the maps…</div>,
});

export default function MapsClient({ backendUrl, initialNode }: { backendUrl: string | null; initialNode: string | null }) {
  return <MapsApp backendUrl={backendUrl} initialNode={initialNode} />;
}
