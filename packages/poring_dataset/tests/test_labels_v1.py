"""labels_for_v1 (Phase 3 M5): v0's filters and player/NPC boxes, predict_sprite's box for every
catalogued monster -- synthetic frames, predict_sprite stubbed (test_render tests it)."""

from types import SimpleNamespace

import numpy as np
import pytest

from poring_dataset import labels as lb
from poring_dataset.render import MonsterAction
from poring_dataset.timeline import ActorState, EntityState, FrameWorld

H = np.array([[30.0, 0.0, 392.0], [0.0, 30.0, 270.0], [0.0, 0.0, 1.0]])  # 30 px per cell


def ent(gid: int, objtype: int, job: int, x: float, y: float) -> EntityState:
    return EntityState(gid=gid, objtype=objtype, job=job, name="", x=x, y=y, moving=False,
                       heading=2)  # fmt: skip


def frame(*ents: EntityState) -> FrameWorld:
    return FrameWorld(t_ns=0, map="prt_fild08", aid=1, self_pos=(10.0, 10.0), entities=ents)


def state(gid: int, kind: str, elapsed_ms: float | None = None) -> ActorState:
    since = None if elapsed_ms is None else int(10e9 - elapsed_ms * 1e6)
    return ActorState(gid=gid, t_ns=10_000_000_000, state=kind,  # type: ignore[arg-type]
                      facing=4, facing_from="stop", x=0, y=0, job=1002, since_ns=since)  # fmt: skip


def test_monsters_get_the_predicted_box_npcs_keep_v0(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_predict(actor, sheet, scene, k):  # type: ignore[no-untyped-def]
        calls.append((actor.action, actor.elapsed_ms, actor.heading, k))
        return SimpleNamespace(box=(440.0, 220.0, 492.0, 270.0), box_kind="opaque",
                               phase_known=actor.elapsed_ms is not None)  # fmt: skip

    monkeypatch.setattr(lb, "predict_sprite", fake_predict)
    f = frame(ent(1, 5, 1002, 12, 10), ent(2, 6, 50, 9, 10), ent(3, 5, 9999, 11, 9))
    states = {1: state(1, "attacking", elapsed_ms=120.0), 3: state(3, "idle")}
    out = lb.labels_for_v1(f, H, (784, 625), scene=None, state=states.get,  # type: ignore[arg-type]
                           sheet=lambda job: object() if job == 1002 else None, k=0.14)  # fmt: skip
    by_gid = {lab.gid: lab for lab in out}
    assert by_gid[1].kind == "opaque" and (by_gid[1].x0, by_gid[1].y1) == (440.0, 270.0)
    assert by_gid[1].state == "attacking" and by_gid[1].phase_known is True
    assert calls == [(MonsterAction.ATTACK, pytest.approx(120.0), 4, 0.14)]  # one-shot: phased
    assert by_gid[2].cls == "npc" and by_gid[2].kind == "v0"  # NPCs keep the v0 box
    assert by_gid[3].kind == "v0"  # an uncatalogued species keeps the v0 box


def test_idle_is_the_envelope_and_nothing_drawn_is_no_box(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = []

    def fake_predict(actor, sheet, scene, k):  # type: ignore[no-untyped-def]
        seen.append(actor.elapsed_ms)
        return None  # the client draws nothing for it

    monkeypatch.setattr(lb, "predict_sprite", fake_predict)
    f = frame(ent(1, 5, 1002, 12, 10))
    out = lb.labels_for_v1(f, H, (784, 625), scene=None,  # type: ignore[arg-type]
                           state=lambda gid: state(gid, "idle", elapsed_ms=900.0),
                           sheet=lambda job: object(), k=0.1333)  # fmt: skip
    assert out == [] and seen == [None]  # idle phase unknown -> envelope; None -> no label


def test_a_v1_box_under_the_ui_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lb, "predict_sprite", lambda *a, **k: SimpleNamespace(
        box=(10.0, 10.0, 60.0, 60.0), box_kind="opaque", phase_known=False))  # fmt: skip
    f = frame(ent(1, 5, 1002, 12, 10))
    out = lb.labels_for_v1(f, H, (784, 625), scene=None,  # type: ignore[arg-type]
                           state=lambda gid: state(gid, "idle"), sheet=lambda job: object(),
                           k=0.1333)  # fmt: skip
    assert out == []  # under the Basic Information window (UI_RECTS): not a visible entity
