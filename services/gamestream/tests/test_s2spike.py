"""The S2 spike (clean-room V3) on the host: no library, no PyAV, no X, no Sunshine needed."""

import json
import re
import shutil
import subprocess
import sys
import zlib
from pathlib import Path
from typing import Any

import pytest

GAMESTREAM = Path(__file__).resolve().parents[1]
ROOT = GAMESTREAM.parents[1]
sys.path.insert(0, str(GAMESTREAM))

from s2spike import identity, limelight, lockstate, nvhttp, pngout, vk  # noqa: E402
from s2spike import x11_mirror_shim as shim  # noqa: E402

PEM_CERT = "-----BEGIN CERTIFICATE-----\nMIIBfake\n-----END CERTIFICATE-----\n"


def qt_bytes(text: str) -> str:
    return "@ByteArray(" + text.replace("\\", "\\\\").replace("\n", "\\n") + ")"


def conf(tmp_path: Path, *, key: bool = True, srvcert: bool = True) -> Path:
    lines = ["[General]", f"certificate={qt_bytes(PEM_CERT)}"]
    if key:
        lines.append(
            "key=" + qt_bytes("-----BEGIN PRIVATE KEY-----\nAAA\n-----END PRIVATE KEY-----\n")
        )
    lines += ["", "[hosts]", "1\\apps\\1\\id=881448767", "1\\apps\\1\\name=Desktop",
              "1\\apps\\2\\id=1093255277", '1\\apps\\2\\name="Steam Big Picture"',
              "1\\apps\\size=2", "1\\uuid=ABC-123"]  # fmt: skip
    if srvcert:
        lines.append("1\\srvcert=" + qt_bytes(PEM_CERT.replace("fake", "server")))
    lines.append("size=1")
    path = tmp_path / "Moonlight.conf"
    path.write_text("\n".join(lines) + "\n")
    return path


# --- identity -------------------------------------------------------------------------------------


def test_identity_reads_moonlight_qts_qsettings(tmp_path: Path) -> None:
    ident = identity.load(conf(tmp_path))
    assert ident.cert_pem == PEM_CERT.encode()
    assert ident.key_pem.startswith(b"-----BEGIN PRIVATE KEY-----\n")
    assert b"server" in ident.server_cert_pem
    assert ident.apps == {"Desktop": 881448767, "Steam Big Picture": 1093255277}
    assert "PRIVATE" not in repr(ident) and "CERTIFICATE" not in repr(ident)  # never in a log


@pytest.mark.parametrize("missing", ["key", "srvcert"])
def test_identity_refuses_an_unpaired_or_incomplete_client(tmp_path: Path, missing: str) -> None:
    with pytest.raises(ValueError):
        identity.load(conf(tmp_path, **{missing: False}))


def test_qt_escapes() -> None:
    assert identity.unescape(r'"a\nb\\c\x41"') == "a\nb\\cA"
    assert identity.byte_array(r"@ByteArray(x\ny)") == b"x\ny"
    with pytest.raises(ValueError):
        identity.byte_array("plain")


@pytest.mark.skipif(shutil.which("openssl") is None, reason="needs the openssl CLI")
def test_client_context_loads_the_key_from_a_sealed_memfd(tmp_path: Path) -> None:
    key, crt = tmp_path / "k.pem", tmp_path / "c.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key),
         "-out", str(crt), "-days", "1", "-subj", "/CN=s2spike-test"],
        check=True, capture_output=True,
    )  # fmt: skip
    ident = identity.Identity(crt.read_bytes(), key.read_bytes(), crt.read_bytes(), "u", {})
    before = set(Path("/proc/self/fd").iterdir())
    ctx = identity.client_context(ident)
    assert ctx is not None
    assert set(Path("/proc/self/fd").iterdir()) <= before  # the memfd was closed again
    assert identity.pinned_der(ident)[:1] == b"\x30"  # DER SEQUENCE


# --- nvhttp ---------------------------------------------------------------------------------------


