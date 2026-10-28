"""scripts/frigate_r3.py: the GPU sharing rules R2 + R3 (infra side, adopted by Batt 2026-10-07).

R3: stop if the Frigate detector is > 5 ms slower than its baseline (a 60 s median of DISTINCT
updates, so one spike is not a trip), stop HARD if a camera drops frames for 30 s, fail closed when
Frigate's stats go quiet. R2: refuse to start while Ollama has a model loaded, yield if one loads.
A due re-baseline stops a training step only right after an epoch ends.
"""

import importlib.util
import json
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "frigate_r3.py"


@pytest.fixture(scope="module")
def fr() -> ModuleType:
    spec = importlib.util.spec_from_file_location("frigate_r3", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stats(updated: int, inf: float = 28.0, det_fps: float = 30.0,
          cams: dict[str, tuple[float, float]] | None = None) -> dict[str, Any]:  # fmt: skip
    cams = cams or {"a": (5.0, 0.0), "b": (2.0, 0.0)}
    return {
        "service": {"last_updated": updated},
        "detectors": {"onnx": {"inference_speed": inf}, "onnx2": {"inference_speed": inf}},
        "detection_fps": det_fps,
        "cameras": {
            k: {"camera_fps": f, "skipped_fps": s, "process_fps": f - s}
            for k, (f, s) in cams.items()
        },  # fmt: skip
    }


def base(t_end: float, **over: Any) -> dict[str, Any]:
    b = {"t_end": t_end, "end": "x", "inference_median": 28.0, "detection_fps_median": 30.0,
         "cameras": {"a": {"camera_fps_median": 5.0, "skipped_nonzero_fraction": 0.0,
                           "skipped_p99": 0.0},
                     "b": {"camera_fps_median": 2.0, "skipped_nonzero_fraction": 0.1,
                           "skipped_p99": 0.5}}}  # fmt: skip
    b.update(over)
    return b


class Fake:
    def __init__(self) -> None:
        self.frigate: dict[str, Any] | None = stats(1)
        self.models: list[dict[str, Any]] = []
        self.ollama_up = True

    def __call__(self, url: str) -> dict[str, Any] | None:
        if url.endswith("/api/stats"):
            return self.frigate
        if url.endswith("/api/ps"):
            return {"models": self.models} if self.ollama_up else None
        raise AssertionError(url)


def step(guard: Any, fake: Fake, t: float, **kw: Any) -> Any:
    fake.frigate = stats(int(t), **kw)
    guard.poll(t)
    return guard.breach(t)


def test_latency_trips_on_the_60s_median_not_on_one_spike(fr: ModuleType) -> None:
    fake = Fake()
    g = fr.R3Guard(base(1000.0), fetch=fake, now=1000.0)
    t = 1000.0
    for inf in (28.0, 29.0, 50.0, 28.0):  # one spike inside the window: the median stays ~28
        t += 15
        assert step(g, fake, t, inf=inf) is None
    for _ in range(3):  # sustained +6 ms
        t += 15
        hit = step(g, fake, t, inf=34.0)
    assert hit is not None and hit[0] == "latency" and hit[2] is False
    assert "+6.0 > +5" in hit[1]


def test_latency_needs_three_distinct_updates(fr: ModuleType) -> None:
    fake = Fake()
    g = fr.R3Guard(base(0.0), fetch=fake, now=0.0)
    assert step(g, fake, 15.0, inf=60.0) is None
    for t in (16.0, 17.0, 18.0):  # the SAME update polled again is not a new sample
        g.poll(t)
        assert g.breach(t) is None
    assert len(g.lat) == 1
    assert step(g, fake, 30.0, inf=60.0) is None
    assert step(g, fake, 45.0, inf=60.0)[0] == "latency"


def test_a_camera_dropping_frames_for_30s_is_a_hard_stop(fr: ModuleType) -> None:
    fake = Fake()
    g = fr.R3Guard(base(0.0), fetch=fake, now=0.0)
    drop = {"a": (5.0, 1.2), "b": (2.0, 0.0)}
    assert step(g, fake, 15.0, cams=drop) is None
    assert step(g, fake, 30.0, cams=drop) is None  # 15 s so far
    hit = step(g, fake, 45.0, cams=drop)
    assert hit is not None and hit[0] == "drops" and hit[2] is True and "camera a" in hit[1]


def test_a_good_update_resets_the_drop_run(fr: ModuleType) -> None:
    fake = Fake()
    g = fr.R3Guard(base(0.0), fetch=fake, now=0.0)
    drop = {"a": (5.0, 1.2), "b": (2.0, 0.0)}
    step(g, fake, 15.0, cams=drop)
    step(g, fake, 30.0, cams=drop)
    assert step(g, fake, 40.0) is None  # recovered
    assert step(g, fake, 55.0, cams=drop) is None
    assert step(g, fake, 70.0, cams=drop) is None


def test_skips_within_the_cameras_own_baseline_floor_do_not_count(fr: ModuleType) -> None:
    """Camera b skipped in the baseline (p99 0.5): 0.4 is its normal, 0.9 is a drop."""
    fake = Fake()
    g = fr.R3Guard(base(0.0), fetch=fake, now=0.0)
    for t in (15.0, 30.0, 45.0, 60.0):
        assert step(g, fake, t, cams={"a": (5.0, 0.0), "b": (2.0, 0.4)}) is None
    for t in (75.0, 90.0):
        step(g, fake, t, cams={"a": (5.0, 0.0), "b": (2.0, 0.9)})
    assert step(g, fake, 105.0, cams={"a": (5.0, 0.0), "b": (2.0, 0.9)})[0] == "drops"


def test_a_camera_feed_below_half_its_baseline_counts_as_dropping(fr: ModuleType) -> None:
    fake = Fake()
    g = fr.R3Guard(base(0.0), fetch=fake, now=0.0)
    low = {"a": (2.0, 0.0), "b": (2.0, 0.0)}  # a: 2 fps vs its baseline 5
    for t in (15.0, 30.0):
        step(g, fake, t, cams=low)
    assert step(g, fake, 45.0, cams=low)[0] == "drops"


def test_frigate_quiet_for_60s_fails_closed(fr: ModuleType) -> None:
    fake = Fake()
    g = fr.R3Guard(base(0.0), fetch=fake, now=0.0)
    assert step(g, fake, 15.0) is None
    fake.frigate = None  # unreachable
    g.poll(70.0)
    assert g.breach(70.0) is None
    g.poll(76.0)
    hit = g.breach(76.0)
    assert hit is not None and hit[0] == "frigate_unreachable" and hit[2] is False
    fake.frigate = stats(15)  # reachable again but FROZEN (same last_updated) is still stale
    g.poll(80.0)
    assert g.breach(80.0)[0] == "frigate_unreachable"


def test_ollama_loading_a_model_mid_job_yields(fr: ModuleType) -> None:
    fake = Fake()
    g = fr.R3Guard(base(0.0), fetch=fake, now=0.0)
    assert step(g, fake, 15.0) is None
    fake.models = [{"name": "qwen3-vl:4b", "size_vram": 4_900_000_000}]
    hit = step(g, fake, 31.0)
    assert hit is not None and hit[0] == "r2_ollama_loaded" and "qwen3-vl:4b" in hit[1]


def test_a_rebaseline_waits_for_an_epoch_to_end(fr: ModuleType, tmp_path: Path) -> None:
    results = tmp_path / "results.csv"
    results.write_text("epoch,loss\n1,0.5\n")
    fake = Fake()
    t0 = 4 * 3600.0
    g = fr.R3Guard(base(0.0), fetch=fake, results_csv=results, now=t0)  # baseline 4 h old
    assert step(g, fake, t0 + 15) is None  # due, but mid-epoch
    results.write_text("epoch,loss\n1,0.5\n2,0.4\n")
    hit = step(g, fake, t0 + 30)
    assert hit is not None and hit[0] == "rebaseline_due" and "4.0 h old" in hit[1]
    no_csv = fr.R3Guard(base(0.0), fetch=fake, now=t0)  # eval/predict steps: never
    assert step(no_csv, fake, t0 + 45) is None


def test_a_changed_camera_activity_pattern_is_due(fr: ModuleType, tmp_path: Path) -> None:
    results = tmp_path / "results.csv"
    results.write_text("epoch\n")
    fake = Fake()
    g = fr.R3Guard(base(0.0), fetch=fake, results_csv=results, now=0.0)
    t = 0.0
    while t < 600:  # 10 min at 3x the baseline's detection rate
        t += 15
        step(g, fake, t, det_fps=90.0)
    assert g.rebaseline_reason(t) is not None and "activity" in g.rebaseline_reason(t)
    results.write_text("epoch\n1\n")
    assert step(g, fake, t + 15, det_fps=90.0)[0] == "rebaseline_due"


def test_prestart_refuses_on_r2_and_r3(fr: ModuleType, tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    fake = Fake()
    assert "no Frigate baseline" in fr.prestart(path, fetch=fake, apps=[])
    path.write_text(json.dumps(base(time.time() - 4 * 3600)))
    assert "h old" in fr.prestart(path, fetch=fake, apps=[])
    path.write_text(json.dumps(base(time.time())))
    assert fr.prestart(path, fetch=fake, apps=[("frigate.detector:onnx", 318)]) is None
    assert fr.prestart(path, fetch=fake, apps=[("/usr/bin/python3", 1450)]).startswith("R2")
    fake.models = [{"name": "qwen3-vl:4b"}]
    assert fr.prestart(path, fetch=fake, apps=[]).startswith("R2: Ollama")
    fake.models, fake.frigate = [], None
    assert "unreachable" in fr.prestart(path, fetch=fake, apps=[])
    fake.frigate, fake.ollama_up = stats(1), False  # Ollama down: nothing can be loaded
    assert fr.prestart(path, fetch=fake, apps=[]) is None


def test_the_baseline_summary_keeps_each_cameras_floor(fr: ModuleType) -> None:
    samples = [fr.parse_stats(stats(i, inf=28.0 + i % 3, cams={"a": (5.0, 0.0),
                                                               "b": (2.0, 0.5 if i == 3 else 0.0)}))
               for i in range(20)]  # fmt: skip
    s = fr.summarise(samples)
    assert s["updates"] == 20 and s["inference_median"] == 29.0
    assert s["cameras"]["a"]["skipped_nonzero_fraction"] == 0
    assert s["cameras"]["b"]["skipped_nonzero_fraction"] == 0.05


def test_the_watcher_stops_vision_containers_not_the_compose_client(fr: ModuleType) -> None:
    """2026-10-07: SIGINT to `timeout ... docker compose run` left the container training."""
    seen: list[list[str]] = []

    class R:
        stdout = "abc123\ndef456\n"

    def run(cmd: list[str], **kw: object) -> R:
        seen.append(cmd)
        return R()

    assert fr.vision_containers(run) == ["abc123", "def456"]
    assert seen == [["docker", "ps", "-q", "--filter", "label=com.docker.compose.service=vision"]]


def test_one_slow_stats_request_is_not_unreachable(fr: ModuleType) -> None:
    """2026-10-07 11:21:44: one slow GET refused a baseline while Frigate was updating normally."""
    answers = iter([None, stats(5)])
    assert fr.frigate_answers(lambda url: next(answers), sleep=lambda s: None) is True
    assert fr.frigate_answers(lambda url: None, sleep=lambda s: None) is False


# --- the PAIRED ON/OFF measurement (docs/operations/r3-paired.md, pre-registered 8c7f8ed) ---------


class Sim:
    """A Frigate whose stats refresh every 15 s; the ON effect and the load follow the phase."""

    def __init__(self, fr: ModuleType, g_phase: Any, on_ms: float, off_ms: float = 28.0,
                 load_on: float = 30.0, load_off: float = 30.0) -> None:  # fmt: skip
        self.fr, self.g_phase = fr, g_phase
        self.on_ms, self.off_ms, self.load_on, self.load_off = on_ms, off_ms, load_on, load_off
        self.t = 0.0
        self.cams: dict[str, tuple[float, float]] = {"a": (5.0, 0.0)}

    def __call__(self, url: str) -> dict[str, Any] | None:
        if url.endswith("/api/ps"):
            return {"models": []}
        on = self.g_phase() == "on"
        return stats(int(self.t // 15), inf=self.on_ms if on else self.off_ms,
                     det_fps=self.load_on if on else self.load_off, cams=self.cams)  # fmt: skip


def run(fr: ModuleType, short: bool, on_ms: float, seconds: float, **kw: Any) -> tuple[Any, list]:
    holder: dict[str, Any] = {}
    sim = Sim(fr, lambda: holder["g"].phase, on_ms, **kw)
    g = fr.PairedR3(short=short, fetch=sim, now=0.0)
    holder["g"] = g
    actions, hit = [], None
    while sim.t < seconds and hit is None:
        sim.t += 5
        a = g.tick(sim.t)
        if a:
            actions.append((sim.t, a))
        g.poll(sim.t)
        hit = g.breach(sim.t)
    return (g, hit), actions


def test_window_value_drops_the_settle_and_needs_enough_updates(fr: ModuleType) -> None:
    s = [(t, 30.0 + (t > 40) * 5, 20.0) for t in range(0, 180, 15)]
    assert fr.window_value(s, 0.0, 30.0, 6) == (35.0, 20.0, 10)
    assert fr.window_value(s, 0.0, 30.0, 11) is None


def test_pairs_use_the_adjacent_off_windows_and_similar_load(fr: ModuleType) -> None:
    ws = [{"phase": "off", "value": (28.0, 30.0, 9)}, {"phase": "on", "value": (35.0, 31.0, 9)},
          {"phase": "off", "value": (30.0, 32.0, 9)}, {"phase": "on", "value": (34.0, 45.0, 9)},
          {"phase": "off", "value": (29.0, 30.0, 9)}]  # fmt: skip
    p = fr.make_pairs(ws)
    assert [x["delta"] for x in p] == [6.0, 4.5] and [x["kept"] for x in p] == [True, False]
    assert p[0]["lat_off"] == 29.0 and p[1]["load_off"] == 31.0
    assert fr.verdict(p) == ("pending", 6.0, 1)
    four = [{"kept": True, "delta": d} for d in (6.0, 5.5, 4.0, 7.0)]
    assert fr.verdict(four)[0] == "trip"
    assert fr.verdict([{"kept": True, "delta": d} for d in (3.0, 5.0, 4.0, 7.0)])[0] == "pass"


def test_the_schedule_alternates_starting_on_and_a_real_effect_trips(fr: ModuleType) -> None:
    (g, hit), actions = run(fr, short=False, on_ms=34.5, seconds=4000)
    assert actions[:3] == [(180.0, "pause"), (360.0, "unpause"), (540.0, "pause")]
    assert hit is not None and hit[0] == "latency" and hit[2] is False and "+6.50 ms" in hit[1]
    assert sum(1 for p in g.pairs() if p["kept"]) >= 4


def test_a_small_effect_passes_into_monitoring(fr: ModuleType) -> None:
    (g, hit), actions = run(fr, short=False, on_ms=31.0, seconds=3600)
    assert hit is None and g.mode == "monitor"
    gaps = [b[0] - a[0] for a, b in zip(actions, actions[1:], strict=False)]
    assert MONITOR_ON in gaps  # 27 min ON once monitoring


MONITOR_ON = 27 * 60.0


def test_a_load_mismatch_is_never_a_verdict_and_ends_inconclusive(fr: ModuleType) -> None:
    """Frigate busier only while we run: no pair is like with like, so no trip -- and no pass."""
    (g, hit), _ = run(fr, short=False, on_ms=40.0, seconds=8000, load_on=45.0, load_off=25.0)
    assert hit is not None and hit[0] == "inconclusive"
    assert not any(p["kept"] for p in g.pairs())


def test_short_steps_use_one_minute_windows(fr: ModuleType) -> None:
    (g, hit), actions = run(fr, short=True, on_ms=31.0, seconds=900)
    assert actions[0] == (60.0, "pause") and hit is None and g.mode == "measure"


def test_drops_are_absolute_without_any_baseline(fr: ModuleType) -> None:
    holder: dict[str, Any] = {}
    sim = Sim(fr, lambda: holder["g"].phase, 28.0)
    sim.cams = {"a": (5.0, 0.3)}  # skipping, and no baseline floor any more
    g = fr.PairedR3(short=False, fetch=sim, now=0.0)
    holder["g"] = g
    hit = None
    while hit is None and sim.t < 120:
        sim.t += 5
        g.tick(sim.t)
        g.poll(sim.t)
        hit = g.breach(sim.t)
    assert hit is not None and hit[0] == "drops" and hit[2] is True


def test_r2_exempts_only_the_jobs_own_ollama_model(fr: ModuleType) -> None:
    """vlm_flag's own qwen3-vl is loaded by design; any OTHER model still yields (R2)."""
    loaded: list[dict[str, Any]] = [{"name": "qwen3-vl:4b"}]

    def fetch(url: str) -> dict[str, Any] | None:
        if url.endswith("/api/ps"):
            return {"models": loaded}
        return stats(0, inf=28.0, det_fps=30.0, cams={"a": (5.0, 0.0)})

    g = fr.PairedR3(short=False, fetch=fetch, now=0.0, allow_models=["qwen3-vl:4b"])
    g.poll(1.0)
    assert g.breach(1.0) is None
    loaded.append({"name": "llama3:8b"})
    g.last_ollama = -1e18
    g.poll(2.0)
    hit = g.breach(2.0)
    assert hit is not None and hit[0] == "r2_ollama_loaded" and "llama3:8b" in hit[1]
    assert "qwen3-vl" not in hit[1]
    plain = fr.PairedR3(short=False, fetch=fetch, now=0.0)
    plain.poll(1.0)
    assert plain.breach(1.0) is not None  # no exemption unless named


# --- the frame-drop resume gate (Batt, 2026-10-07 ~15:40) ---------------------------------------
def upd(i: int, skip: float = 0.0) -> dict[str, Any]:
    return {"updated": i, "inference": 30.0, "detection_fps": 40.0,
            "cameras": {"a": (5.0, skip), "b": (5.0, 0.0)}}  # fmt: skip


def test_the_quiet_gate_needs_15_observed_minutes_without_any_skip(fr: ModuleType) -> None:
    g = fr.QuietGate(15, now=0.0)
    for k, t in enumerate(range(0, 900, 15)):
        g.update(float(t), upd(k))
    assert not g.ready(885.0)
    g.update(900.0, upd(100))
    assert g.ready(900.0)
    g.update(905.0, upd(101, skip=1.5))  # a skip anywhere restarts the clock
    assert not g.ready(905.0) and g.drops == 1
    for k, t in enumerate(range(920, 1805, 15)):
        g.update(float(t), upd(200 + k))
    assert g.ready(1805.0)


def test_unobserved_time_never_counts_as_quiet(fr: ModuleType) -> None:
    g = fr.QuietGate(15, now=0.0)
    g.update(10.0, upd(1))
    g.update(400.0, None)  # Frigate silent for 390 s
    g.update(410.0, upd(2))
    for k, t in enumerate(range(420, 1300, 15)):
        g.update(float(t), upd(3 + k))
    assert not g.ready(1300.0)  # only 890 s observed since the gap
    g.update(1325.0, upd(999))
    assert g.ready(1325.0)


def test_the_quiet_command_returns_0_when_quiet_and_2_on_timeout(fr: ModuleType) -> None:
    clock = {"t": 0.0}

    def tick() -> float:
        clock["t"] += 15.0
        return clock["t"]

    k = {"i": 0}

    def fetch(url: str) -> dict[str, Any]:
        k["i"] += 1
        return stats(k["i"], cams={"a": (5.0, 0.0)})

    assert fr.quiet(15, 120, fetch=fetch, clock=tick, sleep=lambda s: None) == 0
    clock["t"] = 0.0

    def dropping(url: str) -> dict[str, Any]:
        k["i"] += 1
        return stats(k["i"], cams={"a": (5.0, 2.0)})

    assert fr.quiet(15, 30, fetch=dropping, clock=tick, sleep=lambda s: None) == 2


def test_a_frame_drop_abort_names_the_fleet_load(fr: ModuleType) -> None:
    holder: dict[str, Any] = {}
    sim = Sim(fr, lambda: holder["g"].phase, 28.0)
    sim.cams = {"a": (5.0, 0.3)}
    g = fr.PairedR3(short=False, fetch=sim, now=0.0)
    holder["g"] = g
    hit = None
    while hit is None and sim.t < 120:
        sim.t += 5
        g.tick(sim.t)
        g.poll(sim.t)
        hit = g.breach(sim.t)
    assert hit is not None and hit[2] is True
    assert "fleet 30.0 detections/s" in hit[1] and "skipping now: a" in hit[1]


# --- the adaptive duty cycle (Batt, 2026-10-07 ~16:25) ------------------------------------------
def feed(c: Any, t0: float, loads: list[float], dt: float = 15.0, skip: bool = False) -> list[int]:
    out = []
    for i, load in enumerate(loads):
        out.append(c.update(t0 + i * dt, load, skip))
    return out


def test_the_duty_target_follows_the_load_and_a_skip_is_the_floor(fr: ModuleType) -> None:
    assert [fr.duty_target(x, False) for x in (20, 40, 50, 55, 65, 90)] == [0, 1, 2, 3, 4, 4]
    assert fr.duty_target(10, True) == fr.DUTY_FLOOR


def test_up_is_immediate_and_down_is_one_level_after_three_updates_and_a_dwell(
    fr: ModuleType,
) -> None:
    c = fr.DutyController(0.0, start=0)
    assert c.update(15.0, 70.0, False) == 4  # a burst: straight to the floor
    levels = feed(c, 30.0, [20.0] * 12)
    assert levels[:2] == [4, 4]  # 3 lower updates AND >= 60 s since the change
    assert max(levels) == 4 and min(levels) >= 1
    steps = [b - a for a, b in zip(levels, levels[1:], strict=False) if b != a]
    assert all(s == -1 for s in steps)  # never more than one level at a time
    assert feed(c, 30.0 + 12 * 15.0, [20.0] * 30)[-1] == 0


def test_after_an_abort_the_walk_back_is_slower(fr: ModuleType) -> None:
    fast = fr.DutyController(0.0, start=4)
    slow = fr.DutyController(0.0, start=4, after_abort=True)
    lf, ls = feed(fast, 15.0, [20.0] * 20), feed(slow, 15.0, [20.0] * 20)
    assert lf[-1] < ls[-1]  # 180 s dwell vs 60 s


def test_the_latency_floor_and_the_three_abort_cap_bind(fr: ModuleType) -> None:
    c = fr.DutyController(0.0, start=0, minimum=2)
    assert feed(c, 15.0, [10.0] * 20)[-1] == 2  # never faster than the latency floor
    capped2 = fr.DutyController(0.0, start=4, cap_level=3, cap_until=3600.0)
    levels = feed(capped2, 15.0, [10.0] * 230)  # 15 .. 3450 s: still capped
    assert min(levels) == 3
    after = feed(capped2, 3600.0, [10.0] * 40)  # the cap lifts: down one level at a time
    assert after[-1] == 0


def test_a_silent_frigate_is_the_floor(fr: ModuleType) -> None:
    c = fr.DutyController(0.0, start=0)
    c.update(10.0, 20.0, False)
    assert c.tick(35.0) == 0
    assert c.tick(41.0) == fr.DUTY_FLOOR  # > 30 s without a fresh update


def test_time_per_level_is_accounted_and_the_duty_file_is_atomic(
    fr: ModuleType, tmp_path: Path
) -> None:
    c = fr.DutyController(0.0, start=0)
    c.update(100.0, 20.0, False)
    c.update(160.0, 70.0, False)  # -> the floor at t=160
    c.tick(200.0)
    s = c.summary()["seconds_per_level"]
    assert s["100ms"] == 160 and s["2000ms"] == 40
    f = tmp_path / "train-duty" / "duty.json"
    fr.write_duty(f, 2, 51.5, now=123.0)
    assert json.loads(f.read_text()) == {
        "level": 2,
        "sleep_ms": 400,
        "load": 51.5,
        "t_epoch": 123.0,
    }
    assert not list(f.parent.glob("*.tmp"))


# --- the TEMPORARY load hold on the resume gate (Batt, 2026-10-08 ~11:25) ------------------------
def upd_load(i: int, load: float, skip: float = 0.0) -> dict[str, Any]:
    return {"updated": i, "inference": 30.0, "detection_fps": load,
            "cameras": {"a": (5.0, skip), "b": (5.0, 0.0)}}  # fmt: skip


def test_the_load_hold_waits_for_the_rolling_load_after_the_quiet_minutes(fr: ModuleType) -> None:
    g = fr.QuietGate(15, now=0.0, max_load=60.0)
    for k, t in enumerate(range(0, 1200, 15)):  # 20 quiet minutes, but busy: 75 detections/s
        g.update(float(t), upd_load(k, 75.0))
    assert g.quiet_ok(1185.0) and not g.ready(1185.0)
    for k, t in enumerate(range(1200, 1500, 15)):  # 5 calmer minutes: the 10-min mean is ~57.5
        g.update(float(t), upd_load(100 + k, 40.0))
    assert g.rolling_load() == pytest.approx(57.5, abs=1.0) and g.ready(1485.0)
    g.update(1500.0, upd_load(999, 40.0, skip=1.0))  # a drop still restarts the quiet clock
    assert not g.ready(1500.0)


def test_no_hold_without_max_load_and_the_temporary_hold_has_exited(fr: ModuleType) -> None:
    g = fr.QuietGate(15, now=0.0)
    for k, t in enumerate(range(0, 915, 15)):
        g.update(float(t), upd_load(k, 85.0))
    assert g.ready(900.0)  # the continuous rule: quiet is enough
    # the EXIT (Batt, r3-paired.md): mid-epoch checkpoints merged AND re-proof 2 passed, 2026-10-11
    assert fr.TEMP_HOLD_MAX_LOAD is None


def test_the_quiet_command_holds_while_busy(
    fr: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    clock = {"t": 0.0}

    def tick() -> float:
        clock["t"] += 15.0
        return clock["t"]

    k = {"i": 0}

    def busy(url: str) -> dict[str, Any]:
        k["i"] += 1
        return stats(k["i"], det_fps=80.0, cams={"a": (5.0, 0.0)})

    assert fr.quiet(15, 40, fetch=busy, clock=tick, sleep=lambda s: None, max_load=60.0) == 2
    assert "held until it is below 60" in capsys.readouterr().out


def test_remeasure_starts_a_new_series_and_the_job_is_not_stopped(fr: ModuleType) -> None:
    """Batt 2026-10-08: after "inconclusive" the measurement starts over; the counting of cycles
    and pairs begins at the current window, so it is not inconclusive again at once."""
    (g, hit), _ = run(fr, short=False, on_ms=40.0, seconds=8000, load_on=45.0, load_off=25.0)
    assert hit is not None and hit[0] == "inconclusive"
    t = g.last_fresh + 1.0  # the moment of the trip, Frigate still answering
    g.remeasure(t)
    assert g.breach(t) is None and g.result[0] == "pending" and g.remeasures == 1
    assert g.summary()["remeasures"] == 1


def test_the_duty_hold_pins_the_slowest_level_until_released(fr: ModuleType) -> None:
    d = fr.DutyController(0.0, start=1)
    assert d.hold(1.0, True) == fr.DUTY_FLOOR and d.held
    for k in range(20):  # a light load would walk it down -- not while held
        d.update(2.0 + k, 5.0, False)
    assert d.level == fr.DUTY_FLOOR
    d.hold(30.0, False)
    t = 30.0
    for _ in range(fr.DUTY_DOWN_UPDATES + 2):
        t += fr.DUTY_DOWN_MIN_S_AFTER_ABORT + 1
        d.update(t, 5.0, False)
    assert d.level < fr.DUTY_FLOOR  # released: back down, one level at a time


# The R2 CO-TENANT exception (Batt 2026-10-28 ~13:2x): fit-first's VTON worker is the top priority
# on the GPU -- never touched, never stopped -- and our capped vision steps may run beside it.
VTON = b"/work/venv-diag-headless/bin/python\0-s\0-m\0fitfirst_vton_worker.session\0"
CMDS = {
    3167486: VTON,
    734616: b"frigate.detector:onnx\0",
    4242: b"python\0-m\0poring_vision.train\0",
}
ROWS = [
    (734616, "frigate.detector:onnx", 318),
    (3167486, "/work/venv-diag-headless/bin/python", 6376),
]


def test_a_co_tenant_is_matched_by_its_command_line_not_its_bare_python_name(
    fr: ModuleType,
) -> None:
    others, tenants = fr.split_cotenants(ROWS, fr.CO_TENANTS, lambda p: CMDS.get(p, b""))
    assert tenants == [(3167486, "/work/venv-diag-headless/bin/python", 6376)]
    assert others == [("frigate.detector:onnx", 318)]
    # without the exception (vlm_flag's plain R2) nothing is a co-tenant
    others, tenants = fr.split_cotenants(ROWS, (), lambda p: CMDS.get(p, b""))
    assert tenants == [] and len(others) == 2
    # a gone process (no cmdline) is never a co-tenant: it counts as a python job (fail closed)
    _, tenants = fr.split_cotenants(ROWS, fr.CO_TENANTS, lambda p: b"")
    assert tenants == []


def test_prestart_lets_a_co_tenant_stay_only_with_vram_for_our_cap_and_headroom(
    fr: ModuleType,
) -> None:
    fake = Fake()
    cmd = lambda p: CMDS.get(p, b"")  # noqa: E731
    total = 16311
    cap = int(total * fr.VISION_CAP_FRACTION)
    need = cap + fr.COTENANT_HEADROOM_MIB
    ok = (total - need, total)  # exactly enough free
    assert fr.prestart(None, fetch=fake, co_tenants=fr.CO_TENANTS, rows=ROWS, memory=ok,
                       cmdline=cmd) is None  # fmt: skip
    short = (total - need + 1, total)
    why = fr.prestart(None, fetch=fake, co_tenants=fr.CO_TENANTS, rows=ROWS, memory=short,
                      cmdline=cmd)  # fmt: skip
    assert why.startswith("R2 co-tenant:") and f"< our cap {cap} + headroom" in why
    assert "pid 3167486" in why
    # plain R2 (no co_tenants, e.g. vlm_flag): the same python process is "another job"
    assert fr.prestart(None, fetch=fake,
                       apps=[("/work/venv-diag-headless/bin/python", 6376)]).startswith(
        "R2: another job of ours")  # fmt: skip
    # a python job of OURS beside the co-tenant is still refused
    rows = [*ROWS, (4242, "python", 2000)]
    assert fr.prestart(None, fetch=fake, co_tenants=fr.CO_TENANTS, rows=rows, memory=ok,
                       cmdline=cmd).startswith("R2: another job of ours")  # fmt: skip
    # Ollama still refuses first
    fake.models = [{"name": "qwen3-vl:4b"}]
    assert fr.prestart(None, fetch=fake, co_tenants=fr.CO_TENANTS, rows=ROWS, memory=ok,
                       cmdline=cmd).startswith("R2: Ollama")  # fmt: skip


def test_prestart_fails_closed_when_nvidia_smi_cannot_be_read(
    fr: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = Fake()
    monkeypatch.setattr(fr, "gpu_apps", lambda: None)
    assert fr.prestart(None, fetch=fake, co_tenants=fr.CO_TENANTS) == (
        "R2: nvidia-smi unreadable (fail closed)")  # fmt: skip
    monkeypatch.setattr(fr, "gpu_memory", lambda: None)
    why = fr.prestart(None, fetch=fake, co_tenants=fr.CO_TENANTS, rows=ROWS,
                      cmdline=lambda p: CMDS.get(p, b""))  # fmt: skip
    assert why.startswith("R2 co-tenant: VRAM unreadable")


def test_pmon_rows_say_whether_a_process_computes(fr: ModuleType) -> None:
    """Real `nvidia-smi pmon -s u` rows (2026-10-28 13:2x): the VTON worker held 6376 MiB idle."""
    assert fr.parse_pmon("# gpu         pid   type     sm    mem    enc    dec    jpg    ofa    "
                         "command ") is None  # fmt: skip
    assert fr.parse_pmon("# Idx           #    C/G      %      %      %      %      %      %  "
                         "  name ") is None  # fmt: skip
    idle = "    0    3167486     C      -      -      -      -      -      -    python         "
    busy = "    0    3167486     C     37     12      -      -      -      -    python         "
    assert fr.parse_pmon(idle) == (3167486, False)
    assert fr.parse_pmon(busy) == (3167486, True)
    assert fr.parse_pmon("") is None


def test_the_watch_yields_while_the_co_tenant_computes_and_30_s_after(fr: ModuleType) -> None:
    w = fr.CoTenantWatch(fr.CO_TENANTS, cmdline=lambda p: CMDS.get(p, b""))
    frigate_busy = "    0     734616     C     20      5      -      -      -      -    frigate"
    w.feed(frigate_busy, 100.0)
    assert not w.yielding(100.0)  # Frigate computing is not a co-tenant
    w.feed("    0    3167486     C      -      -      -      -      -      -    python", 101.0)
    assert not w.yielding(101.0)  # holding memory idle is not computing
    w.feed("    0    3167486     C     55     20      -      -      -      -    python", 102.0)
    assert w.yielding(102.0) and w.yielding(102.0 + fr.YIELD_HOLD_S)
    assert not w.yielding(102.1 + fr.YIELD_HOLD_S)
    assert w.busy_samples == 1


def test_the_watch_trips_on_free_vram_beside_a_co_tenant_only(fr: ModuleType) -> None:
    cmd = lambda p: CMDS.get(p, b"")  # noqa: E731
    total = 16311
    w = fr.CoTenantWatch(fr.CO_TENANTS, cmdline=cmd)
    low = (total - fr.COTENANT_FLOOR_MIB + 1, total)
    why = w.vram_trip(0.0, rows=ROWS, memory=low)
    assert why.startswith("R2 co-tenant:") and "< the floor 1024 MiB" in why
    assert w.vram_trip(1.0, rows=ROWS, memory=low) is None  # read at most every 10 s
    w = fr.CoTenantWatch(fr.CO_TENANTS, cmdline=cmd)
    assert w.vram_trip(0.0, rows=ROWS, memory=(total - 3000, total)) is None
    w = fr.CoTenantWatch(fr.CO_TENANTS, cmdline=cmd)
    no_tenant = [(734616, "frigate.detector:onnx", 318)]
    assert w.vram_trip(0.0, rows=no_tenant, memory=(total - 10, total)) is None
    tenants = [(3167486, "/work/venv-diag-headless/bin/python", 6376)]
    assert fr.cotenant_vram(None, 1024, "the floor", tenants).startswith(
        "R2 co-tenant: VRAM unreadable")  # fail closed  # fmt: skip
    assert fr.cotenant_vram(None, 1024, "the floor", []) is None  # no co-tenant: plain R2 rules


def test_the_duty_file_carries_the_yield_sleep(fr: ModuleType, tmp_path: Path) -> None:
    f = tmp_path / "duty.json"
    fr.write_duty(f, 1, 30.0, 1000.0)
    assert json.loads(f.read_text())["sleep_ms"] == fr.DUTY_LEVELS_MS[1]
    fr.write_duty(f, 1, 30.0, 1000.0, fr.YIELD_MS)
    d = json.loads(f.read_text())
    assert d["sleep_ms"] == 10_000 and d["level"] == 1
    # the trainer accepts it (train.py read_duty: 0..10_000 ms, else its fallback)
    assert fr.YIELD_MS <= 10_000
