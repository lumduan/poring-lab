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
  { href: "/flows", label: "Flows" },
  { href: "/settings", label: "Settings" },
  // "Label QA" (/qa) left the bar 2026-11-10 (Batt: no longer used); the page itself remains
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

  const current = LINKS.find((l) => l.href === pathname);
  return (
    <nav className="sticky top-0 z-40 border-b border-neutral-800 bg-neutral-950/95 backdrop-blur">
      <div className="mx-auto flex max-w-[1600px] items-center gap-3 px-4 py-2 md:flex-wrap md:gap-4">
        <span className="font-semibold tracking-tight">poring-lab</span>
        {/* phones (< 48rem): one row, the pages in a menu (2026-11-09: /flows needs the height) */}
        <details className="relative md:hidden" data-testid="nav-menu">
          <summary className="cursor-pointer list-none rounded-md bg-neutral-800 px-3 py-1.5 text-sm text-white">
            {current?.label ?? "Pages"} ▾
          </summary>
          <ul className="absolute left-0 top-full z-50 mt-1 min-w-40 rounded-md border border-neutral-800 bg-neutral-950 p-1 text-sm shadow-lg">
            {LINKS.map(({ href, label }) => (
              <li key={href}>
                <Link
                  href={href}
                  aria-current={pathname === href ? "page" : undefined}
                  className={`block rounded-md px-3 py-1.5 ${pathname === href ? "bg-neutral-800 text-white" : "text-neutral-300 hover:bg-neutral-900"}`}
                >
                  {label}
                </Link>
              </li>
            ))}
          </ul>
        </details>
        <ul className="hidden gap-1 text-sm md:flex">
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
