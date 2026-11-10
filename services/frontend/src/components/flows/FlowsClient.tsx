"use client";

// Loads the flow editor in the browser only (it reads window.location for the backend's address,
// as the console does) and keeps its code out of every other page's bundle.
import dynamic from "next/dynamic";

const FlowsApp = dynamic(() => import("@/components/flows/FlowsApp"), {
  ssr: false,
  loading: () => <div className="flex-1 p-4 text-sm text-neutral-400">Loading the flow studio…</div>,
});

export default function FlowsClient({ backendUrl, initialBlock = null }: { backendUrl: string | null; initialBlock?: string | null }) {
  return <FlowsApp backendUrl={backendUrl} initialBlock={initialBlock} />;
}
