# syntax=docker/dockerfile:1
# poring-lab web console: Next.js standalone output, non-root (uid 1001, sibling-project convention).
# pnpm comes from corepack, pinned by package.json "packageManager". Node 24 is Active LTS and still
# bundles corepack (Node 25+ does not -- add `npm i -g corepack` before moving to Node 26).
FROM node:24.21.0-alpine AS base
ENV NEXT_TELEMETRY_DISABLED=1 \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable pnpm

FROM base AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN --mount=type=cache,id=pnpm-store,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm build

FROM node:24.21.0-alpine AS runner
WORKDIR /app
RUN addgroup -g 1001 -S app && adduser -u 1001 -S app -G app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# The standalone server binds process.env.HOSTNAME (default: localhost) -- hence 0.0.0.0 above.
COPY --from=builder --chown=app:app /app/.next/standalone ./
COPY --from=builder --chown=app:app /app/.next/static ./.next/static
USER app
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
    CMD wget -qO- http://127.0.0.1:3000/api/health >/dev/null || exit 1
CMD ["node", "server.js"]