def test_launch_query_is_moonlight_qts() -> None:
    p = nvhttp.LaunchParams(
        app_id=881448767, width=1440, height=900, fps=30, rikey=bytes(range(16)),
        riiv=b"\xfe\xdc\xba\x98" + bytes(12), audio_configuration=limelight.CONSTANTS[
            "AUDIO_CONFIGURATION_STEREO"],
    )  # fmt: skip
    q = nvhttp.launch_query(p, "&corever=1")
    assert q == (
        "appid=881448767&mode=1440x900x30&additionalStates=1&sops=1"
        "&rikey=000102030405060708090a0b0c0d0e0f&rikeyid=-19088744"
        "&localAudioPlayMode=1&surroundAudioInfo=196610"
        "&remoteControllersBitmap=0&gcmap=0&gcpersist=0&corever=1"
    )


def test_requests_carry_moonlight_qts_uniqueid_and_never_pair() -> None:
    path = nvhttp.request_path("serverinfo", None)
    assert path.startswith("/serverinfo?uniqueid=0123456789ABCDEF&uuid=")
    for verb in ("pair", "unpair", "pin"):
        with pytest.raises(ValueError):
            nvhttp.request_path(verb, None)
    code = "".join(p.read_text() for p in (GAMESTREAM / "s2spike").glob("*.py"))
    assert not re.search(r"""["'/](un)?pair[?"'&]""", code), "no pairing request in the spike"


def test_reply_parsing() -> None:
    ok = '<root status_code="200"><PairStatus>1</PairStatus><currentgame>0</currentgame></root>'
    assert nvhttp.parse(ok) == {"PairStatus": "1", "currentgame": "0"}
    with pytest.raises(nvhttp.HostError, match="400"):
        nvhttp.parse('<root status_code="400" status_message="An app is already running"/>')
    applist = ('<root status_code="200"><App><AppTitle>Desktop</AppTitle><ID>881448767</ID></App>'
               "</root>")  # fmt: skip
    assert nvhttp.apps(applist) == {"Desktop": 881448767}


# --- limelight layout -----------------------------------------------------------------------------


def test_ctypes_layout_matches_the_pinned_headers() -> None:
    """tests/layout-8599b60.json: native/layout_check.c compiled against moonlight-common-c at the
    commit moonlight-qt 6.1.0 ships (the image recompiles and re-checks it at every start)."""
    layout = json.loads((GAMESTREAM / "tests" / "layout-8599b60.json").read_text())
    assert limelight.layout_mismatches(layout) == []


def test_a_layout_mismatch_is_reported() -> None:
    layout: dict[str, Any] = json.loads((GAMESTREAM / "tests" / "layout-8599b60.json").read_text())
    layout["structs"]["DECODE_UNIT"]["offsets"]["bufferList"] += 8
    layout["constants"]["CAPABILITY_PULL_RENDERER"] = 0x40
    problems = limelight.layout_mismatches(layout)
    assert any("DECODE_UNIT.bufferList" in p for p in problems)
    assert any("CAPABILITY_PULL_RENDERER" in p for p in problems)


def test_the_dockerfile_pins_the_commit_of_the_fixture() -> None:
    dockerfile = (GAMESTREAM / "Dockerfile").read_text()
    assert "ARG MLCC_SHA=8599b6042a4ba27749b0f94134dd614b4328a9bc" in dockerfile


# --- keys -----------------------------------------------------------------------------------------


def test_vk_table_copies_the_lab_keymap() -> None:
    sys.path.insert(0, str(ROOT / "packages" / "poring_env" / "src"))
    from poring_env.keymap import EVDEV_BY_CODE

    assert vk.EVDEV_BY_CODE == EVDEV_BY_CODE  # drift guard: the image has no poring_env
    assert set(vk.CODE_TO_VK) == set(EVDEV_BY_CODE)  # every key the mux can send has a VK


