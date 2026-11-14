"use client";

// Loads the flow editor in the browser only (it reads window.location for the backend's address,
// as the console does) and keeps its code out of every other page's bundle.
//
// ➡️ 2026-11-14 ~15:2x (Batt: "there should be no runner [page] ... everything in the xmas_dun02
// flow, split into tabs"; docs/planning/live-blocks.md section 12): the runner page
// (`?runner=<id or map>`, RunnerView) is gone; every setting it showed is a block in the map node's
// tabs. An old `?runner=` link opens that map's node of the project (page.tsx).
import dynamic from "next/dynamic";

const ProjectStudio = dynamic(() => import("@/components/flows/ProjectStudio"), {
  ssr: false,
  loading: () => <div className="flex-1 p-4 text-sm text-neutral-400">Loading the flow studio…</div>,
});

export default function FlowsClient({ backendUrl, initialBlock = null }: { backendUrl: string | null; initialBlock?: string | null }) {
  return <ProjectStudio backendUrl={backendUrl} initialNode={initialBlock} />;
}
