"""The tree runtime, SIMULATED (ADR-0020 2.5, 13.6.4-13.6.7; F1 / MW1 acceptance).

A deterministic executor driven by a FAKE environment: a fake clock, a scripted sensor timeline
and scripted block outcomes. It emits the `AgentInput` batches a real run would send through the
mux, and nothing else, so the pre-emption rules are table-tested on the emitted sequence. It does
no I/O: no socket, no mux, no screen. The real executor (F2 / MW2) replaces the fake environment.

`compile_tree(flow)` builds the reactive priority structure 2.5 describes: per map block, the
effective events (13.6.2) by class (guard > critical > survival > upkeep > the main flow), and
the main flow as a selector over the blocks keyed by `current_block`.

The rules it implements (each table-tested in tests/test_runtime.py):
- an event fires on a false -> true edge of its condition, on fresh values only (unknown never
  fires); a one-shot event re-arms when `rearm` holds (else when its condition goes false) and
  `cooldown_s` has passed; a repeating event (`until`) runs its body again while it is on, paced by
  `cooldown_s` and `max_per_min`, until `until` holds;
- a PRE-EMPT event halts anything of a strictly LOWER class at once (an atomic section ends
  first); equal classes queue, de-duplicated, ordered by RANK inside the class (IR 2, Batt
  2026-10-09, contradictions #13: the safety-critical three first, then `ir.rank_of`), first in
  first out only between equal ranks; ReleaseAll precedes the handler's first batch; afterwards
  `then` decides (resume restarts the interrupted block from its start, skip_block fails it,
  restart_flow, relocate, stop); waiting inserts are taken in the same order;
- an INSERT event runs at the running flow's next SAFE POINT (between two ticks, never inside an
  atomic section); the block it suspended continues at its next tick, not restarted; ReleaseAll
  first only if something is held; a failed insert counts toward `max_insert_fails`, then its
  `escalate` procedure runs as a pre-empt (or the run stops);
- relocation reads the position (an active, typed read), picks the block whose map is the actual
  map (an entry containing the cell, an anywhere entry, `resume_here`), and runs its main from the
  first step; no block or no map: stop `relocate_no_block`;
- `max_fires_per_10min` without `until` holding stops the run (`handler_runaway`); `max_per_run`
  stops it (`death_limit` for `dead`); `max_runtime_s` and `stop_when` are guards;
- ONE input token: batches of two flows never interleave.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from typing import Any

from poring_env.protocol import AgentInput, InputEvent, Key, MouseButton, MouseMove, ReleaseAll
from poring_flow import ir
from poring_flow.catalogue import Catalogue, catalogue
from poring_flow.effective import Effective, global_set, merge

TICK_S = 0.1
RANK = {"critical": 0, "survival": 1, "upkeep": 2}  # the CLASS level (lower runs first)
MAIN_RANK = 3


def queue_key(e: Effective) -> tuple[int, int, int]:
    """Where a due event sits in the queue: its class, the safety-critical lead, its rank inside
    the class (#13). Ties keep their arrival order (FIFO only between equal ranks)."""
    h = e.handler
    lead = ir.SAFETY_CRITICAL.index(e.key) if e.key in ir.SAFETY_CRITICAL else 3
    return (RANK[h.priority], lead, ir.rank_of(h))


Outcome = str  # ok | failed | interrupted | ...


# --- the compiled tree --------------------------------------------------------------------------
@dataclass(frozen=True)
class Tree:
    """guard > critical > survival > upkeep > main, per map block (13.6.2: switched at a block
    change, between events)."""

    flow: ir.Flow
    events: dict[str, tuple[Effective, ...]]  # block name ("" for a plain flow) -> active events
    blocks: dict[str, ir.MapBlock]

    def active(self, block: str) -> tuple[Effective, ...]:
        return self.events.get(block, ())


def compile_tree(flow: ir.Flow) -> Tree:
    blocks = {b.name: b for b in flow.workflow.blocks} if flow.workflow else {}
    events = {name: tuple(merge(flow, b).active()) for name, b in blocks.items()}
    if not blocks:
        events[""] = tuple(global_set(flow).active())
    return Tree(flow, events, blocks)


# --- the fake environment -----------------------------------------------------------------------
@dataclass
class Plan:
    """How one simulated block run behaves."""

    ticks: int = 3
    outcome: Outcome = "ok"
    effects: dict[str, Any] = field(default_factory=dict)  # world values set when it ends ok
    atomic: tuple[int, int] | None = None  # ticks [a, b) form an atomic section
    hold: bool = False  # its batches leave the mouse button held between ticks


Planner = Callable[[ir.ActionStmt, "Sim"], Plan]


def default_plan(a: ir.ActionStmt, sim: Sim) -> Plan:
    spec = sim.cat.blocks[a.block].spec if a.block in sim.cat.blocks else None
    if a.block == "use_item":
        return Plan(ticks=1)
    if spec is not None and spec.profile == "atomic":
        return Plan(ticks=3, atomic=(0, 3))
    return Plan(ticks=3)


@dataclass
class Emitted:
    owner: str  # main, a block name, an event label, or "executor" (a ReleaseAll on a halt)
    batch: AgentInput
    why: str  # the block, or the reason for a ReleaseAll


@dataclass
class _EvState:
    armed: bool = True
    on: bool = False  # a repeating event between its start and its stop threshold
    prev: bool = False
    last_end: float = -1e9
    runs: deque[float] = field(default_factory=deque)  # body runs in the last minute
    fires: deque[float] = field(default_factory=deque)  # fires since until last held (10 min)
    per_run: int = 0
    insert_fails: int = 0


@dataclass
class _Frame:
    owner: str
    rank: int
    gen: Generator[_Tick, str | None, str]
    then: str = "resume"
    event: Effective | None = None
    pending: str | None = None  # what to send at its next step: restart | fail
    atomic: bool = False
    started: bool = False


@dataclass
class _Tick:
    batch: list[InputEvent] | None
    atomic: bool
    why: str


class _Halt(Exception):  # noqa: N818 -- a control signal, not an error
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class Sim:
    """Run a flow against a scripted world. `timeline`: (t, {key: value}) changes, applied at the
    first tick at or after t. World keys: hp_percent, weight_percent, is_dead, map (current map),
    cell (x, y), sees:<mob id>, engagement_seen, engaged_species, item:<id>, plus guard keys
    `human` (a takeover: pause) and `interlock` ("red": stop)."""

    def __init__(
        self,
        flow: ir.Flow,
        *,
        world: dict[str, Any] | None = None,
        timeline: list[tuple[float, dict[str, Any]]] | None = None,
        planner: Planner | None = None,
        save_point: tuple[str, tuple[int, int]] | None = None,
        cat: Catalogue | None = None,
        max_ticks: int = 5000,
    ) -> None:
        self.flow = flow
        self.tree = compile_tree(flow)
        self.cat = cat or catalogue()
        self.world: dict[str, Any] = dict(world or {})
        self.timeline = sorted(timeline or [], key=lambda p: p[0])
        self.planner = planner or default_plan
        self.save_point = save_point
        self.max_ticks = max_ticks
        self.t = 0.0
        self.frame_id = 0
        self.out: list[Emitted] = []
        self.log: list[tuple[float, str, str]] = []
        self.vars: dict[str, Any] = {k: v.value for k, v in flow.variables.items()}
        self.state: dict[str, _EvState] = {}
        self.block = flow.workflow.start_block if flow.workflow else ""
        self.held = False
        self.expect_map_change = False
        # pre-empts waiting: (class, safety lead, rank, seq, key) -- sorted, so FIFO by seq only
        # between events of equal rank (#13)
        self.queue: list[tuple[int, int, int, int, str]] = []
        self.inserts: list[str] = []
        self.seq = 0
        self.stack: list[_Frame] = []
        self.end: str | None = None
        self.preempts: list[tuple[int, str]] = []  # (index of the ReleaseAll in out, handler)

    # --- the world ------------------------------------------------------------------------------
    def _apply_timeline(self) -> None:
        while self.timeline and self.timeline[0][0] <= self.t + 1e-9:
            _, changes = self.timeline.pop(0)
            self._set(changes, cause="world")

    def _set(self, changes: dict[str, Any], cause: str) -> None:
        old_map = self.world.get("map")
        self.world.update(changes)
        if "map" in changes and changes["map"] != old_map:
            self.world["map_load_seen"] = True
            self.world["_map_cause"] = cause

    def _sense(self, s: ir.Sense) -> Any:
        if s.sensor == "known":
            return self._eval(s.args["value"]) is not None
        if s.sensor in ("sees", "count_visible"):
            mob = self._eval(s.args["mob"])
            return self.world.get(f"sees:{getattr(mob, 'id', mob)}")
        if s.sensor == "item_count":
            item = self._eval(s.args["item"])
            return self.world.get(f"item:{getattr(item, 'id', item)}")
        key = {"current_map": "map", "position": "cell"}.get(s.sensor, s.sensor)
        return self.world.get(key)

    def _eval(self, e: Any, done: dict[int, str] | None = None) -> Any:
        """A value, or None for unknown (a comparison with unknown is unknown)."""
        if isinstance(e, ir.Lit):
            return e.value
        if isinstance(e, ir.Var):
            return self.vars.get(e.name)
        if isinstance(e, ir.OutcomeLit):
            return e.value
        if isinstance(e, ir.ListE):
            return [self._eval(i, done) for i in e.items]
        if isinstance(e, ir.Sense):
            return self._sense(e)
        if isinstance(e, ir.Do):
            return (done or {}).get(id(e))
        if isinstance(e, ir.Not_):
            v = self._eval(e.term, done)
            return None if v is None else not v
        if isinstance(e, ir.Logic):
            vals = [self._eval(t, done) for t in e.terms]
            if e.kind == "and":
                return False if any(v is False for v in vals) else (None if None in vals else True)
            return True if any(v is True for v in vals) else (None if None in vals else False)
        if isinstance(e, ir.Cmp | ir.Arith):
            a, b = self._eval(e.left, done), self._eval(e.right, done)
            if a is None or b is None:
                return None
            return _OPS[e.op](a, b)
        return None

    # --- input ----------------------------------------------------------------------------------
    def _emit(self, owner: str, events: list[InputEvent], why: str) -> None:
        self.frame_id += 1
        ns = int(round(self.t * 1e9))
        batch = AgentInput(t_mono_ns=ns, frame_id=self.frame_id, t_capture_ns=ns, events=events)
        self.out.append(Emitted(owner, batch, why))
        for ev in events:
            if isinstance(ev, ReleaseAll):
                self.held = False
            elif isinstance(ev, MouseButton | Key):
                self.held = ev.action == "down" or (self.held and ev.action != "up")

    def _release(self, why: str) -> None:
        ns = int(round(self.t * 1e9))
        self._emit("executor", [ReleaseAll(t_mono_ns=ns)], why)

    def _batch(self, a: ir.ActionStmt, hold: bool) -> list[InputEvent]:
        ns = int(round(self.t * 1e9))
        spec = self.cat.blocks[a.block].spec if a.block in self.cat.blocks else None
        if a.block == "use_item":  # through the hotbar (13.6.4)
            return [
                Key(t_mono_ns=ns, code="F1", action="down"),
                Key(t_mono_ns=ns, code="F1", action="up"),
            ]
        if spec is not None and spec.types:
            return [
                Key(t_mono_ns=ns, code="Enter", action="down"),
                Key(t_mono_ns=ns, code="Enter", action="up"),
            ]
        events: list[InputEvent] = [
            MouseMove(t_mono_ns=ns, x=0.5, y=0.5),
            MouseButton(t_mono_ns=ns, button="left", action="down"),
        ]
        if not hold:
            events.append(MouseButton(t_mono_ns=ns, button="left", action="up"))
        return events

    # --- the interpreter (generators that yield one tick at a time) ------------------------------
    def _action(self, a: ir.ActionStmt, owner: str) -> Generator[_Tick, str | None, Outcome]:
        while True:
            plan = self.planner(a, self)
            restarted = False
            for i in range(plan.ticks):
                # the section holds between this tick and the next; a section that ends the block
                # holds through its outcome check (a pre-emption never cuts a confirmed choice)
                lo, hi = plan.atomic if plan.atomic is not None else (0, 0)
                atomic = lo <= i < hi and (i + 1 < hi or hi >= plan.ticks)
                sent = yield _Tick(self._batch(a, plan.hold), atomic, a.block)
                if sent == "restart":
                    restarted = True
                    break
                if sent == "fail":
                    return "failed"
            if restarted:
                continue
            # the outcome check, on a frame decoded AFTER the last input (grab_after): no input.
            # The block is done: a restart or a failure sent now is ignored.
            yield _Tick(None, False, f"{a.block} check")
            if plan.outcome == "ok":
                cause = "expected" if a.block in ("respawn", "escape", "use_item") else "action"
                effects = dict(plan.effects)
                if a.block in ("respawn",) or (a.block == "use_item" and self._is_wing(a)):
                    if self.save_point and "map" not in effects:
                        effects["map"], effects["cell"] = self.save_point
                    effects.setdefault("is_dead", False)
                self._set(effects, cause=cause)
            return plan.outcome

    def _is_wing(self, a: ir.ActionStmt) -> bool:
        v = self._eval(a.params["item"]) if "item" in a.params else None
        return isinstance(v, ir.ItemRef) and self.world.get(f"wing:{v.id}") == "butterfly"

    def _cond(self, e: Any, owner: str) -> Generator[_Tick, str | None, Any]:
        done: dict[int, str] = {}
        for x in ir.sub_exprs(e):
            if isinstance(x, ir.Do):
                done[id(x)] = yield from self._action(x.action, owner)
        return self._eval(e, done)

    def _stmts(self, stmts: list[Any], owner: str) -> Generator[_Tick, str | None, str]:
        for st in stmts:
            r = yield from self._stmt(st, owner)
            if r != "next":
                return r
        return "next"

    def _stmt(self, st: Any, owner: str) -> Generator[_Tick, str | None, str]:
        if isinstance(st, ir.ActionStmt):
            out = yield from self._action(st, owner)
            if st.outcome_to:
                self.vars[st.outcome_to] = out
            if out != "ok" and st.on_fail == "stop":
                raise _Halt(f"{st.block}_{out}")
            return "next"
        if isinstance(st, ir.If):
            c = yield from self._cond(st.cond, owner)
            return (yield from self._stmts(st.then if c else st.orelse, owner))
        if isinstance(st, ir.While | ir.Repeat | ir.ForEach):
            return (yield from self._loop(st, owner))
        if isinstance(st, ir.WaitUntil):
            waited = 0.0
            while not (yield from self._cond(st.cond, owner)):
                if waited >= st.timeout_s:
                    if st.outcome_to:
                        self.vars[st.outcome_to] = "failed"
                    return "next"
                yield _Tick(None, False, "wait_until")
                waited += TICK_S
            if st.outcome_to:
                self.vars[st.outcome_to] = "ok"
            return "next"
        if isinstance(st, ir.SetVar):
            self.vars[st.var] = self._eval(st.value)
            return "next"
        if isinstance(st, ir.CallProc):
            r = yield from self._stmts(self.flow.procedures.get(st.proc, []), owner)
            return r if r in ("exit",) else "next"
        if isinstance(st, ir.Stop):
            raise _Halt(st.reason)
        if isinstance(st, ir.Break_ | ir.Continue_):
            return st.kind
        if isinstance(st, ir.TakeExit):
            yield from self._exit(st.exit, owner)
            return "exit"
        raise TypeError(type(st))

    def _loop(self, st: Any, owner: str) -> Generator[_Tick, str | None, str]:
        n = 0
        start = self.t
        if isinstance(st, ir.Repeat):
            items: list[Any] = list(range(int(self._eval(st.times) or 0)))
        elif isinstance(st, ir.ForEach):
            if isinstance(st.items, ir.Range):
                items = list(
                    range(
                        int(self._eval(st.items.start)),
                        int(self._eval(st.items.stop)),
                        int(self._eval(st.items.step)),
                    )
                )
            else:
                items = list(self._eval(st.items) or [])
        else:
            items = []
        i = 0
        while True:
            if isinstance(st, ir.While):
                if st.max_iter is not None and n >= st.max_iter:
                    return "next"
                if st.max_s is not None and self.t - start >= st.max_s:
                    return "next"
                if not (yield from self._cond(st.cond, owner)):
                    return "next"
            else:
                if i >= len(items):
                    return "next"
                if isinstance(st, ir.ForEach):
                    self.vars[st.var] = items[i]
                i += 1
            n += 1
            r = yield from self._stmts(st.body, owner)
            if r == "break":
                return "next"
            if r == "exit":
                return "exit"

    def _exit(self, x: ir.Exit, owner: str) -> Generator[_Tick, str | None, None]:
        """An exit's actions, then its arrival check (13.1): the map from the world."""
        to = self.tree.blocks.get(x.to_block)
        action = {"walk_exit": "take_warp", "npc_warp": "choose_menu", "item_warp": "use_item"}[
            x.kind
        ]
        params: dict[str, Any] = {}
        if x.kind == "item_warp" and x.item is not None:
            params["item"] = x.item if isinstance(x.item, ir.Var) else ir.Lit(value=x.item)
        a = ir.ActionStmt(
            block=action, concept=self.cat.blocks[action].spec.concept, timeout_s=60, params=params
        )
        self.expect_map_change = True
        try:
            plan = self.planner(a, self)
            for _ in range(plan.ticks):
                yield _Tick(self._batch(a, False), False, f"take_exit {x.kind}")
            if to is not None:
                cell: tuple[int, int] | None
                if x.kind == "item_warp" and self.save_point:  # a wing goes to the SAVE POINT
                    map_id, cell = self.save_point
                else:
                    entry = next((e for e in to.entries if e.name == x.to_entry), None)
                    at = entry.at if entry is not None else None
                    map_id, cell = to.map.map, ((at.x, at.y) if at is not None else None)
                if map_id == to.map.map:
                    self._set({"map": map_id, "cell": cell}, cause="exit")
                    self.block = to.name
                    self.log.append((self.t, "block", to.name))
                else:  # the arrival check reads another map: unexpected_map decides (13.6.3)
                    self._set({"map": map_id, "cell": cell}, cause="world")
        finally:
            self.expect_map_change = False

    def _main_gen(self, block: str) -> Generator[_Tick, str | None, str]:
        while True:
            body = self.tree.blocks[block].main if block else (self.flow.main or [])
            r = yield from self._stmts(body, block or "main")
            if r != "exit":
                return r
            block = self.block

    # --- events ---------------------------------------------------------------------------------
    def _st(self, key: str) -> _EvState:
        return self.state.setdefault(key, _EvState())

    def _due(self, e: Effective, s: _EvState) -> bool:
        h = e.handler
        while s.runs and self.t - s.runs[0] >= 60:
            s.runs.popleft()
        if h.max_per_min is not None and len(s.runs) >= h.max_per_min:
            return False
        return self.t - s.last_end >= h.cooldown_s

    def _perceive(self) -> list[Effective]:
        """Evaluate every effective event on this tick; return the ones that fire now."""
        fired = []
        for e in self.tree.active(self.block):
            h, s = e.handler, self._st(e.key)
            c = self._eval(h.when)
            if (
                e.key == "unexpected_map"
                and c
                and (self.world.get("_map_cause") in ("exit", "expected"))
            ):
                c = False  # an expected map change (an exit, a respawn, a wing) is not unexpected
            c = c is True
            if h.until is not None:
                if s.on and self._eval(h.until) is True:
                    s.on = False
                    s.fires.clear()
                    self.log.append((self.t, "until", e.key))
                elif s.on and self._due(e, s) and e.key not in self._waiting():
                    fired.append(e)
                elif not s.on and c and not s.prev:
                    s.on = True
                    fired.append(e)
            else:
                if not s.armed and e.key not in self._waiting():  # never while it is still on
                    rearm = self._eval(h.rearm) is True if h.rearm is not None else not c
                    if rearm and self.t - s.last_end >= h.cooldown_s:
                        s.armed = True
                if s.armed and c and not s.prev:
                    s.armed = False
                    fired.append(e)
            s.prev = c
        self.world["map_load_seen"] = False
        self.world.pop("_map_cause", None)
        return fired

    def _waiting(self) -> set[str]:
        running = {f.event.key for f in self.stack if f.event is not None}
        return {q[-1] for q in self.queue} | set(self.inserts) | running

    def _fire(self, e: Effective) -> None:
        s = self._st(e.key)
        h = e.handler
        while s.fires and self.t - s.fires[0] >= 600:
            s.fires.popleft()
        s.fires.append(self.t)
        if len(s.fires) > h.max_fires_per_10min:
            raise _Halt("handler_runaway")
        s.per_run += 1
        s.last_end = self.t  # provisional; the run's real end replaces it
        limit = e.max_per_run
        if limit is not None and s.per_run > limit:
            raise _Halt("death_limit" if e.key == "dead" else f"{e.key}_limit")
        self.log.append((self.t, "fire", e.key))
        if h.mode == "insert":
            if e.key not in self.inserts:
                self.inserts.append(e.key)
        elif e.key not in self._waiting():
            self.seq += 1
            self.queue.append((*queue_key(e), self.seq, e.key))

    def _event(self, key: str) -> Effective | None:
        return next((e for e in self.tree.active(self.block) if e.key == key), None)

    # --- the scheduler --------------------------------------------------------------------------
    def _top_rank(self) -> int:
        return self.stack[-1].rank if self.stack else MAIN_RANK

    def _handler_gen(self, e: Effective) -> Generator[_Tick, str | None, str]:
        body = list(e.handler.body)
        if e.extension and not e.extension_after:
            yield from self._stmts(list(e.extension), e.extension_label or e.label)
        yield from self._stmts(body, e.label)
        if e.extension and e.extension_after:
            yield from self._stmts(list(e.extension), e.extension_label or e.label)
        return "next"

    def _preempt(self) -> None:
        if not self.queue or (self.stack and self.stack[-1].atomic):
            return
        self.queue.sort()
        rank, key = self.queue[0][0], self.queue[0][-1]
        if rank >= self._top_rank():
            return  # equal or lower CLASS: it queues (2.5 rule 4), in rank order (#13)
        self.queue.pop(0)
        e = self._event(key)
        if e is None:
            return
        if self.stack:
            top = self.stack[-1]
            top.pending = "restart"
            self.log.append((self.t, "interrupted", top.owner))
        self._release(f"pre-empt by {e.key}")
        self.preempts.append((len(self.out) - 1, e.label))
        s = self._st(e.key)
        s.runs.append(self.t)
        self.stack.append(_Frame(e.label, rank, self._handler_gen(e), e.handler.then, e))

    def _run_inserts(self) -> None:
        """At a safe point: between ticks, never inside an atomic section (13.6.4)."""
        if not self.inserts or (self.stack and self.stack[-1].atomic):
            return
        order = {e.key: queue_key(e) for e in self.tree.active(self.block)}
        far = (len(RANK), 0, 0)
        # by class and rank (#13); the sort is stable, so equal ranks stay first in, first out
        for key in sorted(self.inserts, key=lambda k: order.get(k, far)):
            e = self._event(key)
            if e is None:  # not effective on this block any more
                self.inserts.remove(key)
                continue
            s = self._st(key)
            if RANK[e.handler.priority] >= self._top_rank() or not self._due(e, s):
                continue  # it waits: a handler of its class or higher runs, or it is paced
            self.inserts.remove(key)
            if self.held:
                self._release(f"insert {key}: something was held")
            self.log.append((self.t, "insert", key))
            s.runs.append(self.t)
            gen = self._stmts(list(e.handler.body), e.label)
            outcome = "ok"
            try:
                tick = next(gen)
                while True:
                    if tick.batch is not None:
                        self._emit(e.label, tick.batch, tick.why)
                    self.t += TICK_S
                    tick = gen.send(None)
            except StopIteration:
                pass
            except _Halt as h:
                outcome = h.reason
            s.last_end = self.t
            if outcome != "ok":
                s.insert_fails += 1
                self.log.append((self.t, "insert_failed", key))
                if s.insert_fails >= e.handler.max_insert_fails:
                    s.insert_fails = 0
                    self._escalate(e)

    def _escalate(self, e: Effective) -> None:
        proc = e.handler.escalate
        if proc is None:
            raise _Halt("insert_failed")
        if self.stack:
            self.stack[-1].pending = "restart"
        self._release(f"escalate {e.key}")
        self.preempts.append((len(self.out) - 1, f"{e.label}.escalate"))
        gen = self._stmts(self.flow.procedures.get(proc, []), f"{e.label}.escalate")
        self.stack.append(
            _Frame(f"{e.label}.escalate", RANK[e.handler.priority], gen, e.handler.then, e)
        )

    def _finish(self, frame: _Frame) -> None:
        """A handler ended: its `then` decides (2.5 rule 7, 13.6.6)."""
        e = frame.event
        if e is not None:
            self._st(e.key).last_end = self.t
        then = frame.then
        if then == "stop":
            raise _Halt(f"{frame.owner}_stop")
        if then == "resume":
            return  # the frame below restarts its interrupted block (pending = restart)
        if then == "skip_block":
            if self.stack:
                self.stack[-1].pending = "fail"
            return
        self.stack.clear()  # restart_flow / relocate: nothing below survives
        if then == "restart_flow":
            self.block = self.flow.workflow.start_block if self.flow.workflow else ""
            self.stack.append(_Frame("main", MAIN_RANK, self._main_gen(self.block)))
            return
        self._relocate()

    def _relocate(self) -> None:
        """13.6.6: read where the character is (typed, active), pick its block, run it."""
        read = ir.ActionStmt(block="read_position", concept="nav.read_position", timeout_s=10)
        self._emit("executor", self._batch(read, False), "relocate: read position")
        map_id, cell = self.world.get("map"), self.world.get("cell")
        target = self._resume_block(map_id, cell)
        if target is None:
            raise _Halt("relocate_no_block")
        self.block = target
        self.log.append((self.t, "relocate", target))
        self.stack.append(_Frame("main", MAIN_RANK, self._main_gen(target)))

    def _resume_block(self, map_id: Any, cell: Any) -> str | None:
        if map_id is None:
            return None
        cands = [b for b in self.tree.blocks.values() if b.map.map == map_id]
        if not cands:
            return None
        if len(cands) > 1:
            cands = [b for b in cands if b.resume_here]
        for b in cands:
            for en in b.entries:
                if en.at is None:
                    return b.name
                if cell is not None and max(abs(en.at.x - cell[0]), abs(en.at.y - cell[1])) <= (
                    en.radius
                ):
                    return b.name
        return cands[0].name if cands else None

    def _step(self, frame: _Frame) -> bool:
        """One tick of the running frame; False when it has finished."""
        send, frame.pending = frame.pending, None
        if not frame.started:  # nothing was interrupted before its first tick
            send, frame.started = None, True
        try:
            tick = frame.gen.send(send) if send is not None else next(frame.gen)
        except StopIteration:
            return False
        frame.atomic = tick.atomic
        if tick.batch is not None:
            self._emit(
                frame.owner if frame.event is not None else (self.block or "main"),
                tick.batch,
                tick.why,
            )
        return True

    def run(self) -> str:
        """Run until the flow ends, stops or a guard halts it; returns the end reason."""
        if not self.stack:
            self.stack.append(_Frame("main", MAIN_RANK, self._main_gen(self.block)))
        try:
            for _ in range(self.max_ticks):
                self._apply_timeline()
                if self.world.get("interlock") == "red":
                    raise _Halt("interlock_red")
                if self.world.get("human"):
                    raise _Halt("human_pause")
                if self.t >= self.flow.max_runtime_s:
                    raise _Halt("max_runtime")
                if self.flow.stop_when is not None and self._eval(self.flow.stop_when) is True:
                    raise _Halt("stop_when")
                for e in self._perceive():
                    self._fire(e)
                self._preempt()
                self._run_inserts()
                if not self.stack:
                    self.end = "done"
                    break
                top = self.stack[-1]
                if not self._step(top):
                    self.stack.pop()
                    if top.event is None:
                        self.end = "done"
                        break
                    self._finish(top)
                    continue
                self.t += TICK_S
            else:
                self.end = "max_ticks"
        except _Halt as h:
            self.end = h.reason
        if self.held or self.end not in ("done",):
            self._release(f"end: {self.end}")
        self.log.append((self.t, "end", self.end or ""))
        return self.end or ""


_OPS: dict[str, Callable[[Any, Any], Any]] = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "in": lambda a, b: a in b,
    "not in": lambda a, b: a not in b,
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": lambda a, b: a * b,
    "//": lambda a, b: a // b if b else None,
    "%": lambda a, b: a % b if b else None,
}


def owners(out: list[Emitted]) -> list[str]:
    """The owner of each batch, consecutive repeats collapsed (for sequence assertions)."""
    seq: list[str] = []
    for em in out:
        label = "RELEASE" if isinstance(em.batch.events[0], ReleaseAll) else em.owner
        if not seq or seq[-1] != label:
            seq.append(label)
    return seq
