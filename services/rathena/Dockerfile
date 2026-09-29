# syntax=docker/dockerfile:1
#
# rAthena login/char/map servers, compiled from a pinned commit (rAthena has no tags or releases).
# Upstream tools/docker is dev-only (bind-mounted source, compile-at-runtime, 127.0.0.1-only IPs),
# so this image bakes the binaries in. ubuntu:24.04 + GCC 13 is exactly what rAthena's CI builds on,
# and its MariaDB Connector/C 3.3 avoids 3.4's verify-server-cert-by-default behaviour.
ARG UBUNTU_TAG=noble-20260911

FROM ubuntu:${UBUNTU_TAG} AS build
# dpkg fsyncs every file it unpacks; on the shared host disk those fsync storms stall live capture
# databases. A build layer is committed atomically afterwards, so unsafe-io is safe inside a build.
ENV DEBIAN_FRONTEND=noninteractive
RUN echo force-unsafe-io > /etc/dpkg/dpkg.cfg.d/docker-unsafe-io
# libmariadb-dev-compat is the only package providing `mysql_config` / -lmysqlclient, which
# ./configure requires. libpcre3-dev (PCRE1, optional, NPC chat patterns) no longer exists in trixie.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      g++ make zlib1g-dev libmariadb-dev libmariadb-dev-compat libpcre3-dev ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

ARG RATHENA_REF=e985006171d2eb320ee512a653f4c83aea3d81b6
# Must match the RO client executable's date. 20211103 = upstream default (a RagexeRE client).
ARG PACKETVER=20211103
ARG PRERE=no
ARG VIP=no
# Each big translation unit takes ~1-1.5 GB of RAM; this host also runs live capture services.
ARG MAKE_JOBS=4

# The whole compile runs in a tmpfs: source (~250 MB), objects and g++ temp files never touch the
# host disk, which is shared with live capture databases. Only the finished runtime tree is written
# (to /out). `make common` runs first, serially: rapidyaml has a parallel directory-creation race.
RUN --mount=type=tmpfs,target=/src \
    cd /src \
 && export TMPDIR=/src/.tmp && mkdir -p "$TMPDIR" \
 && curl -fsSL "https://github.com/rathena/rathena/archive/${RATHENA_REF}.tar.gz" \
      | tar -xz --strip-components=1 \
 && ./configure --enable-packetver="${PACKETVER}" --enable-prere="${PRERE}" --enable-vip="${VIP}" \
 && make common \
 && make -j"${MAKE_JOBS}" server \
 && mkdir -p /out/log \
 && cp -a login-server char-server map-server web-server conf db npc sql-files /out/ \
 && printf '%s\n' "ref=${RATHENA_REF}" "packetver=${PACKETVER}" "prere=${PRERE}" "vip=${VIP}" \
      > /out/BUILD_INFO

FROM ubuntu:${UBUNTU_TAG}
ENV DEBIAN_FRONTEND=noninteractive
RUN echo force-unsafe-io > /etc/dpkg/dpkg.cfg.d/docker-unsafe-io
# ubuntu:24.04 ships a default `ubuntu` user at uid 1000; replace it with ours.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libmariadb3 zlib1g libpcre3 mariadb-client gettext-base ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && (userdel --remove ubuntu 2>/dev/null || true) \
 && useradd --uid 1000 --home-dir /opt/rathena --no-create-home --shell /usr/sbin/nologin rathena

# The runtime tree is ~thousands of small db/npc files. A plain COPY writes them in one burst, which
# stalled the capture Postgres (ext4 data=ordered: its fsyncs wait behind the flush). Stream it through
# tar with checkpoint sleeps instead (~10 MB/s), owned by uid 1000 at creation (no chown pass).
RUN --mount=type=bind,from=build,source=/out,target=/mnt/out \
    mkdir -p /opt/rathena \
 && tar -C /mnt/out --owner=1000 --group=1000 -cf - . \
      | tar -C /opt/rathena --same-owner -xf - --checkpoint=1000 --checkpoint-action=sleep=1
COPY --chown=rathena:rathena conf/import/ /opt/rathena/conf-templates/
COPY --chmod=0755 entrypoint.sh /usr/local/bin/rathena-entrypoint

WORKDIR /opt/rathena
USER rathena
EXPOSE 6900 6121 5121
HEALTHCHECK --interval=15s --timeout=5s --start-period=180s --retries=5 \
    CMD ["bash", "-c", "</dev/tcp/127.0.0.1/6900 && </dev/tcp/127.0.0.1/6121 && </dev/tcp/127.0.0.1/5121"]
ENTRYPOINT ["/usr/local/bin/rathena-entrypoint"]
