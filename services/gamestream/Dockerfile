# syntax=docker/dockerfile:1
# Console-mode stream client (ADR-0009, capture backend `console`): moonlight-qt renders the Sunshine
# stream of the Windows CONSOLE session into the lab's Xvfb :99 and takes its input from the X server
# (the backend mux's XTest), with absolute mouse positioning.
#
# Built on the desktop image (same Debian, Mesa/GLX and X libraries -> only small new layers; build it
# with scripts/guarded_build.py, which uses dockerd's own BuildKit for lab images). Its CMD and
# HEALTHCHECK are REPLACED: this container must never run start-xvfb.sh (it would delete the shared
# X99 socket) nor xfreerdp. The AppImage stays ONE file in the image and is unpacked into tmpfs at
# start (the rathena single-tar pattern: no thousands of files on the shared disk). xdotool MOVES the
# stream window to the session area (gamestream-loop.sh place_stream).
#
# The clean-room variants (Batt, 2026-10-03; ADR-0009) need three more things, all inert unless the
# capture-backend's variant file selects them (gamestream-loop.sh read_variant):
#   - gdb: V1's one stack capture (GDB_AFTER_S). gdb is 33 packages and spiked quant IO to 43-49 % on
#     a weekday (2026-10-02); it is built on the weekend window under the tolerant guard.
#   - openbox: V2, Moonlight-qt WITH a window manager. Never running outside its stream.
#   - the S2 spike (V3, services/gamestream/s2spike): moonlight-common-c as a shared library at the
#     commit moonlight-qt 6.1.0 ships (so V3 and V1 speak the same protocol), a variadic-log shim, its
#     struct layout as JSON, and hash-pinned PyAV + numpy wheels. Compiled in a throwaway builder
#     stage: only /opt/s2spike reaches the image. moonlight-common-c is GPLv3: fetched at build
#     time, never vendored in this repo.
ARG MLCC_SHA=8599b6042a4ba27749b0f94134dd614b4328a9bc

FROM debian:trixie-20260918-slim AS s2build
ARG MLCC_SHA
RUN echo force-unsafe-io > /etc/dpkg/dpkg.cfg.d/docker-unsafe-io
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc g++ libc6-dev make cmake git ca-certificates \
      libssl-dev python3 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.20 /uv /bin/uv
WORKDIR /src
RUN git clone -q --filter=blob:none --no-checkout \
      https://github.com/moonlight-stream/moonlight-common-c.git mlcc \
 && git -C mlcc checkout -q "${MLCC_SHA}" \
 && git -C mlcc submodule update -q --init --depth 1
# -Werror is target-level (after CMAKE_C_FLAGS): a 2024 tree must not fail on trixie's newer GCC
# warnings. The sed is checked: if upstream's line changed, the build stops here, visibly. (g++ is
# only for enet's CMake project(), which declares C++ too.)
RUN grep -q -- ' -Werror)' mlcc/CMakeLists.txt \
 && sed -i 's/ -Werror)/)/' mlcc/CMakeLists.txt \
 && cmake -S mlcc -B mlcc/build -DCMAKE_BUILD_TYPE=Release \
 && cmake --build mlcc/build -j2
COPY s2spike/native/ /src/native/
RUN install -d /opt/s2spike/lib \
 && cp mlcc/build/libmoonlight-common-c.so /opt/s2spike/lib/ \
 && gcc -O2 -Wall -shared -fPIC -o /opt/s2spike/lib/libs2shim.so native/s2shim.c \
 && gcc -O0 -Wall -I mlcc/src -o /tmp/layout_check native/layout_check.c \
 && /tmp/layout_check > /opt/s2spike/lib/layout.json \
 && printf '%s\n' "${MLCC_SHA}" > /opt/s2spike/lib/MLCC_SHA
COPY s2spike/requirements.txt /src/requirements.txt
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install -q --python /usr/bin/python3 --target /opt/s2spike/site --require-hashes \
      --only-binary :all: --no-deps -r /src/requirements.txt

FROM poring-lab/desktop:local

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends libegl1 squashfs-tools xdotool \
 && rm -rf /var/lib/apt/lists/* \
 && install -d -m 0755 /opt/moonlight \
 && install -d -o desk -g desk -m 0700 /home/desk/.config

# moonlight-qt's official Linux build. GitHub publishes no digest for this release: the sha256 was
# computed from the download on 2026-10-02 and is pinned here. The directory exists (0755) BEFORE
# the ADD: an ADD that creates it applies --chmod=0644 to the directory too, and `desk` could not
# traverse it ("could not unpack", 2026-10-02).
# /home/desk/.config is the gamestream-state volume (Moonlight's identity + pairing). It exists in the
# image owned by desk so a NEW named volume inherits that owner; a root-owned volume made Moonlight mint
# a fresh identity on every run, so a pairing could never stick (2026-10-02).
ARG MOONLIGHT_VERSION=6.1.0
ARG MOONLIGHT_SHA256=0e855ffd22d407e18ab5fdb575fed5f01ca119a3f91993c5f0213f15ac80b400
ADD --checksum=sha256:${MOONLIGHT_SHA256} --chmod=0644 \
    https://github.com/moonlight-stream/moonlight-qt/releases/download/v${MOONLIGHT_VERSION}/Moonlight-${MOONLIGHT_VERSION}-x86_64.AppImage \
    /opt/moonlight/Moonlight.AppImage
RUN printf '%s\n' "${MOONLIGHT_VERSION}" > /opt/moonlight/VERSION

# gdb + openbox, REFUSED if apt would upgrade any already-installed package: V1 is "moonlight-qt as
# it ran on 2026-10-02", and a newer libGL/libX11/glib under it would change the experiment.
RUN apt-get update \
 && apt-get -s install --no-install-recommends gdb openbox > /tmp/apt-sim.txt \
 && if grep -E '^Inst [^ ]+ \[' /tmp/apt-sim.txt; then \
      echo 'REFUSED: gdb/openbox would upgrade the packages above (V1 must stay as-is)' >&2; \
      exit 1; \
    fi \
 && apt-get install -y --no-install-recommends gdb openbox \
 && rm -rf /var/lib/apt/lists/* /tmp/apt-sim.txt

COPY --from=s2build /opt/s2spike/ /opt/s2spike/
COPY openbox/rc.xml /opt/openbox/rc.xml
COPY s2spike/ /opt/s2spike/s2spike/
COPY --chmod=0755 bin/ /usr/local/bin/

USER desk
ENV HOME=/home/desk XDG_CACHE_HOME=/tmp/cache XDG_RUNTIME_DIR=/tmp/xdg QT_QPA_PLATFORM=xcb \
    DISPLAY=:99 LAB_STATE_DIR=/lab-state \
    PYTHONPATH=/opt/s2spike/site:/opt/s2spike PYTHONDONTWRITEBYTECODE=1 S2_LIB_DIR=/opt/s2spike/lib
ENTRYPOINT []
CMD ["/usr/local/bin/gamestream-loop.sh"]
HEALTHCHECK NONE
