# syntax=docker/dockerfile:1
# A THROWAWAY media probe (Batt 2026-11-08, "ok, try it"): what bot-server's Intel Arc A380 (DG2,
# i915, /dev/dri/renderD128) really does with VA-API -- decode, encode and JPEG -- measured BEFORE
# any lab image changes. Evidence only: no lab service uses this image, and nothing in it reaches
# the lab (compose service `media-probe`, profile `probe`: network none, read-only, no volumes,
# only the render node; tests/test_guards.py).
#
# The VA driver is iHD (intel-media-va-driver-non-free, multiverse): the free build lacks the
# encoders. ffmpeg is Ubuntu's own (--enable-vaapi, libx264). Build context: this directory.
#
# ubuntu:26.04, pinned by the index digest Docker Hub served on 2026-11-08.
FROM ubuntu:26.04@sha256:6a06111c3b0a8600feadb270aec771dc239bf407b25625f93f44ab00e11f4d3c

# dpkg fsyncs every unpacked file; a build layer is committed atomically, so unsafe-io is safe here
RUN echo force-unsafe-io > /etc/dpkg/dpkg.cfg.d/docker-unsafe-io

# multiverse for the non-free iHD driver (added only if the image's sources lack it)
RUN f=/etc/apt/sources.list.d/ubuntu.sources \
 && { grep -q '^Components:.*multiverse' "$f" \
      || sed -i 's/^Components: \(.*\)$/Components: \1 multiverse/' "$f"; } \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      intel-media-va-driver-non-free vainfo ffmpeg libva2 libva-drm2 \
 && rm -rf /var/lib/apt/lists/* \
 && dpkg-query -W -f='${Package} ${Version}\n' \
      intel-media-va-driver-non-free vainfo ffmpeg libva2 libva-drm2 libavcodec-extra \
      libavcodec62 libavcodec61 2>/dev/null | tee /opt/probe-packages.txt || true

RUN useradd --uid 10001 --user-group --no-create-home --home-dir /tmp --shell /usr/sbin/nologin \
      probe
COPY --chmod=0755 probe.sh /usr/local/bin/probe.sh

USER probe
ENV HOME=/tmp LIBVA_DRIVER_NAME=iHD
WORKDIR /tmp
ENTRYPOINT ["/usr/local/bin/probe.sh"]