@pytest.mark.parametrize(
    ("code", "vk_code"),
    [("KeyA", 0x41), ("KeyZ", 0x5A), ("Digit0", 0x30), ("Digit9", 0x39), ("F1", 0x70),
     ("F12", 0x7B), ("Enter", 0x0D), ("Escape", 0x1B), ("Space", 0x20), ("ShiftLeft", 0xA0),
     ("ControlLeft", 0xA2), ("AltLeft", 0xA4), ("Semicolon", 0xBA), ("Quote", 0xDE),
     ("BracketLeft", 0xDB), ("Period", 0xBE), ("Slash", 0xBF), ("Backquote", 0xC0),
     ("Numpad0", 0x60), ("ArrowLeft", 0x25)],
)  # fmt: skip
def test_vk_codes(code: str, vk_code: int) -> None:
    assert vk.vk_for_x_keycode(vk.EVDEV_BY_CODE[code] + 8) == vk_code


# --- the X shim's input forwarding (no X server: handle() only) ----------------------------------


class FakeLib:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def __getattr__(self, name: str) -> Any:
        return lambda *a: self.calls.append((name, *a))


class FakeSender:
    def __init__(self) -> None:
        self.lib = FakeLib()
        self.const = limelight.CONSTANTS


def mirror() -> tuple[shim.Mirror, FakeLib]:
    m = shim.Mirror.__new__(shim.Mirror)
    sender = FakeSender()
    m.w, m.h, m.sender, m.log = 1440, 900, sender, lambda _s: None
    m.counts = {"frames_shown": 0, "keys": 0, "buttons": 0, "moves": 0, "wheel": 0,
                "keys_unmapped": 0}  # fmt: skip
    return m, sender.lib


def ev(**kw: int) -> shim.XInputEvent:
    e = shim.XInputEvent()
    for k, v in kw.items():
        setattr(e, k, v)
    return e


def test_shim_forwards_pointer_buttons_and_wheel() -> None:
    m, lib = mirror()
    m.handle(shim.MOTION_NOTIFY, ev(x=2000, y=-5))
    m.handle(shim.BUTTON_PRESS, ev(detail=3))
    m.handle(shim.BUTTON_RELEASE, ev(detail=3))
    m.handle(shim.BUTTON_PRESS, ev(detail=5))
    m.handle(shim.BUTTON_RELEASE, ev(detail=5))  # wheel: press only
    assert lib.calls == [
        ("LiSendMousePositionEvent", 1439, 0, 1440, 900),  # clamped into the stream
        ("LiSendMouseButtonEvent", b"\x07", 0x03),
        ("LiSendMouseButtonEvent", b"\x08", 0x03),
        ("LiSendHighResScrollEvent", -120),
    ]


def test_shim_sends_keys_as_moonlight_qt_does() -> None:
    m, lib = mirror()
    a = vk.EVDEV_BY_CODE["KeyA"] + 8
    shift = vk.EVDEV_BY_CODE["ShiftLeft"] + 8
    m.handle(shim.KEY_PRESS, ev(detail=shift, state=0))
    m.handle(shim.KEY_PRESS, ev(detail=a, state=shim.SHIFT))
    m.handle(shim.KEY_RELEASE, ev(detail=shift, state=shim.SHIFT))
    m.handle(shim.KEY_PRESS, ev(detail=250))  # no VK: counted, not sent
    as_short = lambda v: v - 0x10000  # noqa: E731 -- C `short`: 0x8000 | VK wraps negative
    assert lib.calls == [
        ("LiSendKeyboardEvent", as_short(0x80A0), b"\x03", b"\x01"),
        ("LiSendKeyboardEvent", as_short(0x8041), b"\x03", b"\x01"),
        ("LiSendKeyboardEvent", as_short(0x80A0), b"\x04", b"\x00"),
    ]
    assert m.counts["keys"] == 3 and m.counts["keys_unmapped"] == 1


def test_rdp_loops_interlock_sees_the_shim_window() -> None:
    """rdp-loop refuses to connect while a WM_CLASS "moonlight" window exists; the shim's
    window must match ITS regex (xwininfo -tree prints `("res_name" "res_class")`)."""
    rdp = (ROOT / "services" / "desktop" / "bin" / "rdp-loop.sh").read_text()
    m = re.search(r"grep -qiE '([^']+moonlight[^']*)'", rdp)
    assert m, "rdp-loop's Moonlight interlock moved: update this test"
    xwininfo_line = '  0x400001 "S2 spike (V3, clean room) - Moonlight": ("moonlight" "S2spike")'
    out = subprocess.run(["grep", "-qiE", m.group(1)], input=xwininfo_line, text=True, check=False)
    assert out.returncode == 0
    assert b'"moonlight"' in b'"' + b"moonlight" + b'"'  # the res_name the shim sets (below)
    assert (
        'XClassHint(b"moonlight", b"S2spike")'
        in (GAMESTREAM / "s2spike" / "x11_mirror_shim.py").read_text()
    )


