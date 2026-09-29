# syntax=docker/dockerfile:1
# PLACEHOLDER. Runs in rathena's network namespace (compose: network_mode "service:rathena",
# cap_add NET_RAW) so it will see client<->server game traffic and inter-server/DB traffic.
# Nothing is captured yet -- see README.md for the intent and the rules.
FROM debian:trixie-20260918-slim
COPY --chmod=0755 stub.sh /usr/local/bin/sniffer-stub
CMD ["/usr/local/bin/sniffer-stub"]
