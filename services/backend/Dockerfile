# syntax=docker/dockerfile:1
# Build context: the repository root (uv workspace: needs uv.lock + packages/poring_env).
FROM python:3.12.14-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.12.20 /uv /uvx /bin/

# dpkg fsyncs every file it unpacks; on the shared host disk those fsync storms stall live capture
# databases. A build layer is committed atomically afterwards, so unsafe-io is safe inside a build.
RUN echo force-unsafe-io > /etc/dpkg/dpkg.cfg.d/docker-unsafe-io

# mss 10.2 captures over XCB (+ MIT-SHM via memfd, + XFixes for the optional cursor).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libxcb1 libxcb-randr0 libxcb-render0 libxcb-shm0 libxcb-xfixes0 \
 && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app
# Dependencies first (cached layer): every workspace member's pyproject must be present.
COPY pyproject.toml uv.lock ./
COPY packages/poring_env/pyproject.toml packages/poring_env/
COPY services/backend/pyproject.toml services/backend/
COPY services/vision/pyproject.toml services/vision/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package poring-backend

COPY packages/poring_env packages/poring_env
COPY services/backend services/backend
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package poring-backend

# uid 1000 = the host user owning ./data (bind-mounted for the input log).
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin app
USER app

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    DISPLAY=:99 \
    DATA_DIR=/data
EXPOSE 8000 8001
HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]
CMD ["poring-backend"]
