---
doc_type: decision
hypothesis: null
status: ACCEPTED
role: null
verdict_date: 2026-10-08
verdict_ticket: null
supersedes: null
related: [ADR-0015, ADR-0002, ADR-0003, ADR-0004, ADR-0006, ADR-0007, ADR-0011, ADR-0012, ADR-0014, ADR-0016, ADR-0018, ADR-0019]
next_action: "ACCEPTED by Batt 2026-10-08, with the decisions recorded at the open questions (16-18, 20, 21, 29, part of 27). Build MW1 / F1 OFFLINE now (the flow IR with map blocks, the block catalogue, linter layers 1-3 incl. the section 13 rules), no runtime changes; the remaining open questions stay open and are answered as MW2+ needs them. ➡️ 2026-10-09: Batt decided 5 of the 19 MW1 contradictions (#6 readiness, #15 always-on safety events, #13 rank = IR 2, #14 ties, #18 one planner: the cross-check, the swap waits) and MW2-editor's parked items; each recorded in place with a dated marker and built (db27d76, 87d654a, c131ddc (+ 3d4215b), 60e75a9 (+ 2f84873), 22ac314). Open question 15 CLOSED, 11 decided."
---

# ADR-0020: Block programs over one flow IR (the agent builds blocks, users compose flows)

- **Status:** ~~PROPOSED (2026-10-07). Batt accepts or not. Nothing is built.~~ ➡️ **ACCEPTED (Batt,
  2026-10-08)**, with his answers recorded at the open questions. MW1 / F1 (the IR and the
  linter, offline) starts now; no runtime changes until MW2 (➡️ MW2-live, 13.8; renamed 2026-10-09).
- **Amended, still PROPOSED (Batt, 2026-10-08):** workflows are organised BY MAP (map blocks,
  typed exits, target / ignore lists with an all-spawn training scope, an automatic preparation
  estimate), with EVENT FLOWS at global and per-map scope. See section 13.
  - **Batt's answers, 2026-10-08:** map blocks are in IR 1; INSERT = hotbar `use_item` only, after
    an alone-test; relocation as 13.6.6; `hp_critical` joins the safety-critical set; the save
    point is REQUIRED before any wing; loot by a hover-scan for the PICKUP cursor; the L3 map-sheet
    extraction is approved. Each is recorded at its open question.
  - **Defence in depth for walking (Batt, 2026-10-08), section 13.9:** PREVENT (the gates),
    DETECT an unintended engagement from pixels, RECOVER per map through an `unintended_engagement`
    event. Walk rules keep the zero-tolerance bar; recovery is tested on its own.
- **The direction (Batt, 2026-10-07):** users build bot behaviour as BLOCK PROGRAMS, the way
  Microsoft MakeCode or LEGO EV3 programs are built. The agent builds the BLOCKS; users compose the
  FLOWS. Flows are not hard-coded by the agent. An example flow: start → walk to (map, x, y) →
  talk with an NPC (by name or position) → choose a menu option (by its text) → …
- **Extends [ADR-0015](0015-phase4-planner-linter-executor.md)** (plan → lint → approve →
  execute). It supersedes nothing. How the two fit is the next section.
- **Gates (unchanged from ADR-0015):** a flow acts on the game only after Phase 3 perception, with
  ADR-0005 implemented (done 2026-10-04) and the environment interlock
  ([ADR-0016](0016-environment-interlock.md), done 2026-10-04). The IR, the linter, the editor and
  the Python view need none of these: they are offline work.
- **Related:**
  - [ADR-0002](0002-input-mux.md): one input writer, the lease, releases on handoff;
  - [ADR-0003](0003-env-abstraction.md): the `Env` contract the blocks act through;
  - [ADR-0004](0004-human-only-clipboard-and-file-transfer.md): no clipboard or file block, ever;
  - [ADR-0006](0006-sanctioned-test-environments.md) / [ADR-0016](0016-environment-interlock.md):
    where a flow may run;
  - [ADR-0007](0007-packet-ground-truth-channel.md): packets are offline ground truth, never
    decision input;
  - [ADR-0011](0011-ui-anchor-map.md) / [ADR-0012](0012-locale-agnostic-ui.md): windows by anchor,
    text by key;
  - [ADR-0014](0014-s2-primary-bot-path.md): S2 is the bot's primary path;
  - [ADR-0018](0018-component-licensing.md): the AGPL boundary around `services/vision`;
  - [ADR-0019](0019-windows-stays-clean.md): nothing of this runs on Windows;
  - the knowledge layers: `packages/poring_skills` (L1 concepts, L2/L3/L4 bindings),
    [knowledge/README.md](../knowledge/README.md), [phase4-ui.md](../phase4-ui.md);
  - the verification method: [demonstrations.md](../demonstrations.md).

## How this relates to ADR-0015

ADR-0015 fixed the pipeline: a request becomes a plan, a layered linter checks it, the owner
approves it, and a deterministic behavior-tree executor runs it through the mux. This ADR fills in
what the plan IS and who writes it.

| ADR-0015 piece | Under this ADR |
|---|---|
| "plan JSON (schema)" | **the flow IR** (section 1): one typed, versioned Pydantic model. It is the only thing the linter checks and the only thing the executor runs |
| the bot owner's request | the owner composes the flow directly, as blocks or restricted Python, or describes it in words |
| the LLM planner | **one more producer** of the IR (section 8), optional, boxed by the same parser and linter. ADR-0015 built it last; it stays last |
| the linter, layers 1–6 | unchanged, plus flow-specific rules: events, loops, outcomes, irreversible blocks (section 5) |
| approval: "the plan as blocks in the console" | the blocks become the **authoring** surface as well as the approval view. Approval binds to the IR's hash (section 6) |
| the behavior-tree executor | runs the IR. The IR compiles to a tree (section 6); the trees stay written from scratch (ADR-0015, ideas only from GPL work) |
| ADR-0015's build order | unchanged in spirit; section 12 refines steps 2–6 into phases F1–F5 |

The hard lines of ADR-0015 hold without change:
- the LLM never drives input, and the executor never calls an LLM;
- flows come only from the bot owner;
- in-game text is DATA, never instructions.

## 1. One canonical flow IR

**Decision.** A flow is ONE data structure, the flow IR: typed, versioned, validated by Pydantic
(`extra="forbid"`, frozen, the same style as `poring_skills/schema.py`). Everything else is a view:

```
  views (each converts to and from the IR; JavaScript is printed only)
  blocks (Blockly, in the console) ◄───►┐
  restricted Python (text)         ◄───►┤
  JSON file (import / export)      ◄───►├── flow IR (Pydantic, canonical JSON, sha256) ──► linter ──► approval ──► executor (behavior tree)
  JavaScript (printed only)        ◄────┘         ▲
                                                  └── LLM draft (restricted Python or IR JSON): same parser, same linter
```

**Why one IR:**
- The executor and the linter each have exactly one input format. A second runnable format would
  need a second linter.
- The IR is language-neutral and versioned. A UI library's workspace format changes with the
  library; our IR changes only by a schema version bump.
- Round trips (blocks ↔ Python ↔ JSON) are defined against one thing, so they can be tested.

**Properties:**
- **Typed.** Parameters are typed references (section 4), never free strings where a list exists.
- **Versioned.** `ir: 1`. A breaking change is a new version with a converter, never a silent edit
  (the ADR-0012 rule for keys, applied to flows).
  ➡️ **IR 2 since 2026-10-09** (Batt, contradictions #13): `Handler.rank`, the rank inside an event
  class (13.6.3). IR 1 converts on load (`poring_flow.ir.upgrade`, and the editor's importer): the
  version becomes 2 and every handler's rank is left at its default, 13.6.3's table order; the
  converted flow has a new hash (no flow had been approved). Any other version is refused with a
  message. The examples below that say `ir=1` load converted. "IR 2" in contradictions #19 (a route
  crossing maps) now means a LATER version.
- **Canonical form and hash.** Canonical JSON (sorted keys, no insignificant whitespace, UTF-8,
  NFC). `flow_hash` = sha256 of it. Approval, run logs and progress messages cite the hash.
- **Node ids are structural paths** (`main.2.then.0`, `handlers.1.body.0`), computed by the
  canonicaliser and never stored by authors. Together with the hash they name a block
  unambiguously in a log, and they make every round trip exact.
- **View state is not IR.** Block positions, collapsed blocks and the like are editor metadata
  stored beside the IR, keyed by node path, and excluded from the hash.
- **Text is never stored** (ADR-0012: the bot thinks in keys). The IR holds keys and ids; the views
  show text from the active locale pack and the local L3 data.
- **Generated, not hand-written, for the frontend.** The JSON Schema and the TypeScript types are
  generated from the Pydantic models and drift-tested, exactly like the wire protocol
  (`scripts/gen_protocol.sh`, `test_committed_schema_matches_models`).

**Schema sketch** (illustrative, NOT committed code; the models land in phase F1 and may differ):

```python
CFG = ConfigDict(extra="forbid", frozen=True)
NAME = r"^[A-Za-z][A-Za-z0-9_]{0,47}$"  # ASCII only (see 7.2: identifier normalisation)


# --- typed references: keys and ids, never display text (ADR-0012) --------------------------
class MapRef(BaseModel):
    model_config = CFG
    kind: Literal["map"]
    map: str  # map id


class CellRef(BaseModel):
    model_config = CFG
    kind: Literal["cell"]
    map: str
    x: int
    y: int


class NpcRef(BaseModel):
    model_config = CFG
    kind: Literal["npc"]
    key: str  # L3 key


class OptionRef(BaseModel):
    model_config = CFG
    kind: Literal["option"]
    key: str  # L3/L4 key


class ItemRef(BaseModel):
    model_config = CFG
    kind: Literal["item"]
    id: int  # item.<id>


class MobRef(BaseModel):
    model_config = CFG
    kind: Literal["mob"]
    id: int  # mob.<id>


class SkillRef(BaseModel):
    model_config = CFG
    kind: Literal["skill"]
    id: int
    level: int | None = None


class WindowRef(BaseModel):
    model_config = CFG
    kind: Literal["window"]
    name: str  # ADR-0011 name


Ref = Annotated[
    MapRef | CellRef | NpcRef | OptionRef | ItemRef | MobRef | SkillRef | WindowRef,
    Field(discriminator="kind"),
]


# --- expressions (every model below also sets model_config = CFG) --------------------------
class Lit(BaseModel):
    kind: Literal["lit"]
    value: int | float | bool | str | Ref | list[Ref]


class Var(BaseModel):
    kind: Literal["var"]
    name: str = Field(pattern=NAME)


class Logic(BaseModel):
    kind: Literal["and", "or"]
    terms: list["Expr"] = Field(min_length=2)


class Not_(BaseModel):
    kind: Literal["not"]
    term: "Expr"


class Sense(BaseModel):
    kind: Literal["sense"]
    sensor: str  # a catalogue sensor, e.g. hp_percent
    args: dict[str, "Expr"] = {}


class Cmp(BaseModel):
    kind: Literal["cmp"]
    op: Literal["==", "!=", "<", "<=", ">", ">="]
    left: "Expr"
    right: "Expr"


class Arith(BaseModel):
    kind: Literal["arith"]
    op: Literal["+", "-", "*", "//", "%"]
    left: "Expr"
    right: "Expr"


Expr = Annotated[Lit | Var | Sense | Cmp | Logic | Not_ | Arith, Field(discriminator="kind")]


# --- statements ----------------------------------------------------------------------------
class Action(BaseModel):
    kind: Literal["action"]
    block: str  # catalogue name, e.g. walk_to
    concept: str = Field(pattern=CONCEPT_ID)  # its L1 concept, e.g. nav.walk_to
    params: dict[str, Expr]
    timeout_s: float = Field(gt=0, le=600)
    on_fail: Literal["stop", "continue"] = "stop"
    outcome_to: str | None = None  # a variable receiving the outcome (section 2.2)
    note: str | None = Field(default=None, max_length=200)


class If(BaseModel):
    kind: Literal["if"]
    cond: Expr
    then: list["Stmt"]
    orelse: list["Stmt"] = []


class While(BaseModel):
    kind: Literal["while"]
    cond: Expr
    body: list["Stmt"]
    max_iter: int | None = Field(default=None, ge=1, le=100_000)
    max_s: float | None = Field(default=None, gt=0)


class WaitUntil(BaseModel):
    kind: Literal["wait_until"]
    cond: Expr
    timeout_s: float = Field(gt=0, le=3600)  # mandatory
    outcome_to: str | None = None


class Repeat(BaseModel):
    kind: Literal["repeat"]
    times: Expr
    body: list["Stmt"]


class ForEach(BaseModel):
    kind: Literal["for"]
    var: str
    items: Lit | Var
    body: list["Stmt"]


class SetVar(BaseModel):
    kind: Literal["set"]
    var: str
    value: Expr


class CallProc(BaseModel):
    kind: Literal["call"]
    proc: str


class Stop(BaseModel):
    kind: Literal["stop"]
    reason: str = Field(pattern=r"^[a-z_]{1,40}$")


class Break_(BaseModel):
    kind: Literal["break"]


class Continue_(BaseModel):
    kind: Literal["continue"]


Stmt = Annotated[
    Action | If | While | WaitUntil | Repeat | ForEach | SetVar | CallProc | Stop | Break_ | Continue_,
    Field(discriminator="kind"),
]  # fmt: skip


# --- event handlers (section 2.5) -------------------------------------------------------------
class Handler(BaseModel):  # extended by section 13.6: until, insert/preempt, relocate, limits
    model_config = CFG
    name: str = Field(pattern=NAME)
    when: Expr  # passive sensors only (linter)
    priority: Literal["critical", "survival", "upkeep"]
    rearm: Expr | None = None  # hysteresis: armed again only when this is true
    cooldown_s: float = Field(default=0, ge=0, le=3600)
    max_fires_per_10min: int = Field(default=10, ge=1, le=100)
    then: Literal["resume", "skip_block", "restart_flow", "stop"] = "resume"
    body: list[Stmt] = Field(min_length=1)


# --- the flow ---------------------------------------------------------------------------------
class Target(BaseModel):
    model_config = CFG
    client: str  # the L2 build, e.g. kro-20211103-prere
    server: str  # the environment id, e.g. lab-rathena
    locale: str  # the L4 pack, e.g. en
    path: Literal["s2", "rdp"] = "s2"  # ADR-0014: S2 is the bot's primary path


class Flow(BaseModel):
    model_config = CFG
    ir: Literal[1]
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")
    description: str = Field(default="", max_length=500)
    target: Target
    assumes: list[Expr] = []  # character facts, checked by sensors before any input
    max_runtime_s: int = Field(ge=1, le=MAX_RUNTIME_S)  # mandatory; the bound is an open question
    stop_when: Expr | None = None
    variables: dict[str, Lit] = {}  # every variable with its initial value (and type)
    procedures: dict[str, list[Stmt]] = {}  # named sub-flows, no parameters in IR 1
    handlers: list[Handler] = []
    main: list[Stmt] = Field(min_length=1)
```

## 2. Blocks come from the L1 skills

**Decision.** The block catalogue is GENERATED from the L1 concepts (`packages/poring_skills/src/
poring_skills/l1/*.yaml`) plus a small block registry that adds what L1 does not hold: typed
parameters, the sensor/action split, the pre-emption profile and the implementing rule. The
catalogue is one JSON document, served to the editor and given to the LLM drafter.

- **One action block per L1 concept.** A block calls the concept's rule (`name@version`, the same
  code the alone-test ran, section 12), then the concept's runtime outcome check.
- **Bindings are resolved per environment, fail closed.** Before a block runs (and at lint time),
  `poring_skills.resolve.resolve()` resolves every binding the concept needs for the active
  (client, server, locale, path): L2 from `l2/<client>.yaml`, L3 from
  `data/kb/bindings/<server>.json` (generated locally, never committed), L4 from the locale pack. A
  missing binding raises `Unsupported` (layer, key, reason). A binding is never guessed. So the same
  block works on every server that has the bindings, and refuses cleanly on one that does not.
- **The agent builds blocks; users compose flows.** Building a block means: the L1 concept, its L2
  and L3 bindings, its rule, the rule's pre-registered alone-test, and its registry entry. Composing
  a flow never needs code.
- **A coverage test** keeps the catalogue honest: every L1 concept is an action block, a sensor, or
  listed as excluded with a reason. A new L1 concept without a block fails the test.

### 2.1 Action blocks

Each row is one L1 concept. The outcome column is the concept's RUNTIME check (screen only), taken
from its L1 entry.

