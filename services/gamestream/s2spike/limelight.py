"""ctypes bindings for moonlight-common-c (Limelight.h) at the commit moonlight-qt 6.1.0 ships.

Every struct below is checked against layout.json -- sizeof/offsetof printed by a C program compiled
against the PINNED headers in the image's builder stage -- before the library is used: a silent
offset mismatch would send garbage to the host, so a mismatch refuses to start.

CONNECTION_LISTENER_CALLBACKS.logMessage is variadic, which ctypes can't implement; libs2shim.so's
s2_log_message formats the line and passes it to a plain callback (s2_set_log_sink).
"""

from __future__ import annotations

import ctypes
import json
from ctypes import (
    CFUNCTYPE,
    POINTER,
    Structure,
    c_bool,
    c_char,
    c_char_p,
    c_int,
    c_short,
    c_ubyte,
    c_uint,
    c_uint16,
    c_uint64,
    c_ushort,
    c_void_p,
)
from pathlib import Path
from typing import Any


class STREAM_CONFIGURATION(Structure):  # noqa: N801 -- the C names, for the layout check
    _fields_ = [
        ("width", c_int),
        ("height", c_int),
        ("fps", c_int),
        ("bitrate", c_int),
        ("packetSize", c_int),
        ("streamingRemotely", c_int),
        ("audioConfiguration", c_int),
        ("supportedVideoFormats", c_int),
        ("clientRefreshRateX100", c_int),
        ("colorSpace", c_int),
        ("colorRange", c_int),
        ("encryptionFlags", c_int),
        ("remoteInputAesKey", c_char * 16),
        ("remoteInputAesIv", c_char * 16),
    ]


class SERVER_INFORMATION(Structure):  # noqa: N801
    _fields_ = [
        ("address", c_char_p),
        ("serverInfoAppVersion", c_char_p),
        ("serverInfoGfeVersion", c_char_p),
        ("rtspSessionUrl", c_char_p),
        ("serverCodecModeSupport", c_int),
    ]


class LENTRY(Structure):
    pass


LENTRY._fields_ = [
    ("next", POINTER(LENTRY)),
    ("data", c_void_p),
    ("length", c_int),
    ("bufferType", c_int),
]


class DECODE_UNIT(Structure):  # noqa: N801
    _fields_ = [
        ("frameNumber", c_int),
        ("frameType", c_int),
        ("frameHostProcessingLatency", c_uint16),
        ("receiveTimeMs", c_uint64),
        ("enqueueTimeMs", c_uint64),
        ("presentationTimeMs", c_uint),
        ("fullLength", c_int),
        ("bufferList", POINTER(LENTRY)),
        ("hdrActive", c_bool),
        ("colorspace", c_ubyte),
    ]


# Callback types (fixed-argument ones only; logMessage goes through the shim).
DrSetup = CFUNCTYPE(c_int, c_int, c_int, c_int, c_int, c_void_p, c_int)
DrVoid = CFUNCTYPE(None)
DrSubmit = CFUNCTYPE(c_int, POINTER(DECODE_UNIT))
ArInit = CFUNCTYPE(c_int, c_int, c_void_p, c_void_p, c_int)
ArSample = CFUNCTYPE(None, c_void_p, c_int)
ClStage = CFUNCTYPE(None, c_int)
ClStageFailed = CFUNCTYPE(None, c_int, c_int)
ClVoid = CFUNCTYPE(None)
ClTerminated = CFUNCTYPE(None, c_int)
ClStatus = CFUNCTYPE(None, c_int)
LogSink = CFUNCTYPE(None, c_char_p)


class DECODER_RENDERER_CALLBACKS(Structure):  # noqa: N801
    _fields_ = [
        ("setup", DrSetup),
        ("start", DrVoid),
        ("stop", DrVoid),
        ("cleanup", DrVoid),
        ("submitDecodeUnit", DrSubmit),
        ("capabilities", c_int),
    ]


