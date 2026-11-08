"""The hardware monitor (hardware.py, routes_hardware.py; Batt 2026-11-08): parsers against
fixture /proc + /sys trees, the delta math (CPU %, watts, RC6 busy, counter resets), every sensor
optional (null + a reason, logged once, the task never dies), and GET /hardware's shape and who may
call it (never the agent's :8001)."""

import asyncio
import logging
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from poring_backend import hardware as hw
from poring_backend.config import Settings
from poring_backend.main import create_app

ORIGIN = "http://lab.test:3000"
LAN = ("192.168.1.20", 40000)
S = 10**9  # ns


class Clock:
    def __init__(self) -> None:
        self.ns = 1_000 * S

    def __call__(self) -> int:
        return self.ns

    def tick(self, seconds: float = 2.0) -> None:
        self.ns += int(seconds * S)


def put(root: Path, rel: str, text: str | int) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{text}\n")
    return path


def stat_text(total: tuple[int, ...], cores: list[tuple[int, ...]]) -> str:
    lines = ["cpu  " + " ".join(map(str, total))]
    lines += [f"cpu{i} " + " ".join(map(str, c)) for i, c in enumerate(cores)]
    return "\n".join(lines + ["intr 1 2 3", "ctxt 99"])


MEMINFO = """MemTotal:       16000000 kB
MemFree:         2000000 kB
MemAvailable:   12000000 kB
Cached:          9000000 kB
SwapTotal:       4000000 kB
SwapFree:        3000000 kB
Shmem:           1000000 kB
HugePages_Total:       0"""

CPUINFO = """processor\t: 0
model name\t: Intel(R) Xeon(R) CPU E5-2609 v4 @ 1.70GHz
cpu MHz\t\t: 1197.468

processor\t: 1
model name\t: Intel(R) Xeon(R) CPU E5-2609 v4 @ 1.70GHz
cpu MHz\t\t: 1700.000
"""


