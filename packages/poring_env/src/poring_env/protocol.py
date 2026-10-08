"""Wire protocol for every poring-lab channel.

The Pydantic models here are the single source of truth. `poring-protocol-schema` prints the
JSON Schema that `scripts/gen_protocol.sh` commits to `packages/poring_env/schema/` and turns into
TypeScript for the frontend; `tests/test_protocol.py` fails when the committed schema drifts.

Clock rule (ADR-0003): every message carries
  * ``t_mono_ns`` -- the SENDER's monotonic clock in nanoseconds, and
  * ``frame_id``  -- the frame the message refers to or was produced from (``NO_FRAME`` if none).
Backend and vision share the host kernel's CLOCK_MONOTONIC, so their timestamps compare directly.
The browser's ``performance.now()`` is a separate clock domain: relate it only via ping/pong echo.
JavaScript parses these integers as float64, which drops sub-microsecond precision once uptime
passes ~104 days -- irrelevant for millisecond latency work.
"""

import json
import sys
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

NO_FRAME = -1

# Cap on one clipboard paste, in UTF-8 bytes (ADR-0004). Well inside one X ChangeProperty request
# (Xvfb's max request is ~256 KiB), so the backend never needs the INCR protocol.
PASTE_MAX_BYTES = 64 * 1024

_MODEL_CONFIG = ConfigDict(
    extra="forbid",
    frozen=True,
    # Fields with defaults (notably the `type` discriminator) are still always serialized; marking
    # them required keeps the generated TypeScript discriminants non-optional.
    json_schema_serialization_defaults_required=True,
)

NormCoord = Annotated[float, Field(ge=0.0, le=1.0)]


class Mode(StrEnum):
    """Input-mux mode (ADR-0002). The backend boots in HUMAN; only ASSIST can come back by itself,
    after a GUARDED restart (scripts/guarded_build.py restart:backend; ADR-0002 amendment)."""

    HUMAN = "HUMAN"
    BOT = "BOT"
    ASSIST = "ASSIST"


class Message(BaseModel):
    """Fields every pipeline message carries."""

    model_config = _MODEL_CONFIG

    t_mono_ns: int = Field(ge=0, description="Sender's monotonic clock, ns (see module docstring).")
    frame_id: int = Field(
        default=NO_FRAME,
        ge=NO_FRAME,
        description="Frame this message refers to or was produced from; -1 means none.",
    )


# --- input events (browser -> backend, and inside agent_input) -----------------------------------


class MouseMove(Message):
    """Absolute pointer move; x/y are normalized to [0, 1] over the captured screen."""

    type: Literal["mouse_move"] = "mouse_move"
    x: NormCoord
    y: NormCoord


class MouseButton(Message):
    """Button press or release. With x/y the pointer moves there first; without them (null) the
    button acts wherever the pointer already is -- used for the mux's synthetic releases, which
    must never yank the pointer away from whoever now controls it."""

    type: Literal["mouse_button"] = "mouse_button"
    button: Literal["left", "middle", "right"]
    action: Literal["down", "up"]
    x: NormCoord | None = None
    y: NormCoord | None = None


class Wheel(Message):
    """Wheel notches at the current pointer position; dy > 0 scrolls down (DOM deltaY sign)."""

    type: Literal["wheel"] = "wheel"
    dy: int = Field(ge=-10, le=10)


class Key(Message):
    """A physical key named by KeyboardEvent.code -- layout-independent (see keymap.py)."""

    type: Literal["key"] = "key"
    code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9]+$")
    action: Literal["down", "up"]


class ReleaseAll(Message):
    """Release every key and button the sender holds (browser blur, agent reset)."""

    type: Literal["release_all"] = "release_all"


type InputEvent = Annotated[
    MouseMove | MouseButton | Wheel | Key | ReleaseAll, Field(discriminator="type")
]


# --- control --------------------------------------------------------------------------------------


class SetMode(Message):
    """Switch the input mux (HUMAN / BOT / ASSIST)."""

    type: Literal["set_mode"] = "set_mode"
    mode: Mode