| Block | L1 concept | Main parameters | Runtime outcome (screen) | Notes |
|---|---|---|---|---|
| `walk_to` | `nav.walk_to` | cell | the readout reaches the cell | legs on screen; long routes cross warps |
| `take_warp` | `nav.take_warp` | destination map | a loading screen, then the new map in the readout | |
| `kafra_teleport` | `nav.kafra_teleport` | destination | a new map; zeny drops by the fee | |
| `ride_transport` | `nav.take_transport` | destination | a map change to the arrival point | |
| `talk_npc` | `npc.talk` | npc | the dialog anchor appears | walks close first |
| `next_page` | `npc.next` | – | the text changes or a menu appears | |
| `choose_menu` | `npc.choose` | option (a key) | the menu closes, the next dialog state shows | text-checked before the click; never by position alone |
| `enter_value` | `npc.input` | value | the input box closes, the dialog continues | TYPES: the foreground gate applies |
| `close_dialog` | `npc.close` | – | the dialog anchor disappears | |
| `attack_nearest` | `combat.attack_target` | mob, `until`, `within` | damage or a miss above the target; the target gone at the end | target choice by the detector and tracker |
| `use_skill` | `combat.use_skill` | skill, target | the skill effect; the SP bar drops | |
| `loot` | `loot.pick_up` | item or any | the item vanishes, its count rises | not bindable yet: no ground-item class (L1 exception) ➡️ **Batt, 2026-10-08: bindable WITHOUT new training** -- a hover-scan around the cell where the tracker saw a monster die, for the PICKUP cursor; verified by the weight readout rising (open question 21) |
| `buy` / `sell` | `trade.buy` / `trade.sell` | shop npc, items, keep policy | zeny drops / rises; items appear / leave | `sell` takes a KEEP list; an empty one must be acknowledged at approval |
| `kafra_store` / `kafra_withdraw` | `storage.deposit` / `storage.withdraw` | items | items move between the windows | |
| `use_item` | `item.use` | item | the bar rises, the count drops | |
| `equip` / `unequip` | `item.equip` / `item.unequip` | item | the slot shows the item / is empty | |
| `insert_card` / `refine` | `item.insert_card` / `item.refine` | card, item | per L1 | IRREVERSIBLE: the linter demands an explicit acknowledgement at approval |
| `open_window` / `close_window` / `press_button` | `ui.*` | window, button | the anchor appears / disappears / per button | |
| `sit` / `stand` | `char.sit` / `char.stand` | – | the pose | |
| `raise_stat` / `learn_skill` | `char.allocate_stat` / `char.learn_skill` | stat or skill, count | the value rises, points drop | |
| `respawn` | `char.respawn` | – | the death dialog closes, the save map is drawn | |
| `rent_cart` / `cart_transfer` | `cart.rent` / `cart.transfer` | items, direction | per L1 | |
| `change_job` | `char.change_job` | job | the job name and sprite change | a PROCEDURE, not one rule: the process is server script (L3), spelled out in blocks per server (section 10) |

**Excluded in IR 1 (with reasons, so the coverage test passes):**
- `session.login`, `session.select_char`, `session.logout`: before a map session exists the
  interlock is red, and only an operator window (ASSIST, a HOST tool, ≤ 120 s) lets input through.
  The agent channel can never open one (ADR-0016). Flows therefore start in game. How a flow could
  ask for a window is an open question.
- `vitals.read`, `nav.read_position`: they become SENSORS (2.3).

**Never a block, in any version:** clipboard or file transfer (ADR-0004); chat or whispers (the
social research is Phase 6, and other players' text stays local); raw clicks, raw keys or
coordinates (section 3); anything on the Windows desktop or shell (those steps stay ro_agent's,
ADR-0019); anything that reads packets (ADR-0007).

### 2.2 Outcomes

Every action block ends in its L1 runtime check and yields ONE outcome:

| Outcome | Meaning |
|---|---|
| `ok` | the L1 runtime (screen) check passed |
| `failed` | the check failed, a precondition failed, or the block timed out (a cause is attached) |
| `unsupported` | a binding did not resolve for the active environment (layer and key attached) |
| `interrupted` | an event handler, a pause or the human took over (section 6) |
| `refused` | the mux refused the input: the interlock, the foreground gate, a stale frame |

- **`ok` is not "verified".** At run time the check is pixels only; packets never feed a decision
  (ADR-0007, `poring_skills.schema.Outcome` refuses a packet runtime check). On the lab environment
  each block execution is ALSO logged as a `DemoRecord` (`poring_env.demo`, actor
  `bot:flow.<name>@<hash12>`, outcome pending). The offline packet verifier scores it later,
  exactly like a demonstration ([demonstrations.md](../demonstrations.md) §1-2). That is the
  flywheel, never an input.
- **Branching.** As a statement, a non-`ok` outcome stops the flow (`on_fail: stop`, the safe
  default) unless the block says `continue`. As an expression (`outcome_to`, or a block used in a
  condition), the outcome is a value to branch on.

### 2.3 Sensor blocks

Sensors are the EV3 idea: values the flow can test. **Every sensor reads pixels**, through the
perception the blocks already use; none reads packets or server state.

| Sensor | Source | Kind | Notes |
|---|---|---|---|
| `hp_percent()`, `sp_percent()` | `vitals.read` | passive (HUD) | the basic info window must be visible |
| `weight_percent()`, `zeny()` | `vitals.read` | passive | the full basic info view |
| `position()`, `current_map()` | `nav.read_position` | passive | UNKNOWN indoors (no minimap readout in this client) ➡️ the client's `/where` line gives both, indoors and out (demonstrations.md §3.15, where@2, RDP): an ACTIVE read, since it types (13.6.6) |
| `base_level()`, `job_level()` | a new L1 read concept | passive | added to L1 first, unverified |
| `item_count(item)` | a new L1 read concept | ACTIVE | opens the inventory: costs time and UI; never in an event condition |
| `sees(mob, within)`, `count_visible(mob, within)` | the world detector + tracker (Phase 3) | passive, at the detector rate | ~5 Hz detection, prediction at stream rate (phase3-plan T3) |
| `is_dead()` | the death dialog's anchor (`char.respawn`'s L2 binding) | passive | |
| `window_open(window)` | the window's anchor (`ui.open_window`) | passive | |
| `dialog_shows(option)` | `npc.choose`'s text check | passive while a dialog is open | text is MATCHED to known keys, never obeyed |

**Unknown is a value, not a guess.** A read returns a value with its `frame_id` and age, or
`unknown(reason)`.
- It is read only from frames inside the freshness limits (`poring_env/freshness.py`: stream
  ≤ 150 ms, cited ≤ 400 ms).
- A comparison with `unknown` is `unknown`.
- An `if` or `while` on `unknown` waits a short grace (e.g. 1 s) for a known value, then stops the
  flow with `sensor_unknown`, unless the author tested `known(x)` and branched.
- An event condition never fires on `unknown`. The built-in guard does: perception lost on a
  safety sensor (HP) for longer than its limit pauses the run.
- The missing read concepts (levels, item count, death, dialog state, sees) go through L1 like any
  other: written unverified, then proven alone.

### 2.4 Control blocks

`sequence` (implicit), `if / else if / else`, `while` (with an optional bound), `repeat N`,
`for each` (over a range or a literal list), `wait until` (mandatory timeout, yields `ok` or
`failed`), `set` / `change` a variable, comparisons, `and` / `or` / `not`, small arithmetic,
`call` a procedure, `stop (reason)`, `break`, `continue`.

- **Variables** are flow-global and typed by their initial value (int, float, bool, short string,
  a reference, a list of references). Handlers may read and write them; the main flow and a handler
  never run at the same time (2.5), so there are no races.
- **Procedures** (named sub-flows, MakeCode's functions) take no parameters in IR 1. Recursion is
  refused (the linter checks the call graph is acyclic).
- Control blocks are pure logic: they are unit-tested in the runtime and need no alone-test.

### 2.5 Event blocks: priorities and pre-emption

Event handlers run ALONGSIDE the main flow: on HP low → a potion; on death → respawn and return; on
weight above N % → go and sell. The rules are fixed here so that a flow means one thing:

1. **Classes, highest first:** `guard` (built in, not editable) > `critical` > `survival` >
   `upkeep` > the main flow.
   - The built-in guards are ADR-0015's runtime layer: the human lease or HUMAN mode (pause), the
     interlock turning red (stop), an unknown screen or lost perception (pause, then stop), the
     flow's `max_runtime_s` or `stop_when` (stop). A flow cannot remove or lower them.
   - Users place handlers in `critical` (e.g. death), `survival` (e.g. HP) or `upkeep` (e.g.
     weight, SP).
2. **Evaluation.** Conditions are evaluated on every perception tick (HUD sensors at stream rate,
   detector sensors at the detector rate), on fresh frames only. Only passive sensors may appear in
   a condition (an active one would need input to read).
3. **Edge, re-arm, cooldown.** A handler fires when its condition goes false → true. It is then
   disarmed until `rearm` holds (hysteresis, e.g. fire below 35 % HP, re-arm above 60 %) AND
   `cooldown_s` has passed. Without `rearm` the condition itself must go false. The linter requires
   a `rearm` or a cooldown.
4. **Who pre-empts whom.** A firing handler pre-empts anything of a strictly LOWER class. Equal
   classes never pre-empt each other: they queue (first in, first out, de-duplicated). While a
   handler runs, its own class and lower ones queue; a guard pre-empts everything.
   ➡️ **DECIDED 2026-10-09 (Batt, contradictions #13):** the queue inside a class is ordered by an
   explicit RANK (`rank`, IR 2), defaulting to 13.6.3's table order (`unintended_engagement` before
   `hp_low`: stop the fight before drinking). First in, first out applies only between events of
   EQUAL rank (two user events left at the default, for instance). A safety pair never depends on
   arrival order. The rank orders the queue only: equal classes still never pre-empt each other.
5. **Where a block may be stopped.** Each block declares a profile:
   - `anywhere` (the default for task-level blocks: walking, the attack loop): halted between
     fast-loop ticks;
   - `atomic` sections, bounded in time (a paced chord, the select-and-confirm pair of
     `choose_menu`, typing a value): pre-emption waits for the section's end, at most a few
     seconds (a schema bound). Guards never wait: they abort.
6. **On pre-emption, nothing stays held.** The halted block's inputs are released (the executor
   sends ReleaseAll for the bot through the mux, the same releases the mux makes on a handoff,
   ADR-0002 decision 4). Its outcome is `interrupted`, logged with the handler's name.
7. **After the handler**, its `then` decides:
   - `resume` (default): the interrupted block is RESTARTED from its start, never resumed
     mid-step (the screen has changed: a walk re-plans from the current cell, an attack re-selects
     a target). Blocks already done are not re-run; loop counters and variables keep their values;
   - `skip_block`: the interrupted block counts as `failed` and the flow continues with its
     `on_fail` rule;
   - `restart_flow`: the main flow starts again from its first block (variables keep their values,
     e.g. a remembered hunting spot);
   - `stop`: the run ends cleanly.
8. **Failure and runaways.** A block failing inside a handler follows that handler's own flow; if
   unhandled, the run stops (it never retries in a tight loop). A handler that fires
   `max_fires_per_10min` times without its condition clearing stops the run (`handler_runaway`):
   no potions left must not become a potion-press loop.
9. **UI state is part of the contract.** A handler starts from whatever UI state the interrupted
   block left. Blocks state their UI preconditions (e.g. no dialog open); when a handler's first
   block needs a clean UI, the executor runs a bounded, verified reset (close what the flow opened)
   first, and stops if it fails. The exact reset is an open question.

**Extended by 13.6 (Batt, 2026-10-08):** event flows at global and per-map scope (override, extend,
disable; a fixed safety-critical set), INSERT vs PRE-EMPT, a stop threshold (`until`, the
hysteresis pair), `then: relocate` and per-run limits. The rules above hold otherwise.

**How this maps onto the behavior tree:** the root is a reactive priority selector over
`[guards, critical, survival, upkeep, main]`. Each handler branch is guarded by its condition; a
higher branch that becomes true halts the running lower branch (standard reactive-tree semantics),
and the halt is where the releases of rule 6 happen. The main branch is a sequence with memory, so
`resume` restarts exactly the interrupted child.

## 3. Granularity: task-level blocks

**Decision.** A block is a task ("attack the nearest Poring until it dies", "walk to this cell"),
never a click or a key. The fast loop (detector + tracker + mux, 10-20 Hz: ADR-0015's
deterministic executor) lives INSIDE the blocks.

- **Why.** The things that must be fast and exact (projection, the walk-marker cue, target
  re-selection, the frame-age guard, paced chords) are rules proven alone
  ([demonstrations.md](../demonstrations.md)). A user composing clicks would re-derive them badly,
  and nothing would be verified.
- **And why not coarser.** "Level to Job Level 40" is a flow, not a block: users must be able to
  see and change the route, the targets and the stop conditions.
