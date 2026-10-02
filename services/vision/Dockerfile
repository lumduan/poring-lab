# syntax=docker/dockerfile:1
# Build context: the repository root (uv workspace).
#
# CUDA: torch 2.14.0+cu130 is the current build with sm_120 (RTX 5060 Ti) kernels that also runs on
# the host's R580 driver. The wheels bring their own CUDA 13.0 runtime/cuBLAS/cuDNN from PyPI, so the
# `base` flavour is enough -- `runtime`/`cudnn-runtime` would only add duplicate, mismatched libs.
# (A cu132 / nvidia/cuda:13.2 image sets NVIDIA_REQUIRE_CUDA=cuda>=13.2 and refuses to start on R580.)
FROM nvidia/cuda:13.0.3-base-ubuntu24.04

COPY --from=ghcr.io/astral-sh/uv:0.12.20 /uv /uvx /bin/

# dpkg fsyncs every file it unpacks; on the shared host disk those fsync storms stall live capture
# databases. A build layer is committed atomically afterwards, so unsafe-io is safe inside a build.
RUN echo force-unsafe-io > /etc/dpkg/dpkg.cfg.d/docker-unsafe-io

# XCB libs for mss capture (+ MIT-SHM via memfd, + XFixes for the optional cursor).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates libxcb1 libxcb-randr0 libxcb-render0 libxcb-shm0 libxcb-xfixes0 \
 && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    UV_PYTHON_PREFERENCE=only-managed \
    UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv python install 3.12

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/poring_env/pyproject.toml packages/poring_env/
# Workspace discovery needs every member's pyproject.toml. poring_packets' SOURCE never enters this
# image (ADR-0007: no packet data on the agent side; tests/test_guards.py).
COPY packages/poring_packets/pyproject.toml packages/poring_packets/
COPY packages/poring_dataset/pyproject.toml packages/poring_dataset/
COPY services/backend/pyproject.toml services/backend/
COPY services/vision/pyproject.toml services/vision/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package poring-vision

COPY packages/poring_env packages/poring_env
COPY services/vision services/vision
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package poring-vision
COPY scripts/check_gpu.py scripts/check_gpu.py

# The ubuntu24.04 base ships a default `ubuntu` user at uid 1000 (the host user owning ./data).
RUN (userdel --remove ubuntu 2>/dev/null || true) \
 && useradd --uid 1000 --create-home --shell /usr/sbin/nologin agent
USER agent

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    DISPLAY=:99 \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
    YOLO_CONFIG_DIR=/tmp/ultralytics
CMD ["poring-vision"]