class ClipboardPaste(Message):
    """Paste this text into the focused Windows window (ADR-0004: human-only, browser channel only).

    The backend owns the X CLIPBOARD for the duration of one paste, sends Ctrl+V through the mux and
    answers with a ``PasteResult``. The text itself is never logged."""

    type: Literal["clipboard_paste"] = "clipboard_paste"
    request_id: int = Field(ge=0, description="Echoed in the PasteResult.")
    text: str = Field(
        min_length=1,
        max_length=PASTE_MAX_BYTES,
        description=f"At most {PASTE_MAX_BYTES} bytes once UTF-8 encoded.",
    )

    @field_validator("text")
    @classmethod
    def _utf8_within_cap(cls, text: str) -> str:
        try:
            size = len(text.encode("utf-8"))
        except UnicodeEncodeError:  # lone surrogate from a broken JS string
            raise ValueError("text is not valid Unicode") from None
        if size > PASTE_MAX_BYTES:
            raise ValueError(f"text is {size} bytes as UTF-8, over the {PASTE_MAX_BYTES} cap")
        return text


class FrameTiming(BaseModel):
    """When one frame reached a viewer, all on the VIEWER's clock (ns)."""

    model_config = _MODEL_CONFIG

    frame_id: int = Field(ge=0)
    recv_ns: int = Field(ge=0)
    decoded_ns: int = Field(ge=0)
    painted_ns: int = Field(ge=0)


class SecretInput(Message):
    """Human secret typing on/off (a password into Windows or the game), from the console's toggle.

    While any console connection has it on, the backend still injects every key through the mux,
    but the input log keeps no key identities for the human source (type, action and timing only),
    a synthetic release of a human-held key is redacted the same way, and a paste logs neither its
    length nor a digest. Browser channel only; never on the agent protocol."""

    type: Literal["secret_input"] = "secret_input"
    on: bool


class ViewerTiming(Message):
    """Latency telemetry from a console tab, about once a second (Phase 0).

    ``offset_ns`` maps the tab's clock to the backend's: backend = browser + offset. It comes from
    Cristian's algorithm on the ping/pong with the smallest round trip, so the mapping is uncertain
    by ``offset_uncertainty_ns`` (half that round trip)."""

    type: Literal["viewer_timing"] = "viewer_timing"
    offset_ns: int | None = None
    offset_uncertainty_ns: int | None = Field(default=None, ge=0)
    visible: bool
    user_agent: str = Field(default="", max_length=200)
    frames: list[FrameTiming] = Field(default_factory=list, max_length=240)


class Ping(Message):
    """Round-trip probe; its ``t_mono_ns`` comes back verbatim as ``Pong.echo_t_mono_ns``."""

    type: Literal["ping"] = "ping"


class Pong(Message):
    """Answer to a Ping. ``t_mono_ns`` is the backend clock; the echo is the pinger's clock."""

    type: Literal["pong"] = "pong"
    echo_t_mono_ns: int = Field(ge=0)


# --- backend -> viewers / agent -------------------------------------------------------------------


class FrameMeta(Message):
    """Sent immediately before exactly one binary WebSocket message holding this frame's JPEG."""

    type: Literal["frame"] = "frame"
    t_capture_ns: int = Field(ge=0)
    t_encoded_ns: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    nbytes: int = Field(gt=0)


class CaptureBackend(BaseModel):
    """Who owns the ONE Windows session (ADR-0009): the capture-backend lock, read by the backend.

    ``hold`` = the lock is unreadable or not mounted (both clients refuse to connect)."""

    model_config = _MODEL_CONFIG

    backend: Literal["rdp", "console", "hold"]
    seq: int = Field(default=0, ge=0, description="Lock generation; every handover increments it.")
    phase: Literal["steady", "switching", ""] = Field(
        default="", description="switching = a handover is in progress; '' when backend=hold."
    )
    since: int | None = Field(default=None, description="Unix time of the last lock write.")
    owner: str | None = Field(default=None, description="Who wrote the lock (a tool name).")
    reason: str | None = Field(default=None, description="Why: hold reason, or the handover.")


class CleanRoom(BaseModel):
    """A clean-room experiment in progress (ADR-0009): the session stays on the console, RDP holds,
    and only the lab's stream client varies. Read from ``state/cleanroom`` (written only by
    scripts/capture_backend.py) and honoured only while the lock's reason is ``cleanroom*``."""

    model_config = _MODEL_CONFIG

    variant: Literal["V1", "V1gdb", "V2", "V3", "V3b", "S2"] | None = Field(
        default=None, description="The stream client variant under test; null = none started yet."
    )
    streaming: bool = Field(
        description="A variant is streaming now (lock console/steady); false between variants."
    )
    box_left_s: int | None = Field(
        default=None, ge=0, description="Seconds left in the variant's time box; null = no box."
    )
    hard_cap_left_s: int | None = Field(
        default=None, ge=0, description="Seconds until the room's hard cap ends it; null = none."
    )


