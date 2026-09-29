#!/usr/bin/env bash
# Regenerate the wire-protocol artifacts from the Pydantic models (the single source of truth):
#   packages/poring_env/schema/protocol.schema.json   (pytest fails when this is stale)
#   services/frontend/src/lib/protocol.gen.ts         (json-schema-to-typescript)
# Run after ANY change to packages/poring_env/src/poring_env/protocol.py and commit both files.
set -euo pipefail
cd "$(dirname "$0")/.."

uv run poring-protocol-schema >packages/poring_env/schema/protocol.schema.json
# corepack resolves the pnpm version from the package.json in the CURRENT directory.
(cd services/frontend && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm run -s gen:protocol)
git status --short -- packages/poring_env/schema services/frontend/src/lib/protocol.gen.ts 2>/dev/null || true
