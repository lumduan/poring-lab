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


class RecoveryAmount(PacketEventBase):
    """ZC_RECOVERY (0x0A27 / 0x013D): a heal AMOUNT, not the new value -- potions, skills and the
    regen ticks of (Moving) HP Recovery. A stat_change series alone misses every regen tick."""

    type: Literal["recovery"] = "recovery"
    var: int
    name: str
    amount: int


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


# --- 2026-10-07: NPC dialogs, shops, stat/skill points, equipment, items, the action request -----
# Decoded for OFFLINE REPLAY of banked captures (poring_packets.replay); the sniffer image is not
# rebuilt for them. Layouts and citations: decode.py (MAP_SC / MAP_CS). Inventory indexes are the
# client's, as on the wire (the server's index + 2).
class _NpcEvent(PacketEventBase):
    npc_gid: int = Field(description="The NPC's block id (the id entity_appear reports).")


class NpcContact(_NpcEvent):
    """CZ_CONTACTNPC (0x0090): we clicked a unit. The server starts the NPC's script, or, for a
    monster's or player's id, a continuous attack on it."""

    type: Literal["npc_contact"] = "npc_contact"
    contact_type: int = Field(description="1 = a click.")


class NpcSay(_NpcEvent):
    """ZC_SAY_DIALOG (0x00B4): one line of the NPC's dialog, cp874; `raw_hex` keeps the bytes."""

    type: Literal["npc_say"] = "npc_say"
    text: str
    raw_hex: str


class NpcWait(_NpcEvent):
    """ZC_WAIT_DIALOG (0x00B5): the dialog shows its 'next' button."""

    type: Literal["npc_wait"] = "npc_wait"


class NpcClose(_NpcEvent):
    """ZC_CLOSE_DIALOG (0x00B6): the dialog shows its 'close' button (the script is ending)."""

    type: Literal["npc_close"] = "npc_close"


class NpcMenu(_NpcEvent):
    """ZC_MENU_LIST (0x00B7): a menu; `options` is the ':'-split list, empty entries kept."""

    type: Literal["npc_menu"] = "npc_menu"
    options: list[str] = Field(
        description="Option N (1-based, what npc_choose sends) is options[N-1]; an empty string "
        "is an option the client hides but still counts."
    )
    raw_hex: str


class NpcChoose(_NpcEvent):
    """CZ_CHOOSE_MENU (0x00B8): our menu answer."""

    type: Literal["npc_choose"] = "npc_choose"
    choice: int = Field(ge=0, le=255, description="1-based option; 255 = cancel.")
    cancelled: bool


class NpcNextClick(_NpcEvent):
    """CZ_REQ_NEXT_SCRIPT (0x00B9): we clicked 'next'."""

    type: Literal["npc_next_click"] = "npc_next_click"


class NpcCloseClick(_NpcEvent):
    """CZ_CLOSE_DIALOG / CZ_REQ_CLOSE_SCRIPT (0x0146): we clicked 'close'."""

    type: Literal["npc_close_click"] = "npc_close_click"


class NpcNumberPrompt(_NpcEvent):
    """ZC_OPEN_EDITDLG (0x0142): the NPC asks for a number."""

    type: Literal["npc_number_prompt"] = "npc_number_prompt"


class NpcNumberInput(_NpcEvent):
    """CZ_INPUT_EDITDLG (0x0143): the number we entered."""

    type: Literal["npc_number_input"] = "npc_number_input"
    value: int


class NpcTextPrompt(_NpcEvent):
    """ZC_OPEN_EDITDLGSTR (0x01D4): the NPC asks for a text."""

    type: Literal["npc_text_prompt"] = "npc_text_prompt"


class NpcTextInput(_NpcEvent):
    """CZ_INPUT_EDITDLGSTR (0x01D5): the text we entered, cp874; `raw_hex` keeps the bytes."""

    type: Literal["npc_text_input"] = "npc_text_input"
    text: str
    raw_hex: str


class ShopDealPrompt(_NpcEvent):
    """ZC_SELECT_DEALTYPE (0x00C4): a shop NPC asks buy or sell."""

    type: Literal["shop_deal_prompt"] = "shop_deal_prompt"


class ShopDealChoice(_NpcEvent):
    """CZ_ACK_SELECT_DEALTYPE (0x00C5): our buy/sell answer."""

    type: Literal["shop_deal_choice"] = "shop_deal_choice"
    deal: int = Field(ge=0, le=255, description="0 = buy, 1 = sell.")
    kind: str = Field(description="buy, sell, or typeN for an unknown one.")


class ShopBuyListItem(BaseModel):
    model_config = _MODEL_CONFIG
    item_id: int
    price: int
    discount_price: int
    item_type: int