class AUDIO_RENDERER_CALLBACKS(Structure):  # noqa: N801
    _fields_ = [
        ("init", ArInit),
        ("start", DrVoid),
        ("stop", DrVoid),
        ("cleanup", DrVoid),
        ("decodeAndPlaySample", ArSample),
        ("capabilities", c_int),
    ]


class CONNECTION_LISTENER_CALLBACKS(Structure):  # noqa: N801
    _fields_ = [
        ("stageStarting", ClStage),
        ("stageComplete", ClStage),
        ("stageFailed", ClStageFailed),
        ("connectionStarted", ClVoid),
        ("connectionTerminated", ClTerminated),
        ("logMessage", c_void_p),  # the shim's s2_log_message (variadic in C)
        ("rumble", c_void_p),
        ("connectionStatusUpdate", ClStatus),
        ("setHdrMode", c_void_p),
        ("rumbleTriggers", c_void_p),
        ("setMotionEventState", c_void_p),
        ("setControllerLED", c_void_p),
    ]


STRUCTS: dict[str, type[Structure]] = {
    "STREAM_CONFIGURATION": STREAM_CONFIGURATION,
    "SERVER_INFORMATION": SERVER_INFORMATION,
    "LENTRY": LENTRY,
    "DECODE_UNIT": DECODE_UNIT,
    "DECODER_RENDERER_CALLBACKS": DECODER_RENDERER_CALLBACKS,
    "AUDIO_RENDERER_CALLBACKS": AUDIO_RENDERER_CALLBACKS,
    "CONNECTION_LISTENER_CALLBACKS": CONNECTION_LISTENER_CALLBACKS,
}

# The constants this module relies on, checked against the headers' values in layout.json.
CONSTANTS = {
    "CAPABILITY_PULL_RENDERER": 0x20,
    "ENCFLG_ALL": -1,  # 0xFFFFFFFF in an int field
    "ENCFLG_AUDIO": 0x1,
    "VIDEO_FORMAT_H264": 0x1,
    "AUDIO_CONFIGURATION_STEREO": (0x3 << 16) | (2 << 8) | 0xCA,
    "SCM_H264": 0x1,
    "STREAM_CFG_LOCAL": 0,
    "COLORSPACE_REC_601": 0,
    "COLOR_RANGE_LIMITED": 0,
    "BUTTON_ACTION_PRESS": 0x07,
    "BUTTON_ACTION_RELEASE": 0x08,
    "BUTTON_LEFT": 0x01,
    "BUTTON_MIDDLE": 0x02,
    "BUTTON_RIGHT": 0x03,
    "BUTTON_X1": 0x04,
    "BUTTON_X2": 0x05,
    "KEY_ACTION_DOWN": 0x03,
    "KEY_ACTION_UP": 0x04,
    "MODIFIER_SHIFT": 0x01,
    "MODIFIER_CTRL": 0x02,
    "MODIFIER_ALT": 0x04,
    "MODIFIER_META": 0x08,
    "DR_OK": 0,
    "ML_ERROR_GRACEFUL_TERMINATION": 0,
}


def capability_slices_per_frame(n: int) -> int:
    return (n & 0xFF) << 24


def layout_mismatches(layout: dict[str, Any]) -> list[str]:
    """Every difference between these ctypes structs/constants and the C layout (empty = OK)."""
    problems: list[str] = []
    structs = layout.get("structs", {})
    for name, cls in STRUCTS.items():
        c = structs.get(name)
        if c is None:
            problems.append(f"{name}: missing from layout.json")
            continue
        if ctypes.sizeof(cls) != c["size"]:
            problems.append(f"{name}: sizeof {ctypes.sizeof(cls)} != C {c['size']}")
        mine = {f[0]: getattr(cls, f[0]).offset for f in cls._fields_}
        if set(mine) != set(c["offsets"]):
            problems.append(f"{name}: fields {sorted(set(mine) ^ set(c['offsets']))} differ")
        for f, off in c["offsets"].items():
            if f in mine and mine[f] != off:
                problems.append(f"{name}.{f}: offset {mine[f]} != C {off}")
    consts = layout.get("constants", {})
    for name, value in CONSTANTS.items():
        c_value = consts.get(name)
        if c_value is None:
            problems.append(f"{name}: missing from layout.json")
        elif ctypes.c_int(c_value).value != ctypes.c_int(value).value:
            problems.append(f"{name}: {value} != C {c_value}")
    return problems


