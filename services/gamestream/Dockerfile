# Console-mode stream client (ADR-0009, capture backend `console`): moonlight-qt renders the Sunshine
# stream of the Windows CONSOLE session into the lab's Xvfb :99 and takes its input from the X server
# (the backend mux's XTest), with absolute mouse positioning.
#
# Built on the desktop image (same Debian, Mesa/GLX and X libraries -> only small new layers; build it
# with scripts/guarded_build.py, which uses dockerd's own BuildKit for lab images). Its CMD and
# HEALTHCHECK are REPLACED: this container must never run start-xvfb.sh (it would delete the shared
# X99 socket) nor xfreerdp. The AppImage stays ONE file in the image and is unpacked into tmpfs at
# start (the rathena single-tar pattern: no thousands of files on the shared disk). xdotool MOVES the
# stream window to the session area (gamestream-loop.sh place_stream); there is no window manager.
# NO gdb here: installing it (33 packages; trixie's gdb-minimal is a transitional package for gdb)
# spiked quant IO to 43 % / 49 % on 2026-10-02 and the guard aborted both builds. The loop's
# GAMESTREAM_GDB_AFTER_S diagnostics stay inert until gdb is added in an operator-chosen window.
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

COPY --chmod=0755 bin/ /usr/local/bin/

USER desk
ENV HOME=/home/desk XDG_CACHE_HOME=/tmp/cache XDG_RUNTIME_DIR=/tmp/xdg QT_QPA_PLATFORM=xcb \
    DISPLAY=:99 LAB_STATE_DIR=/lab-state
ENTRYPOINT []
CMD ["/usr/local/bin/gamestream-loop.sh"]
HEALTHCHECK NONE
