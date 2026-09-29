"""Print the Windows host's RDP certificate SHA-256, for RDP_CERT_SHA256 in .env.

    python3 scripts/rdp_cert_fingerprint.py 192.168.1.169 [3389]

Does a pre-authentication handshake only (X.224 negotiation + TLS). It never logs in and never
touches the interactive session. Windows renews its self-signed RDP certificate about every six
months. After a renewal the pinned connection fails TLS verification (rdp-loop backs off; no
credentials are sent), so re-run this and update .env, then `docker compose restart desktop`.
"""

import hashlib
import socket
import ssl
import struct
import sys

# RDP_NEG_REQ requestedProtocols
PROTOCOL_SSL, PROTOCOL_HYBRID = 0x1, 0x2
SELECTED = {0: "RDP (legacy)", 1: "TLS", 2: "HYBRID (NLA)", 8: "HYBRID_EX (NLA + early auth)"}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    host = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 3389

    sock = socket.create_connection((host, port), timeout=5)
    neg_req = struct.pack("<BBHI", 0x01, 0x00, 8, PROTOCOL_SSL | PROTOCOL_HYBRID)
    x224 = bytes([len(neg_req) + 6, 0xE0, 0, 0, 0, 0, 0]) + neg_req  # Connection Request TPDU
    sock.sendall(struct.pack(">BBH", 3, 0, 4 + len(x224)) + x224)  # TPKT header
    reply = sock.recv(64)
    if len(reply) < 19 or reply[11] != 0x02:  # TYPE_RDP_NEG_RSP
        print(f"{host}:{port}: unexpected negotiation reply {reply.hex()}", file=sys.stderr)
        return 1
    selected = struct.unpack("<I", reply[15:19])[0]

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # we are *reading* the certificate in order to pin it
    with ctx.wrap_socket(sock, server_hostname=host) as tls:
        der = tls.getpeercert(binary_form=True)
        version = tls.version()
    if der is None:
        print("server sent no certificate", file=sys.stderr)
        return 1

    print(f"# {host}:{port}  protocol {SELECTED.get(selected, hex(selected))}  {version}")
    print(f"RDP_CERT_SHA256={hashlib.sha256(der).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
