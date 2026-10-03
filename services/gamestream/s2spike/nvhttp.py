"""Sunshine's GameStream HTTP(S) API, the subset the spike needs: serverinfo, applist, launch,
resume, cancel. Requests mirror Moonlight-qt 6.1.0 (app/backend/nvhttp.cpp) parameter for
parameter, so V3 asks Sunshine for exactly what V1 asks for.

There is deliberately NO pairing code here: the spike only ever uses the lab's existing pairing
(tests assert that no pair/unpair request can be built). The server certificate is pinned to the
one stored at pairing time.
"""

from __future__ import annotations

import http.client
import ssl
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from . import identity as ident

HTTP_PORT = 47989
LAUNCH_TIMEOUT_S = 120  # Moonlight-qt's LAUNCH_TIMEOUT_MS
REQUEST_TIMEOUT_S = 10
ALLOWED_VERBS = frozenset({"serverinfo", "applist", "launch", "resume", "cancel"})


class HostError(RuntimeError):
    """Sunshine answered with a non-200 status_code (or garbage)."""


def surround_audio_info(audio_configuration: int) -> int:
    """SURROUNDAUDIOINFO_FROM_AUDIO_CONFIGURATION: channel mask << 16 | channel count."""
    channel_count = (audio_configuration >> 8) & 0xFF
    channel_mask = (audio_configuration >> 16) & 0xFFFF
    return (channel_mask << 16) | channel_count


def rikeyid(iv: bytes) -> int:
    """The `rikeyid` Moonlight-qt sends: the first 4 IV bytes as a big-endian signed int."""
    return int.from_bytes(iv[:4], "big", signed=True)


@dataclass(frozen=True)
class LaunchParams:
    app_id: int
    width: int
    height: int
    fps: int
    rikey: bytes  # 16 bytes: STREAM_CONFIGURATION.remoteInputAesKey
    riiv: bytes  # 16 bytes: remoteInputAesIv (only the first 4 random, as Moonlight-qt does)
    audio_configuration: int
    sops: bool = True  # --game-optimization (V1's flag)
    local_audio: bool = True  # --audio-on-host (V1's flag)


def launch_query(p: LaunchParams, li_launch_params: str) -> str:
    """Moonlight-qt's startApp() arguments, in its order (no HDR: H.264 8-bit only)."""
    return (
        f"appid={p.app_id}"
        f"&mode={p.width}x{p.height}x{p.fps}"
        f"&additionalStates=1&sops={int(p.sops)}"
        f"&rikey={p.rikey.hex()}"
        f"&rikeyid={rikeyid(p.riiv)}"
        f"&localAudioPlayMode={int(p.local_audio)}"
        f"&surroundAudioInfo={surround_audio_info(p.audio_configuration)}"
        "&remoteControllersBitmap=0&gcmap=0&gcpersist=0"
        f"{li_launch_params}"
    )


def request_path(verb: str, args: str | None) -> str:
    if verb not in ALLOWED_VERBS:
        raise ValueError(f"the spike never sends /{verb}")
    query = f"uniqueid={ident.UNIQUE_ID}&uuid={uuid.uuid4().hex}"
    return f"/{verb}?{query}" + (f"&{args}" if args else "")


def parse(xml_text: str) -> dict[str, str]:
    """A GameStream XML reply -> {tag: text} of the root's children; raises HostError if not 200."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise HostError(f"unparsable reply: {exc}") from None
    status = root.get("status_code", "")
    if status != "200":
        raise HostError(f"status {status}: {root.get('status_message', '')}")
    return {child.tag: (child.text or "") for child in root}


def apps(xml_text: str) -> dict[str, int]:
    root = ET.fromstring(xml_text)
    out: dict[str, int] = {}
    for app in root.iter("App"):
        title, app_id = app.findtext("AppTitle"), app.findtext("ID")
        if title and app_id and app_id.isdigit():
            out[title] = int(app_id)
    return out


class NvHttp:
    def __init__(self, host: str, identity: ident.Identity) -> None:
        self.host = host
        self.identity = identity
        self._ctx = ident.client_context(identity)
        self._pin = ident.pinned_der(identity)
        self.https_port = 0

    def _http(self, path: str) -> str:
        conn = http.client.HTTPConnection(self.host, HTTP_PORT, timeout=REQUEST_TIMEOUT_S)
        try:
            conn.request("GET", path)
            return conn.getresponse().read().decode("utf-8", "replace")
        finally:
            conn.close()

    def _https(self, path: str, timeout: float = REQUEST_TIMEOUT_S) -> str:
        if not self.https_port:
            self.https_port = int(self.serverinfo_http().get("HttpsPort") or 47984)
        conn = http.client.HTTPSConnection(
            self.host, self.https_port, timeout=timeout, context=self._ctx
        )
        try:
            conn.connect()
            sock = conn.sock
            assert isinstance(sock, ssl.SSLSocket)
            if sock.getpeercert(binary_form=True) != self._pin:
                raise HostError("the host's certificate is not the one paired: refusing")
            conn.request("GET", path)
            return conn.getresponse().read().decode("utf-8", "replace")
        except (TimeoutError, OSError) as exc:
            raise HostError(f"{path.split('?')[0]}: {exc}") from None
        finally:
            conn.close()

    def serverinfo_http(self) -> dict[str, str]:
        """Unauthenticated serverinfo (no client cert): HttpsPort, versions. PairStatus is 0."""
        return parse(self._http(request_path("serverinfo", None)))

    def serverinfo(self) -> dict[str, str]:
        """Authenticated serverinfo: PairStatus=1 proves the lab certificate is paired."""
        return parse(self._https(request_path("serverinfo", None)))

    def applist(self) -> dict[str, int]:
        return apps(self._https(request_path("applist", None)))

    def launch(self, p: LaunchParams, li_launch_params: str, resume: bool) -> str:
        """/launch (or /resume when an app already runs); returns sessionUrl0 (the RTSP URL)."""
        verb = "resume" if resume else "launch"
        reply = parse(
            self._https(request_path(verb, launch_query(p, li_launch_params)), LAUNCH_TIMEOUT_S)
        )
        return reply.get("sessionUrl0", "")

    def cancel(self) -> None:
        parse(self._https(request_path("cancel", None)))
