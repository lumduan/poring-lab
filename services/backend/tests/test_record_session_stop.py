"""scripts/record_session.py ends a recording CLEANLY on SIGINT/SIGTERM (2026-10-05: the M4 re-run
stops it when its spawns are done): the signal only sets a flag, the loop ends as on its duration,
and the shards + manifest are finalised -- an uncaught KeyboardInterrupt skipped that."""

import importlib.util
import signal
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def test_a_signal_only_sets_the_stop_flag() -> None:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("record_session", SCRIPTS / "record_session.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.STOP == {"flag": False}
    mod.request_stop(signal.SIGINT, None)
    assert mod.STOP["flag"] is True
    src = (SCRIPTS / "record_session.py").read_text()
    assert src.count('while time.monotonic() < t_end and not STOP["flag"]:') == 2  # png and h264
    assert src.count('stop_reason = "stopped by signal"') == 2


MOUNTS = """\
/dev/mapper/ubuntu--vg-ubuntu--lv / ext4 rw,relatime 0 0
tmpfs /dev/shm tmpfs rw,nosuid,nodev 0 0
192.168.1.6:/mnt/tank-main/poring-lab/datasets /mnt/poring-lab-datasets nfs4 rw 0 0
"""


def _rs() -> object:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("record_session", SCRIPTS / "record_session.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_io_rule_follows_the_sink_ram_is_sustained_only_and_a_disk_keeps_the_spike() -> None:
    """Batt 2026-10-28 ~13:2x (gef10-detector.md 13y): a recording on RAM writes nothing to the
    disk shared with capture, so it stops only on 30 s of stall above 30 %; any other sink (the
    default /home/batt/poring-lab-rec is the root disk) keeps the tolerant one-spike rule."""
    rs: Any = _rs()
    assert rs.fs_type(Path("/dev/shm/poring-lab-rec"), MOUNTS) == "tmpfs"
    assert rs.fs_type(Path("/dev/shm"), MOUNTS) == "tmpfs"
    assert rs.fs_type(Path("/home/batt/poring-lab-rec"), MOUNTS) == "ext4"
    assert rs.fs_type(Path("/dev/shmx/rec"), MOUNTS) == "ext4"  # a prefix that is not a mount
    assert rs.fs_type(Path("/mnt/poring-lab-datasets/x"), MOUNTS) == "nfs4"
    assert rs.guard_rule(Path("/dev/shm/poring-lab-rec"), MOUNTS) == {
        "threshold": 30.0, "sustain": 30.0, "spike": None}  # fmt: skip
    assert rs.guard_rule(Path("/home/batt/poring-lab-rec"), MOUNTS) == {
        "threshold": 10.0, "sustain": 30.0, "spike": 25.0}  # fmt: skip
    assert rs.guard_rule(Path("/mnt/poring-lab-datasets/x"), MOUNTS) == rs.DISK_RULE
    assert rs.guard_rule(Path("/dev/shm/x"), "") == rs.DISK_RULE  # unknown -> disk (fail safe)
    src = (SCRIPTS / "record_session.py").read_text()
    assert src.count("guard = load_guard(a.out)") == 2  # png and h264
    assert src.count('"guard_rule": guard.describe(),') == 2


def test_the_ram_rule_ignores_a_spike_and_stops_on_sustained_stall(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The same Guard, the two rules, on one scripted capture cgroup: a 2-s burst at 60 % trips the
    disk rule and not the RAM rule; 30 s above 30 % trips both."""
    rs: Any = _rs()
    gb_spec = importlib.util.spec_from_file_location("guarded_build", SCRIPTS / "guarded_build.py")
    assert gb_spec and gb_spec.loader
    gb: Any = importlib.util.module_from_spec(gb_spec)
    gb_spec.loader.exec_module(gb)
    clock = {"t": 0.0}
    monkeypatch.setattr(gb.time, "monotonic", lambda: clock["t"])

    def run(rule: dict[str, Any], stall_pct: list[float]) -> object:
        f = tmp_path / "io.pressure"
        total = 0
        f.write_text(f"some avg10=0 total=0\nfull avg10=0 avg60=0 avg300=0 total={total}\n")
        clock["t"] = 0.0
        g = gb.Guard({"cg": f}, rule["threshold"], 1.0, sustain=rule["sustain"],
                     spike=rule["spike"])  # fmt: skip
        g.breach()
        for pct in stall_pct:
            clock["t"] += 1.0
            total += int(pct * 1e4)  # pct % of one second, in microseconds
            f.write_text(f"some avg10=0 total=0\nfull avg10=0 avg60=0 avg300=0 total={total}\n")
            hit = g.breach()
            if hit:
                return hit
        return None

    burst = [2.0] * 5 + [60.0, 60.0] + [2.0] * 40
    sustained = [2.0] * 5 + [35.0] * 40
    assert run(rs.DISK_RULE, burst) is not None
    assert run(rs.RAM_RULE, burst) is None
    hit = run(rs.RAM_RULE, sustained)
    assert hit is not None and "above 30.0% for" in hit[2]
    assert run(rs.DISK_RULE, sustained) is not None
