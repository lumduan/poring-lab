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

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

NO_FRAME = -1

_MODEL_CONFIG = ConfigDict(
    extra="forbid",
    frozen=True,
    # Fields with defaults (notably the `type` discriminator) are still always serialized; marking
    # them required keeps the generated TypeScript discriminants non-optional.
    json_schema_serialization_defaults_required=True,
)

NormCoord = Annotated[float, Field(ge=0.0, le=1.0)]


class Mode(StrEnum):
    """Input-mux mode (ADR-0002). The backend always boots in HUMAN."""

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
    capture_fps: float = Field(ge=0.0)
    viewers: int = Field(ge=0)


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


class InputAck(Message):
    """Mux verdict for one AgentInput batch."""

    type: Literal["input_ack"] = "input_ack"
    accepted: int = Field(ge=0)
    dropped: int = Field(ge=0)
    reasons: list[str] = Field(default_factory=list)


# --- channels -------------------------------------------------------------------------------------

type BrowserToBackend = Annotated[
    MouseMove | MouseButton | Wheel | Key | ReleaseAll | SetMode | Ping,
    Field(discriminator="type"),
]
type BackendToBrowser = Annotated[
    FrameMeta | Status | Detections | Pong, Field(discriminator="type")
]
type AgentToBackend = Annotated[
    AgentHello | AgentInput | Detections | Ping, Field(discriminator="type")
]
type BackendToAgent = Annotated[Status | InputAck | Pong, Field(discriminator="type")]

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
