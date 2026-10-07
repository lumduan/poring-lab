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
