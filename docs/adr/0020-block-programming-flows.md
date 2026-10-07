---
doc_type: decision
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [ADR-0015, ADR-0002, ADR-0003, ADR-0004, ADR-0006, ADR-0007, ADR-0011, ADR-0012, ADR-0014, ADR-0016, ADR-0018, ADR-0019]
next_action: "Batt accepts, amends or rejects. On acceptance: answer the open questions marked FIRST (unverified blocks, executor placement, session blocks, takeover resume, where approved flows live), then build phase F1 (the flow IR, the block catalogue and linter layers 1-3, offline, no UI and no input). Nothing is built yet."
---

# ADR-0020: Block programs over one flow IR (the agent builds blocks, users compose flows)

- **Status:** PROPOSED (2026-10-07). Batt accepts or not. Nothing is built.
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
class Handler(BaseModel):
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
| `loot` | `loot.pick_up` | item or any | the item vanishes, its count rises | not bindable yet: no ground-item class (L1 exception) |
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
| `position()`, `current_map()` | `nav.read_position` | passive | UNKNOWN indoors (no minimap readout in this client) |
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
| 2 · semantics | every reference exists for the target environment: the map; the NPC on that map; the option offered by that NPC; the item, monster, skill. Every action block resolves its bindings (`resolve()`); an `Unsupported` is an error naming the layer and key. `assumes` uses known sensors | "main.1: npc n_3f2a is not on the map the flow is on at this point" |
| 3 · simulation | an abstract walk through the flow tracking the current map: reachability on the GAT/warp graph (`poring_dataset/walk.py`, legs ≤ 128 steps, waypoints beyond); a time estimate; monster spawns on the map for `attack_nearest`; element matchups (warning) | "main.2: cell (170, 210) is unreachable from the warp you arrive by" |
| 3 · loops | every `while` has a bound, a sensor/variable its body can change, or a `break`; a loop body with no action and no wait is a busy loop (error); the flow-level `max_runtime_s` bounds everything | "main.6: this loop can never end: nothing in it changes job_level()" |
| 3 · events | every handler has `rearm` or a cooldown; conditions use passive sensors only; two handlers of one class with overlapping conditions (warning); a handler that can re-trigger itself; a handler with no failure path; a `critical` handler containing a long action (warning) | "handlers.drink: no re-arm and no cooldown: it would fire on every tick" |
| 3 · irreversible | `refine`, `insert_card`, and `sell` with an empty keep list | "main.9: refine can destroy the item: acknowledge it at approval" |
| 4 · approval | the owner sees the blocks, the lint report, the time estimate and the badges (section 12), and approves THIS hash | – |
| 5 · runtime | the built-in guards (2.5), block timeouts, perception confidence | – |
| 6 · interlock | the target environment is `allowed` in the user-managed set (`settings/environments.json`); never the community server or an official one. The mux stays the enforcement (`environment_unattested`); the lint check only fails earlier | "target community-bot-testing is pending: flows never run there" |

The linter re-runs at run start against the current KB and catalogue. If either changed since
approval and the result changed, the run does not start.

## 6. Runtime

**Where it runs (proposal).** In the `vision` container, as an agent on `/internal/agent`:
- it needs the detector and the frame bus, and vision is S2-only (ADR-0005 option c2);
- the IR, parser, printer, catalogue, linter and tree runtime live in a new Apache-2.0 package
  (`poring_flow`, name to be decided); the block implementations that need the detector live in
  `services/vision` (AGPL-3.0, ADR-0018). Mixing is one-way, as ADR-0018 allows;
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
6. **Today:** 37 L1 concepts, 0 verified. And `resolve()` has no L4 resolver yet ("lands with the
   L4 work"), so every block that needs an L4 binding (menu options, Kafra services) resolves
   `unsupported` today. So flows can be built, linted and approved now, and become runnable only as
   bindings land and alone-tests pass. That is the intended order: rules are proven alone first.

## Open questions

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