def link(path: Path, target: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(target)


def host_tree(root: Path) -> Path:
    """A small bot-server: 2 cores, coretemp + a tg3 NIC + the ACPI power meter + an Arc on i915
    (card1; card0 is the BMC's mgag200), RAPL root-only."""
    put(root, "proc/stat", stat_text((100, 0, 100, 800, 0, 0, 0, 0), [(50, 0, 50, 400, 0)] * 2))
    put(root, "proc/meminfo", MEMINFO)
    put(root, "proc/loadavg", "0.51 0.49 0.41 1/684 645219")
    put(root, "proc/cpuinfo", CPUINFO)
    put(root, "sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", 1197339)
    put(root, "sys/devices/system/cpu/cpu1/cpufreq/scaling_cur_freq", 1496928)
    hwmon = root / "sys/class/hwmon"
    # hwmon0: coretemp (labels), hwmon1: tg3 named by its interface, hwmon2: the power meter
    put(hwmon, "hwmon0/name", "coretemp")
    for n, label, c in ((1, "Package id 0", 35000), (2, "Core 0", 27000), (3, "Core 1", 29000)):
        put(hwmon, f"hwmon0/temp{n}_label", label)
        put(hwmon, f"hwmon0/temp{n}_input", c)
        put(hwmon, f"hwmon0/temp{n}_max", 78000)
        put(hwmon, f"hwmon0/temp{n}_crit", 88000)
    put(hwmon, "hwmon1/name", "tg3")
    put(hwmon, "hwmon1/temp1_input", 52000)
    put(hwmon, "hwmon1/temp1_max", 100000)
    (hwmon / "hwmon1/device/net/eno1").mkdir(parents=True)
    put(hwmon, "hwmon2/name", "power_meter")
    put(hwmon, "hwmon2/power1_average", 69000000)
    put(hwmon, "hwmon2/power1_average_interval", 300000)
    # the GPU: its hwmon lives under the PCI device, /sys/class/hwmon links to it
    drm = root / "sys/class/drm"
    (drm / "card0/device").mkdir(parents=True)
    link(drm / "card0/device/driver", "../../bus/pci/drivers/mgag200")
    (drm / "card0-VGA-1").mkdir()
    card = drm / "card1"
    link(card / "device/driver", "../../bus/pci/drivers/i915")
    put(card, "device/vendor", "0x8086")
    put(card, "device/device", "0x56a5")
    gpu_hwmon = card / "device/hwmon/hwmon3"
    put(gpu_hwmon, "name", "i915")
    put(gpu_hwmon, "temp1_input", 50000)
    put(gpu_hwmon, "energy1_input", 1_000_000_000)
    put(gpu_hwmon, "power1_max", 43000000)
    put(gpu_hwmon, "fan1_input", 146)
    link(hwmon / "hwmon3", str(gpu_hwmon))
    put(card, "gt_act_freq_mhz", 0)
    put(card, "gt_cur_freq_mhz", 1450)
    put(card, "gt_max_freq_mhz", 2450)
    put(card, "gt/gt0/rc6_residency_ms", 10_000)
    (drm / "card1-DP-1").mkdir()
    rapl = root / "sys/class/powercap/intel-rapl:0"
    put(rapl, "energy_uj", 123).chmod(0o000)  # root only on the host (mode 0400 root)
    put(rapl, "max_energy_range_uj", 262143328850)
    return root


def monitor(root: Path, clock: Clock, **kw: Any) -> hw.HardwareMonitor:
    return hw.HardwareMonitor(root, clock=clock, wall=lambda: 1.0e9, **kw)


def advance(root: Path, clock: Clock) -> None:
    """2 s later: CPU 25 % busy in total (100 of 400 jiffies; iowait counts as idle), cpu0 50 %,
    cpu1 0 %; the GPU used 20 J (10 W) and spent 1.5 s of the 2 s in RC6 (25 % busy)."""
    clock.tick(2.0)
    cores = [(100, 0, 100, 500, 0), (50, 0, 50, 600, 0)]
    put(root, "proc/stat", stat_text((150, 0, 150, 1050, 50, 0, 0, 0), cores))
    put(root, "sys/class/drm/card1/device/hwmon/hwmon3/energy1_input", 1_020_000_000)
    put(root, "sys/class/drm/card1/gt/gt0/rc6_residency_ms", 11_500)


# --- the pure parts -------------------------------------------------------------------------------


def test_proc_parsers() -> None:
    times = hw.cpu_times(stat_text((1, 2, 3, 4, 5, 6, 7, 8, 9, 10), [(1, 0, 1, 2)]))
    # busy = user+nice+system+irq+softirq+steal; idle+iowait excluded; guest (in user) not twice
    assert times == {"cpu": (1 + 2 + 3 + 6 + 7 + 8, 36), "cpu0": (2, 4)}
    assert hw.busy_pct(None, (5, 10)) is None
    assert hw.busy_pct((0, 0), (25, 100)) == 25.0
    assert hw.busy_pct((10, 100), (10, 100)) is None  # no time between them
    assert hw.busy_pct((10, 100), (5, 200)) is None  # went back
    mem = hw.parse_meminfo(MEMINFO)
    assert mem["MemTotal"] == 16000000 * 1024 and mem["HugePages_Total"] == 0
    assert hw.parse_loadavg("0.51 0.49 0.41 1/684 645219") == [0.51, 0.49, 0.41]
    assert hw.parse_cpuinfo(CPUINFO) == (
        "Intel(R) Xeon(R) CPU E5-2609 v4 @ 1.70GHz",
        [1197.468, 1700.0],
    )


def test_counter_rate_handles_the_first_reading_a_reset_and_a_wrap() -> None:
    assert hw.counter_rate(None, 5, S) == (None, "warming up")
    assert hw.counter_rate((100, 0), 300, 2 * S) == (100.0, None)
    assert hw.counter_rate((100, S), 300, S) == (None, "no time between samples")
    assert hw.counter_rate((300, 0), 100, S) == (None, "counter reset")  # driver reload
    # RAPL wraps at max_energy_range_uj: 990 -> 10 over a range of 1000 is 20 units
    assert hw.counter_rate((990, 0), 10, S, wrap=1000) == (20.0, None)


def test_root_only_is_named_from_the_files_owner_and_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "energy_uj"
    path.write_text("1\n")
    real = os.stat(path)

    def as_root(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        fields = list(real)
        fields[0], fields[4] = 0o100400, 0  # st_mode r-------- , st_uid root
        return os.stat_result(fields)

    monkeypatch.setattr(Path, "stat", as_root)
    assert hw._denied(path) == "root only"
    monkeypatch.undo()
    path.chmod(0o640)
    assert hw._denied(path) == "permission denied"  # ours, not root's


# --- one host, sampled twice ----------------------------------------------------------------------


def test_a_full_sample_and_its_rates(tmp_path: Path) -> None:
    root, clock = host_tree(tmp_path / "host"), Clock()
    shm = tmp_path / "shm"
    shm.mkdir()
    m = monitor(root, clock, shm_path=shm, disk_path=tmp_path)
    first = m.sample()
    assert first.cpu.busy_pct is None and first.na["cpu.busy_pct"] == "warming up"
    assert first.gpu is not None and first.gpu.power_w is None
    assert first.na["gpu.power_w"] == first.na["gpu.busy_pct"] == "warming up"
    advance(root, clock)
    s = m.sample()
    assert s.seq == 2 and s.t_mono_ns == clock.ns
    assert s.cpu.busy_pct == 25.0
    assert s.cpu.core_pct == [50.0, 0.0]
    assert s.cpu.cores == 2
    assert s.cpu.model == "Intel(R) Xeon(R) CPU E5-2609 v4 @ 1.70GHz"
    assert (s.cpu.core_mhz, s.cpu.mhz_source) == ([1197, 1497], "cpufreq")
    assert s.cpu.load == [0.51, 0.49, 0.41]
    gib = 1024
    assert s.memory.total_b == 16000000 * gib and s.memory.used_b == 4000000 * gib
    assert s.memory.swap_used_b == 1000000 * gib and s.memory.shmem_b == 1000000 * gib
    assert s.shm is not None and s.shm.path == str(shm) and s.shm.limit_b == hw.SHM_LIMIT_B
    assert s.disk is not None and s.disk.total_b > 0 and s.disk.limit_b is None
    gpu = s.gpu
    assert gpu is not None
    assert (gpu.vendor, gpu.driver, gpu.card, gpu.pci_id, gpu.name) == (
        "intel", "i915", "card1", "8086:56a5", "Intel Arc A380",
    )  # fmt: skip
    assert gpu.power_w == 10.0  # 20 J in 2 s
    assert gpu.busy_pct == 25.0  # 1.5 s of 2 s in RC6
    assert (gpu.temp_c, gpu.power_max_w, gpu.fan_rpm) == (50.0, 43.0, 146)
    assert (gpu.freq_act_mhz, gpu.freq_cur_mhz, gpu.freq_max_mhz) == (0, 1450, 2450)
    assert gpu.vram_used_b is None and s.na["gpu.vram_used_b"] == hw.VRAM_NA
    labels = [(t.chip, t.label, t.c, t.max_c, t.crit_c) for t in s.temps]
    assert labels == [
        ("coretemp", "Package id 0", 35.0, 78.0, 88.0),
        ("coretemp", "Core 0", 27.0, 78.0, 88.0),
        ("coretemp", "Core 1", 29.0, 78.0, 88.0),
        ("tg3", "eno1", 52.0, 100.0, None),  # a NIC's sensor is named by its interface
        ("i915", "i915", 50.0, None, None),
    ]
    assert (s.power.server_w, s.power.server_avg_s) == (69.0, 300.0)
    assert (s.power.gpu_w, s.power.gpu_max_w) == (10.0, 43.0)
    if os.geteuid() != 0:  # root reads a mode-000 file anyway
        assert s.power.cpu_pkg_w is None and s.na["power.cpu_pkg_w"] == "permission denied"
    assert "cpu.busy_pct" not in s.na and "gpu.power_w" not in s.na


def test_a_counter_reset_is_null_with_its_reason_then_recovers(tmp_path: Path) -> None:
    root, clock = host_tree(tmp_path), Clock()
    m = monitor(root, clock)
    m.sample()
    advance(root, clock)
    m.sample()
    clock.tick(2.0)  # the driver reloaded: both counters restart near zero
    put(root, "sys/class/drm/card1/device/hwmon/hwmon3/energy1_input", 5_000_000)
    put(root, "sys/class/drm/card1/gt/gt0/rc6_residency_ms", 100)
    s = m.sample()
    assert s.gpu is not None and s.gpu.power_w is None and s.gpu.busy_pct is None
    assert s.na["gpu.power_w"] == s.na["gpu.busy_pct"] == "counter reset"
    assert s.power.gpu_w is None and s.na["power.gpu_w"] == "counter reset"
    clock.tick(2.0)
    put(root, "sys/class/drm/card1/device/hwmon/hwmon3/energy1_input", 15_000_000)
    put(root, "sys/class/drm/card1/gt/gt0/rc6_residency_ms", 2100)
    s = m.sample()
    assert s.gpu is not None and (s.gpu.power_w, s.gpu.busy_pct) == (5.0, 0.0)


def test_the_rapl_wraparound_is_unwound(tmp_path: Path) -> None:
    root, clock = host_tree(tmp_path), Clock()
    energy = root / "sys/class/powercap/intel-rapl:0/energy_uj"
    energy.chmod(0o644)  # as if Batt granted the read (an option, never done by us)
    put(root, "sys/class/powercap/intel-rapl:0/max_energy_range_uj", 100_000_000)
    put(root, "sys/class/powercap/intel-rapl:0/energy_uj", 90_000_000)
    m = monitor(root, clock)
    assert m.sample().na["power.cpu_pkg_w"] == "warming up"
    clock.tick(2.0)
    put(root, "sys/class/powercap/intel-rapl:0/energy_uj", 30_000_000)  # 40 J later, wrapped
    assert m.sample().power.cpu_pkg_w == 20.0


def test_rapl_masked_in_a_container_says_so(tmp_path: Path) -> None:
    root = host_tree(tmp_path)
    rapl = root / "sys/class/powercap/intel-rapl:0"
    for f in rapl.iterdir():
        f.chmod(0o644)
        f.unlink()
    rapl.rmdir()
    link(rapl, "../../devices/virtual/powercap/intel-rapl/intel-rapl:0")  # the target is masked
    s = monitor(root, Clock()).sample()
    assert s.power.cpu_pkg_w is None
    assert s.na["power.cpu_pkg_w"] == "masked in this container (root only on the host)"


def test_the_power_meter_is_read_at_most_every_10_s(tmp_path: Path) -> None:
    root, clock = host_tree(tmp_path), Clock()
    m = monitor(root, clock)
    assert m.sample().power.server_w == 69.0
    put(root, "sys/class/hwmon/hwmon2/power1_average", 80000000)
    clock.tick(2.0)
    assert m.sample().power.server_w == 69.0  # the ACPI read is not repeated within 10 s
    clock.tick(hw.POWER_METER_EVERY_S)
    assert m.sample().power.server_w == 80.0


def test_mhz_falls_back_to_cpuinfo(tmp_path: Path) -> None:
    root = host_tree(tmp_path)
    for n in (0, 1):
        (root / f"sys/devices/system/cpu/cpu{n}/cpufreq/scaling_cur_freq").unlink()
    s = monitor(root, Clock()).sample()
    assert (s.cpu.core_mhz, s.cpu.mhz_source) == ([1197, 1700], "cpuinfo")


# --- every sensor is optional --------------------------------------------------------------------


def test_an_empty_host_gives_nulls_with_reasons_never_an_exception(tmp_path: Path) -> None:
    m = monitor(tmp_path, Clock())
    s = m.sample()
    assert s.cpu.busy_pct is None and s.cpu.cores is None and s.cpu.load is None
    assert s.memory.total_b is None and s.temps == [] and s.gpu is None
    assert (s.shm, s.disk) == (None, None)
    assert s.na == {
        "cpu.busy_pct": "absent",
        "cpu.model": "absent",
        "cpu.core_mhz": "absent",
        "cpu.load": "absent",
        "memory": "absent",
        "shm": "the host's /dev/shm is not mounted here",
        "disk": "no disk path configured",
        "gpu": "no DRM card",
        "power.gpu_w": "no GPU",
        "power.server_w": "no ACPI power meter",
        "power.cpu_pkg_w": "absent",
    }
    m.record(s)
    view = m.view(s.t_mono_ns)
    assert view.current is not None and view.history.series["cpu_pct"] == [None]


def test_a_bug_in_one_section_nulls_that_section_not_the_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = host_tree(tmp_path)
    put(root, "proc/stat", "cpu0 1 2 3 4 5")  # no aggregate line: an unexpected layout
    m = monitor(root, Clock())

    def broken(probe: hw.Probe, t_ns: int) -> hw.Gpu | None:
        raise KeyError("an unexpected layout")

    monkeypatch.setattr(m, "_read_gpu", broken)
    s = m.sample()
    assert s.cpu.busy_pct is None and s.cpu.cores == 1
    assert s.gpu is None and s.na["gpu"] == "error (KeyError)"
    assert s.power.server_w == 69.0 and len(s.temps) == 5  # the other sections stand


def test_a_missing_statvfs_path_is_null(tmp_path: Path) -> None:
    s = monitor(tmp_path, Clock(), disk_path=tmp_path / "gone").sample()
    assert s.disk is None and s.na["disk"] == f"{tmp_path / 'gone'} absent"


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a mode-000 file anyway")
def test_an_unreadable_sensor_is_skipped_and_logged_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root, clock = host_tree(tmp_path), Clock()
    (root / "sys/class/hwmon/hwmon1/temp1_input").chmod(0o000)
    m = monitor(root, clock)
    with caplog.at_level(logging.INFO, logger="poring_backend.hardware"):
        for _ in range(3):
            s = m.sample()
            clock.tick(2.0)
    assert [t.label for t in s.temps if t.chip == "tg3"] == []
    assert s.na["temps.hwmon1.temp1"] == "permission denied"
    logged = [r for r in caplog.records if "temps.hwmon1.temp1" in r.getMessage()]
    assert len(logged) == 1


def test_a_garbled_file_is_unparsable_and_logged_as_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = host_tree(tmp_path)
    put(root, "sys/class/drm/card1/gt_cur_freq_mhz", "fast")
    with caplog.at_level(logging.INFO, logger="poring_backend.hardware"):
        s = monitor(root, Clock()).sample()
    assert s.gpu is not None and s.gpu.freq_cur_mhz is None
    assert s.na["gpu.freq_cur_mhz"] == "unparsable"
    assert any(r.levelno == logging.WARNING and "freq_cur_mhz" in r.getMessage()
               for r in caplog.records)  # fmt: skip


def test_other_gpus_are_null_with_the_reason(tmp_path: Path) -> None:
    drm = tmp_path / "sys/class/drm"
    (drm / "card0/device").mkdir(parents=True)
    link(drm / "card0/device/driver", "../../bus/pci/drivers/nvidia")
    s = monitor(tmp_path, Clock()).sample()
    assert s.gpu is None and s.na["gpu"] == "no reader for nvidia (by design: no nvidia-smi)"
    (drm / "card0/device/driver").unlink()
    link(drm / "card0/device/driver", "../../bus/pci/drivers/mgag200")
    assert hw.find_gpu(tmp_path) == (None, "no reader for card0 mgag200")


# --- the ring and the task ------------------------------------------------------------------------


def test_the_history_ring_is_columns_relative_to_the_newest_sample(tmp_path: Path) -> None:
    root, clock = host_tree(tmp_path), Clock()
    m = monitor(root, clock, history=3)
    for _ in range(4):
        m.record(m.sample())
        advance(root, clock)
    view = m.view(clock.ns)
    assert view.history_len == 3 and view.history.t_s == [-4.0, -2.0, 0.0]
    assert set(view.history.series) == set(hw.SERIES)
    assert all(len(v) == 3 for v in view.history.series.values())
    assert view.history.series["cpu_temp_c"] == [35.0, 35.0, 35.0]  # the package sensor
    assert view.history.series["server_w"] == [69.0, 69.0, 69.0]
    assert view.age_s == 2.0  # clock.ns moved on after the newest sample
    assert view.current is not None and view.current.seq == 4


async def test_the_task_survives_a_failing_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    m = hw.HardwareMonitor(host_tree(tmp_path), period_s=0.01)
    real = m.sample
    calls = {"n": 0}

    def flaky() -> hw.Sample:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("a bug")
        return real()

    monkeypatch.setattr(m, "sample", flaky)
    m.start()
    for _ in range(200):
        if m.view().current is not None:
            break
        await asyncio.sleep(0.01)
    await m.stop()
    assert calls["n"] >= 2 and m.view().current is not None


# --- GET /hardware --------------------------------------------------------------------------------


class NoCapture:
    def grab(self) -> Any:
        raise RuntimeError("no X in this test")

    def close(self) -> None:
        pass


class NoInput:
    def send_many(self, events: Any) -> None:
        pass

    def pointer(self) -> tuple[int, int]:
        return (0, 0)

    def has_window_class(self, needle: str) -> bool:
        return False

    def close(self) -> None:
        pass


@pytest.fixture
def make(tmp_path: Path) -> Iterator[Any]:
    clients: list[TestClient] = []

    def factory(peer: tuple[str, int] = LAN, **overrides: Any) -> TestClient:
        fields: dict[str, Any] = {
            "data_dir": tmp_path / "data", "public_port": 80, "frontend_origins": ORIGIN,
            "lab_state_dir": tmp_path / "lab-state", "hardware_root": host_tree(tmp_path / "h"),
            "hardware_period_s": 0.05,
        }  # fmt: skip
        fields.update(overrides)
        (tmp_path / "lab-state").mkdir(exist_ok=True)
        (tmp_path / "data").mkdir(exist_ok=True)
        app = create_app(Settings(**fields), capture_factory=NoCapture, input_factory=NoInput)
        client = TestClient(app, client=peer)
        client.__enter__()
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


def wait_for_samples(client: TestClient, n: int = 2) -> dict[str, Any]:
    body: dict[str, Any] = {}
    for _ in range(400):
        body = client.get("/hardware").json()
        if len(body["history"]["t_s"]) >= n:
            return body
        time.sleep(0.01)
    raise AssertionError(f"no {n} samples: {body}")


def test_the_route_serves_the_sample_and_history(make: Any, tmp_path: Path) -> None:
    client = make()
    body = wait_for_samples(client)
    assert set(body) == {"t_mono_ns", "period_s", "history_len", "age_s", "current", "history"}
    assert body["period_s"] == 0.05 and body["history_len"] == hw.HISTORY_LEN
    current = body["current"]
    assert set(current) == {
        "seq", "t_mono_ns", "t_wall", "read_ms", "cpu", "memory", "shm", "disk", "gpu", "temps",
        "power", "na",
    }  # fmt: skip
    assert current["gpu"]["name"] == "Intel Arc A380" and current["power"]["server_w"] == 69.0
    assert current["disk"]["path"] == str(tmp_path / "data")  # DATA_DIR by default
    assert current["shm"] is None and current["na"]["shm"].startswith("the host's /dev/shm")
    assert set(body["history"]["series"]) == set(hw.SERIES)
    assert body["age_s"] is not None and body["age_s"] >= 0
    # the console (another origin) may read it
    r = client.get("/hardware", headers={"origin": ORIGIN})
    assert r.headers["access-control-allow-origin"] == ORIGIN


def test_the_agents_internal_listener_never_serves_it(make: Any) -> None:
    client = make(public_port=8000, internal_port=80)  # requests arrive on 80 = the internal one
    r = client.get("/hardware")
    assert r.status_code == 404 and r.json()["detail"]["reason"] == "not_public_listener"
    assert client.get("/health").json()["dropped_messages"]["hardware_http"] == {
        "not_public_listener": 1
    }


def test_the_agent_network_is_refused_before_the_route(make: Any) -> None:
    client = make(peer=("10.210.97.7", 1))  # ADR-0005 c2
    r = client.get("/hardware")
    assert r.status_code == 403 and r.json()["detail"]["reason"] == "agent_network"


def test_nics_hidden_by_the_network_namespace_keep_distinct_labels(tmp_path: Path) -> None:
    """2026-11-08 (Batt's console error `tg3:tg3`): inside the backend's container the NICs'
    interfaces are not visible (device/net is empty), so 4 tg3 sensors all read "tg3"; their
    PCI addresses keep them apart."""
    root, clock = host_tree(tmp_path / "host"), Clock()
    hwmon = root / "sys/class/hwmon"
    for i, fn in enumerate(("0000:02:00.0", "0000:02:00.1"), start=5):
        dev = root / f"sys/devices/pci0000:00/0000:00:1c.4/{fn}"
        (dev / "net").mkdir(parents=True)  # the dir is there, its interface is not
        put(hwmon, f"hwmon{i}/name", "tg3")
        put(hwmon, f"hwmon{i}/temp1_input", 50000)
        (hwmon / f"hwmon{i}/device").symlink_to(dev)
    m = monitor(root, clock, shm_path=None, disk_path=tmp_path)
    labels = [t.label for t in m.sample().temps if t.chip == "tg3"]
    assert labels == ["eno1", "NIC 02:00.0", "NIC 02:00.1"]
    assert len(set(labels)) == len(labels)
