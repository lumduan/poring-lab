// Entry point of the frontend-dev container (compose.dev.yaml). Keeps every write off the host disk:
//   /src  the frontend source, bind-mounted READ-ONLY
//   /app  tmpfs working copy: source + node_modules + pnpm store + corepack (and /app/.next, tmpfs)
// 1. copy /src -> /app, 2. pnpm install into tmpfs, 3. `next dev`, 4. mirror later source edits
// into /app so hot reload keeps working.
import { spawn } from "node:child_process";
import { watch } from "node:fs";
import { cp, mkdir, readdir, rm, stat } from "node:fs/promises";
import path from "node:path";

const SRC = "/src";
const APP = "/app";
// Host artifacts that must never be copied in, and paths that only exist in the tmpfs copy.
const SKIP = new Set([
  "node_modules",
  ".next",
  "next-env.d.ts",
  "tsconfig.tsbuildinfo",
  ".pnpm-store",
  ".corepack",
  ".home",
]);

const skipped = (rel) => rel !== "" && SKIP.has(rel.split(path.sep)[0]);
const log = (msg) => console.log(`[run-dev] ${msg}`);

function run(cmd, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, { cwd: APP, stdio: "inherit" });
    child.on("exit", (code) =>
      code === 0 ? resolve() : reject(new Error(`${cmd} ${args.join(" ")} exited with ${code}`)),
    );
  });
}

async function mirror(rel) {
  const from = path.join(SRC, rel);
  const to = path.join(APP, rel);
  try {
    await stat(from);
    await cp(from, to, { recursive: true, force: true });
  } catch {
    await rm(to, { recursive: true, force: true });
  }
}

await mkdir(path.join(APP, ".home"), { recursive: true });
await cp(SRC, APP, {
  recursive: true,
  force: true,
  filter: (src) => !skipped(path.relative(SRC, src)),
});
log("source copied into tmpfs; installing dependencies (tmpfs only)");
await run("corepack", ["pnpm", "install", "--frozen-lockfile"]);

const dev = spawn("corepack", ["pnpm", "exec", "next", "dev", "--hostname", "0.0.0.0", "--port", "3000"], {
  cwd: APP,
  stdio: "inherit",
});

// Debounced mirroring of source edits (editors often write a file several times in a row).
const pending = new Map();
watch(SRC, { recursive: true }, (_event, file) => {
  if (!file || skipped(file)) return;
  clearTimeout(pending.get(file));
  pending.set(
    file,
    setTimeout(() => {
      pending.delete(file);
      mirror(file).catch((err) => log(`sync ${file} failed: ${err}`));
    }, 100),
  );
});
log("watching /src for changes");

// fs.watch (recursive, Linux) follows file inodes: once a file is replaced by a new inode (a git
// checkout, an atomic editor save) its later edits never arrive. Console.tsx stayed at its 09-30
// copy for two days that way (2026-10-02). A cheap poll of size+mtime mirrors whatever the watcher
// missed, deletions included. Metadata only: no file is read unless it changed.
const seen = new Map();
async function scan(dir, found) {
  for (const entry of await readdir(path.join(SRC, dir), { withFileTypes: true })) {
    const rel = path.join(dir, entry.name);
    if (skipped(rel)) continue;
    if (entry.isDirectory()) {
      await scan(rel, found);
    } else if (entry.isFile()) {
      const st = await stat(path.join(SRC, rel));
      found.set(rel, `${st.size}:${st.mtimeMs}`);
    }
  }
}
let scanning = false;
async function reconcile(initial) {
  if (scanning) return;
  scanning = true;
  try {
    const found = new Map();
    await scan("", found);
    if (!initial) {
      for (const [rel, sig] of found) {
        if (seen.get(rel) !== sig) await mirror(rel);
      }
      for (const rel of seen.keys()) {
        if (!found.has(rel)) await mirror(rel); // deleted on the host
      }
    }
    seen.clear();
    for (const [rel, sig] of found) seen.set(rel, sig);
  } catch (err) {
    log(`reconcile failed: ${err}`);
  } finally {
    scanning = false;
  }
}
await reconcile(true);
setInterval(() => reconcile(false), 2000);
log("polling /src every 2 s as a backstop to the watcher");

for (const signal of ["SIGTERM", "SIGINT"]) {
  process.on(signal, () => dev.kill(signal));
}
dev.on("exit", (code) => process.exit(code ?? 0));
