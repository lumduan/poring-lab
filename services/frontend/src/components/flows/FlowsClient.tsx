"use client";

// Loads the flow editor in the browser only (it reads window.location for the backend's address,
// as the console does) and keeps its code out of every other page's bundle.
import dynamic from "next/dynamic";

const FlowsApp = dynamic(() => import("@/components/flows/FlowsApp"), {
  ssr: false,
  loading: () => <div className="p-4 text-sm text-neutral-400">Loading the flow editor…</div>,
});

export default function FlowsClient({ backendUrl }: { backendUrl: string | null }) {
  return <FlowsApp backendUrl={backendUrl} />;
}
