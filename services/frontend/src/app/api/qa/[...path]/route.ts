// Phase 2 label QA bundles (scripts/qa_export.py -> services/frontend/.qa-local/, gitignored and
// .dockerignore'd). Dev server ONLY: frontend-dev mirrors the source tree into its tmpfs, so a new
// bundle appears without a restart; a production build answers 404 and never contains one.
import { readFile } from "node:fs/promises";
import path from "node:path";

const ROOT = path.join(process.cwd(), ".qa-local");
const TYPES: Record<string, string> = {
  ".json": "application/json",
  ".png": "image/png",
  ".jpg": "image/jpeg",
};

export async function GET(_req: Request, { params }: { params: Promise<{ path: string[] }> }) {
  if (process.env.NODE_ENV !== "development") return new Response("not found", { status: 404 });
  const parts = (await params).path;
  if (parts.some((p) => p === ".." || p.includes("/") || p.startsWith("."))) {
    return new Response("bad path", { status: 400 });
  }
  const file = path.join(ROOT, ...parts);
  const type = TYPES[path.extname(file)];
  if (!type || !file.startsWith(ROOT + path.sep)) return new Response("not found", { status: 404 });
  try {
    return new Response(new Uint8Array(await readFile(file)), {
      headers: { "content-type": type, "cache-control": "no-store" },
    });
  } catch {
    return new Response("not found", { status: 404 });
  }
}
