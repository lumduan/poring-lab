"""The lab client's paired identity, read from Moonlight-qt's own config (gamestream-state volume).

V3 talks to Sunshine AS the one paired lab client (Batt, 2026-10-03): same certificate, same key,
same uniqueid. "One client at a time" is enforced at stream start (lockstate.may_stream), not here.

The private key never touches a filesystem (CLAUDE.md rule 2, amended 2026-10-03): the PEMs are read
into this process's memory, handed to OpenSSL through a SEALED, close-on-exec memfd that is closed
right after load_cert_chain, and the process is made non-dumpable (no core, no ptrace by peers).
Nothing here ever logs or prints certificate or key material.
"""

from __future__ import annotations

import ctypes
import fcntl
import os
import re
import ssl
from dataclasses import dataclass, field
from pathlib import Path

CONF = Path.home() / ".config" / "Moonlight Game Streaming Project" / "Moonlight.conf"
UNIQUE_ID = "0123456789ABCDEF"  # Moonlight-qt's fixed uniqueid (nvhttp.cpp, ADR-0009)
_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "a": "\a", "b": "\b", "f": "\f", "v": "\v",
            "\\": "\\", '"': '"', "0": "\0", ";": ";", ",": ",", "=": "="}  # fmt: skip


def unescape(raw: str) -> str:
    """One QSettings INI value: optional "quotes", backslash escapes (\\n, \\xHH, ...)."""
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        raw = raw[1:-1]
    out: list[str] = []
    i = 0
    while i < len(raw):
        c = raw[i]
        if c != "\\" or i + 1 == len(raw):
            out.append(c)
            i += 1
            continue
        nxt = raw[i + 1]
        if nxt == "x":
            m = re.match(r"[0-9a-fA-F]{1,4}", raw[i + 2 :])
            if m:
                out.append(chr(int(m.group(0), 16)))
                i += 2 + len(m.group(0))
                continue
        out.append(_ESCAPES.get(nxt, nxt))
        i += 2
    return "".join(out)


def byte_array(raw: str) -> bytes:
    """`@ByteArray(...)` -> bytes (Qt stores QByteArray values this way)."""
    text = unescape(raw)
    m = re.fullmatch(r"@ByteArray\((.*)\)", text, flags=re.S)
    if not m:
        raise ValueError("not a @ByteArray value")
    return m.group(1).encode("latin-1")


def parse_ini(text: str) -> dict[str, dict[str, str]]:
    """QSettings INI -> {section: {key: raw value}} (raw: unescape/byte_array decode it)."""
    sections: dict[str, dict[str, str]] = {"General": {}}
    current = sections["General"]
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1], {})
            continue
        key, sep, value = line.partition("=")
        if sep:
            current[key.strip()] = value
    return sections


@dataclass(frozen=True)
class Identity:
    cert_pem: bytes = field(repr=False)
    key_pem: bytes = field(repr=False)
    server_cert_pem: bytes = field(repr=False)
    host_uuid: str
    apps: dict[str, int]  # app name -> Sunshine app id, as Moonlight-qt cached them


def load(conf: Path = CONF, host_index: int = 1) -> Identity:
    sections = parse_ini(conf.read_text(encoding="latin-1"))
    general, hosts = sections.get("General", {}), sections.get("hosts", {})
    prefix = f"{host_index}\\"
    apps: dict[str, int] = {}
    count = int(unescape(hosts.get(f"{prefix}apps\\size", "0")) or 0)
    for i in range(1, count + 1):
        name = unescape(hosts.get(f"{prefix}apps\\{i}\\name", ""))
        app_id = unescape(hosts.get(f"{prefix}apps\\{i}\\id", ""))
        if name and app_id.isdigit():
            apps[name] = int(app_id)
    for need in ("certificate", "key"):
        if need not in general:
            raise ValueError(f"Moonlight.conf has no {need}: the lab client is not set up")
    if f"{prefix}srvcert" not in hosts:
        raise ValueError("Moonlight.conf has no paired host (srvcert): pair first")
    return Identity(
        cert_pem=byte_array(general["certificate"]),
        key_pem=byte_array(general["key"]),
        server_cert_pem=byte_array(hosts[f"{prefix}srvcert"]),
        host_uuid=unescape(hosts.get(f"{prefix}uuid", "")),
        apps=apps,
    )


_PR_SET_DUMPABLE, _PR_SET_NAME = 4, 15
# linux/fcntl.h; not every CPython build exposes them in the fcntl module.
F_ADD_SEALS = getattr(fcntl, "F_ADD_SEALS", 1024 + 9)
F_SEAL_ALL = (
    getattr(fcntl, "F_SEAL_SEAL", 0x1)
    | getattr(fcntl, "F_SEAL_SHRINK", 0x2)
    | getattr(fcntl, "F_SEAL_GROW", 0x4)
    | getattr(fcntl, "F_SEAL_WRITE", 0x8)
)


def harden_process(name: bytes = b"s2spike") -> None:
    """Non-dumpable (no core file, no same-uid ptrace) and a comm name capture_backend can count."""
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(_PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl(PR_SET_DUMPABLE, 0) failed")
    libc.prctl(_PR_SET_NAME, ctypes.c_char_p(name[:15]), 0, 0, 0)


def client_context(identity: Identity) -> ssl.SSLContext:
    """TLS client context with the lab certificate + key, loaded from a sealed memfd (no file).
    The server is NOT verified by a CA (Sunshine's cert is self-signed): callers pin it with
    `pinned_der`."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # pinned instead: nvhttp compares the peer cert to srvcert
    fd = os.memfd_create("s2spike-id", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        os.write(fd, identity.cert_pem.rstrip(b"\n") + b"\n" + identity.key_pem)
        fcntl.fcntl(fd, F_ADD_SEALS, F_SEAL_ALL)  # nothing can change it any more
        ctx.load_cert_chain(f"/proc/self/fd/{fd}")
    finally:
        os.close(fd)
    return ctx


def pinned_der(identity: Identity) -> bytes:
    return ssl.PEM_cert_to_DER_cert(identity.server_cert_pem.decode("ascii"))