class Lib:
    """The loaded library + shim, with argtypes set for every function the spike calls."""

    def __init__(self, lib_dir: Path) -> None:
        layout = json.loads((lib_dir / "layout.json").read_text())
        problems = layout_mismatches(layout)
        if problems:
            raise RuntimeError("ctypes layout != pinned headers: " + "; ".join(problems))
        self.sha = (lib_dir / "MLCC_SHA").read_text().strip()
        self.mlcc = ctypes.CDLL(str(lib_dir / "libmoonlight-common-c.so"))
        self.shim = ctypes.CDLL(str(lib_dir / "libs2shim.so"))
        m, s = self.mlcc, self.shim
        sig: dict[str, tuple[Any, list[Any]]] = {
            "LiInitializeStreamConfiguration": (None, [POINTER(STREAM_CONFIGURATION)]),
            "LiInitializeVideoCallbacks": (None, [POINTER(DECODER_RENDERER_CALLBACKS)]),
            "LiInitializeAudioCallbacks": (None, [POINTER(AUDIO_RENDERER_CALLBACKS)]),
            "LiInitializeConnectionCallbacks": (None, [POINTER(CONNECTION_LISTENER_CALLBACKS)]),
            "LiInitializeServerInformation": (None, [POINTER(SERVER_INFORMATION)]),
            "LiStartConnection": (
                c_int,
                [
                    POINTER(SERVER_INFORMATION),
                    POINTER(STREAM_CONFIGURATION),
                    POINTER(CONNECTION_LISTENER_CALLBACKS),
                    POINTER(DECODER_RENDERER_CALLBACKS),
                    POINTER(AUDIO_RENDERER_CALLBACKS),
                    c_void_p,
                    c_int,
                    c_void_p,
                    c_int,
                ],
            ),
            "LiStopConnection": (None, []),
            "LiInterruptConnection": (None, []),
            "LiGetStageName": (c_char_p, [c_int]),
            "LiGetLaunchUrlQueryParameters": (c_char_p, []),
            "LiWaitForNextVideoFrame": (c_bool, [POINTER(c_void_p), POINTER(POINTER(DECODE_UNIT))]),
            "LiCompleteVideoFrame": (None, [c_void_p, c_int]),
            "LiWakeWaitForVideoFrame": (None, []),
            "LiRequestIdrFrame": (None, []),
            "LiSendMousePositionEvent": (c_int, [c_short, c_short, c_short, c_short]),
            "LiSendMouseButtonEvent": (c_int, [c_char, c_int]),
            "LiSendKeyboardEvent": (c_int, [c_short, c_char, c_char]),
            "LiSendHighResScrollEvent": (c_int, [c_short]),
        }
        for name, (restype, argtypes) in sig.items():
            fn = getattr(m, name)
            fn.restype, fn.argtypes = restype, argtypes
        s.s2_set_log_sink.restype, s.s2_set_log_sink.argtypes = None, [LogSink]
        self.log_message_ptr = ctypes.cast(s.s2_log_message, c_void_p).value

    def __getattr__(self, name: str) -> Any:
        return getattr(self.mlcc, name)


def char(value: int) -> bytes:
    """A C `char` argument (ctypes wants a 1-byte bytes object)."""
    return bytes([value & 0xFF])


def ushort(value: int) -> int:
    return c_ushort(value).value
