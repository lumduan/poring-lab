"""The demonstration log: every lab action with its intention, its cue and its VERIFIED outcome.

Batt, 2026-10-07 (docs/demonstrations.md): the OUTCOME judges, never the explanation.
- When an agent (Claude), a rule or the bot acts in the lab, one record is appended: what it did,
  what it meant to hit, and the cue it says it used.
- An offline verifier fills the outcome later from the packet ground truth (the dataset package's
  verify module; ADR-0007: packets are never decision input), or from the screen for client-side
  menus.
- A stated cue is only a HYPOTHESIS. It becomes a rule, the rule is tested ALONE on new situations,
  and it is adopted only if it passes a pre-registered bar.

The schema is shared by every actor, so the bot's own actions feed the same verify -> label loop:
- ``claude-demo``: a demonstration;
- ``rule:<name>@<version>``: a rule running alone;
- ``bot:<policy>@<version>``: the bot.

It lives in poring_env (not the offline-only dataset package, which poring_env never names:
test_guards) because the vision container writes it too, when the attack rule runs there.

A demo session is a directory (RAM first, /dev/shm; shipped to the NAS; NEVER committed: client
frames and packet data):
    manifest.json   kind "demo", backend, lock seq, server, t0/t1
    demo.jsonl      one DemoRecord per line, appended under an exclusive flock, fsync'd
    snapshots/      the game region before/after an action, PNG (client-derived)
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION: Literal[1] = 1
DEMO_ROOT = Path("/dev/shm/poring-lab-demo")  # rule 7: RAM; dataset_ship moves it to the NAS
ACTOR = re.compile(r"^(claude-demo|human|(rule|bot):[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+)$")
SESSION = re.compile(r"^\d{8}T\d{6}-demo-[a-z0-9-]+$")

ActionType = Literal[
    "login", "logout", "walk", "attack_target", "menu_shortcut",
    "npc_talk", "npc_choice", "npc_input", "shop_buy", "shop_sell",
    "stat_up", "skill_up", "item_use", "chat", "gm", "other",
]  # fmt: skip
Status = Literal["pending", "success", "fail", "ambiguous"]
_CONFIG = ConfigDict(extra="forbid", frozen=True)


class FrameRef(BaseModel):
    """The frame the actor looked at: a session frame, or a snapshot in this demo session."""

    model_config = _CONFIG
    frame_id: int = -1  # the bus writer's frame_id; -1 on X grabs
    source: Literal["bus", "x11", "none"] = "none"
    t_capture_ns: int | None = None
    ref: str | None = None  # "snapshots/<file>.png" or "session:<session_id>#<frame_id>"


class Intended(BaseModel):
    """What the actor meant to hit, in its own terms (the verifier checks it, never trusts it)."""

    model_config = _CONFIG
    kind: str = Field(min_length=1, max_length=40)  # monster | cell | window | npc | option | login
    gid: int | None = None
    cell: tuple[int, int] | None = None  # world cell (x, y) or, for a relative walk, (dx, dy)
    relative: bool = False  # cell is an offset from our own cell
    window: str | None = None
    option: int | None = None  # 1-based menu option
    approx_px: tuple[float, float] | None = None  # client px (GAME_REGION origin)
    note: str | None = Field(default=None, max_length=200)


class Action(BaseModel):
    model_config = _CONFIG
    type: ActionType
    points: list[tuple[float, float]] = []  # client px (GAME_REGION origin), in order
    keys: list[str] = []  # KeyboardEvent.code, in order (chords as "AltLeft+KeyE")
    intended: Intended


class Outcome(BaseModel):
    model_config = _CONFIG
    status: Status = "pending"
    verifier: str | None = None  # "<name>@<version>"
    cause: str | None = Field(default=None, max_length=200)
    evidence: dict[str, Any] = {}


class DemoRecord(BaseModel):
    model_config = _CONFIG
    schema_version: Literal[1] = SCHEMA_VERSION
    record_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    session: str
    actor: str
    t_mono_ns: int = Field(ge=0)  # when the action STARTED (sender's CLOCK_MONOTONIC)
    t_done_ns: int | None = None  # when its last input was acknowledged
    frame: FrameRef = FrameRef()
    frame_after: FrameRef | None = None
    action: Action
    cue: str = Field(min_length=1, max_length=300)
    rule: str | None = None  # "<name>@<version>" when a rule chose the action
    scene: str | None = None  # e.g. "outdoor:prt_fild08", "indoor:prt_church", "login"
    outcome: Outcome = Outcome()
    click_to_sprite_px: float | None = None  # filled by the verifier for clicks on world objects
    pseudonymised: bool = True

    @field_validator("actor")
    @classmethod
    def _actor(cls, v: str) -> str:
        if not ACTOR.match(v):
            raise ValueError(
                "actor must be claude-demo | human | rule:<name>@<ver> | bot:<p>@<ver>"
            )
        return v

    @field_validator("cue")
    @classmethod
    def _cue(cls, v: str) -> str:
        if v.count("\n") > 1:
            raise ValueError("the cue is one or two lines")
        return v


def new_session_id(label: str, now: float | None = None) -> str:
    label = re.sub(r"[^a-z0-9-]+", "-", label.lower()).strip("-") or "session"
    return time.strftime("%Y%m%dT%H%M%S", time.localtime(now)) + f"-demo-{label}"


class DemoLog:
    """One demo session's directory: the manifest, the append-only log, the snapshots."""

    def __init__(self, session: str, root: Path = DEMO_ROOT) -> None:
        if not SESSION.match(session):
            raise ValueError(f"not a demo session id: {session!r}")
        self.session = session
        self.dir = root / session
        self.path = self.dir / "demo.jsonl"
        (self.dir / "snapshots").mkdir(parents=True, exist_ok=True)

    def start(self, **meta: Any) -> None:
        """Write manifest.json once (kind demo, t0); later calls keep the first t0."""
        path = self.dir / "manifest.json"
        if path.exists():
            return
        man = {"session_id": self.session, "kind": "demo", "schema_version": SCHEMA_VERSION,
               "t0_wall": time.time(), "t0_mono_ns": time.monotonic_ns(), **meta}  # fmt: skip
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(man, indent=1))
        os.replace(tmp, path)

    def finish(self, **meta: Any) -> None:
        path = self.dir / "manifest.json"
        man = json.loads(path.read_text()) if path.exists() else {"session_id": self.session}
        man.update({"t1_wall": time.time(), "t1_mono_ns": time.monotonic_ns(), **meta})
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(man, indent=1))
        os.replace(tmp, path)

    def append(self, rec: DemoRecord) -> DemoRecord:
        if rec.session != self.session:
            raise ValueError(f"record for {rec.session}, log is {self.session}")
        line = rec.model_dump_json() + "\n"
        with self.path.open("a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
        return rec

    def snapshot(self, name: str, png: bytes) -> str:
        """Store a PNG under snapshots/; returns the relative ref a FrameRef carries."""
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
        path = self.dir / "snapshots" / f"{safe}.png"
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(png)
        os.replace(tmp, path)
        return f"snapshots/{path.name}"

    def records(self) -> list[DemoRecord]:
        return read(self.path)


def read(path: Path) -> list[DemoRecord]:
    if not path.exists():
        return []
    return [DemoRecord.model_validate_json(line) for line in path.read_text().splitlines() if line]