class ShopBuyList(PacketEventBase):
    """ZC_PC_PURCHASE_ITEMLIST (0x0B77 at this PACKETVER): what the shop sells, with prices."""

    type: Literal["shop_buy_list"] = "shop_buy_list"
    items: list[ShopBuyListItem]


class ShopBuyRequestItem(BaseModel):
    model_config = _MODEL_CONFIG
    item_id: int
    amount: int


class ShopBuyRequest(PacketEventBase):
    """CZ_PC_PURCHASE_ITEMLIST (0x00C8): what we buy."""

    type: Literal["shop_buy_request"] = "shop_buy_request"
    items: list[ShopBuyRequestItem]


class ShopBuyResult(PacketEventBase):
    """ZC_PC_PURCHASE_RESULT (0x00CA): 0 = the deal completed; 1 = not enough zeny, 2 = over the
    weight limit, 3 = too many items (rAthena e_purchase_result). Zeny itself arrives as a
    stat_change (var 20)."""

    type: Literal["shop_buy_result"] = "shop_buy_result"
    result: int = Field(ge=0, le=255)
    ok: bool


class ShopSellListItem(BaseModel):
    model_config = _MODEL_CONFIG
    index: int = Field(description="The client's inventory index.")
    price: int
    overcharge: int = Field(description="The price after our Overcharge skill.")


class ShopSellList(PacketEventBase):
    """ZC_PC_SELL_ITEMLIST (0x00C7): what of ours the shop would buy."""

    type: Literal["shop_sell_list"] = "shop_sell_list"
    items: list[ShopSellListItem]


class ShopSellRequestItem(BaseModel):
    model_config = _MODEL_CONFIG
    index: int = Field(description="The client's inventory index.")
    amount: int


class ShopSellRequest(PacketEventBase):
    """CZ_PC_SELL_ITEMLIST (0x00C9): what we sell."""

    type: Literal["shop_sell_request"] = "shop_sell_request"
    items: list[ShopSellRequestItem]


class ShopSellResult(PacketEventBase):
    """ZC_PC_SELL_RESULT (0x00CB): 0 = the deal completed, 1 = it failed."""

    type: Literal["shop_sell_result"] = "shop_sell_result"
    result: int = Field(ge=0, le=255)
    ok: bool


class StatRaiseRequest(PacketEventBase):
    """CZ_STATUS_CHANGE (0x00BB): raise a base stat (13-18 = str, agi, vit, int, dex, luk)."""

    type: Literal["stat_raise_request"] = "stat_raise_request"
    stat: int
    name: str
    amount: int = Field(ge=0, le=255)


class StatRaiseResult(PacketEventBase):
    """ZC_STATUS_CHANGE_ACK (0x00BC): the raise's outcome and the stat's new value (capped at
    255). The status points left arrive as a stat_change (var 9)."""

    type: Literal["stat_raise_result"] = "stat_raise_result"
    stat: int
    name: str
    ok: bool
    value: int = Field(ge=0, le=255)


class SkillUpRequest(PacketEventBase):
    """CZ_UPGRADE_SKILLLEVEL (0x0112): raise a skill's level."""

    type: Literal["skill_up_request"] = "skill_up_request"
    skill_id: int


class SkillUpdate(PacketEventBase):
    """ZC_SKILLINFO_UPDATE (0x010E): a skill's new level (sent after a raise; the skill points
    left arrive as a stat_change, var 12)."""

    type: Literal["skill_update"] = "skill_update"
    skill_id: int
    level: int
    sp: int = Field(description="Its SP cost at this level.")
    range: int
    upgradable: bool


class SkillEntry(BaseModel):
    model_config = _MODEL_CONFIG
    skill_id: int
    level: int
    sp: int
    range: int
    upgradable: bool


class SkillList(PacketEventBase):
    """ZC_SKILLINFO_LIST (0x0B32 at this PACKETVER): the whole skill tree."""

    type: Literal["skill_list"] = "skill_list"
    skills: list[SkillEntry]


class EquipRequest(PacketEventBase):
    """CZ_REQ_WEAR_EQUIP (0x0998): wear an item at `location` (rAthena EQP_* bits)."""

    type: Literal["equip_request"] = "equip_request"
    index: int = Field(description="The client's inventory index.")
    location: int


class EquipResult(PacketEventBase):
    """ZC_REQ_WEAR_EQUIP_ACK (0x0999): 0 = worn, 1 = level too low, 2 = failed."""

    type: Literal["equip_result"] = "equip_result"
    index: int = Field(description="The client's inventory index.")
    location: int
    view_sprite: int
    result: int = Field(ge=0, le=255)
    ok: bool


