import { type NextRequest, NextResponse } from "next/server";

import { backendSources, cspHeader } from "@/lib/csp";

/** A fresh nonce and the strict CSP on every page (src/lib/csp.ts). Next reads the nonce from the
 * request's CSP header and puts it on its own scripts; pages are dynamic (`await connection()`). */
export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const host = request.headers.get("host");
  const csp = cspHeader({
    nonce,
    dev: process.env.NODE_ENV === "development",
    backend: backendSources(process.env.BACKEND_PUBLIC_URL ?? null, host),
    host,
  });
  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: [
    {
      source: "/((?!api|_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
