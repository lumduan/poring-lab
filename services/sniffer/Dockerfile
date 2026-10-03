# syntax=docker/dockerfile:1
# The packet sniffer (ADR-0007): OFFLINE GROUND TRUTH ONLY, never agent input. Build context: the
# repository root (uv workspace: uv.lock + every member's pyproject). Slim: Python + pydantic +
# websockets + poring_packets -- no backend, no X. Same base and uv as the backend image, so the
# layers are shared. Runs in rathena's network namespace (compose: network_mode service:rathena,
# user 0:0 with every capability dropped except NET_RAW for the AF_PACKET socket, read-only rootfs).
FROM python:3.12.14-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.12.20 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/poring_env/pyproject.toml packages/poring_env/
COPY packages/poring_packets/pyproject.toml packages/poring_packets/
COPY packages/poring_dataset/pyproject.toml packages/poring_dataset/
COPY services/backend/pyproject.toml services/backend/
COPY services/vision/pyproject.toml services/vision/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package poring-packets --extra sniffer

# The length table (_generated/lengths.json) is generated from pinned sources and never committed
# (ADR-0007); it ships inside the wheel (hatch `artifacts`). The image refuses to BUILD without the
# exact table: load() checks it against tables.lock.json, run from / so it tests the INSTALLED copy.
COPY packages/poring_packets packages/poring_packets
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package poring-packets --extra sniffer \
 && cd / && /opt/venv/bin/python -c \
      "from poring_packets.tables import load; t = load(); print('length table OK:', len(t.lengths))"

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
CMD ["python", "-m", "poring_packets.sniffer"]