# --- lock gate ------------------------------------------------------------------------------------


def write(dirpath: Path, text: str) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / "capture-backend").write_text(text)
    return dirpath


@pytest.mark.parametrize(
    ("lock", "allowed"),
    [
        ("BACKEND=console\nSEQ=4\nPHASE=steady\nREASON=cleanroom\n", True),
        ("BACKEND=console\nSEQ=4\nPHASE=switching\nREASON=cleanroom-hold\n", False),
        ("BACKEND=rdp\nSEQ=4\nPHASE=steady\n", False),
        ("garbage line\n", False),
    ],
)
def test_stream_only_on_console_steady(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lock: str, allowed: bool
) -> None:
    monkeypatch.setattr(lockstate, "xfreerdp_window_present", lambda _d: False)
    monkeypatch.setattr(lockstate, "moonlight_qt_running", lambda: False)
    ok, _why = lockstate.may_stream(write(tmp_path / "s", lock), ":99")
    assert ok is allowed


def test_never_two_lab_clients(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = write(tmp_path / "s", "BACKEND=console\nPHASE=steady\n")
    monkeypatch.setattr(lockstate, "xfreerdp_window_present", lambda _d: False)
    monkeypatch.setattr(lockstate, "moonlight_qt_running", lambda: True)
    assert lockstate.may_stream(state, ":99")[0] is False
    monkeypatch.setattr(lockstate, "moonlight_qt_running", lambda: False)
    monkeypatch.setattr(lockstate, "xfreerdp_window_present", lambda _d: True)
    assert lockstate.may_stream(state, ":99")[0] is False


def test_moonlight_qt_is_found_by_comm(tmp_path: Path) -> None:
    for pid, comm in (("10", "bash"), ("11", "s2spike"), ("12", "AppRun.wrapped")):
        (tmp_path / pid).mkdir()
        (tmp_path / pid / "comm").write_text(comm + "\n")
    assert lockstate.moonlight_qt_running(tmp_path) is True
    (tmp_path / "12" / "comm").write_text("python3\n")
    assert lockstate.moonlight_qt_running(tmp_path) is False


# --- evidence -------------------------------------------------------------------------------------


class Pixels:
    def __init__(self, h: int, w: int) -> None:
        self.shape = (h, w, 3)
        self._b = bytes((x * 7 + y) % 256 for y in range(h) for x in range(w * 3))

    def tobytes(self) -> bytes:
        return self._b


def test_png_writer_round_trips(tmp_path: Path) -> None:
    img = Pixels(4, 5)
    data = pngout.png_bytes(img)
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR"
    idat = data.index(b"IDAT")
    length = int.from_bytes(data[idat - 4 : idat], "big")
    raw = zlib.decompress(data[idat + 4 : idat + 4 + length])
    assert len(raw) == 4 * (1 + 5 * 3) and raw[1 : 1 + 15] == img.tobytes()[:15]
    pngout.write_atomic(tmp_path / "f.png", data)
    assert (tmp_path / "f.png").read_bytes() == data and not list(tmp_path.glob("*.tmp"))


def test_the_vendored_frame_bus_is_byte_identical() -> None:
    """The gamestream image has no pydantic, so it cannot import poring_env: s2spike carries a copy
    of poring_env/framebus.py. Edit the original and re-copy; never the copy alone."""
    root = Path(__file__).resolve().parents[3]
    original = root / "packages" / "poring_env" / "src" / "poring_env" / "framebus.py"
    vendored = root / "services" / "gamestream" / "s2spike" / "framebus.py"
    assert vendored.read_bytes() == original.read_bytes()
