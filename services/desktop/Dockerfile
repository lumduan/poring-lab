# syntax=docker/dockerfile:1
#
# The ONE RDP session (ADR-0001): Xvfb :99 + xfreerdp3 fullscreen (no window manager) + view-only
# x11vnc/noVNC for debugging. Other services reach the display through the shared /tmp/.X11-unix
# volume; only the backend's input mux ever injects input.
#
# FreeRDP is pinned to MAJOR 3 (3.15, Debian trixie). 2.x is EOL upstream and its CLI differs
# (/cert-ignore, /gfx-h264, /kbd:0x409 are not even compiled into 3.x distro builds). Ubuntu's
# FreeRDP 3 builds lack H.264 (/gfx:AVC444 is a parse error there), Debian's use FFmpeg.
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
    XVFB_RESOLUTION=1280x720x24 \
    NOVNC_VIEW_ONLY=true

EXPOSE 6080
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD ["/usr/local/bin/healthcheck.sh"]
CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
