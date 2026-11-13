"use client";

// Loads the flow editor in the browser only (it reads window.location for the backend's address,
// as the console does) and keeps its code out of every other page's bundle.
//
// It also switches to a RUNNER FLOW (2026-11-12, lib/flow/runner.ts): `?runner=<id or map>`, the
// Load menu, a map block's "how the bot hunts here", or `?block=<map>` when the flow has no such
// block. That view is a description of a live runner: display + SIMULATE only, no backend call.
import dynamic from "next/dynamic";
import { useCallback, useState } from "react";

import { findRunner, runnerHref } from "@/lib/flow/runners";

const FlowsApp = dynamic(() => import("@/components/flows/FlowsApp"), {
  ssr: false,
  loading: () => <div className="flex-1 p-4 text-sm text-neutral-400">Loading the flow studio…</div>,
});
const RunnerView = dynamic(() => import("@/components/flows/RunnerView"), {
  ssr: false,
  loading: () => <div className="flex-1 p-4 text-sm text-neutral-400">Loading the runner&apos;s flow…</div>,
});

export default function FlowsClient({ backendUrl, initialBlock = null, initialRunner = null }: { backendUrl: string | null; initialBlock?: string | null; initialRunner?: string | null }) {
  const [runner, setRunner] = useState<string | null>(() => findRunner(initialRunner)?.id ?? null);
  // `?block=` is used once: back from a runner flow, the studio opens as usual (not the runner again)
  const [block, setBlock] = useState<string | null>(initialRunner ? null : initialBlock);
  const open = useCallback((id: string | null) => {
    const doc = findRunner(id);
    setBlock(null);
    setRunner(doc?.id ?? null);
    try {
      window.history.replaceState(null, "", doc ? runnerHref(doc) : "/flows");
    } catch {
      // the address bar keeps the old link: the view is right anyway
    }
  }, []);
  const doc = findRunner(runner);
  if (doc) return <RunnerView key={doc.id} doc={doc} onBack={() => open(null)} onRunner={open} backendUrl={backendUrl} />;
  return <FlowsApp backendUrl={backendUrl} initialBlock={block} onRunner={open} />;
}
