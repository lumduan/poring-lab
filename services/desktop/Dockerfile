# syntax=docker/dockerfile:1
#
# The ONE RDP session (ADR-0001): Xvfb :99 + xfreerdp3 fullscreen (no window manager) + view-only
# x11vnc/noVNC for debugging. Other services reach the display through the shared /tmp/.X11-unix
# volume; only the backend's input mux ever injects input.
#
# FreeRDP is pinned to MAJOR 3. 2.x is EOL upstream and its CLI differs (/cert-ignore, /gfx-h264,
# /kbd:0x409 are not even compiled into 3.x distro builds). Ubuntu's FreeRDP 3 builds lack H.264
# (/gfx:AVC444 is a parse error there); Debian's use FFmpeg.
# Arm C (docs/h264-plan.md, 2026-10-01): 3.32.1 from trixie-backports instead of trixie's 3.15.
# In 3.32 the binary package is `freerdp-x11` (`xfreerdp`); `freerdp3-x11` is now a transitional
# package whose `xfreerdp3` link rdp-loop.sh keeps using (the process's comm stays `xfreerdp3`;
# scripts/rdp_reconnect.sh counts both names). Rollback image: poring-lab/desktop:freerdp-3.15
# (re-tag it as :local, then a guarded recreate) -- REMOVED 2026-10-23 in the host's approved image
# cleanup (OS-039 phase 3 A): a rollback now means rebuilding 3.15 from git history
# (docs/operations/freerdp-315-rollback.md; Batt 2026-10-23: documented, not rebuilt).
FROM debian:trixie-20260918-slim

ENV DEBIAN_FRONTEND=noninteractive
# dpkg fsyncs every file it unpacks; on the shared host disk those fsync storms stall live capture
# databases. A build layer is committed atomically afterwards, so unsafe-io is safe inside a build.
RUN echo force-unsafe-io > /etc/dpkg/dpkg.cfg.d/docker-unsafe-io
# apt version globs survive Debian point releases (+deb13uN) but never cross an upstream version.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      'freerdp3-x11=3.15.0+dfsg-2.1+deb13u*' \
      'xvfb=2:21.1.16-1.3+deb13u*' \
      'x11vnc=0.9.17-*' \
      'python3-websockify=0.12.0+dfsg1-*' \
      'supervisor=4.2.5-*' \
      x11-utils \
      ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && xfreerdp3 --version | tee /dev/stderr | grep -q 'version 3\.15\.'

# Arm C: upgrade ONLY FreeRDP to 3.32.1 from trixie-backports, in its own small layer, so the big
# dependency layer above stays cached. (Rebuilding it in one layer re-unpacked 135 packages and
# tripped the IO guard at 27.8 % quant-postgres stall, 2026-10-01.)
RUN echo 'deb http://deb.debian.org/debian trixie-backports main' \
      > /etc/apt/sources.list.d/trixie-backports.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends -t trixie-backports \
      'freerdp-x11=3.32.1+dfsg-1~bpo13*' \
      'freerdp3-x11=3.32.1+dfsg-1~bpo13*' \
 && rm -rf /var/lib/apt/lists/* \
 && xfreerdp3 --version | tee /dev/stderr | grep -q 'version 3\.32\.' \
 && xfreerdp3 /buildconfig > /tmp/bc 2>&1 \
 && grep -q 'WITH_GFX_H264=ON' /tmp/bc && grep -Eq 'WITH_(VIDEO_)?FFMPEG=ON' /tmp/bc && rm /tmp/bc

# noVNC static files from the upstream release. Debian's `novnc` package hard-depends on nodejs.
ARG NOVNC_VERSION=1.7.0
ADD --checksum=sha256:b1003a11b6e6e8d8f7f5e5586daae7f8ca651d8aee0aa155ff9ac841c48f52c6 \
    https://github.com/novnc/noVNC/archive/refs/tags/v${NOVNC_VERSION}.tar.gz /tmp/novnc.tar.gz
RUN mkdir -p /opt/novnc \
 && tar -xzf /tmp/novnc.tar.gz -C /opt/novnc --strip-components=1 \
 && rm /tmp/novnc.tar.gz \
 && ln -s vnc.html /opt/novnc/index.html

# Unprivileged display user (uid 1000). /tmp/.X11-unix must be root-owned 1777; an empty named
# volume mounted there inherits these permissions from the image.
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin desk \
 && install -d -m 1777 -o root -g root /tmp/.X11-unix

COPY supervisord.conf /etc/supervisor/supervisord.conf
COPY --chmod=0755 bin/ /usr/local/bin/

ENV DISPLAY=:99 \
    XVFB_RESOLUTION=1440x900x24 \
    NOVNC_VIEW_ONLY=true

EXPOSE 6080
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD ["/usr/local/bin/healthcheck.sh"]
CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