class EnvironmentStatus(BaseModel):
    """The environment interlock's verdict (ADR-0016, rewritten 2026-10-04), for the console and
    /health. Only humans see it: the copy of Status sent to an agent carries null here."""

    model_config = _MODEL_CONFIG

    state: Literal["green", "window", "red"] = Field(
        description="green: an allowed environment is attested; window: an operator window lets "
        "ASSIST's bot side through; red: every bot press is refused."
    )
    reason: str = Field(description='"ok", "window:<kind>", or why bot presses are refused.')
    env_id: str | None = Field(default=None, description="The attested environment's id.")
    window: Literal["login", "desktop"] | None = None
    window_left_s: float | None = Field(default=None, ge=0)
    attest_age_s: float | None = Field(
        default=None, description="Seconds since the sniffer's last attestation; null = none yet."
    )


class ForegroundStatus(BaseModel):
    """The TYPING-ONLY foreground gate (2026-10-06): the last check before a bot typing batch.
    Only humans see it: the copy of Status sent to an agent carries null here."""

    model_config = _MODEL_CONFIG

    state: Literal["ok", "refused", "exempt", "unchecked"] = Field(
        description="ok: the client's active title bar was seen on a fresh frame; refused: the "
        "batch's keys were refused and held bot keys released; exempt: a desktop operator window "
        "(the agent's own console); unchecked: no bot typing since boot."
    )
    reason: str | None = Field(default=None, description="ok, or why the typing was refused.")
    distance: float | None = Field(default=None, description="Signature distance (match <= 6).")
    age_ms: float | None = Field(default=None, description="Age of the frame that was judged.")
    path: Literal["x11", "bus"] | None = Field(default=None, description="Where it was seen.")
    since_s: float | None = Field(default=None, ge=0, description="Seconds since that check.")
    refused: int = Field(default=0, ge=0, description="Refused typing batches since boot.")


class Status(Message):
    """Mux and pipeline state, pushed at ~1 Hz and on every change."""

    type: Literal["status"] = "status"
    mode: Mode
    lease_until_ns: int | None = Field(
        default=None, description="End of the ASSIST human lease (backend clock); null = none."
    )
    bot_connected: bool
    rdp_window_present: bool | None = Field(
        default=None, description="An xfreerdp window exists on the display; null = X unreachable."
    )
    stream_window_present: bool | None = Field(
        default=None,
        description="A Moonlight (console-mode) window is on the display; null = X unreachable.",
    )
    capture_backend: CaptureBackend | None = Field(
        default=None, description="The capture-backend lock (ADR-0009); null = not read yet."
    )
    alarms: list[str] = Field(
        default_factory=list,
        description=(
            "Safety alarms the console shows RED (2026-10-04), e.g. watchdog_down: a clean-room "
            "session runs without its watchdog."
        ),
    )
    cleanroom: CleanRoom | None = Field(
        default=None, description="The clean room in progress (ADR-0009); null = none."
    )
    capture_fps: float = Field(ge=0.0)
    viewers: int = Field(ge=0)
    clipboard_enabled: bool = Field(
        default=False,
        description=(
            "Clipboard paste to Windows is available (ADR-0004): RDP mode only -- in console mode "
            "a Ctrl+V would paste Windows' own clipboard."
        ),
    )
    transfer_enabled: bool = Field(
        default=False, description="The \\\\tsclient\\transfer file area is available (ADR-0004)."
    )
    # Console tuning, switched at runtime by the backend (Phase 0, docs/phase0-latency.md)
    move_interval_ms: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Pointer-move send interval; null = one per animation frame (the original).",
    )
    paint: Literal["decode", "raf"] = Field(
        default="decode",
        description="decode: draw each frame once decoded; raf: newest decoded frame per rAF.",
    )
    game_black: bool | None = Field(
        default=None,
        description=(
            "The game region has been near-uniformly black for the hold time (in RDP mode, usually "
            "a lost D3D device after a reconnect; in console mode, no game picture in the stream); "
            "null = unknown (no recent grab)."
        ),
    )
    human_secret: bool = Field(
        default=False,
        description=(
            "Human secret typing is on (a console's SecretInput): the input log keeps no human key "
            "identities until it is off."
        ),
    )
    mode_restored: bool = Field(
        default=False,
        description=(
            "ASSIST was restored automatically after a guarded backend restart (ADR-0002 "
            "amendment); false again once a human sets the mode."
        ),
    )
    environment: EnvironmentStatus | None = Field(
        default=None,
        description="The environment interlock (ADR-0016); null in an agent's copy of Status.",
    )
    foreground: ForegroundStatus | None = Field(
        default=None,
        description="The typing-only foreground gate (2026-10-06); null in an agent's copy.",
    )
    bot_agents: list[str] = Field(
        default_factory=list,
        description="The connected agents' AgentHello ids (e.g. auto_recover: guarded_build's GM "
        "re-login after a sniffer restart, 2026-10-04).",
    )


