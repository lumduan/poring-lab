# Console-mode stream client (ADR-0009, capture backend `console`): moonlight-qt renders the Sunshine
# stream of the Windows CONSOLE session into the lab's Xvfb :99 and takes its input from the X server
# (the backend mux's XTest), with absolute mouse positioning.
#
# Built on the desktop image (same Debian, Mesa/GLX and X libraries -> only small new layers; build it
# with scripts/guarded_build.py, which uses dockerd's own BuildKit for lab images). Its CMD and
# HEALTHCHECK are REPLACED: this container must never run start-xvfb.sh (it would delete the shared
# X99 socket) nor xfreerdp. The AppImage stays ONE file in the image and is unpacked into tmpfs at
# start (the rathena single-tar pattern: no thousands of files on the shared disk).
FROM poring-lab/desktop:local

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends libegl1 squashfs-tools \
 && rm -rf /var/lib/apt/lists/*

# moonlight-qt's official Linux build. GitHub publishes no digest for this release: the sha256 was
# computed from the download on 2026-10-02 and is pinned here.
ARG MOONLIGHT_VERSION=6.1.0
ARG MOONLIGHT_SHA256=0e855ffd22d407e18ab5fdb575fed5f01ca119a3f91993c5f0213f15ac80b400
ADD --checksum=sha256:${MOONLIGHT_SHA256} --chmod=0644 \
    https://github.com/moonlight-stream/moonlight-qt/releases/download/v${MOONLIGHT_VERSION}/Moonlight-${MOONLIGHT_VERSION}-x86_64.AppImage \
    /opt/moonlight/Moonlight.AppImage
RUN printf '%s\n' "${MOONLIGHT_VERSION}" > /opt/moonlight/VERSION

COPY --chmod=0755 bin/ /usr/local/bin/

USER desk
ENV HOME=/home/desk XDG_CACHE_HOME=/tmp/cache XDG_RUNTIME_DIR=/tmp/xdg QT_QPA_PLATFORM=xcb \
    DISPLAY=:99 LAB_STATE_DIR=/lab-state
ENTRYPOINT []
CMD ["/usr/local/bin/gamestream-loop.sh"]
HEALTHCHECK NONE