class UnequipRequest(PacketEventBase):
    """CZ_REQ_TAKEOFF_EQUIP (0x00AB): take an item off."""

    type: Literal["unequip_request"] = "unequip_request"
    index: int = Field(description="The client's inventory index.")


class UnequipResult(PacketEventBase):
    """ZC_REQ_TAKEOFF_EQUIP_ACK (0x099A): 0 = taken off (inverted at this PACKETVER)."""

    type: Literal["unequip_result"] = "unequip_result"
    index: int = Field(description="The client's inventory index.")
    location: int
    result: int = Field(ge=0, le=255)
    ok: bool


class UseItemRequest(PacketEventBase):
    """CZ_USE_ITEM2 (0x0439): use an item."""

    type: Literal["use_item_request"] = "use_item_request"
    index: int = Field(description="The client's inventory index.")
    aid: int = Field(description="The account id the client sends with it (its own).")


class UseItemResult(PacketEventBase):
    """ZC_USE_ITEM_ACK2 (0x01C8): an item use's outcome. A success is sent to the whole area,
    so `aid` says whose it was."""

    type: Literal["use_item_result"] = "use_item_result"
    index: int = Field(description="The client's inventory index.")
    item_id: int
    aid: int
    amount: int = Field(description="How many are left.")
    ok: bool


class AttackRequest(PacketEventBase):
    """CZ_REQUEST_ACT2 (0x0437): an action on a unit -- an attack click (action 0 once, 7 keep
    attacking), or sit (2) / stand (3) with no target. A walk click is a self_move_request."""

    type: Literal["attack_request"] = "attack_request"
    target_gid: int = Field(description="The target's block id (0 for sit/stand).")
    action: int = Field(ge=0, le=255, description="rAthena e_damage_type, as ZC_NOTIFY_ACT.")
    kind: str = Field(description="The action's name (decode.ACT_KINDS): normal, repeat, sit, ...")
    is_attack: bool = Field(description="action is 0 or 7.")


# --- 2026-10-08 (loot@1 P2): floor items, the pickup request and its result, the drop -----------
# OFFLINE ground truth like the rest (ADR-0007); layouts and citations in decode.py.
class FloorItemAppear(PacketEventBase):
    """An item on the floor: ZC_ITEM_FALL_ENTRY5 (0x0ADD, kind "fall": a FRESH drop, e.g. a kill's
    loot) or ZC_ITEM_ENTRY (0x009D, kind "in_sight": one already lying there comes into view)."""

    type: Literal["floor_item_appear"] = "floor_item_appear"
    kind: Literal["fall", "in_sight"]
    floor_id: int = Field(description="The floor item's block id: the pickup act's target_gid.")
    item_id: int
    item_type: int | None = Field(
        default=None, description="rAthena item_types (mmo.hpp:223); fall entries only."
    )
    identified: bool
    x: int
    y: int
    sub_x: int = Field(description="Position inside the cell (rAthena subx / suby).")
    sub_y: int
    amount: int
    drop_effect: bool = Field(default=False, description="A drop pillar is shown (fall only).")


class FloorItemVanish(PacketEventBase):
    """ZC_ITEM_DISAPPEAR (0x00A1): a floor item is gone -- picked up, expired, or out of OUR sight
    (the packet does not say which)."""

    type: Literal["floor_item_vanish"] = "floor_item_vanish"
    floor_id: int


class PickupRequest(PacketEventBase):
    """CZ_ITEM_PICKUP2 (0x0362): our client asks to pick up a floor item (after walking in)."""

    type: Literal["pickup_request"] = "pickup_request"
    floor_id: int


class PickupResult(PacketEventBase):
    """ZC_ITEM_PICKUP_ACK (0x0B41): an item ENTERED our inventory (ok), or a pickup failed. Sent
    for every inventory gain (an @item, an NPC, a trade) -- a floor pickup is this plus our act of
    kind pickup on the floor id plus that id's floor_item_vanish."""

    type: Literal["pickup_result"] = "pickup_result"
    index: int = Field(description="The client's inventory index (2 on a failure).")
    amount: int = Field(description="How many were added (0 on a failure).")
    item_id: int = Field(description="0 on a failure.")
    identified: bool
    item_type: int
    result: int = Field(ge=0, le=255, description="rAthena e_additem_result (pc.hpp:113).")
    reason: str = Field(
        description="ok, invalid, overweight, item, inventory_full, over_amount, refused (also "
        "the generic refusal: too far, loot priority, ...), stack_limit, or resultN."
    )
    ok: bool
    refine: int


class DropRequest(PacketEventBase):
    """CZ_ITEM_THROW2 (0x0363): our client drops an inventory item to the floor."""

    type: Literal["drop_request"] = "drop_request"
    index: int = Field(description="The client's inventory index.")
    amount: int


