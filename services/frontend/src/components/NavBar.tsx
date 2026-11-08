"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import ModeBadge from "@/components/ModeBadge";
import type { InterlockLike } from "@/lib/mode";
import type { Mode } from "@/lib/protocol";
import { backendHttpBase } from "@/lib/ws";

const LINKS = [
  { href: "/", label: "Console" },
  { href: "/settings", label: "Settings" },
  { href: "/qa", label: "Label QA" },
  { href: "/hardware", label: "Hardware" },
];

/** The top bar on every page: navigation and the always-visible mode badge. The badge reads the
 * backend's /health once a second, so it is right on every page, not only on the console. */
export default function NavBar({ backendUrl }: { backendUrl: string | null }) {
  const pathname = usePathname();
  const [mode, setMode] = useState<Mode | null>(null);
  const [env, setEnv] = useState<InterlockLike | null>(null);

  useEffect(() => {
    let alive = true;
    const base = backendHttpBase(backendUrl);
    const tick = async () => {
      try {
        const r = await fetch(`${base}/health`, { cache: "no-store" });
        const h = (await r.json()) as { mode?: Mode; environment?: InterlockLike };
        if (alive) {
          setMode(h.mode ?? null);
          setEnv(h.environment ?? null);
        }
      } catch {
        if (alive) setMode(null); // unknown is shown as unknown, never as a safe mode
      }
    };
    void tick();
    const id = setInterval(() => void tick(), 1000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [backendUrl]);

  return (
    <nav className="sticky top-0 z-40 border-b border-neutral-800 bg-neutral-950/95 backdrop-blur">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-4 px-4 py-2">
        <span className="font-semibold tracking-tight">poring-lab</span>
        <ul className="flex gap-1 text-sm">
          {LINKS.map(({ href, label }) => (
            <li key={href}>
              <Link
                href={href}
                aria-current={pathname === href ? "page" : undefined}
                className={`rounded-md px-3 py-1.5 ${
                  pathname === href
                    ? "bg-neutral-800 text-white"
                    : "text-neutral-300 hover:bg-neutral-900"
                }`}
              >
                {label}
              </Link>
            </li>
          ))}
        </ul>
        <div className="ml-auto">
          <ModeBadge mode={mode} env={env} />
        </div>
      </div>
    </nav>
  );
}