class PasteResult(Message):
    """Outcome of one ClipboardPaste. ``reason`` is "ok" or why it was refused or failed."""

    type: Literal["paste_result"] = "paste_result"
    request_id: int = Field(ge=0)
    ok: bool
    reason: str = Field(max_length=64)
    chars: int = Field(ge=0, description="Characters offered to Windows (0 when refused).")


class ErrorReply(Message):
    """A message from this sender was dropped: it failed validation or could not be read.

    Never silent (ADR-0004 decision 4): the drop is also logged and counted in /health."""

    type: Literal["error"] = "error"
    channel: Literal["ws_input", "ws_stream", "agent", "ingest", "ws_packets"]
    reason: str = Field(max_length=128, description="e.g. missing:key.t_mono_ns, json_invalid.")
    ref_type: str | None = Field(
        default=None, max_length=32, description="The dropped message's type, if readable."
    )


class Box(BaseModel):
    """One detection, corners normalized to [0, 1]."""

    model_config = _MODEL_CONFIG

    x1: NormCoord
    y1: NormCoord
    x2: NormCoord
    y2: NormCoord
    cls: str = Field(min_length=1, max_length=64)
    conf: float = Field(ge=0.0, le=1.0)


class Detections(Message):
    """Detections computed on ``frame_id`` (the agent's own grab); relayed to viewers as overlay."""

    type: Literal["detections"] = "detections"
    t_capture_ns: int = Field(ge=0)
    boxes: list[Box] = Field(default_factory=list, max_length=512)


class RoutePoint(BaseModel):
    """One point of a planned route, normalized to [0, 1] like a detection box."""

    model_config = _MODEL_CONFIG

    x: NormCoord
    y: NormCoord
    kind: Literal["start", "waypoint", "goal", "click", "feet"] = "waypoint"


class RouteSegment(BaseModel):
    """A stretch of route the character has just walked over (a LIVE preview): drawn fading by
    its age, then gone (Batt 2026-10-08: the consumed route disappears)."""

    model_config = _MODEL_CONFIG

    points: list[RoutePoint] = Field(min_length=2, max_length=8)
    age_ms: int = Field(ge=0, le=10_000)


class RouteRect(BaseModel):
    """A client UI window the overlay must stay UNDER (normalized like the points)."""

    model_config = _MODEL_CONFIG

    x: NormCoord
    y: NormCoord
    w: NormCoord
    h: NormCoord


class RoutePreview(Message):
    """The agent's PLANNED route, drawn for the human over the stream (walk@8, Batt 2026-10-07):
    the waypoint polyline it will follow and the point it will click next. Display only -- it
    moves nothing and never reaches the mux. An empty list clears it; it fades after ttl_ms.

    LIVE (Batt 2026-10-08): the route is anchored to the WORLD. The agent re-projects its map cells
    for this message's t_mono_ns (the host clock, the stream frames' clock too) from the
    character's CURRENT position, ~20 times a second; the first point is the character's feet
    ("feet"), `passed` holds the stretches just walked over (fading), `clip` the client's UI
    windows. The console draws the live message nearest the displayed frame's capture time and
    nothing when none is close: a stale route is never drawn."""

    type: Literal["route_preview"] = "route_preview"
    points: list[RoutePoint] = Field(default_factory=list, max_length=64)
    label: str = Field(default="", max_length=64)
    ttl_ms: int = Field(default=5000, ge=0, le=60_000)
    live: bool = False
    passed: list[RouteSegment] = Field(default_factory=list, max_length=16)
    clip: list[RouteRect] = Field(default_factory=list, max_length=16)