class DropResult(PacketEventBase):
    """ZC_ITEM_THROW_ACK (0x00AF): the dropped amount left the inventory (0 = refused)."""

    type: Literal["drop_result"] = "drop_result"
    index: int = Field(description="The client's inventory index.")
    amount: int
    ok: bool


class UnknownPacket(PacketEventBase):
    """A packet id the length table does not know; its stream is resynchronised (counted)."""

    type: Literal["unknown"] = "unknown"
    count: int


class Desync(PacketEventBase):
    type: Literal["desync"] = "desync"
    skipped_bytes: int


# The 2026-10-07 events (and the 2026-10-08 floor-item / pickup ones), shared by both unions below.
_Interaction = (
    NpcContact
    | NpcSay
    | NpcWait
    | NpcClose
    | NpcMenu
    | NpcChoose
    | NpcNextClick
    | NpcCloseClick
    | NpcNumberPrompt
    | NpcNumberInput
    | NpcTextPrompt
    | NpcTextInput
    | ShopDealPrompt
    | ShopDealChoice
    | ShopBuyList
    | ShopBuyRequest
    | ShopBuyResult
    | ShopSellList
    | ShopSellRequest
    | ShopSellResult
    | StatRaiseRequest
    | StatRaiseResult
    | SkillUpRequest
    | SkillUpdate
    | SkillList
    | EquipRequest
    | EquipResult
    | UnequipRequest
    | UnequipResult
    | UseItemRequest
    | UseItemResult
    | AttackRequest
    | FloorItemAppear
    | FloorItemVanish
    | PickupRequest
    | PickupResult
    | DropRequest
    | DropResult
)
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
    | RecoveryAmount
    | Chat
    | _Interaction
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


class PacketSource(BaseModel):
    """The console's Packet timeline: WHERE its packets come from, right now (Batt 2026-10-09).

    Made by the BACKEND for /ws/packets (the LAN viewers' channel) about the sniffer it hears;
    never sent by the sniffer (parse_feed refuses it on /ingest/packets) and never to an agent.
    It tells "nothing happened" apart from "nobody is listening": an idle GM sends few game
    packets, so liveness is the sniffer's own 1 Hz heartbeat (its PacketStats + Attestation
    pair), not the last game packet. Wall-clock times are the BACKEND's receipt times (unix ms),
    for display only; ages are the backend's own (CLOCK_MONOTONIC)."""

    model_config = _MODEL_CONFIG
    type: Literal["packet_source"] = "packet_source"
    t_mono_ns: int = Field(ge=0, description="The backend's clock when it made this line.")
    state: Literal["live", "sniffer_offline", "external"] = Field(
        description="live: the lab sniffer's heartbeat is fresh; sniffer_offline: it is not "
        "(no packets can arrive); external: the human plays on an external server whose packets "
        "are not captured by design (no such environment exists yet: the backend never says so)."
    )
    reason: str = Field(
        max_length=64,
        description="One word: ok, never_heard, ingest_disconnected, heartbeat_stale, "
        "not_attesting, external_environment.",
    )
    ingest_connected: bool = Field(description="The sniffer's /ingest/packets socket is open.")
    heartbeat_age_ms: int | None = Field(
        default=None, ge=0,
        description="Since the OLDER of the sniffer's last stats and last attestation (backend "
        "clock); null = one of them never arrived since the backend started.",
    )  # fmt: skip
    stale_after_ms: int = Field(ge=0, description="The heartbeat age beyond which it is offline.")
    last_feed_unix_ms: int | None = Field(
        default=None, ge=0,
        description="Wall clock (unix ms) of the backend's last receipt of ANY sniffer line "
        "(heartbeat or game packet); null = none since the backend started.",
    )  # fmt: skip
    last_event_unix_ms: int | None = Field(
        default=None, ge=0,
        description="Wall clock (unix ms) of the last GAME packet event received; null = none.",
    )  # fmt: skip


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
    | RecoveryAmount
    | Chat
    | _Interaction
    | UnknownPacket
    | Desync
    | PacketStats
    | Attestation,
    Field(discriminator="type"),
]
_FEED_ADAPTER: TypeAdapter[FeedMessage] = TypeAdapter(FeedMessage)


def parse_feed(text: str | bytes) -> FeedMessage:
    """One line of the sniffer -> backend feed: a packet event, a stats snapshot or the
    session attestation. Never a PacketSource: that line is the backend's own."""
    return _FEED_ADAPTER.validate_json(text)


class PacketDocument(BaseModel):
    """Root of the packet-event JSON Schema (packets.schema.json -> frontend packets.gen.ts)."""

    model_config = ConfigDict(
        title="PoringPackets", json_schema_serialization_defaults_required=True
    )
    event: PacketEvent
    stats: PacketStats
    source: PacketSource


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
