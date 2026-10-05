"""Packet events: what the sniffer reports, on the host clock (`t_mono_ns`).

OFFLINE GROUND TRUTH / human console only (ADR-0007). These models are deliberately NOT part of
poring_env's protocol: no agent-side schema can reach them (tests pin that).

`validation_account` marks every event of a session logged in with a validation (GM) account, and
`gm_command` marks a GM command and the events within GM_WINDOW_NS after it, so both can be excluded
from datasets.
"""

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

_MODEL_CONFIG = ConfigDict(
    extra="forbid", frozen=True, json_schema_serialization_defaults_required=True
)
Server = Literal["login", "char", "map"]
Direction = Literal["cs", "sc"]
GM_WINDOW_NS = 2_000_000_000


class PacketEventBase(BaseModel):
    model_config = _MODEL_CONFIG
    t_mono_ns: int = Field(ge=0, description="Kernel receive time mapped onto CLOCK_MONOTONIC.")
    server: Server
    dir: Direction
    packet_id: int = Field(ge=0, le=0xFFFF)
    validation_account: bool = False
    gm_command: bool = False


class LoginAccepted(PacketEventBase):
    type: Literal["login_accepted"] = "login_accepted"
    aid: int
    sex: int


class CharSelected(PacketEventBase):
    type: Literal["char_selected"] = "char_selected"
    char_id: int
    map: str
    map_port: int


class MapEnter(PacketEventBase):
    """ZC_ACCEPT_ENTER: our character is on the map at (x, y); server tick at entry."""

    type: Literal["map_enter"] = "map_enter"
    server_tick: int
    x: int
    y: int
    facing: int


class MapChange(PacketEventBase):
    type: Literal["map_change"] = "map_change"
    map: str
    x: int
    y: int


class TimeSync(PacketEventBase):
    """ZC_NOTIFY_TIME: rAthena gettick() (CLOCK_MONOTONIC ms, mod 2^32) at send."""

    type: Literal["time_sync"] = "time_sync"
    server_tick: int


class SelfMoveRequest(PacketEventBase):
    type: Literal["self_move_request"] = "self_move_request"
    x: int
    y: int


class SelfMove(PacketEventBase):
    """ZC_NOTIFY_PLAYERMOVE: our walk from (x0, y0) to (x1, y1) starting at server_tick."""

    type: Literal["self_move"] = "self_move"
    server_tick: int
    x0: int
    y0: int
    x1: int
    y1: int


class EntityAppear(PacketEventBase):
    """ZC_NOTIFY_{NEW,STAND,MOVE}ENTRY11."""

    type: Literal["entity_appear"] = "entity_appear"
    kind: Literal["new", "stand", "move"]
    gid: int = Field(description="Block id (rAthena bl.id): the id vanish/stop packets use.")
    char_id: int = Field(default=0, description="Character id for players; 0 for anything else.")
    objtype: int
    job: int
    speed: int
    name: str
    x: int
    y: int
    x1: int | None = None  # move entries: destination
    y1: int | None = None
    move_start_tick: int | None = None
    effect_state: int | None = Field(
        default=None, ge=0,
        description="The unit's option bits (rAthena sc.option): HIDE 0x2, CLOAK 0x4 and "
        "INVISIBLE 0x40 mean the client draws nothing.",
    )  # fmt: skip
    heading: int | None = Field(
        default=None, ge=0, le=7,
        description="Heading 0..7 (0 = north, counter-clockwise) for new/stand entries; a walking "
        "entity faces its step (derived downstream).",
    )  # fmt: skip


class EntityVanish(PacketEventBase):
    type: Literal["entity_vanish"] = "entity_vanish"
    gid: int
    reason: int  # 0 out of sight, 1 died (the client plays its die action), 2 logged out,
    # 3 teleport, 4 trickdead


class EntityStop(PacketEventBase):
    type: Literal["entity_stop"] = "entity_stop"
    gid: int
    x: int
    y: int


class EntityTurn(PacketEventBase):
    """ZC_CHANGE_DIRECTION (0x009C): a unit now faces `heading`."""

    type: Literal["entity_turn"] = "entity_turn"
    gid: int
    heading: int | None = Field(
        default=None, ge=0, le=7,
        description="Body direction 0..7 (0 = north, counter-clockwise); None if the byte is out "
        "of range.",
    )  # fmt: skip
    head_dir: int = Field(
        description="Players' head relative to the body: 0 straight, 1 turned clockwise, 2 "
        "counter-clockwise (0 for anything else)."
    )


class Act(PacketEventBase):
    """ZC_NOTIFY_ACT (0x08C8 at this PACKETVER; 0x008A / 0x02E1 on older clients): `src_gid` acts
    on `target_gid` -- a hit or a miss, an item pickup, sitting down or standing up."""

    type: Literal["act"] = "act"
    src_gid: int
    target_gid: int = Field(
        description="The target's block id; the floor item's id for a pickup; 0 for sit/stand."
    )
    server_tick: int = Field(
        description="gettick() of the action, mod 2^32 (0 for sit, stand and pickup)."
    )
    src_speed: int = Field(description="The source's attack motion, ms (rAthena amotion).")
    dmotion: int = Field(description="The target's damage motion, ms: how long a hit stuns it.")
    damage: int = Field(description="0 is a miss; -1 is a hidden amount (a disguised source).")
    damage2: int = Field(description="The second hand's damage (dual wield).")
    div: int = Field(description="The number of hits.")
    action: int = Field(ge=0, le=255, description="rAthena e_damage_type (clif.hpp:691).")
    kind: str = Field(
        description="The action's name: normal, pickup, sit, stand, endure, splash, single, "
        "repeat, multi_hit, multi_hit_endure, critical, lucky_dodge, touch, multi_hit_critical, "
        "splash_endure, or typeN for an unknown one."
    )
    sp_damage: bool | None = Field(
        default=None, description="The damage hits SP (blue digits); 0x08C8 only."
    )