# --- the operator HUD (display only; Batt 2026-10-08, docs/phase4-ui.md) --------------------------

# One plain-words line: bounded, printable (no control characters, so no line breaks either). The
# console renders it as TEXT only (canvas fillText / React text nodes), never as markup.
HudText = Annotated[str, Field(max_length=96, pattern=r"^[^\x00-\x1f\x7f]*$")]
HUD_MAX_UNITS = 64
HUD_MAX_LOG = 12


class HudPoint(BaseModel):
    """A point on the desktop, normalized to [0, 1] like a detection box."""

    model_config = _MODEL_CONFIG

    x: NormCoord
    y: NormCoord


class HudRect(BaseModel):
    """A rectangle on the desktop, normalized to [0, 1] (top-left x, y; width, height)."""

    model_config = _MODEL_CONFIG

    x: NormCoord
    y: NormCoord
    w: NormCoord
    h: NormCoord


class HudCell(BaseModel):
    """A map cell (the rules reason in cells)."""

    model_config = _MODEL_CONFIG

    x: int = Field(ge=0, le=4096)
    y: int = Field(ge=0, le=4096)


class HudUnit(BaseModel):
    """One detected unit as the rule saw it. ``dist_cells`` is the Chebyshev distance in CELLS from
    our cell to the cell under the unit's feet, computed by the agent from its camera model and
    the client's picking (never screen px); null when no cell could be picked."""

    model_config = _MODEL_CONFIG

    cls: str = Field(min_length=1, max_length=32)
    conf: float = Field(ge=0.0, le=1.0)
    box: HudRect
    foot: HudPoint
    dist_cells: int | None = Field(default=None, ge=0, le=4096)
    id: int | None = Field(default=None, ge=0, le=2**31 - 1, description="A track id, if any.")


class HudLock(BaseModel):
    """The rule's locked target: a unit of this message by ``index``, or by track ``id`` (a lock
    may outlive its unit's detection). ``lock_remaining_ms`` counts down from this message."""

    model_config = _MODEL_CONFIG

    index: int | None = Field(default=None, ge=0, lt=HUD_MAX_UNITS)
    id: int | None = Field(default=None, ge=0, le=2**31 - 1)
    lock_remaining_ms: int = Field(ge=0, le=60_000)


class HudZone(BaseModel):
    """The work zone: the game area minus the client's UI windows (``exclude``)."""

    model_config = _MODEL_CONFIG

    area: HudRect
    exclude: list[HudRect] = Field(default_factory=list, max_length=16)


class HudWalk(BaseModel):
    """The walk vector: the destination cell, a short text, and (when on screen) the vector from
    our feet (``start``) to the destination (``end``)."""

    model_config = _MODEL_CONFIG

    dest: HudCell | None = None
    text: HudText = ""
    start: HudPoint | None = None
    end: HudPoint | None = None


class HudCounters(BaseModel):
    """Units in view and the detector's rate (frames per second; null when unknown)."""

    model_config = _MODEL_CONFIG

    units: int = Field(default=0, ge=0, le=512)
    det_fps: float | None = Field(default=None, ge=0.0, le=1000.0)


class OperatorHud(Message):
    """The operator HUD (Batt 2026-10-08, docs/phase4-ui.md): what the rule saw and decided, drawn
    for the human over the stream on its own canvas -- detector boxes with class, confidence and
    distance in CELLS, the locked target with its countdown, the work zone, the walk vector, a
    short plain-words log and counters. DISPLAY ONLY, exactly like RoutePreview: the backend relays
    it to viewers, never to the mux, never into the input log; it carries no input. A console
    shows it only while its per-tab HUD toggle is on (off on every load), and drops it after
    ttl_ms (0 clears at once)."""

    type: Literal["operator_hud"] = "operator_hud"
    units: list[HudUnit] = Field(default_factory=list, max_length=HUD_MAX_UNITS)
    lock: HudLock | None = None
    zone: HudZone | None = None
    walk: HudWalk | None = None
    log: list[HudText] = Field(default_factory=list, max_length=HUD_MAX_LOG)
    counters: HudCounters = Field(default_factory=HudCounters)
    label: str = Field(default="", max_length=64)
    ttl_ms: int = Field(default=1500, ge=0, le=60_000)


# --- agent <-> backend ----------------------------------------------------------------------------


