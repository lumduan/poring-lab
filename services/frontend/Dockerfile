# syntax=docker/dockerfile:1
# poring-lab web console: Next.js standalone output, non-root (uid 1001, sibling-project convention).
# pnpm comes from corepack, pinned by package.json "packageManager". Node 24 is Active LTS and still
# bundles corepack (Node 25+ does not -- add `npm i -g corepack` before moving to Node 26).
FROM node:24.21.0-alpine AS base
ENV NEXT_TELEMETRY_DISABLED=1 \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable pnpm

# Install + build in ONE step with the pnpm store and node_modules in tmpfs: ~20k files / ~700 MB
# of writes stay in RAM instead of hitting the host disk (shared with live capture databases).
# Only .next (the standalone server + static assets) lands in the layer.
FROM base AS builder
WORKDIR /app
COPY . .
RUN --mount=type=tmpfs,target=/root/.local/share/pnpm/store \
    --mount=type=tmpfs,target=/app/node_modules \
    --mount=type=tmpfs,target=/app/.next/cache \
    pnpm install --frozen-lockfile \
 && pnpm build

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
# Static files (MW2: Blockly's self-hosted media, /blockly-media/*): standalone output does not copy them.
COPY --from=builder --chown=app:app /app/public ./public
USER app
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
    CMD wget -qO- http://127.0.0.1:3000/api/health >/dev/null || exit 1
CMD ["node", "server.js"]