class StatChange(PacketEventBase):
    type: Literal["stat_change"] = "stat_change"
    var: int
    name: str
    value: int


class Chat(PacketEventBase):
    """Chat text decoded as cp874; `raw_hex` keeps the exact bytes (ground truth vs chatlog)."""

    type: Literal["chat"] = "chat"
    kind: Literal[
        "public", "self", "party", "guild", "whisper_in", "whisper_out", "broadcast", "npc"
    ]
    gid: int | None = None
    speaker: str | None = None
    text: str
    raw_hex: str


class UnknownPacket(PacketEventBase):
    """A packet id the length table does not know; its stream is resynchronised (counted)."""

    type: Literal["unknown"] = "unknown"
    count: int


class Desync(PacketEventBase):
    type: Literal["desync"] = "desync"
    skipped_bytes: int


PacketEvent = Annotated[
    LoginAccepted
    | CharSelected
    | MapEnter
    | MapChange
    | TimeSync
    | SelfMoveRequest
    | SelfMove
    | EntityAppear
    | EntityVanish
    | EntityStop
    | EntityTurn
    | Act
    | StatChange
    | Chat
    | UnknownPacket
    | Desync,
    Field(discriminator="type"),
]
_EVENT_ADAPTER: TypeAdapter[PacketEvent] = TypeAdapter(PacketEvent)


class PacketStats(BaseModel):
    """Periodic counters + world summary for the console (never silent)."""

    model_config = _MODEL_CONFIG
    type: Literal["packet_stats"] = "packet_stats"
    t_mono_ns: int = Field(ge=0)
    packets: int
    unknown: int
    desyncs: int
    skipped_bytes: int
    tcp_gaps: int
    clock_steps: int
    map: str | None
    self_x: float | None
    self_y: float | None
    entities: int
    hp: int | None
    max_hp: int | None
    sp: int | None
    max_sp: int | None
    ingest_dropped: int = 0


class Attestation(BaseModel):
    """The environment interlock's session signal (ADR-0016, rewritten 2026-10-04): the sniffer
    attests that a map-server session from the lab Dell to THIS rathena is live, and for which
    account. ATTESTATION, NEVER WORLD DATA: no position, map, HP or entity rides with it, and the
    backend hands it to the mux only (never to a viewer or an agent)."""

    model_config = _MODEL_CONFIG
    type: Literal["attest"] = "attest"
    t_mono_ns: int = Field(ge=0)
    client_ip: str = Field(description="The Windows host whose sessions the sniffer watches.")
    session_live: bool = Field(description="A map connection is open (no FIN/RST) and recent.")
    aid: int | None = Field(default=None, description="The live session's account id.")
    last_packet_age_ms: int | None = Field(default=None, ge=0)
    map_conns: int = Field(default=0, ge=0, description="Open map connections from the host.")
    server: str | None = Field(
        default=None,
        description="WHICH server the session belongs to: the sniffer's SNIFFER_SERVER_ID, an "
        "environment id in config/environments.yaml (2026-10-05, Batt: one sniffer per rathena; "
        "the interlock requires it to equal the environment's id).",
    )


def parse_event(text: str | bytes) -> PacketEvent:
    return _EVENT_ADAPTER.validate_json(text)


FeedMessage = Annotated[
    LoginAccepted
    | CharSelected
    | MapEnter
    | MapChange
    | TimeSync
    | SelfMoveRequest
    | SelfMove
    | EntityAppear
    | EntityVanish
    | EntityStop
    | EntityTurn
    | Act
    | StatChange
    | Chat
    | UnknownPacket
    | Desync
    | PacketStats
    | Attestation,
    Field(discriminator="type"),
]
_FEED_ADAPTER: TypeAdapter[FeedMessage] = TypeAdapter(FeedMessage)


def parse_feed(text: str | bytes) -> FeedMessage:
    """One line of the sniffer -> backend feed: a packet event, a stats snapshot or the
    session attestation."""
    return _FEED_ADAPTER.validate_json(text)


class PacketDocument(BaseModel):
    """Root of the packet-event JSON Schema (packets.schema.json -> frontend packets.gen.ts)."""

    model_config = ConfigDict(
        title="PoringPackets", json_schema_serialization_defaults_required=True
    )
    event: PacketEvent
    stats: PacketStats


def _drop_property_titles(node: dict[str, Any]) -> None:
    for prop in node.get("properties", {}).values():
        if isinstance(prop, dict):
            prop.pop("title", None)


def json_schema() -> dict[str, Any]:
    schema = PacketDocument.model_json_schema(mode="serialization")
    _drop_property_titles(schema)
    for definition in schema.get("$defs", {}).values():
        _drop_property_titles(definition)
    return schema


def main() -> None:
    print(json.dumps(json_schema(), indent=2, sort_keys=True))
