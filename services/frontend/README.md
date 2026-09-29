# poring-lab frontend

Next.js 16 (App Router, TypeScript, Tailwind 4), pnpm via corepack. One page: the live RDP view on a
canvas, a separate overlay canvas for detection boxes, the HUMAN / ASSIST / BOT mode switch, and an
FPS / latency panel. See the repository `README.md` for the whole system.

```bash
corepack pnpm install
BACKEND_PUBLIC_URL=http://192.168.1.13:8000 corepack pnpm dev   # unset: ws://<page host>:8000
corepack pnpm lint && corepack pnpm typecheck && corepack pnpm build
```

- **Protocol types are generated** — `src/lib/protocol.gen.ts` comes from the Pydantic models in
  `packages/poring_env` via `scripts/gen_protocol.sh`. Never edit it by hand.
- **Input** — keys are sent as `KeyboardEvent.code` (physical key), mouse moves are coalesced to one per
  animation frame, every other event is immediate; the page `preventDefault`s every key while the game
  view is focused (Cmd/Meta combos excepted) and sends `release_all` on blur.
- **Runtime config** — `BACKEND_PUBLIC_URL` is read per request by `src/app/page.tsx`; nothing about the
  backend is baked in at build time.
- Read `AGENTS.md` before changing Next.js code: this Next version differs from most training data.