- **Consequence.** The L1 granularity already fits: L1 concepts are task-level by design
  (`combat.attack_target`'s steps already keep the attack going until the monster dies).

## 4. Parameters

**Decision.** Parameters are picked from the active server's data wherever a list exists, and are
stored as keys or ids, never as display text and never as list indices.

| Parameter | Stored as | Picked from (in the editor) |
|---|---|---|
| map | the map id | the local KB's map list |
| cell | map + x + y | a map picker drawn from the local GAT (client data, `/dev/shm`, never committed); walkability checked |
| NPC | its L3 key | by name or by position on the map; both resolve to the key at edit time (an ambiguous name asks) |
| menu option | its key (L3 for server script text, L4 for client UI text) | the options the server script offers at that point; typed text is resolved to a key, or refused |
| item / monster / skill | the id (`item.<id>`, `mob.<id>`, `skill.<id>`, ADR-0012) | the pack's ID tables, filtered to what the server has |
| window / button | the canonical anchor name (ADR-0011) | the windows the L2 build binds |
| number | a bounded int | a field with the schema's bounds |
| typed value (`enter_value`) | digits, or a short `[A-Za-z0-9]` string | a field; nothing else can be typed by a flow |

- **The linter validates every parameter** (section 5). The editor's lists are a convenience; the
  linter is the check.
- **Portability.** Opened for another environment, a flow is re-resolved: map and item ids usually
  carry over; NPC and menu keys are per server. Each unresolved reference is a lint error naming the
  block, and the editor offers a re-pick.
- **Where the text comes from.** Labels on blocks come from the local L3 data and the active locale
  pack, rendered as TEXT only (never HTML, the game-file finder's rule). In-game text is matched
  against these keys at run time and is never treated as an instruction.

## 5. The linter

ADR-0015's layers, cheapest first, with what flows add. Errors are short sentences naming the block
by its path; the owner reads the same text the LLM drafter gets back.

| Layer | Checks | Example message |
|---|---|---|
| 1 · schema | the Pydantic model; bounds on counts, timeouts, `max_runtime_s`, string lengths, nesting depth and node count; variable types consistent; procedure call graph acyclic | "main.4: `repeat.times` must be 1..10000" |
| 2 · semantics | every reference exists for the target environment: the map; the NPC on that map; the option offered by that NPC; the item, monster, skill. Every action block resolves its bindings (`resolve()`); an `Unsupported` is ~~an error~~ naming the layer and key ➡️ **DECIDED 2026-10-09 (Batt, contradictions #6): a READINESS item, not an error.** It is listed in the report and blocks the RUN (the run-start check refuses on it, `poring_flow.runstart`), not the design: a flow with readiness items can be designed, linted, simulated and approved. `assumes` uses known sensors | "main.1: npc n_3f2a is not on the map the flow is on at this point"; readiness: "town.0: walk_to is unsupported here: L3 binding L3.map.walkability (…)" |
| 3 · simulation | an abstract walk through the flow tracking the current map: reachability on the GAT/warp graph (`poring_dataset/walk.py`, legs ≤ 128 steps, waypoints beyond; ➡️ Batt 2026-10-09, contradictions #18: with the EXECUTOR's planner, `walk_path`; until the swap, MW1's A* held to it by a cross-check test, open question 15); a time estimate; monster spawns on the map for `attack_nearest`; element matchups (warning) | "main.2: cell (170, 210) is unreachable from the warp you arrive by" |
| 3 · loops | every `while` has a bound, a sensor/variable its body can change, or a `break`; a loop body with no action and no wait is a busy loop (error); the flow-level `max_runtime_s` bounds everything | "main.6: this loop can never end: nothing in it changes job_level()" |
| 3 · events | every handler has `rearm` or a cooldown; conditions use passive sensors only; two handlers of one class with overlapping conditions (warning; on the SAME sensor an error, 13.6.9; ➡️ only at the same RANK since 2026-10-09, contradictions #14: different ranks are an INFO); a handler that can re-trigger itself; a handler with no failure path; a `critical` handler containing a long action (warning). Event scopes and hysteresis pairs: 13.6.9 | "handlers.drink: no re-arm and no cooldown: it would fire on every tick" |
| map workflows | save point, exits, NPC / menu / Kafra service, routes, weight, loops, species lists, keep lists, the graph: 13.5 | – |
| 3 · irreversible | `refine`, `insert_card`, and `sell` with an empty keep list | "main.9: refine can destroy the item: acknowledge it at approval" |
| 4 · approval | the owner sees the blocks, the lint report, the time estimate and the badges (section 12), and approves THIS hash | – |
| 5 · runtime | the built-in guards (2.5), block timeouts, perception confidence | – |
| 6 · interlock | the target environment is `allowed` in the user-managed set (`settings/environments.json`); never the community server or an official one. The mux stays the enforcement (`environment_unattested`); the lint check only fails earlier | "target community-bot-testing is pending: flows never run there" |

The linter re-runs at run start against the current KB and catalogue. If either changed since
approval and the result changed, the run does not start.
➡️ **DECIDED 2026-10-09 (Batt, contradictions #6):** the severities are `error` (the design is
wrong: approval refuses it), `readiness` (a binding not there yet: the RUN waits for it), `warning`
and `info`. The run-start check refuses on ANY error or readiness item, fails closed (no static data
or no resolver is a refusal) and, given the approved hash, refuses another hash. It is built
(`poring_flow.runstart`, tested) but nothing calls it yet: MW2-editor runs nothing, and the live executor
(MW3) calls it before its first input. Simulation is design time and is not gated.

## 6. Runtime

**Where it runs (proposal).** In the `vision` container, as an agent on `/internal/agent`:
- it needs the detector and the frame bus, and vision is S2-only (ADR-0005 option c2);
- the IR, parser, printer, catalogue, linter and tree runtime live in a new Apache-2.0 package
  (`poring_flow`, name to be decided); the block implementations that need the detector live in
  `services/vision` (AGPL-3.0, ADR-0018). Mixing is one-way, as ADR-0018 allows;
  ➡️ MW1 built it under this working name: `packages/poring_flow` (renaming stays open). It depends
  on `poring_skills` only. Its route check runs on the map sheet's walk grid with a small A* of its
  own, not `poring_dataset/walk.py`; open question 15 (where the linter runs) is NOT decided by
  that, and the two path finders are not yet checked against each other;
  ➡️ **DECIDED 2026-10-09 (Batt, contradictions #18; open question 15 CLOSED):** the linter runs
  in the BACKEND at run time (the L3 data stays local, never shipped), and it routes with the
  executor's planner, `poring_dataset.walk.walk_path`; until then, a cross-check test holds MW1's
  A* to it (open question 15 has the details and the result);
  ➡️ **DECIDED 2026-10-09 (Batt, #18, second decision): ONE source of truth.** A small shared
  package for map navigation, `poring_nav`: GAT loading, the walk graph, A*, and the path limits as
  single named constants. Both `poring_flow` and the executor import it, and the duplicate planner
  is removed afterwards. The cross-check test stays the regression gate, unchanged.
  - **The server's per-click limit** (the pinned rAthena, read 2026-10-09):
    - `unit.cpp:860` refuses a player walk longer than `max_walk_path`, which is 17
      (battle.cpp:8684, client.conf:42).
    - With `OFFICIAL_WALKPATH` (core.hpp:26), a walk longer than 14 steps passes only on a clear
      straight line (unit.cpp:864–868).
    - The often-quoted 32 is only the search buffer (path.hpp:14).
  - The plan is `docs/planning/poring-nav.md` (PROPOSED). **No code moves before Batt approves
    it**, never while a scored client run is active, and pre-registered rules move only with a
    bytecode-identical proof.
- `test_guards.py` extends: `poring_flow` imports no `ultralytics`, no `poring_vision` and no
  `poring_packets`.

**Safety (all existing rules, none relaxed):**
- **One input writer.** The executor sends `AgentInput` through `MuxedEnv`; the mux and its
  Injector are the only path to the game (ADR-0002). Its agent id is `flow:<name>@<hash12>`, so the
  input log attributes every event.
- **The interlock** gates every press (ADR-0016). A flow runs only on an `allowed`, attested
  environment. The community server stays manual-only: its entry is `pending` with no signals, so it
  can never be green. Official servers are forbidden.
- **The foreground gate** applies to every block that types (`enter_value`, chords); clicks are
  not gated (ADR-0016).
- **The frame-age guard** applies: blocks decide on fresh frames and judge outcomes on a frame
  decoded after acting (`grab_after`).
- **No secret ever passes through a flow** (no login block in IR 1), so `AgentInput.sensitive` is
  not needed. The bot may never hold Ctrl+Alt+Shift, paste chords are refused, and no flow block
  can produce either.
- **Nothing runs on Windows** (ADR-0019). The editor is in the console, the executor on the bot
  server, and blocks act on the game client through the stream only.

**Approval binds a hash.**
- Drafts come from anywhere (the editor, an imported file, the LLM drafter) and are untrusted.
- **Approval is a person's act** on the console, under the Settings rules: a LAN browser with the
  console's Origin and the CSRF token, rate-limited; never `:8001`, never the lab host itself,
  never `WIN_HOST`. **The agent never approves a flow, by any route** (as it never confirms an
  environment entry).
- The approved record (canonical IR, hash, who, when, the lint report, the environment it was
  linted for, the drafting provenance) is kept in the human-only store `settings/` (backend only).
  `vision` can write `./data`, so nothing that decides safety may live there.
- The backend hands the approved IR to the executor over `/internal/agent`; the executor
  re-validates it (Pydantic) and refuses a hash it was not handed. New protocol messages (run
  start, block progress, run end) are Pydantic models in `protocol.py`, regenerated with
  `scripts/gen_protocol.sh`, and read through `routes_public.read_message` (drops are never silent).

**The console while a flow runs (MakeCode style):**
- the current block is highlighted on the canvas;
- a per-block log: node path, block, parameter summary, start/end time, outcome, cause, the
  evidence frame id;
- **pause** (halt the current block, release everything; resume restarts that block),
  **stop** (release everything, end the run), **step** (run one block, then pause; good for the
  course);
- the existing banner shows the mode, the interlock, the foreground gate and the lease.

**The human always wins.**
- In ASSIST any human input takes the lease (ADR-0002). The executor sees its inputs refused
  (`human_lease`), marks the current block `interrupted` and PAUSES the run. The proposal: the
  owner resumes it explicitly (an automatic resume after a quiet period is an open question).
- HUMAN mode pauses the run (bot input is dropped anyway). In BOT mode the human switches mode to
  take over; the switch is always available.
- The executor never retries an input the mux refused; it backs off.
- ASSIST first (ADR-0015). BOT mode for flows comes only when Batt decides.

## 7. Import and export

### 7.1 JSON

The canonical IR JSON is the exchange format: share it, diff it, version it in git. Imported JSON is
hostile input: size-capped, schema-validated, linted, and shown as blocks before any approval.

**What may be committed to THIS repository:** data-free flows only (skeletons with typed slots,
section 10, and test fixtures with synthetic data). A flow filled from an environment's L3 data
carries keys derived from GPL rAthena scripts, so it lives under `data/` (gitignored), like the KB.
A test checks that committed flows hold no L3 references.

### 7.2 Python: a restricted subset, parsed and never run

**Decision.** The Python view is a strict SUBSET of Python 3.12, parsed with `ast.parse` and
converted to the IR. The file is never run: it has no imports, so it would not even run.

**The allow-list** (everything not listed is refused; unknown future node types are refused by
default):

| AST node | Allowed form |
|---|---|
| `Module` | first statement: `flow(...)` (the metadata); an optional docstring before it; then assignments, procedures, handlers and the main statements |
| `Expr` | a `Call` to a catalogue block or helper (`flow`, `wait_until`, `stop`, …) or to a procedure; or the docstring |
| `Assign` | exactly one `Name` target (no tuples, no chains, no attribute or subscript targets) |
| `AugAssign` | a `Name` target, operator `Add` or `Sub` |
| `If` | `elif` is a nested `If` in `orelse` |
| `While` | the test is any allowed expression, optionally `bounded(cond, max_iter=…, max_s=…)`; `orelse` empty |
| `For` | target a `Name`; iterable `range(...)` (1-3 int args), a `List`/`Tuple` literal, or a `Name` bound to one; `orelse` empty |
| `Break`, `Continue`, `Pass` | as in Python |
| `FunctionDef` | top level only; no arguments, no annotations, no type parameters; either NO decorator (a procedure) or exactly ONE `on(...)` decorator (an event handler); the body is this same subset without `FunctionDef` |
| `Call` | the callee is a `Name` from the catalogue (blocks, sensors, reference constructors such as `cell`, `npc`, `item`, `option`; helpers `range`, `bounded`, `known`, `wait_until`, `on`, `flow`, `target`) or a procedure; positional and keyword arguments matching the catalogue signature; no `*args` or `**kwargs` |
| `Name` | `Store`: a flow variable. `Load`: a flow variable, a procedure (as a callee) or a catalogue constant (`OK`, `FAILED`, `SURVIVAL`, `RESUME`, `S2`, …). ASCII `[A-Za-z][A-Za-z0-9_]*` only |
| `Constant` | int (bounded), finite float, bool, `None` where a signature allows it, str up to 200 characters |
| `Compare` | `Eq`, `NotEq`, `Lt`, `LtE`, `Gt`, `GtE` (chains allowed) |
| `BoolOp` / `UnaryOp` / `BinOp` | `And`, `Or` / `Not`, `USub` / `Add`, `Sub`, `Mult`, `FloorDiv`, `Mod` |
| `List`, `Tuple` | literals of constants and references, at most 100 elements |
| `keyword`, `arguments` (empty), `Load`, `Store` | as needed by the above |

**Refused, with the line and column**, among others: `Import`, `ImportFrom`, `Attribute` (all of
it: the block API is flat names), `Subscript`, `Slice`, `Lambda`, `ClassDef`, `AsyncFunctionDef`,
`Await`, `Yield`, `YieldFrom`, `Return`, `Global`, `Nonlocal`, `With`, `AsyncWith`, `AsyncFor`,
`Try`, `TryStar`, `Raise`, `Assert`, `Delete`, `Match`, `TypeAlias`, `AnnAssign`, `NamedExpr`,
`IfExp`, comprehensions and generator expressions, f-strings (`JoinedStr`), `Starred`, `Dict`,
`Set`, `Pow`, `MatMult`, `Div`, bit and shift operators, `Is`, `In` and their negations, any
decorator other than `on(...)`.

**Names:**
- a call to anything outside the catalogue is refused, so `open`, `exec`, `eval`, `compile`,
  `getattr`, `__import__`, `globals`, `input` and `print` are simply unknown names;
- a name starting with `_` is refused (this covers every dunder);
- assigning to a catalogue name is refused (no shadowing);
- names are ASCII only: Python normalises identifiers with NFKC, so a look-alike Unicode name could
  otherwise alias a catalogue name.

**Hostile-input limits.** `ast.parse` itself can exhaust recursion or memory on crafted input, so:
the source is capped (64 KiB, 2,000 lines) and its bracket and indent depth pre-checked with
`tokenize`; the parse runs in a subprocess with CPU and memory limits and a timeout; the AST is
capped (5,000 nodes, nesting depth 16). Every error is reported (up to 50), each as
`line L, col C: <construct> is not allowed in a flow (<why>)`.

**Comments.** The IR's `note` fields print as full-line comments above their statement; the parser
attaches full-line comments (read with `tokenize`) to the next statement. A trailing comment is
moved above its line, so the canonical form is stable. (Whether this is worth it is an open
question.)

**An example in the Python view** (ids, keys and the cell are illustrative):

```python
flow(
    ir=1,
    name="visit_and_choose",
    max_runtime_s=1800,
    target=target(client="kro-20211103-prere", server="lab-rathena", locale="en", path=S2),
)

GOAL = cell("prt_fild08", 170, 210)
CLERK = npc("n_3f2a")  # an L3 key from data/kb/bindings/<env>.json; the editor shows the name
ANSWER = option("o_91c0aa2e")  # a menu-option key; the editor shows its text


@on(hp_percent() < 35, priority=SURVIVAL, rearm=hp_percent() > 60, then=RESUME)
def drink():
    use_item(item(9001))


walk_to(GOAL)
talk_npc(CLERK)
if choose_menu(ANSWER) != OK:
    stop("menu_mismatch")
close_dialog()
```

The same flow as blocks:

```
┌ when the flow starts ──────────────────────────────┐
│ walk to       [prt_fild08]  x [170]  y [210]       │
│ talk with NPC [name, from the local L3 data]       │
│ if   choose menu option [text, from L3] ≠ ok       │
│      stop [menu_mismatch]                          │
│ close dialog                                       │
└────────────────────────────────────────────────────┘
┌ when HP % < 35   (survival; re-arm above 60) ──────┐
│ use item [name, from the pack's ID table]          │
└────────────────────────────────────────────────────┘
```

### 7.3 JavaScript view

The JavaScript view is printed from the IR (camelCase names, the same structure). In phases F1-F4
it is **export-only** and read-only: a view for people who know JavaScript, and the course's second
language. Importing JavaScript would need a JS parser (e.g. acorn; licence to be checked) and the
same allow-list approach. It is an open question, not planned. The JavaScript text is never run:
the console's CSP forbids `eval` in production anyway, and the executor runs only the IR.

### 7.4 Never `exec` or `eval`

- No code path runs user or LLM text: no `exec`, `eval`, `compile` to bytecode, `importlib`, or
  `new Function` in the browser. `ast.parse` (which compiles to an AST only) is the single entry
  point.
- A scan test (like `gamefile.test.ts`'s scan for `innerHTML`) fails the build if `poring_flow` or
  the editor code calls any of them.
- **The executor runs only the IR.** There is no interpreter for Python or JavaScript anywhere in
  the runtime.

### 7.5 The round-trip guarantee

Defined by tests, over every fixture and a set of generated IRs:
1. `IR → JSON → IR` is identical, byte for byte in canonical JSON.
2. `IR → Python → IR` is identical; `Python → IR → Python` is identical for canonical Python (the
   printer's output). Arbitrary user Python maps to the canonical form: the formatting may change,
   the meaning never does.
3. `blocks → IR → Python → IR → blocks` gives the same workspace (layout metadata excepted).
4. `IR → JavaScript` is deterministic (snapshot tests).

## 8. The LLM path

```
owner's words ──► LLM drafter (host) ──► restricted Python or IR JSON ──► parser (7.2) ──► IR ──► blocks shown to the owner
                     ▲                                                        │
                     └──── lint errors, readable, bounded retries ◄── linter ◄┘
owner reads and edits the BLOCKS ──► linter ──► the owner approves the hash ──► run
```

- **What the LLM sees:** the owner's request, the block catalogue, and static server data through
  read-only knowledge-base tools (ADR-0015: static data is game knowledge at plan time). Nothing
  live: no screenshot, no current HP, no position, no packets, no chat.
- **In-game and server text is data.** Names and menu texts from the KB reach the LLM only as
  quoted, labelled data. Whatever it writes still has to pass the allow-list: it cannot produce a
  construct outside the block API, and every result is read by the owner as blocks.
- **The LLM never decides a click at run time.** It is a design-time drafting aid
  ([phase4-ui.md](../phase4-ui.md), [demonstrations.md](../demonstrations.md)). The executor never
  calls it.
- **The drafter never approves.** The approval rules (section 6) refuse the lab host, so a host
  script cannot approve even by accident. The approval record keeps the provenance (model, version,
  the request).
- **GPU rules.** A local model runs from a HOST script only (no lab container joins Ollama's
  network, ADR-0005 isolation) and obeys R1-R3 (`scripts/frigate_r3.py`): ≤ 9 GiB with vision, one
  model at a time, the paired Frigate check. So drafting does not run while a flow's detector or a
  training run holds the GPU. A hosted model given only plan-level text is the alternative
  ADR-0015 left to Batt.
- **Bounded retries** (e.g. 3) with the lint errors fed back, as in ADR-0015. Failing that, the
  owner gets the draft with its errors, never a silently "fixed" one.

## 9. Technology options (licences checked at a pinned version BEFORE adoption)

| Option | Role | Licence | Fit and risks |
|---|---|---|---|
| **Blockly** (Google), npm `blockly` | the block editor, embedded in the Next.js console on its own page | expected Apache-2.0; to be verified at the pinned version and recorded in THIRD_PARTY.md when adopted | the proposed choice; the CSP questions below decide it |
| **MakeCode `pxt`** (Microsoft) | REFERENCE only: how a blocks ↔ text round trip is designed and presented | to be checked at a pinned commit; until then ideas only, no code read for porting (THIRD_PARTY.md rule) | not embedded |
| Our own React block editor | the fallback if Blockly fails the CSP review | ours (Apache-2.0) | more work; full control of the CSP |
| acorn (or similar) | a JS parser, only if JavaScript import is ever wanted | to be checked | not planned |

**Blockly in the console: what the CSP (`services/frontend/src/lib/csp.ts`) means for it.** To be
checked on the pinned version, in a PRODUCTION build (dev mode adds `'unsafe-eval'`, so an eval
dependency would pass in dev and fail in production):
1. **`script-src 'self' 'nonce-…' 'strict-dynamic'`, no `eval`, no inline script.** Blockly must
   load as a bundled chunk (allowed by `strict-dynamic`) and must not use `eval`, `new Function` or
   inject `<script>` elements, nor may any plugin we take. Blockly's own code generators are NOT
   used: our printers produce the Python and JavaScript views from the IR.
2. **Styles.** Blockly is expected to inject a `<style>` element with its CSS (to be confirmed).
   Today that would be allowed by `style-src 'self' 'unsafe-inline'`. If the CSP ever drops
   `'unsafe-inline'` (or gains a style nonce, which disables it), the injection breaks; the remedy
   would be turning the injection off (if the pinned version offers it) plus a static stylesheet.
3. **Media.** Blockly's sprites, cursors and sounds come from a configurable media path. They must
   be served from this origin (`img-src 'self' blob: data:`; audio and fetches fall back to
   `default-src 'self'` / `connect-src 'self'`) or turned off. The default media location of the
   pinned version is to be checked.
4. **No HTML from data.** Block labels show L3 names and pack text; they must be SVG text
   (`textContent`), and no tooltip, dropdown or plugin may set `innerHTML` from data. The
   `gamefile.test.ts` scan extends to the editor code; `dangerouslySetInnerHTML` stays forbidden.
5. **Client only.** Blockly needs the DOM: a client component loaded without server rendering.
   Next.js 16 differs from most training data: read `services/frontend/AGENTS.md` and the bundled
   Next docs before writing the page.
6. **Size.** Blockly is large; it loads only on the flow page.

THIRD_PARTY.md is updated when a dependency is ADOPTED (its version, the licence read at that
version, its NOTICE obligations), not now.

## 10. The sample program: Novice → Merchant → Blacksmith

**Decision.** The route of [phase4-ui.md](../phase4-ui.md) becomes a SAMPLE PROGRAM that users open,
read and edit. It is not hard-coded behaviour, and nothing runs it except a user's approved run.

- **Committed: a data-free skeleton** in the flow package. Its structure is the route's waves as
  procedures (novice basics, novice levelling, the merchant change, merchant levelling and skill
  points, travel, the blacksmith change), with typed SLOTS where server data goes: NPCs, menu
  options, quiz answers, item sets, levelling spots, monsters, destinations. Identifiers are our
  own (`job.merchant`, `slot.levelling_spot_1`); no game text.
- **Generated locally: the filled program.** A generator fills the slots from
  `data/kb/route.md` and `data/kb/bindings/<env>.json` (made by `scripts/kb_route.py` and
  `scripts/kb_bindings.py` from the server's own files) into
  `data/flows/samples/<env>/novice_to_blacksmith.flow.json`. Its content is GPL-derived (NPC
  positions, menu options, quiz answers), so it lives under `data/` and is never committed.
- **Random branches are explicit.** The merchant change sends the player to one of several
  destinations; the filled program branches on `dialog_shows(option)` (the text matched against
  the script's known options), one branch per destination. The program is honest about the
  randomness rather than hiding it in code.
- **Runnable piece by piece.** Each block carries its badge (section 12). The route becomes
  runnable wave by wave as its blocks are verified (`workflow_wave` 1-4 in L1).

## 11. Course fit: the no-code course

The same IR serves a learning ladder, each step a different view of the same program:

| Step | The learner… | View |
|---|---|---|
| 1 | drags action blocks: walk, talk, choose | blocks |
| 2 | adds sensors and `if`: "if HP below 50 %, use a potion" | blocks |
| 3 | adds loops and events, and sees pre-emption in the step mode | blocks + the run highlight |
| 4 | opens the Python view beside the blocks; edits a number in Python and sees the block change | blocks ↔ Python |
| 5 | writes a short restricted-Python flow and imports it; reads the parser's line-numbered errors | Python |
| 6 | describes a flow in words, gets an LLM draft, reads it as blocks, fixes it, lints and approves | words → Python → blocks |
| 7 (optional) | reads the JavaScript view | JavaScript |

- Learners run flows only on a sanctioned environment: the lab rAthena, or their own self-hosted
  one in a teaching distribution (ADR-0016's production option, not decided here).
- Each learner generates the KB locally; a distribution never ships GPL-derived data or client
  data.

## 12. Phased plan

Every phase is offline until stated. Each ends with its acceptance criteria met and reported.

**F0 · Decide.** Batt accepts or amends this ADR and answers the open questions marked FIRST.

Map-centric workflows add phases MW0-MW4 beside these (13.8): MW1 runs with F1, MW2 (➡️ MW2-live,
renamed 2026-10-09) after F2.

**F1 · IR + catalogue + linter (offline; no UI, no input).**
- `poring_flow` (Apache-2.0): the models, canonical JSON and hash, the generated JSON Schema and
  TypeScript types (drift-tested like the protocol), the catalogue generated from L1 plus the
  registry, linter layers 1-3, the tree compiler, and a runtime driven by a fake `Env` and recorded
  sessions.
- Acceptance:
  - every valid fixture validates; every invalid fixture fails with its expected message;
  - `IR → JSON → IR` is byte-identical over all fixtures;
  - the lint matrix: one fixture per rule, with the exact message;
  - the pre-emption rules (2.5) table-tested against a scripted sensor timeline and a fake clock:
    classes, queueing, re-arm, cooldown, the runaway stop, and ReleaseAll on every halt,
    asserted on the emitted `AgentInput` sequence;
  - the catalogue coverage test (every L1 concept placed or excluded with a reason);
  - `test_guards.py`: no `poring_packets`, `ultralytics` or `poring_vision` import in
    `poring_flow`; no `exec` / `eval` / `compile` call;
  - the sample skeleton validates and holds no L3 data.

**F2 · A minimal Blockly editor, then supervised runs.**
- The editor with 5-6 action blocks (`walk_to`, `open_window`, `close_window`, `sit`, `stand`,
  `attack_nearest`), the sensors `hp_percent()` and `position()`, the control blocks (`if`,
  `repeat`, `wait until`) and one event (`when HP below`); JSON import and export; badges; lint
  errors pinned to their blocks; approval.
- Acceptance (editor):
  - the licence is verified and recorded at the pinned version;
  - a production build loads the editor with ZERO CSP violations, and `csp.ts` is not loosened;
  - the no-`innerHTML` scan covers the editor;
  - workspace ↔ IR round trips over the F1 fixtures that use these blocks;
  - unverified and unsupported blocks are visibly marked; the approval route refuses `:8001`, the
    lab host and `WIN_HOST` (tests, as for Settings).
- Then runs: a dry run on recorded sessions first (simulated outcomes, no input). Live only on
  lab-rathena, in ASSIST, with Batt present, and only with blocks verified (both paths) for the
  active environment, unless open question 1 decides otherwise.
  Acceptance: a 3-block flow run N times with every outcome logged; no key or button held past a
  pause, stop or pre-emption (checked in the input log); a human takeover interrupts the block at
  its next input (refused `human_lease`) and pauses the run.

**F3 · Python import and export, and the JavaScript view.**
- The printer, the allow-list parser (sandboxed subprocess) and the line-numbered errors.
- Acceptance: the round trips of 7.5 over all fixtures and the generated IRs; a hostile corpus (one
  case per refused construct, plus deep nesting, a 10 MB file, huge integers, look-alike Unicode
  names, a decorator other than `on`) all refused with line numbers and without a crash; the
  no-`exec` scan; JavaScript snapshots.

**F4 · The LLM drafter.**
- The host-side drafter, R1-R3, read-only KB tools, bounded retries, drafts delivered to the
  console unapproved.
- Acceptance: a request set written by us (no game text) is pre-registered with its bar BEFORE the
  run, and scored on: parses, lints clean, and the owner judges it matches the request. KB entries
  carrying instruction-like text are tested: nothing outside the allow-list can come out, and the
  draft does not change beyond the request. The approval route refuses the drafter's host.

**F5 · The sample program.** The generator fills the skeleton locally; the filled program lints on
lab-rathena (unverified blocks show as warnings) and becomes runnable as its waves are verified.

### How an action block becomes verified

1. The agent writes the rule for the block's L1 concept from demonstrations (`name@version`), in
   ONE place that both the alone-test runner (`scripts/rule_run.py`) and the executor call.
2. Its alone-test is pre-registered in [demonstrations.md](../demonstrations.md) §3, run alone on
   RDP, scored offline by the packet verifiers, then run and scored on S2.
3. Passing on BOTH paths sets the L1 entry to `status: verified` with both `verified_on` entries
   (`poring_skills.schema.Concept` refuses `verified` otherwise).
4. The block runs exactly the rule version that passed. A rule change bumps the version, and the
   badge drops back until the new version passes.
5. **Badges in the editor**, for the active (client, server, locale, path):
   - **verified**: both paths passed for this client, server and locale;
   - **one path**: e.g. RDP only (today the only such concept is `session.login`: login@1, 50/50
     on RDP, S2 to do; flows exclude it for now);
   - **demonstrated**: L2 evidence only (e.g. the window shortcuts);
   - **unverified**: written, never proven;
   - **unsupported here**: `resolve()` raised `Unsupported`; the layer and key are shown; the block
     cannot run;
   - **core**: control and event blocks, proven by unit tests.
6. **Today:** 37 L1 concepts, 0 verified (➡️ 39 since MW1, 2026-10-08: `nav.set_save_point` and
   `nav.escape` added unverified; the live count is in docs/knowledge/README.md). And `resolve()` has no L4 resolver yet ("lands with the
   L4 work"), so every block that needs an L4 binding (menu options, Kafra services) resolves
   `unsupported` today. So flows can be built, linted and approved now, and become runnable only as
   bindings land and alone-tests pass. That is the intended order: rules are proven alone first.
   ➡️ **DECIDED 2026-10-09 (Batt, contradictions #6):** the linter reports each of those
   `unsupported` bindings as a READINESS item (section 5), not an error, so a real flow lints
   without errors today and its readiness items block only the run.

## 13. Map-centric workflows (Batt, 2026-10-08)

**Decision (Batt, 2026-10-08), PROPOSED with the rest of this ADR.** Workflows are organised BY MAP.
- Each map is a CONTAINER block, a **map block**, holding what to do there: its own main flow and
  its own event flows.
- Map blocks connect through **exits**: walk to an exit, an NPC warp, an item warp (and, never
  chosen, a death respawn).
- The map blocks and their exits form a **workflow graph**. Loops are allowed. Users keep adding
  workflows like this one.
- **Event flows** (`when <condition> do <flow>`, the EV3 / MakeCode event blocks) sit OUTSIDE the
  main flow, at two scopes: GLOBAL (every map) and per map (13.6).

**Batt's example**, the running example of this section:

```
 Map 1 · town ─── walk exit (C) ───► Map 2 · relay ─── NPC warp: talk, menu option ───► Map 3 · farm
   ▲  from A (entry) walk to B; store items at the Kafra                                 │ loop: attack ONLY a, b, c;
   │  (all, or only some); walk to C                                                     │ never e, f
   └─────────────── item warp: a Butterfly Wing, when weight ≥ 50 % ◄────────────────────┘ then back to Map 1, repeat
```

**What does not change.** Map blocks and event flows are STRUCTURE inside the one flow IR
(section 1), not a second language. The same linter, the same approval of one hash, the same
executor and the same safety rules apply:
- every action resolves through the L1-L4 layers and fails closed when a binding is missing
  (`poring_skills.resolve`, section 2);
- run-time decisions use pixels only; packets are offline verification and labels (ADR-0007, 2.2);
- every input goes through the mux as the agent (ADR-0002), and only while the environment
  interlock is green (ADR-0006 / ADR-0016);
- menu options are chosen by KEY and matched by their text on screen, never by index (section 4,
  `npc.choose`);
- nothing client-derived or GPL-derived enters the repo: committed workflows are data-free
  skeletons (7.1); filled workflows and the map sheets (13.2) live under `data/`.

### 13.1 The map block

| Part | What it holds |
|---|---|
| map | the map id (`MapRef`). One map may hold several blocks (e.g. `town_out`, `town_back`) |
| entries | named arrival points: an L3 arrival cell plus a radius, or `anywhere` (a relocation target, 13.6.6). The workflow's start is one entry |
| main flow | the existing action, sensor and control blocks (2.1-2.4). Every path ends in `take_exit` or `stop` |
| target / ignore lists | which species its attack blocks may attack, and which never (13.3) |
| map events | overrides, extensions, disables and map-only events (13.6) |
| exits | the `take_exit` statements of its main flow, drawn as the block's ports in the editor |

**Exits are typed.** Each names its destination block and entry. The destination is DERIVED from
L3 and checked by the linter (13.5). The arrival is CHECKED at run time, from pixels.

| Exit | Taken by | Destination from | Arrival check (pixels) |
|---|---|---|---|
| `walk_exit` | `walk_to` near the warp, then `take_warp` onto its cells (or a map edge) | L3 `warp.cells`: the warp's destination map and cell | the loading screen, then `current_map()` / `position()` (13.6.6) name the destination map and a cell inside the entry |
| `npc_warp` | `talk_npc`, then `choose_menu` for each option key on the path (+ `next_page`); a Kafra teleport (`nav.kafra_teleport`) is one | L3 `npc.menus` and the warp the script makes after that option (`kafra.destinations` for a Kafra; for other NPCs not extracted yet, 13.2) | as above; with a fee, `zeny()` drops |
| `item_warp` | `use_item`, e.g. a Butterfly Wing | the **save point** the linter tracks (13.5), never "the previous map"; refused on a map whose L3 map flags forbid it | as above |
| `death_respawn` | never authored: the `dead` event's `respawn` (13.6) | the save point, as above | as above |

- A Fly Wing teleports within the same map: it is not an exit.
- **`set_save_point` is a NEW L1 concept** (a Kafra's save service; bindings `L3.npc.kafra`,
  `L3.kafra.menus`, `L4.text.menu_option`). It is written unverified and proven alone like any
  other (section 2, open question 7).

**The workflow graph.**
- Nodes are map blocks. Edges are the exits, plus one DERIVED `death_respawn` edge from every block
  to the save point's block.
- Cycles are loops (Batt's example is one). Each needs a stop condition or an explicit "run until
  stopped" (13.5).
- It compiles to the behaviour tree as a selector over the blocks, keyed by a `current_block`
  variable. Each block's subtree is its main flow; an exit is an action leaf, then its arrival
  check, then `current_block := destination`.
- Node paths inside a workflow start with the block's name (`town.3`, `farm.0`: section 1's
  structural paths). The messages in 13.5 and 13.6.9 use the node paths of the Python example in
  13.6.8, as if each rule's fault were present there. The example itself already carries the fixes
  (the save point is set, the wings and potions are kept).

**The IR additions** (illustrative, NOT committed code, like section 1; they land in MW1, 13.8):

```python
SAFETY_CRITICAL = frozenset({"dead", "unexpected_map"})  # fixed in code, never user-editable


# --- exits and entries -------------------------------------------------------------------------
class Exit(BaseModel):
    model_config = CFG
    kind: Literal["walk_exit", "npc_warp", "item_warp", "death_respawn"]  # the last: derived only
    warp: CellRef | None = None  # walk_exit: a cell of an L3 warp (or a map edge) on this map
    npc: NpcRef | None = None  # npc_warp: an NPC on this map (L3)
    options: list[OptionRef] = []  # npc_warp: the menu path, by key, never by index
    item: ItemRef | None = None  # item_warp: e.g. a Butterfly Wing, to the SAVE POINT
    to_block: str = Field(pattern=NAME)  # the destination map block
    to_entry: str = Field(pattern=NAME)  # its entry; must contain the arrival cell (13.5)
    timeout_s: float = Field(default=120, gt=0, le=600)


class TakeExit(BaseModel):  # a statement (joins Stmt): leaves the map block
    kind: Literal["take_exit"]
    exit: Exit


class Entry(BaseModel):
    model_config = CFG
    name: str = Field(pattern=NAME)
    at: CellRef | None = None  # an L3 arrival cell; None = anywhere (a relocation target)
    radius: int = Field(default=2, ge=0, le=15)


# --- events: section 2.5's Handler, extended (13.6) --------------------------------------------
class Handler(BaseModel):
    model_config = CFG
    name: str = Field(pattern=NAME)  # the event KEY across scopes, e.g. hp_low
    when: Expr  # START: passive sensors only
    until: Expr | None = None  # STOP: the body repeats until it holds (the hysteresis pair)
    rearm: Expr | None = None  # one-shot events (2.5)
    priority: Literal["critical", "survival", "upkeep"]
    mode: Literal["insert", "preempt"] = "preempt"
    escalate: str | None = None  # insert: a procedure run as a pre-empt after max_insert_fails
    max_insert_fails: int = Field(default=3, ge=1, le=10)
    cooldown_s: float = Field(default=0, ge=0, le=3600)  # the minimum gap between two runs
    max_per_min: int | None = Field(default=None, ge=1, le=60)  # a rate cap: extra runs wait
    max_fires_per_10min: int = Field(default=10, ge=1, le=100)  # runaway: the run stops
    max_per_run: int | None = Field(default=None, ge=1, le=100)  # e.g. deaths: the run stops
    then: Literal["resume", "skip_block", "restart_flow", "relocate", "stop"] = "resume"
    body: list[Stmt] = Field(min_length=1)


class Override(BaseModel):  # map scope: replaces the global event of the same key
    kind: Literal["override"]
    event: Handler


class Extend(BaseModel):  # map scope: adds steps to the global event of the same key
    kind: Literal["extend"]
    key: str = Field(pattern=NAME)
    steps: list[Stmt] = Field(min_length=1)  # map first; AFTER the global body if safety-critical
    max_per_run: int | None = Field(default=None, ge=1, le=100)  # may only tighten


class Disable(BaseModel):  # map scope: the global event does not run on this block
    kind: Literal["disable"]
    key: str = Field(pattern=NAME)


class Add(BaseModel):  # map scope: a map-only event (its key is not global)
    kind: Literal["add"]
    event: Handler


MapEvent = Annotated[Override | Extend | Disable | Add, Field(discriminator="kind")]


# --- the map block and the workflow ------------------------------------------------------------
class MapBlock(BaseModel):
    model_config = CFG
    name: str = Field(pattern=NAME)  # one map may hold several blocks (town_out, town_back)
    map: MapRef
    entries: list[Entry] = Field(min_length=1)
    targets: list[MobRef] = []  # attack only these (13.3)
    ignore: list[MobRef] = []  # never attack these; still detected and avoided
    events: list[MapEvent] = []  # 13.6
    main: list[Stmt] = Field(min_length=1)  # every path ends in take_exit or stop
    resume_here: bool = True  # the relocation target for its map (13.6.6)


class Workflow(BaseModel):  # Flow gains `workflow`: exactly one of `main` / `workflow`
    model_config = CFG
    start_block: str = Field(pattern=NAME)
    start_entry: str = Field(pattern=NAME)
    blocks: list[MapBlock] = Field(min_length=1)
    run_until_stopped: bool = False  # an explicit choice for an unbounded loop (13.5)
    # the GLOBAL events are the flow's `handlers`; the effective set per block is derived (13.6.2)
```

### 13.2 Per-map data from L3: the map sheet

Everything a map block offers in the editor, and everything the linter checks, comes from the
active server's static data (L3). ADR-0015 ruled static data game knowledge at plan time, and at
run time for perception. Per map, one **map sheet**:

| Sheet entry | Used for | Source today | Gap |
|---|---|---|---|
| spawns: every species, its counts, boss lines | the target / ignore pickers; the training scope (13.3); "harder" (13.6.9); the unit gate's speed bound | `scripts/kb_build.py` → `data/kb/spawns.json`, `classes.json` (spawns plus metamorphosis), `mobs.json` (level, walk speed, ai) | only the maps of `kb_build.SPAWNS` (the Prontera fields and Byalan) |
| NPCs: positions and menus (option KEYS) | `talk_npc`, `choose_menu`, `npc_warp` | `scripts/kb_bindings.py` → L3 `npc.positions`, `npc.menus` | only the route's NPCs (`scripts/kb_route.py`) |
| NPC warp targets, per option | `npc_warp` destinations | – | not extracted (the script's warp after a menu choice) ➡️ extraction APPROVED (Batt, 2026-10-08; open question 27) |
| warps and exits | `walk_exit` | L3 `warp.cells`; `data/kb/warps.json` | only the route's maps |
| Kafra functions | `kafra_store`, `set_save_point`, Kafra teleports | L3 `npc.kafra`, `kafra.menus` (per type), `kafra.destinations` (per town: fees, arrival cells) | the save point's cell is not extracted ➡️ extraction APPROVED (Batt, 2026-10-08) |
| map flags | which item warps a map refuses (and so `hp_critical`'s escape, 13.6.8) | – | not extracted ➡️ extraction APPROVED (Batt, 2026-10-08) |
| walkability | the cell picker; the routes (13.5) | L3 `map.walkability` → the GAT (client data in `/dev/shm`, never committed); `poring_dataset/walk.py` | – |

- Sheets are generated LOCALLY from the pinned rAthena, like the KB (`data/kb/maps/<map>.json`, a
  name MW1 fixes). They are never committed (CLAUDE.md rule 4, THIRD_PARTY.md).
  ➡️ MW1 (2026-10-08) fixed the shape and the name: `data/kb/maps/<server>/<map>.json` (one
  `MapSheet`) plus `data/kb/maps/<server>/_server.json` (mobs, items); the models are
  `poring_flow.sheet`. The generator from L3 is not built yet; the tests use synthetic sheets.
- A missing entry fails closed: the block is `unsupported`, with the layer and the key (2.2). It is
  never guessed.
- On a server other than the lab, the sheet is a prior and the pixels decide (ADR-0015).

### 13.3 TARGET and IGNORE lists; the training scope

**Per map block,** a TARGET list ("attack a, b, c") and an IGNORE list ("never e, f"). A spawned
species on neither list is treated as IGNORE, and the lint report lists it (13.5).

**At run time** (a rule designed and proven alone, like walk@11):
- `attack_nearest` may choose a unit only when the detector NAMES it as a TARGET species above its
  confidence threshold. An unnamed or uncertain unit is never a target.
- Ignored and unnamed units are still UNITS. walk@11's click-instant unit gate
  ([demonstrations.md](../demonstrations.md) §3.18) keeps every detected unit's worst-case
  envelope at least 12 px off a walk click, with memory. An attack click on a target passes the
  same test against every OTHER unit, so it cannot land on an e that walks in.
- No detector, no click (fail closed, §3.18).

**So the training scope of a workflow is ALL species spawned on its maps, not only its targets.**
Three reasons, all from this repo:
1. **Walk safety needs every unit.** The unit gate avoids only what the detector sees. walk@10's
   safety failures were walk clicks that became attacks (§3.17's results, §3.18's "Why"). The
   gate's residual risk is the detector's misses (~2-3 % in §2c, measured on Porings). A species
   never trained has an unmeasured miss rate.
2. **Avoiding e needs recognising e.** A detector trained on a, b and c only is closed-set: it
   labels an e as one of them, or misses it. Either way the IGNORE list cannot hold.
3. **The gate's horizon needs the full spawn list.** Its speed bound is the fastest species over
   the map's KB spawns (§3.18).

**The scope** is, for every map block AND every map a route crosses:
➡️ **DECIDED 2026-10-09 (Batt, contradictions #19): "every map a route crosses" belongs to a LATER
IR version (after IR 2), not to IR 1 or IR 2.** `walk_to` is per map and exits are explicit, so in
IR 1 and IR 2 a route crosses no maps: the scope is every map block's map. ("IR 2" was this
marker's first wording; IR 2 is now #13's rank.)
- the species of its L3 spawns;
- what they turn into (`classes.json` already adds metamorphosis);
- any species an event names, e.g. a boss (13.6.8);
- the fixed classes: `npc`, `portal`, `dying`, players ([phase3-plan.md](../phase3-plan.md) §4).

A town with no spawns adds only the fixed classes.

**Worked example.** The Byalan maps (iz_dun00/01) spawn 7 species between them (phase3-plan.md
§2's spawn table). A workflow that targets two of them still has a training scope of all 7.

### 13.4 Automatic preparation and its estimate

From a workflow, the editor derives a **preparation report** (offline: the linter's simulation
layer plus the catalogue).

| Item | Derived from | Open while |
|---|---|---|
| species to recognise | the training scope (13.3) | a species is not in the detector, or its per-species recall is not measured |
| UI windows | every block's L2 bindings (`L2.window.*`: storage, inventory, basic info, the death dialog, the NPC dialog and menu), for the active path | an anchor or template is missing for S2 or RDP (ADR-0011) |
| NPC dialogs | every NPC and option key on the workflow's path (L3), and its text match (L4) | a key does not resolve. Today every L4 binding is `unsupported` (section 12, "Today") |
| routes | entry → steps → exits on the walk graph | a leg is unreachable (13.5) |
| blocks | the badges (section 12) | a block is not verified for this environment (open question 1) |
| bindings | `resolve()` for every block | any `Unsupported`: the linter's READINESS items (section 5; ➡️ Batt 2026-10-09, contradictions #6) |

**The estimate of the AI preparation time.** The editor computes it with the planning formula of
[training-cost.md](../planning/training-cost.md). That document is the instrument: its constants
and their history live there, not here.

    new map time = map prep + Σ over the new species ( difficulty × (collect per species + train per species) ) × contingency

- **Compute hours and wall-clock hours are reported separately.** wall = compute / availability.
  Availability is MEASURED from the training duty-cycle logs (`state/train-duty`, the `duty_stats`
  lines; [r3-paired.md](../operations/r3-paired.md)), night and day apart.
- A standard per-species data budget (frames and instances) makes the cost linear in species.
- The difficulty multipliers: similar to a known species, normal, a large multi-form boss.
- A species already trained AND measured adds nothing to the sum. A new map still costs its map
  prep.
- The constants are ESTIMATES until measured on the first species addition after v1, then updated
  after every addition. The editor shows the constants' version, and the word ESTIMATE until then.

**Shown before a workflow can run.** An ILLUSTRATIVE panel; the symbols stand for the instrument's
values, not for numbers decided here:

```
┌ Prepare: farm_loop · lab-rathena / kro-20211103-prere / en / s2 ─────────────────┐
│ Species to recognise: 7 (targets 3, ignore 2, unlisted 2) · new: 3 (d1, d2, d2)  │
│ UI windows: storage (s2) MISSING · death dialog ok · basic info ok               │
│ NPC dialogs: the Kafra (save, storage), the relay NPC: L4 UNSUPPORTED            │
│ Routes: 4 legs, all reachable · Blocks: 2 verified, 5 unverified                 │
│ AI preparation (training-cost.md, constants ESTIMATE v<n>):                      │
│   compute ≈ <C> h · wall ≈ <W> h (availability: night <a_n>, day <a_d>)          │
│ [Run] disabled: 11 items open                                                    │
└──────────────────────────────────────────────────────────────────────────────────┘
```

- **Run stays disabled while any item is open** (proposal; open question 25).
  ➡️ **DECIDED for the bindings row (Batt 2026-10-09, contradictions #6):** an unsupported binding
  is a lint READINESS item, and the run-start check refuses while any is open (section 5). The
  other rows (species, windows, blocks) stay open question 25.
- **The editor never starts preparation work.** Collection sessions and training runs are operator
  steps on the existing paths (`scripts/guarded_build.py`, R1-R3, the clean-room and ASSIST rules).
  The report is their to-do list. The agent never self-authorises GPU work.

### 13.5 Linter rules for map workflows

Added to section 5's layers. The simulation layer already tracks the current map; it now also
tracks the save point. The messages are examples.

| Rule | Layer | Checks | Example message |
|---|---|---|---|
| save point | 3 · simulation | An `item_warp` (a Butterfly Wing) and every death go to the SAVE POINT, never to "the previous map". The save point cannot be read from pixels, so it is UNKNOWN at the start unless the workflow sets it (`set_save_point` at a Kafra) or `assumes` asserts it (an assertion stays a visible warning at approval). WARNING when a wing or a respawn relies on an unknown or different save point; the editor offers the fix block "set save point at Kafra" in the intended map's block ➡️ **Batt, 2026-10-08: an ERROR for every wing.** Each `item_warp` that goes to the save point needs, on every path before it, a `set_save_point` at the intended map's Kafra, or an `assert_save_point(map, cell)` block, which stays a visible warning at approval. A respawn relying on an unknown save point stays a WARNING (open question 20) | "farm.1: a Butterfly Wing returns to the save point, not to town, and nothing sets it on map_1. Add 'set save point' at town's Kafra?" |
| exit destinations | 2 · semantics | The destination map exists; the exit's L3 data leads there; its arrival cell lies in `to_entry`. `walk_exit`: an L3 warp (or edge) on this map. `npc_warp`: the NPC is on this map, every option key is in its menu at that point, the warp after them is known (else the destination is the author's: a warning, checked on arrival). `item_warp`: the map allows it (L3 map flags) | "relay.0: option o_5d0e of npc n_2b71 warps to map_4, not to farm's map_3" |
| NPC, menu, Kafra service | 2 · semantics | The NPC is on the block's map (L3 `npc.positions`); option keys are in `npc.menus`, never an index; the Kafra service (save, storage, teleport) is offered by that Kafra's type (`kafra.menus`); L1 preconditions are `assumes` or sensors (storage: Basic Skill 6 and the fee, `storage.deposit`, [phase4-ui.md](../phase4-ui.md)) | "town.1: npc n_k1 is not on map_1" |
| routes | 3 · simulation | Every entry reaches every walk target and exit on the walk graph (`poring_dataset/walk.py`, legs ≤ 128 steps; ➡️ the executor's planner, Batt 2026-10-09, contradictions #18: MW1's A* is cross-checked against it until the swap, open question 15). A leg that crosses another warp's cells would leave the map: ERROR | "town.3: the route from A to C crosses the warp at (156, 22): it would leave map_1" |
| weight thresholds | 3 · simulation | Explained with RO's rules (`vitals.read` in [knowledge/README.md](../knowledge/README.md)): at ≥ 50 % natural HP / SP regeneration stops; at ≥ 90 % attacks and skills stop. A threshold ≥ 90 % guarding an attack loop: ERROR (the loop stalls before it fires). 50-89 %: INFO (regeneration is already off). A weight condition in a block where nothing adds weight: WARNING. Today `loot` is unsupported (no ground-item class, 2.1), so nothing does (open question 21) | "farm.0: weight_percent() < 50 can change only by picking up items, and loot is unsupported here" |
| unbounded loops | 3 · loops | Every cycle of the workflow graph and every `while` has a stop condition (a counter, a sensor bound, `stop_when`) or the explicit `run_until_stopped`. `max_runtime_s` still bounds the run | "the cycle town → relay → farm → town never ends: add a stop condition or mark the workflow run until stopped" |
| species lists | 2 · semantics | Every TARGET and IGNORE species spawns on that block's map (L3 spawns); none is on both lists; unlisted spawned species are listed as IGNORE (INFO). An aggressive species on IGNORE: WARNING (it attacks; the bot never answers; the HP event decides). A target and an ignored species that look alike: WARNING until the detector's confusion between them is measured | "farm: mob 9104 is in no spawn line of map_3" |
| keep lists | 3 · simulation | A store-all or sell-all keeps every item that a later block or an event uses (the wings, the potions) | "town.2: storing everything also stores the Butterfly Wings that farm's exit uses: add them to the keep list" |
| graph | 2 · semantics | Every block is reachable from the start; every `take_exit` names an existing block and entry; every path of a main flow ends in `take_exit` or `stop`; a map with several blocks has exactly one `resume_here`. A death that lands on no block: WARNING (a death then stops the run) | "map_1 holds town and town_back: mark one resume_here" |
| readiness | 4 · approval | The preparation report (13.4). Not a lint error, but Run waits for it. ➡️ Unsupported bindings are the linter's own `readiness` severity (section 5; Batt 2026-10-09, contradictions #6): the run-start check refuses on them | "not runnable: 3 species untrained, 5 blocks unverified" |

### 13.6 Event flows and event scopes (Batt, 2026-10-08)

**Event flows** are separate `when <condition> do <flow>` blocks (EV3 / MakeCode style). They sit
OUTSIDE the main flow and run only when their condition occurs. Batt's examples: when dead →
respawn at the save point; when HP < 50 % → drink potions UNTIL HP > 80 %.

They ARE section 2.5's handlers, with these additions: scopes and the merge rule (13.6.1-2),
INSERT vs PRE-EMPT (13.6.4), the `until` stop threshold and run limits (13.6.7), and
`then: relocate` (13.6.6). Section 2.5's rules hold otherwise.
- **Conditions read pixels only:** the HP / SP / weight readouts, the death dialog, the map name (a
  map load on screen, then the client's `/where` line). Packets never drive them; runs are scored
  offline as DemoRecords (2.2).
- **Every step of an event flow is an action block,** with its L1 runtime outcome check and its
  outcome (2.2).
- New sensors (`map_load_seen()`, `sees(boss)` for a species) are L1 read concepts like any other
  (open question 7).

#### 13.6.1 Scopes

- **GLOBAL events** (the flow's `handlers`) apply on every map.
- **MAP events** (a map block's `events`) apply only while that block is current. Each map block
  has its own main flow AND its own event flows.
- An event's `name` is its KEY across scopes (`dead`, `hp_low`, …). A map event relates to the
  global event with the same key in one of three ways:
  - **OVERRIDE** (the default for a same-key map event: the more specific wins): the map's event
    replaces the global one on that map, all of it (trigger, thresholds, class, mode, limits,
    body);
  - **EXTEND:** both run, the map's steps FIRST. Trigger, thresholds, class and limits stay global;
    a limit may only be tightened;
  - **DISABLE:** the global event does not run on that map.
- A map event with a new key is **map-only** (ADDED).
- **The safety-critical set is FIXED,** in this design and in code, and never user-editable:
  **`dead`, `hp_critical` and `unexpected_map`.** `hp_critical` was added by Batt (2026-10-08,
  open question 29).
  - Every workflow has all three, globally (13.6.8). ➡️ **DECIDED 2026-10-09 (Batt,
    contradictions #15): EVERY flow, a workflow or a plain main flow, by construction**: the
    compiler adds the ones a flow does not write, and a flow may only make them stricter (13.6.8).
  - A map may only EXTEND them. A DISABLE or an OVERRIDE is a lint ERROR.
  - **Their extensions run AFTER the global body,** not first (confirmed by Batt, 2026-10-08): a dead character can do nothing
    before it respawns, and nothing may act on an unexpected map before the position is read. The
    extension runs before the global `then`, and is skipped if the global body ends the run.
  - **An extension may ADD bounded recovery steps** (e.g. close an NPC dialog left open on that
    map) and **TIGHTEN a limit** (e.g. stop at the first death on a dangerous map).
  - **It may not** change the trigger, the class, `then` or the global body, or loosen a limit. Its
    failure is logged and never changes the global outcome.
- The built-in guards (2.5 rule 1: the human lease, the interlock, lost perception,
  `max_runtime_s`) are not events. They sit outside every scope.

#### 13.6.2 The merge rule: a block's EFFECTIVE event set

For the current map block B, in this order:
1. Start from the global events, by key. ➡️ The always-on `dead`, `hp_critical` and
   `unexpected_map` are among them in every flow, written or added by the compiler (Batt
   2026-10-09, contradictions #15; 13.6.8).
2. Apply B's map events, at most one per key (two is an ERROR):
   - **DISABLE k:** k must be global and not safety-critical (else ERROR). Remove it.
   - **OVERRIDE k:** k must be global and not safety-critical (else ERROR). Replace it.
   - **EXTEND k:** k must be global. An ordinary k runs the map steps, then the global body. A
     safety-critical k runs the global body, then the map steps. Limits: the tighter of the two.
   - **ADD k:** k must not be global (else ERROR; the views turn a same-key map event into an
     OVERRIDE, so only a hand-written IR can hit this).
3. Order the result by class: guard > critical > survival > upkeep > the main flow. Inside
   `critical`, `dead` comes before `unexpected_map`. Other equal-class events queue (2.5 rule 4).
   ➡️ Inside a class, by RANK (Batt 2026-10-09, contradictions #13; 13.6.3): the safety-critical
   three lead `critical` in their fixed order, then the rank, then the declaration order for equal
   ranks.
4. **Ties are a lint ERROR:** two effective events of one class whose conditions can hold together
   on the same sensor.

- The effective set is DERIVED, never stored. The canonicaliser computes it from the IR, so the
  flow hash covers it.
- **The merged set is what the executor runs, and what the editor and the runtime display show**
  (13.7).
- The executor switches sets at a block change, between events, never inside one.

#### 13.6.3 Priorities

| Order | Event (key) | Class | Default mode | Trigger (pixels) |
|---|---|---|---|---|
| 0 | the built-in guards | guard | abort | 2.5 rule 1 |
| 1 | `dead` (safety-critical) | critical | pre-empt | the death dialog's anchor: `is_dead()` |
| 2 | `hp_critical` (safety-critical; Batt, 2026-10-08) | critical | pre-empt | `hp_percent() < 20`, rearmed above 50 %: an immediate ESCAPE (the fixed body in 13.6.8), then `relocate`. Its place above `unexpected_map` is a proposal (open question 30) |
| 3 | `unexpected_map` (safety-critical) | critical | pre-empt | a map load seen while no exit, respawn or relocating event runs (`map_load_seen()`: the loading screen, or the client's map-load notice, demonstrations.md §3.13); or an exit's arrival check reads another map |
| 4 | `unintended_engagement` (13.9; Batt, 2026-10-08) | survival | pre-empt | `engagement_seen()`: an engagement we did not order, from pixels (13.9). Its place is a proposal (open question 31) |
| 5 | `hp_low` | survival | INSERT | `hp_percent() < 50`, until `> 80` |
| 6 | `weight` | upkeep | pre-empt | `weight_percent() >= 90`: the backstop. The plan's own threshold sits in the map's main flow (farm's 50 %) |
| 7 | the main flow | – | – | – |

- So **dead > HP critical > (unexpected map) > unintended engagement > HP low > weight > the main flow.** `dead` and `unexpected_map` never
  compete: a respawn is an expected map change. Nor do `hp_critical` and `unexpected_map`: a Fly
  Wing keeps the map.
- These defaults hold on every map unless a map OVERRIDE changes a class. The linter WARNS on any
  change (13.6.9). The safety-critical rows cannot change.
- ➡️ **DECIDED 2026-10-09 (Batt, contradictions #13): an explicit RANK inside each class.**
  - Every event has a `rank` (IR 2; 1..99, a lower rank runs first). Left out, it is this table's
    order: `dead` 1, `hp_critical` 2, `unexpected_map` 3, `unintended_engagement` 4, `hp_low` 5,
    `weight` 6; any other key 50, after the table's events of its class.
  - So `unintended_engagement` runs before `hp_low` when both wait (stop the fight before
    drinking), whatever their arrival order. First in, first out only between events of equal
    rank.
  - The safety-critical ranks are fixed (writing another one is a lint ERROR, 13.6.9); they lead
    `critical` whatever a user event's rank.
  - The queue of the simulated executor follows it (`runtime.queue_key`), and so do waiting
    inserts; the effective sets (13.6.2) are listed in this order.

#### 13.6.4 INSERT or PRE-EMPT

| | INSERT | PRE-EMPT |
|---|---|---|
| for | a short action that changes neither the position, the target nor the windows: a potion by its hotbar key (`use_item` through `L2.shortcut.hotbar`) | everything else: a respawn, a wing, walking, a window, an NPC |
| when | at the main flow's next SAFE POINT: between two fast-loop ticks of the running block, never inside an `atomic` section (2.5 rule 5) | at once, between ticks. An atomic section ends first (bounded); a guard never waits |
| the running block | suspended, then it CONTINUES at its next tick on a fresh frame (`grab_after`). Not restarted, not `interrupted`; the log shows the insert | halted, outcome `interrupted`. Afterwards `then` decides (2.5 rule 7, plus `relocate`) |
| held input | ReleaseAll first if anything is held (normally nothing between ticks) | ReleaseAll always (2.5 rule 6) |
| bound | one insert ≤ 2 s (proposal); the typing-only foreground gate applies to its key | the event's own block timeouts |
| example | HP < 50 % → one potion per insert, until HP > 80 % | dead → respawn; weight ≥ 90 % → a Butterfly Wing |

- Only blocks the registry marks `insertable` may appear in an INSERT body (lint, 13.6.9).
  **Batt, 2026-10-08: `insertable` = `use_item` through the hotbar only.** No insert runs live
  before an alone-test (insert@1, pre-registered in demonstrations.md §3 before it runs) shows that
  a hotbar potion during an attack leaves the attack going (the server's act packets from the GM,
  offline) and during a walk leaves the walk going to the same destination (the accepted move,
  offline).
- **Escalation.** An insert whose L1 runtime check fails (`item.use`: the bar does not rise and the
  count does not drop, e.g. no potions left) counts toward `max_insert_fails`. Then its `escalate`
  procedure runs as a PRE-EMPT (e.g. a wing out, then `relocate`), or, without one, the run stops.

#### 13.6.5 One input path

- **Event flows are not separate agents.** ONE executor, with one `/internal/agent` connection and
  one agent id (`flow:<name>@<hash12>`, section 6), runs the main flow and every event flow.
- Every action from every flow is an `AgentInput` through the backend's `InputMux` (ADR-0002: one
  input writer). No event has a second path, a second connection or a direct Injector call.
- **The executor serialises with ONE input token.** At any instant exactly one flow owns it: the
  main flow between its ticks, an insert at a safe point, a pre-empt after the halt and its
  ReleaseAll. Batches from two flows never interleave (checked in the input log, MW1 and MW2-live).
- The mux's own checks apply to every batch unchanged: the lease, the interlock, the foreground
  gate, the frame-age guard. A refused event input is never retried fast (section 6). A human
  takeover pauses everything; a red interlock stops everything (the guards).
- The run progress messages (section 6) name the event and its node path, so the run log and the
  input log line up by time.

#### 13.6.6 After a pre-empt: resume where the character IS (`then: relocate`; confirmed by Batt, 2026-10-08)

1. **Read where the character is, from pixels:** `current_map()` and `position()` through the
   client's own `/where` line ([demonstrations.md](../demonstrations.md) §3.15, where@2 on RDP:
   indoor 48 / 50, outdoor 50 / 50, 0 wrong). It is an ACTIVE read: it types, through the mux and
   the foreground gate. So it runs in or after an event body, never in an event condition.
2. **Pick the map block whose map is the actual map:** the entry that contains the cell, or an
   `anywhere` entry. When several blocks share the map, the one marked `resume_here` (lint:
   exactly one).
3. **Run that block's main flow from its first step.** The first step re-plans from the actual cell
   (a walk re-routes, an attack re-selects). Not from the workflow's start, and not the halted
   block. Variables and loop counters keep their values.
4. **No matching block, or no readable position after a bounded retry: STOP safely.** Release
   everything, end the run with `relocate_no_block`, report the map and the cell.

Batt's loop runs through this rule: farm's wing → the save point on map_1 → `town`.

#### 13.6.7 Hysteresis, cooldowns and limits

- **Two thresholds, no flapping.** `when` starts the event; `until` stops it. The body repeats while
  the event is on (paced by `cooldown_s` and `max_per_min`). The event re-arms only after `until`
  has held. One-shot events keep 2.5's `rearm`.
- **`cooldown_s`:** the minimum gap between two runs of the body (e.g. a potion, then the bar's
  update).
- **`max_per_min`:** a rate cap; extra runs wait (e.g. at most 6 potions a minute).
- **`max_fires_per_10min`:** the runaway bound. Reached while `until` never held, the run STOPS
  (`handler_runaway`, 2.5 rule 8). **An event that keeps re-firing is a stop condition, never a
  loop.**
- **`max_per_run`:** a hard count. `dead` defaults to 1: the first death respawns and relocates, the
  second stops the workflow (`death_limit`; open question 19).

#### 13.6.8 The always-on set, and the scope examples

Every new workflow starts with six GLOBAL events:
- `dead`, `hp_critical` and `unexpected_map`: safety-critical and required (removing any of them is
  a lint ERROR);
  ➡️ **DECIDED 2026-10-09 (Batt, contradictions #15): ALWAYS ON BY CONSTRUCTION, in every flow.**
  - The compiler adds `dead`, `hp_critical` and `unexpected_map` to EVERY flow, a workflow or a
    plain main flow, as global events (`poring_flow.always_on`). Their definitions are this
    section's global events, fixed in code: `dead` respawn, 1 per run, relocate; `hp_critical`
    below 20 % the fixed escape, re-armed above 50 %, at most 2 a minute, relocate;
    `unexpected_map` read the position, relocate.
  - They are derived like the effective set, not written into the IR: a flow that leaves one out
    keeps its own hash and runs the built-in. Leaving one out is no longer an error.
  - A flow that writes one may only make it STRICTER. The lint check is "not weakened" (13.6.9):
    the class (critical) and mode (pre-empt) stay; `then` is relocate or stop; the trigger fires no
    later (e.g. `hp_percent() < 30` for `hp_critical`); the re-arm stays the built-in's; the limits
    (`max_per_run`, `max_per_min`, `max_fires_per_10min`, `cooldown_s`) are no looser; the body
    starts with the built-in step (`hp_critical`'s body is exactly the escape). Anything else is an
    ERROR at the event's node path.
  - The canvas shows them as LOCKED rows on the global events node: "BUILT-IN, always on,
    read-only" when the flow does not write them, "stricter only" when it does.
  - Their bindings are checked even when the flow does not write them (a death needs the death
    dialog bound), so they appear among the readiness items (section 5).
  - A consequence for open question 19: `dead`'s 1 per run is now a CEILING a flow cannot raise,
    not only a default. The MW2-editor sample said 3; it now says 1.
- `unintended_engagement`, `hp_low` and `weight`: defaults, editable per map (13.9 for the first).

Map events then shape them per map. The effective sets of Batt's example (farm is taken to be a
dungeon):

| Event (key) | Global | town (map_1) | relay (map_2) | farm (map_3) |
|---|---|---|---|---|
| `dead` · critical · safety | respawn; 1 per run; relocate | global | global | global |
| `hp_critical` · critical · safety | < 20 % → ESCAPE: a Fly Wing where the map allows it, else a Butterfly Wing, else stop; rearm > 50 %; relocate | global | global | global |
| `unexpected_map` · critical · safety | read the position; relocate or stop | global | EXTENDED: + close an open dialog, after the global body | global |
| `unintended_engagement` · survival · pre-empt | walk away; close an unintended NPC dialog (13.9) | global | global | OVERRIDDEN by species: a passive weak species → finish it; a dangerous or chasing one → a wing; relocate |
| `hp_low` · survival · insert | < 50 % → potions until > 80 %, ≤ 6 a minute | DISABLED: a safe town, no potions spent | global | OVERRIDDEN: < 70 % → until > 90 % |
| `weight` · upkeep · pre-empt | ≥ 90 % → a wing; relocate | DISABLED: town is where the weight is stored; a wing there would loop to the save point | global | global |
| `boss_seen` · survival · pre-empt | – | – | – | ADDED: `sees(boss)` → a wing; relocate |

- **`hp_critical`'s body is FIXED** (it is safety-critical): ESCAPE with the first item the map's
  L3 flags allow. A Fly Wing is a random teleport within the map; a Butterfly Wing goes to the save
  point. Otherwise it releases everything and stops the run. rAthena's map flags `noteleport` and
  `noreturn` restrict the two wings; the exact flags are read from the map sheet once its
  extraction lands (13.2, open question 27). The linter shows which escape applies on each map,
  and flags a map with none (open question 30). A Fly Wing keeps the map, so `relocate` resumes
  the same block from its first step.
- **`boss_seen` needs the detector to recognise that boss species.** It joins the workflow's
  training scope (13.3), and the linter checks that it spawns on map_3 (L3).
- **The town disables the combat events** (`hp_low`, `weight`), and no others. A town that tries to
  DISABLE `dead` gets an ERROR (13.6.9).

**The example in the Python view.** Ids, keys and cells are illustrative placeholders. The views
add `map_block(...)` and `extend(...)` decorators and `disable(...)` calls to 7.2's allow-list; a
same-key `on(...)` with `overrides=` is an OVERRIDE.

```python
flow(
    ir=1,
    name="farm_loop",
    max_runtime_s=14400,
    run_until_stopped=True,
    start=entry("town", "A"),
    target=target(client="kro-20211103-prere", server="lab-rathena", locale="en", path=S2),
)

WING = item(9002)  # every id, key and cell below is an illustrative placeholder
POTION = item(9001)
BOSS = mob(9109)


@map_block(map_id("map_1"), entries=[entry_at("A", cell("map_1", 150, 180))])
def town():
    walk_to(cell("map_1", 146, 92))  # B, beside the Kafra
    set_save_point(npc("n_k1"))  # the fix the linter offers (13.5)
    kafra_store(npc("n_k1"), all_except=[WING, POTION])  # all, keeping what later maps use
    take_exit(walk_exit(cell("map_1", 150, 20), to=entry("relay", "south")))  # C


@map_block(map_id("map_2"), entries=[entry_at("south", cell("map_2", 40, 300))])
def relay():
    take_exit(npc_warp(npc("n_2b71"), [option("o_5d0e")], to=entry("farm", "arrival")))


@map_block(
    map_id("map_3"),
    entries=[entry_at("arrival", cell("map_3", 100, 100))],
    targets=[mob(9101), mob(9102), mob(9103)],
    ignore=[mob(9105), mob(9106)],
)
def farm():
    while weight_percent() < 50:
        attack_nearest(within=12)
    take_exit(item_warp(WING, to=entry("town", "A")))


# GLOBAL events: every map
@on(is_dead(), priority=CRITICAL, max_per_run=1, then=RELOCATE)
def dead():
    respawn()


@on(hp_percent() < 20, rearm=hp_percent() > 50, priority=CRITICAL, then=RELOCATE, max_per_min=2)
def hp_critical():
    escape()  # fixed body: Fly Wing where allowed, else Butterfly Wing, else stop (13.6.8)


@on(map_load_seen(), priority=CRITICAL, then=RELOCATE)
def unexpected_map():
    read_position()


@on(hp_percent() < 50, until=hp_percent() > 80, priority=SURVIVAL, mode=INSERT, max_per_min=6)
def hp_low():
    use_item(POTION)


@on(weight_percent() >= 90, rearm=weight_percent() < 50, priority=UPKEEP, then=RELOCATE)
def weight():
    use_item(WING)


@on(engagement_seen(), priority=SURVIVAL, then=RELOCATE, max_per_min=4)
def unintended_engagement():  # 13.9: the global default
    close_npc_dialog()  # if one opened
    walk_away(min_cells=5)  # NOT yet proven to stop an attack (13.9, open question 32)


# MAP events
disable(hp_low, scope=town)  # a safe town: no potions spent
disable(weight, scope=town)  # town is where the weight is stored


@extend(unexpected_map, scope=relay)
def relay_recover():
    close_dialog()  # safety-critical: runs AFTER the global body


@on(
    hp_percent() < 70,
    until=hp_percent() > 90,
    priority=SURVIVAL,
    mode=INSERT,
    max_per_min=6,
    overrides=hp_low,
    scope=farm,
)
def farm_hp_low():
    use_item(POTION)


@on(
    sees(BOSS, within=15),
    rearm=not sees(BOSS, within=15),
    priority=SURVIVAL,
    then=RELOCATE,
    scope=farm,
)
def boss_seen():  # BOSS joins the training scope (13.3)
    use_item(WING)


@on(
    engagement_seen(),
    priority=SURVIVAL,
    then=RELOCATE,
    max_per_min=4,
    overrides=unintended_engagement,
    scope=farm,
)
def farm_engagement():  # by species (13.9); the policies are suggested from L3 mob data
    if engaged_species() in (mob(9101), mob(9102)):  # passive and weak: finish it
        finish_target()
    else:  # dangerous, chasing, or not recognised: leave
        use_item(WING)
```

#### 13.6.9 Lint rules for events

They extend section 5's "3 · events" row. Where they are stricter (a same-sensor tie is an ERROR,
not a warning), they win.

| Rule | Severity and check | Example message |
|---|---|---|
| hysteresis pair (`until` or `rearm`) | ERROR unless the stop threshold lies BEYOND the start threshold, on the far side: `hp < 50` with `until hp > 80` is valid; `until hp > 40` is INVERTED (both hold between 40 and 50, so the event flaps). ERROR when the stop can never hold (`hp > 100`). WARNING when the band is narrower than the readout's resolution | "hp_low: until hp_percent() > 40 overlaps when hp_percent() < 50: the stop threshold must exceed 50" |
| same direction | ERROR: start and stop compare the same way, so the stop never ends the event (`weight >= 90` until `weight > 95`) | "weight: until weight_percent() > 95 does not end weight_percent() >= 90: the stop must lie below 90" |
| ties | ERROR: two effective events of one class on overlapping conditions of the same sensor (13.6.2 step 4). WARNING for different sensors (they queue, 2.5 rule 4). ➡️ **DECIDED 2026-10-09 (Batt, contradictions #14, after #13's rank):** a tie needs the same class AND the same RANK. Same rank: the ERROR (the same sensor, overlapping) and the WARNING (different sensors: they queue first in, first out) stand. Different ranks: the order is decided, so only an INFO says which runs first. Batt's 13.6.8 example's four tie WARNINGs (`unintended_engagement` / `hp_low` globally and on farm, `hp_low` / `boss_seen`, `unintended_engagement` / `boss_seen`) are INFOs now | "farm: hp_low and hp_panic are both survival on hp_percent() < 30" ➡️ "farm: hp_low and hp_panic are both survival at rank 5 on hp_percent() < 30"; info: "farm: unintended_engagement and hp_low are both survival: unintended_engagement runs first when both are due (rank 4 before 5)" |
| safety-critical | ERROR: a DISABLE or OVERRIDE of `dead`, `hp_critical` or `unexpected_map`; ~~any of them missing from the global set~~ ➡️ **not weakened** (Batt 2026-10-09, contradictions #15: the compiler adds a missing one, 13.6.8): a written one weaker than the built-in in class, mode, `then`, trigger, re-arm, limits or body, or with a rank other than its fixed one (#13, 13.6.3); an extension that tries to loosen a limit | "town: dead is safety-critical: it can be extended, never disabled"; "dead: dead is safety-critical: max_per_run 3 loosens the built-in 1: it may only be tightened" |
| scope | ERROR: an OVERRIDE, EXTEND or DISABLE of a key that is not global; an ADD of a key that is; two map events on one key | "relay: extend weight_low: there is no global event weight_low" |
| class change | WARNING on any map OVERRIDE that changes a class | "farm: hp_low moved from survival to upkeep: weight no longer waits for it" |
| looser on a harder map | WARNING, acknowledged at approval: a map OVERRIDE that fires later, stops earlier or allows more (a lower HP start or stop, a higher weight, a higher death count, a longer cooldown) on a HARDER map. **A map is HARDER, from its L3 sheet, when** it spawns an aggressive species (mob_db `ai`), it has a boss spawn line, or its highest spawn level exceeds the character's base level (from `assumes`; skipped, and said so, when unknown) | "farm: hp_low < 30 is looser than the global < 50, and map_3 spawns an aggressive species (mob 9105)" |
| insert body | ERROR: a block not marked `insertable` inside an INSERT event | "hp_low: walk_to cannot be inserted: make the event pre-empt" |
| relocating events | ERROR: an event whose body can change the map (a wing, a respawn) without `then: relocate` or `stop` | "boss_seen: a Butterfly Wing changes the map: then must be relocate or stop" |
| engagement policy (13.9) | WARNING: a map's `unintended_engagement` override that FINISHES a species the L3 mob data marks aggressive, chasing or above our level; a species policy while the detector cannot name species (the run uses the map's most cautious policy instead); a policy that is a mob-data suggestion nobody confirmed | "farm: finish_target for mob 9103: it chases (L3 mob data)" |
| species named by events | WARNING: a `sees(mob)` species that spawns on none of the event's maps. It joins the training scope either way | "boss_seen: mob 9109 is in no spawn line of map_3" |

### 13.7 The runtime display

- **The workflow canvas is the map graph:** map blocks as nodes, exits as edges by type (walk, NPC,
  item, death). The current block is highlighted, and inside it the current step, as in section 6.
- **The current block's EFFECTIVE event set** (13.6.2): each event with its source (global or map)
  and its state (inherited, OVERRIDDEN, EXTENDED, DISABLED, ADDED); the running event (insert or
  pre-empt), its cooldown, and the limits left (deaths 0 / 1, potions this minute). The editor
  shows the same merged view for every block before the run.
- **Per-map progress:** visits, time in the map, loops completed, kills per TARGET species (the
  bot's own L1 runtime checks: pixels), exits taken by type, relocations with their reason, the
  weight trend.
- **The live route preview** (`RouteCanvas.tsx`, `scripts/route_preview.py`, f7cac8e) shows the
  current block's walk legs.
- These counts are the executor's own pixel judgements. Packet-verified counts appear only after the
  offline scoring (DemoRecords, 2.2), labelled as such.
- New progress messages (block entered or left, exit taken, event fired, relocation) are Pydantic
  models in `protocol.py`, regenerated with `scripts/gen_protocol.sh` and read through
  `routes_public.read_message`.

### 13.8 Phased plan for map workflows

Aligned with F1-F2 (section 12). Each phase ends with its acceptance criteria met and reported.

**MW0 · Decide.** Batt accepts or amends this section and answers its FIRST questions (16-18, 29).
➡️ The FIRST questions were answered on 2026-10-08 (16, 17, 18, 29; also 20, 21 and part of 27).
The section itself stays PROPOSED until Batt accepts it.

**MW1 · Offline, with F1 (no UI, no input).**
- The IR additions (map blocks, entries, typed exits, target / ignore lists, event scopes, `until`,
  insert / pre-empt, `relocate`, the limits) and their lint rules (13.5, 13.6.9); the merge rule
  (13.6.2); the tree compiler (the block selector, the insert gate, relocation).
- The map-sheet generator (local, never committed): the extended L3 extraction Batt approved on
  2026-10-08 (NPC warp targets per option, the Kafra save cell, map flags). Then the preparation
  report, and the estimator, reading training-cost.md's constants.
- The new L1 concepts, written unverified: `set_save_point`, `assert_save_point`, the
  `hp_critical` escape, and `loot.pick_up` by a hover-scan.
- Acceptance:
  - one fixture per lint rule, with its exact message (committed fixtures hold synthetic map data
    only);
  - Batt's example as a synthetic fixture lints with exactly the expected findings, and its
    effective sets equal 13.6.8's table;
  - the valid and invalid hysteresis pairs;
  - insert, pre-empt, escalation and relocation table-tested against a scripted sensor timeline and
    a fake clock, asserting the emitted `AgentInput` sequence: ReleaseAll before every pre-empt;
    inserts only between ticks; no batches of two flows interleaved;
  - the estimator equals a hand computation;
  - the Byalan fixture's training scope is all 7 species.

**MW2-live · One map block and its exits, live** (after F2; lab-rathena, ASSIST, Batt present). Named
"MW2" until 2026-10-09.
➡️ 2026-10-08: not the EDITOR plan [mw2-block-editor.md](../planning/mw2-block-editor.md), which is
also called "MW2" (its skeleton is built on branch `feat/mw2-editor`, SIMULATE only, no live run).
The naming is parked for Batt. ➡️ **DECIDED by Batt 2026-10-09: this phase is MW2-live; the
editor plan is MW2-editor** (mw2-block-editor.md section 0).
- Prerequisites: `walk_to` under walk@11's safety bar, `take_warp` and the position read verified
  alone.
- Alone-tests before their blocks run in a flow, each pre-registered:
  - insert@1: a hotbar potion during an attack and during a walk (13.6.4);
  - save@1: `set_save_point` at a Kafra, then a Butterfly Wing arrives at its cell;
  - escape@1: the `hp_critical` escape (a Fly Wing) proven by a staged low-HP positive case;
  - loot@1: the hover-scan pickup, with the weight readout rising;
  - rec@1: recovery from DELIBERATE engagements, scored on its own (13.9), never inside a walk run's score.
- One block: entry → walk → `walk_exit`, the arrival confirmed by `/where`. Then `npc_warp` and
  `item_warp`, each alone.
- `unexpected_map` and `dead` proven by a DELIBERATE positive case each (a staged warp and a staged
  death, made by the harness). A zero from a sensor that never saw the event is not evidence
  (demonstrations.md §2a).
- Acceptance: N runs pre-registered in demonstrations.md §3; every arrival confirmed; walk@11's
  safety signals at zero (attack requests, NPC contacts, the GM's act of kinds normal and pickup);
  no event batch interleaved with a main-flow batch.

**MW3 · Batt's example end to end.**
- Every block verified alone first. The farm's whole training scope trained and measured per
  species.
- TARGET / IGNORE proven by a deliberate positive case: an ignored species beside a target, zero
  acts on it (the server's act packets, offline).
- N loops in ASSIST, with every event, relocation and exit logged.

**MW4 · Users add workflows.** Each new map or species goes through the preparation report.
training-cost.md's history table is updated after every species addition (that document's own
rule).

### 13.9 Defence in depth for walking (Batt, 2026-10-08)

Three layers. Each is measured on its own, so one never hides the failure of another.

| layer | what | how it is measured |
|---|---|---|
| 1 · PREVENT | the existing gates: the picking model, the cursor gate (two reads, fail closed), walk@11's unit gate with memory (demonstrations.md §3.18) | the walk rules' ZERO-TOLERANCE bar, unchanged. An engagement during a walk run is a HARD FAIL even when layer 3 recovered from it: the live packet signals count it either way |
| 2 · DETECT | an unintended engagement, from PIXELS only (rule 1) | its own pre-registered test (rec@1), with packets as the OFFLINE ground truth for recall and latency |
| 3 · RECOVER | the `unintended_engagement` event (13.6): a global default, overridden per map and by species | the same test: did the bot apply the map's rule, and did the outcome follow |

**2 · DETECT: the pixel cues.** Each is a new L1 read concept, written unverified and proven by a
DELIBERATE positive case (demonstrations.md §2a: a zero from a sensor that cannot see the event is
not evidence):
- damage numbers rising from a unit near our character;
- our own attack animation;
- our HP dropping (`vitals.read`, against its regeneration noise);
- an NPC dialog window opening (its anchor, L2).

`engagement_seen()` is true when any cue fires while the running block ordered no attack and no
talk. The live packets (`attack_request`, `npc_contact`, the GM's `act`) never feed it: they score
it offline.

**3 · RECOVER: the event flow** (13.6 scopes apply):
- **Global default:** walk away, and close any unintended NPC dialog.
  - ⚠️ **"A walk click cancels an attack" is NOT confirmed here.** walk@11's cancel test
    (demonstrations.md §3.18 point 3: a static Red Plant, n = 3) clicked a walk point 2 cells away
    right after the attack click. The client re-requested the attack after the walk, and hits
    continued 3 / 3.
  - Untested: a walk beyond the target's reach, a key, closing the target's window. rec@0 measures
    which one stops an attack before rec@1 fixes the default (open question 32).
  - ➡️ **Batt, 2026-10-08:** the premise was his assumption, never measured on our client. Keep
    "walk away" with this caveat. **rec@0 is PRE-REGISTERED** (demonstrations.md §3.19):
    - the conditions: no cancel (the positive control), a walk 2 cells away, a walk of ≥ 6 cells,
      sit/stand, and a Fly Wing;
    - n = 10 each; the bar is 9 / 10 with the control proven.
- **Map override, by species** (Batt's example, the farm map):
  - a passive, weak species (e.g. Poring, Lunatic) → finish it;
  - a dangerous or chasing species → a Butterfly Wing or a Fly Wing.
- **Default policies are SUGGESTED from the L3 mob data** (rAthena's mob_db: `ai` / mode flags for
  aggressive and chasing, the level against ours). Proposal:
  - passive and not above our level → finish;
  - aggressive, chasing, or above our level → a wing (a Fly Wing where the map allows it);
  - immobile → walk out of its range.
  - A suggestion is shown in the preparation report (13.4) and runs only after the owner confirms
    it.
- **Species knowledge:** today's detector names player, monster and npc, not the species.
  - A species policy needs species recognition: per-species classes from the training scope
    (13.3), or a sprite match.
  - Until then, the map's override runs its MOST CAUTIOUS policy for every engagement (here: the
    wing), and the linter says so (13.6.9). Open question 33.

**Testing stays separated** (Batt):
- The walk rules keep the zero-tolerance bar, which measures PREVENTION.
- Recovery is tested alone, pre-registered: rec@0 (which cancel works), then rec@1.
  - rec@1 stages DELIBERATE engagements: a click on a monster of each policy class, and a click on
    an NPC.
  - Detection is scored on recall and latency, against the packets.
  - The rule is scored on whether the map's policy was applied, and whether its outcome followed:
    the attack stopped, the target finished, the wing taken, or the dialog closed.

## Open questions

**➡️ The 19 contradictions MW1 found** (each built one provisional way), with a recommended
resolution per item: [docs/planning/adr0020-contradictions.md](../planning/adr0020-contradictions.md).
They await Batt's decision (2026-10-08); this ADR is unchanged until he decides.
➡️ **2026-10-09: Batt decided 5 of them, each as recommended: #6, #15, #13, #14, #18** (his order).
Each is recorded where the ADR said otherwise, with a "DECIDED 2026-10-09 (Batt, contradictions
#N)" marker (sections 1, 2.5, 5, 6, 12, 13.4, 13.5, 13.6.1-13.6.3, 13.6.8, 13.6.9; open question
15 closed). The other 14 still await him.

Marked FIRST: needed before F1 or F2.

1. **FIRST · Unverified blocks at run time.** Proposal: a run is refused unless every action
   block's L1 concept is `verified` (both paths passed) for the active client, server and locale.
   Should ASSIST allow a supervised trial of unverified-but-supported blocks on lab-rathena, every
   attempt logged for offline verification? Or should a single-path pass suffice for a run on that
   path?
2. **FIRST · Executor placement.** Proposal: `vision` (S2 only), with RDP execution kept for the
   host-side alone-test runner. Confirm, or name another home.
3. **FIRST · Session blocks.** Login, character select and logout need operator windows, which only
   host tools can open. Stay excluded (flows start in game), or design how a flow asks the owner
   for a window?
4. **FIRST · After a human takeover.** Proposal: the run pauses and the owner resumes it. Or
   resume automatically after a quiet period (how long)?
5. **FIRST · Where approved flows live.** Proposal: the human-only `settings/` store (backend only).
6. **L1 parameter types.** Proposal: a separate block registry with the coverage test, L1's schema
   unchanged. The alternative: typed parameters in L1 itself.
7. **New L1 read concepts** for the sensors (levels, item count, death, dialog state, sees): agree
   that they go through L1 and the alone-test like any concept.
8. **`max_runtime_s`'s bound and default**, and when long runs are allowed: ADR-0002 notes the
   input log grows ~1 GB/day and needs rotation before long unattended runs.
9. **The UI reset before a handler** (2.5 rule 9): which windows and dialogs it may close, and how
   it is verified.
10. **How the console reaches the host-side LLM drafter** without any lab container joining
    Ollama's network (ADR-0005 isolation): a host job picking up requests, or another route.
11. **Committing L3-derived keys.** ADR-0012 allowed one-way message keys from the client table.
    Are keys derived from GPL server scripts (NPC and option keys) committable in shared flows, or
    do filled flows always stay under `data/`? Proposal: they stay under `data/` until Batt rules.
    ➡️ **DECIDED by Batt 2026-10-09 (with MW2-editor's parked items): the proposal.** L3-derived
    NPC and option keys, and every filled flow that holds them, stay LOCAL under `data/` and are
    never committed; committed flows and fixtures hold synthetic keys only. The PROVISIONAL scheme
    of `poring_flow/kbsheet.py` (`n_` / `o_` + 8 hex digits of sha256) stays as built: no derived
    key is ever committed, so a later change only re-resolves local flows (section 4's re-pick).
12. **Comments in the Python view**: carry them (tokenize) or drop them.
13. **JavaScript import**: never, or later with a parser whose licence is checked first.
14. **Blockly's CSP fit** (section 9): only measurable on the pinned version; the fallback is our
    own editor.
15. **FIRST · Where the linter runs** (added at review, 2026-10-07). Layer 3 uses the walk graph
    (`poring_dataset/walk.py`), and section 5 re-runs the linter at run start. `vision` may never
    get the dataset package (ADR-0010; `test_guards.py`
    `test_vision_and_poring_env_never_get_the_dataset_package`). So either the linter runs host- or
    backend-side and hands `vision` an approved, re-linted IR, or the walk graph moves to a package
    `vision` may import (it is our own clean A*, but it lives beside the label code). Decide before
    F1.
    ➡️ **2026-10-09, Batt's second #18 decision: one shared package (`poring_nav`); the plan
    `docs/planning/poring-nav.md` awaits his approval (section 5 has the summary).**
    ➡️ **CLOSED 2026-10-09 (Batt, contradictions #18):** "the linter runs in the backend at run
    time (L3 local), and routes with the EXECUTOR's planner (`poring_dataset.walk.walk_path`, the
    client's own path rules), not MW1's small A*. Until then, a cross-check test on the sheet
    maps."
    - **Where it runs:** the backend. It already lints there for the editor (`/flows/lint`), and
      the run-start check (`poring_flow.runstart`, section 5) is where a live run re-lints; the
      backend hands `vision` an approved, re-linted IR (MW3).
    - **The swap WAITS**, because the dependency rules do not allow it yet and it is not small:
      1. `poring_flow` may not import `poring_dataset` (`test_guards.py`: vision imports
         `poring_flow`, and vision never gets the dataset package, ADR-0010);
      2. the backend has no `poring_dataset` either (its image copies only the pyproject; dev mode
         mounts `poring_flow` and `poring_skills` only; the package brings PyAV);
      3. the executor itself (MW3, in `vision`) needs the same planner, so `walk_path` (our own
         clean A*, stdlib only) has to MOVE first to a package the backend and `vision` may both
         import. The walk rules in `scripts/` import it from `poring_dataset` today. That move is
         a code change with its own review, and where it lands is a choice for Batt.
    - **Until then, the cross-check:** `packages/poring_dataset/tests/test_walk_matches_flow_planner.py`.
      For sampled pairs of walkable cells, MW1's `Walk.route` and `walk_path` (unbounded) must
      agree on reachability, on the path cost exactly (both are shortest under one cost model:
      10 straight, 14 diagonal, no corner cutting) and on the step count within 2 (equally cheap
      paths can trade 7 straight steps for 5 diagonal ones); both paths must be legal walks.
      Committed: the MW2-editor sample's two sheets (150 pairs each) and four seeded mazes (120
      pairs each, with unreachable pockets): no disagreement. A deliberately corner-cutting
      planner is caught (the positive case). Local only (client data, never committed), with
      `PORING_FLOW_CROSSCHECK_GAT=data/gat`: 240 sampled legs (40 per map, targets within 60 cells) on alberta, alberta_in, iz_dun00, prontera, prt_church and prt_fild08 (2026-10-09 10:16): 206 reachable, 34 unreachable, 0 disagreements, the same cost and the same step count on every reachable leg; the two GAT readers (kbsheet.read_gat, the linter's; poring_dataset.gat, the executor's) see identical walkable cells on all six maps. 75 of the 240 legs are longer than the executor's one-plan limit (below); one plan refuses all 75.
    - **A difference it found, recorded and not hidden:** the executor plans ONE walk of at most
      48 steps (`PLAN_MAX`, scripts/walk5.py), and MW1's linter routes a leg of any length. A
      longer leg is either refused by one plan (it needs waypoints: section 5 says legs ≤ 128
      steps, waypoints beyond, which MW1 does not model), or, where a walk of at most 48 steps
      exists, the plan takes a DEARER route than the one the linter checked (seen on a seeded
      maze, asserted in the test). The swap has to bring the executor's leg limit into the
      linter with the planner.

**Added with section 13 (map-centric workflows and event flows, Batt, 2026-10-08).** FIRST here
means needed before MW1.

16. **FIRST · Map blocks in IR 1?** Proposal: yes. Nothing is built, so no converter is needed. A
    plain `main` flow stays valid for small flows and the course's first steps.
    ➡️ **ANSWERED (Batt, 2026-10-08): yes, map blocks are in IR 1.**
17. **FIRST · INSERT mode (13.6.4).** Which blocks are `insertable` (proposal: `use_item` through
    the hotbar only), and the bound (proposal: ≤ 2 s). Does a hotbar potion during an attack or a
    walk really leave it undisturbed? An alone-test decides before any insert runs live.
    ➡️ **ANSWERED (Batt, 2026-10-08): insertable = hotbar `use_item` only, as proposed.** The
    alone-test (insert@1) must show that a potion during an attack and during a walk disturbs
    neither (13.6.4). The ≤ 2 s bound stays a proposal until insert@1 measures it.
18. **FIRST · Relocation (13.6.6).** Resume only through a matching entry or an `anywhere` entry,
    with `resume_here` for a shared map (proposal)? Or always stop after a pre-empt that changed
    the map?
    ➡️ **ANSWERED (Batt, 2026-10-08):** resume at the matching map block when the actual map is
    known and has a block. On any unknown map, stop safely through the `unexpected_map` event.
    This is 13.6.6 as written.
19. **The death limit.** `dead` defaults to `max_per_run` 1: the second death stops the workflow
    (proposal). Another default? Deaths cost EXP (L1 `char.respawn`).
20. **The save point (13.5)** cannot be read from pixels. Is Batt's WARNING enough, or should a
    BOT-mode run need an ERROR unless the workflow sets the save point itself?
    ➡️ **ANSWERED for wings (Batt, 2026-10-08):** add `set_save_point` (at a Kafra) and an
    `assert_save_point` block. The linter REQUIRES one of them before any wing use (an ERROR, 13.5).
    A respawn relying on an unknown save point stays a WARNING: open.
21. **Loot and weight.** `loot` is unsupported (no ground-item class), so nothing in Batt's farm adds
    weight, and its weight exit cannot fire. Add a ground-item class (it would join the training
    scope), or another plan? Batt decides.
    ➡️ **ANSWERED (Batt, 2026-10-08): loot WITHOUT new training.**
    1. The tracker knows where a monster died.
    2. Hover-scan the cells around that cell for the PICKUP cursor (references calibrated
       2026-10-07, demonstrations.md).
    3. Click it, and verify by the weight readout rising (`vitals.read`).
    - A ground-item detector class is a later improvement.
    - The plan's dependencies:
      - the tracker reporting a death cell from pixels (Phase 3 T1, not built);
      - every scan click passing the cursor gate with PICKUP as its only allowed shape, and the
        unit gate (walk@11), so a scan never clicks a monster or an NPC;
      - the weight readout visible (the basic info window).
    - `loot.pick_up` is written unverified and proven alone (loot@1) before it runs in a flow.
      ➡️ loot@1 is PRE-REGISTERED (demonstrations.md §3.20, after rec@0).
      - Its prerequisites: a weight-readout reader, the item-on-floor and pickup-result decoders
        (offline only), and a death-cell stand-in for the tracker.
      - 20 drop trials; the bar is 19 / 20, with zero-tolerance safety in the loot phase.
22. **The training scope beyond spawns (13.3).** Metamorphosis is covered (`classes.json`). Summoned
    slaves (mob skills)? The maps a route only crosses (proposal: in scope)? ➡️ That part waits
    for a later IR version (after IR 2): in IR 1 and IR 2 a route crosses no maps (Batt 2026-10-09,
    contradictions #19; 13.3).
23. **Unlisted species:** treated as IGNORE (proposal), or must the owner place every spawned
    species on a list?
24. **An aggressive species on IGNORE** attacks us: never answer (proposal; the HP events decide),
    or a separate "defend" option?
25. **Readiness (13.4).** Run disabled until every preparation item is closed (proposal)? May an
    ASSIST run go ahead with an untrained IGNORE species? Proposal: no, the unit gate needs its
    recall.
26. **Where the estimator's constants live,** so the editor and docs/planning/training-cost.md
    cannot drift. Proposal: one machine-readable source the editor reads, with its history in the
    doc.
27. **Map sheets (13.2):** generated on demand for the maps a workflow names (proposal), or for the
    whole server at KB build? The NPC warp targets, the Kafra save cell and the map flags are not
    extracted yet (`scripts/kb_bindings.py`).
    ➡️ **PARTLY ANSWERED (Batt, 2026-10-08): extend the L3 extraction for per-map sheets.** The
    new outputs are the NPC warp targets per menu option, the Kafra save cell and the map flags.
    They are generated locally from the pinned rAthena and never committed. On demand vs the
    whole server stays open.
28. **The unexpected-map cue:** which passive signal (the loading screen, or the client's map-load
    notice in chat, demonstrations.md §3.13), proven like any L1 read concept.
29. **FIRST · Event scopes (13.6.1-2, 13.6.9).**
    - Is the safety-critical set {`dead`, `unexpected_map`} complete, or should a last-resort
      `hp_critical` (e.g. a wing out below 20 %) join it?
      ➡️ **ANSWERED (Batt, 2026-10-08): add `hp_critical`** (e.g. HP < 20 % → an immediate
      escape with a Fly Wing). The set is now {`dead`, `hp_critical`, `unexpected_map`} (13.6.1,
      13.6.3, 13.6.8, 13.6.9).
    - Safety-critical extensions run AFTER the global body, unlike Batt's "map first" EXTEND, for
      the reason in 13.6.1. Confirm.
      ➡️ **CONFIRMED (Batt, 2026-10-08):** a dead character respawns first.
    - A looser override on a harder map: a WARNING acknowledged at approval (proposal), or an
      ERROR?
    - The "harder" criteria: an aggressive species, a boss spawn line, a spawn level above the
      character's. Enough?
30. **`hp_critical`'s details (new, from Batt's answer to 29).**
    - Its place above `unexpected_map` (proposal: yes; a Fly Wing keeps the map, so they do not
      compete).
    - The thresholds: proposal < 20 %, rearmed above 50 %, at most 2 a minute.
    - What happens on a map where neither wing is allowed. Proposal: the linter shows "no escape"
      on that map, and a BOT run there needs Batt's explicit acknowledgement at approval.
31. **`unintended_engagement`'s priority (13.9).** Proposal: below `unexpected_map`, above
    `hp_low`; pre-empt. Should it outrank `hp_low`, given that recovering may itself cost HP?
32. **Which action stops an attack** (13.9). A 2-cell walk click did not stop it (3 / 3). rec@0
    measures the candidates before the global default is fixed: a walk beyond the target's reach, a
    key, closing its window.
33. **Species policies before the detector names species** (13.9). Proposal: the map's most
    cautious policy for every engagement. Or a sprite match for the species a map's policy names?
34. **Detection thresholds** (13.9): how near our character a damage number counts; the HP-drop
    size against regeneration noise; the latency budget from the cue to the recovery's first
    input.

## Consequences

**Positive:**
- **Behaviour becomes data.** Users change what the bot does without code; the agent's work goes
  into blocks that are proven once and reused.
- **One runtime, one linter, one approval.** Blocks, Python, JavaScript and LLM drafts all reduce to
  the same IR; nothing reaches the executor unlinted or unapproved.
- **Portable by construction.** The L1-L4 layers resolve a block per environment and fail closed,
  so a flow either works on a server or says exactly which binding is missing.
- **Testable.** Flows are fixtures; pre-emption, loops and outcomes are unit-tested; runs produce
  DemoRecords for the offline verifiers.
- **The LLM is optional and boxed.** It drafts; a person reads blocks and approves a hash.
- **A course ladder** from blocks to Python to LLM drafting, on the same program.
- **Workflows read the way players think** (section 13): by map, with exits between maps and events
  beside them. The preparation report states, before any run, what a workflow needs and roughly
  how long the AI preparation takes.

**Negative and costs:**
- A new package, an editor, a parser and two printers to maintain, and a round-trip test burden.
- A large front-end dependency with a CSP risk and a NOTICE obligation (if Blockly is adopted).
- **The runnable vocabulary grows slowly**: every action block needs alone-tests on RDP and S2
  before it runs. Today nothing is verified.
- **Deliberately limited expressiveness**: no parameters on procedures, no data structures beyond
  literal lists, no arbitrary code. Some flows will be clumsier than code.
- **The linter checks structure, not wisdom.** A valid flow can still be a poor strategy.
- Filled flows carry GPL-derived keys and stay out of the repository; only skeletons are shared
  here.
- **The training scope grows with every map, not with every target** (13.3): every species spawned
  on a workflow's maps must be trained and measured before it runs. And the map sheets need L3 data
  the generators do not extract yet (13.2).

**Unchanged:** CLAUDE.md hard rules 1-10, the mux as the only writer, the interlock, the foreground
gate, the frame-age guard, packets as offline ground truth only, and Windows staying clean.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| **The agent writes hard-coded flows** (one script per route, like `ro_agent` today) | Users cannot change behaviour without code and a review. Route data is GPL L3 data, which code would embed. Nothing is portable across servers. It contradicts Batt's direction: the agent builds blocks, users compose flows |
| **Free-form Python, executed** (in a sandbox) | A Python sandbox is not a security boundary (introspection escapes). Arbitrary code cannot be linted (termination, side effects), could reach files, the network or the mux directly, and would bypass the per-block outcome checks. LLM-written code would run unreviewed. A parsed subset gives the familiar syntax with none of this |
| **An LLM deciding at run time** (the next block or the next click from the screen) | ADR-0015's hard line and demonstrations.md: no LLM in the fast loop. Seconds of latency against a 10-20 Hz loop; not deterministic, so not testable or reproducible; open to prompt injection through in-game text; and R2 (one model at a time) would set an LLM against the detector for the GPU |
| **The block editor's own format as the stored truth** (Blockly workspace JSON) | It ties the executor and the linter to one UI library's serialisation and its versions; Python import would target a UI format. The IR is ours, validated and versioned |
| **Our own text language instead of a Python subset** | It needs a grammar, a parser and tooling, and teaches nothing transferable. Python is the course's next step and what LLMs write well; `ast` is a robust, non-executing parser in the standard library |
| **Users edit behavior trees directly** | Tick, running and fallback semantics are harder for no-code users than sequence, if, loop and events. The tree stays the executor's internal form, compiled from the IR |
| **A state-machine editor** | ADR-0015 already replaced the FSM with behavior trees |