class AgentHello(Message):
    """First message on /internal/agent."""

    type: Literal["agent_hello"] = "agent_hello"
    agent_id: str = Field(min_length=1, max_length=64)
    version: str = Field(min_length=1, max_length=64)


class AgentInput(Message):
    """A batch of bot input decided on ``frame_id`` (captured at ``t_capture_ns``)."""

    type: Literal["agent_input"] = "agent_input"
    t_capture_ns: int = Field(ge=0)
    events: list[InputEvent] = Field(min_length=1, max_length=64)
    sensitive: bool = Field(
        default=False,
        description=(
            "Credentials or other secrets: the input log keeps only the event count and timing, "
            "never key identities. Refused unless every key/button it presses is released within "
            "the same batch (nothing held could leak later through a synthetic release)."
        ),
    )


class InputAck(Message):
    """Mux verdict for one AgentInput batch."""

    type: Literal["input_ack"] = "input_ack"
    accepted: int = Field(ge=0)
    dropped: int = Field(ge=0)
    reasons: list[str] = Field(default_factory=list)


# --- channels -------------------------------------------------------------------------------------

# ClipboardPaste is deliberately ONLY on the browser channel: the agent protocol has no clipboard or
# file-transfer message at all (ADR-0004), and tests pin that.
type BrowserToBackend = Annotated[
    MouseMove
    | MouseButton
    | Wheel
    | Key
    | ReleaseAll
    | SetMode
    | Ping
    | ClipboardPaste
    | SecretInput
    | ViewerTiming,
    Field(discriminator="type"),
]
type BackendToBrowser = Annotated[
    FrameMeta | Status | Detections | RoutePreview | OperatorHud | Pong | PasteResult | ErrorReply,
    Field(discriminator="type"),
]
type AgentToBackend = Annotated[
    AgentHello | AgentInput | Detections | RoutePreview | OperatorHud | Ping,
    Field(discriminator="type"),
]
type BackendToAgent = Annotated[Status | InputAck | Pong | ErrorReply, Field(discriminator="type")]

_BROWSER_TO_BACKEND: TypeAdapter[BrowserToBackend] = TypeAdapter(BrowserToBackend)
_BACKEND_TO_BROWSER: TypeAdapter[BackendToBrowser] = TypeAdapter(BackendToBrowser)
_AGENT_TO_BACKEND: TypeAdapter[AgentToBackend] = TypeAdapter(AgentToBackend)
_BACKEND_TO_AGENT: TypeAdapter[BackendToAgent] = TypeAdapter(BackendToAgent)
_INPUT_EVENT: TypeAdapter[InputEvent] = TypeAdapter(InputEvent)


def parse_browser_to_backend(raw: str | bytes) -> BrowserToBackend:
    return _BROWSER_TO_BACKEND.validate_json(raw)


def parse_backend_to_browser(raw: str | bytes) -> BackendToBrowser:
    return _BACKEND_TO_BROWSER.validate_json(raw)


def parse_agent_to_backend(raw: str | bytes) -> AgentToBackend:
    return _AGENT_TO_BACKEND.validate_json(raw)


def parse_backend_to_agent(raw: str | bytes) -> BackendToAgent:
    return _BACKEND_TO_AGENT.validate_json(raw)


def parse_input_event(raw: str | bytes) -> InputEvent:
    return _INPUT_EVENT.validate_json(raw)


class ProtocolDocument(BaseModel):
    """Schema root that pulls every channel into one document for json-schema-to-typescript."""

    model_config = ConfigDict(
        title="PoringProtocol", json_schema_serialization_defaults_required=True
    )

    browser_to_backend: BrowserToBackend
    backend_to_browser: BackendToBrowser
    agent_to_backend: AgentToBackend
    backend_to_agent: BackendToAgent
    input_event: InputEvent


def _drop_property_titles(schema: dict[str, Any]) -> None:
    # Pydantic titles every property ("Frame Id"); json-schema-to-typescript would turn each one
    # into its own alias (FrameId1, FrameId2, ...). Model titles stay: they name the interfaces.
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)


def json_schema() -> dict[str, Any]:
    """The protocol's JSON Schema, serialization mode (what actually goes over the wire)."""
    schema = ProtocolDocument.model_json_schema(mode="serialization")
    _drop_property_titles(schema)
    for definition in schema.get("$defs", {}).values():
        _drop_property_titles(definition)
    return schema


def main() -> None:
    json.dump(json_schema(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
