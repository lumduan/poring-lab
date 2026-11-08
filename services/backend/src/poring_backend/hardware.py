"""The hardware monitor (Batt 2026-11-08: "a hardware monitor page showing CPU, RAM, GPU,
temperature and power"): one sampler task in the backend process, served at GET /hardware
(routes_hardware.py) for the console's /hardware page.

It reads PLAIN FILES only: no subprocess, no nvidia-smi, no new mount, privilege or package. The
backend container sees the host's own counters read-only (no lxcfs): /proc/{stat,meminfo,loadavg,
cpuinfo}, /sys/devices/system/cpu, /sys/class/{hwmon,drm,powercap}.

  CPU     busy % (total and per core) from /proc/stat deltas; MHz per core from cpufreq's
          scaling_cur_freq, else /proc/cpuinfo; load 1/5/15; the model; the online core count.
  Memory  /proc/meminfo: used = MemTotal - MemAvailable; swap used; Shmem (host-wide: every tmpfs
          and shared mapping, so it is NOT the lab's /dev/shm). /dev/shm and the root disk come from
          statvfs of a path ON them (HARDWARE_SHM_PATH, HARDWARE_DISK_PATH; config.py).
  GPU     vendor-neutral (ADR-0022): the first DRM card whose driver has a reader. Intel i915 now:
          its hwmon (temp, the energy counter -> W, the power limit, the fan), the GT frequencies,
          and busy % from RC6 residency (1 - time in RC6 / wall time). Any other driver -> null
          with the reason; there is deliberately no nvidia-smi call.
  Temps   every hwmon temp*_input, with its label, max and crit.
  Power   the whole server from hwmon "power_meter" (ACPI; on the HP ML350 it is iLO's average over
          power1_average_interval), the GPU (above), and the CPU package from RAPL energy_uj (root
          only on the host, masked in containers -> null with the reason).

Every sensor is optional: a missing or unreadable one is null in the sample and its reason is in
``na`` (e.g. ``"power.cpu_pkg_w": "root only"``). Nothing a sensor does stops the task, and each
sensor logs at most once per process. The reads run in a worker thread (the ACPI power meter's
first read took 10 ms on bot-server), so the event loop -- the stream -- never waits on sysfs.

Clocks: every time here is the backend's CLOCK_MONOTONIC (``t_mono_ns``), except ``t_wall``, which
is display only. The page adds its own fetch age to ``age_s``; it never subtracts across clocks.
"""

import asyncio
import contextlib
import logging
import os
import re
import time
from collections import deque
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import NamedTuple, Protocol

from pydantic import BaseModel, Field

from poring_env.clock import monotonic_ns

log = logging.getLogger(__name__)

PERIOD_S = 2.0
HISTORY_LEN = 300  # 10 minutes at 2 s, for the page's sparklines
# CLAUDE.md rule 7 (Batt 2026-10-29): the lab's /dev/shm total stays at or under 4 GB (decimal).
SHM_LIMIT_B = 4 * 10**9
MAX_READ = 1 << 20  # no sysfs/proc file we read is near this; a bound, not an expectation
CPU_CHIPS = frozenset({"coretemp", "k10temp", "zenpower", "cpu_thermal"})
# Names for the PCI ids this lab has (display only; anything else shows its id).
KNOWN_GPUS = {"8086:56a5": "Intel Arc A380", "8086:56a6": "Intel Arc A310"}
VRAM_NA = "no unprivileged source (i915 debugfs is root only)"
# The sparkline series, in the order a history row stores them.
SERIES = ("cpu_pct", "mem_pct", "gpu_busy_pct", "cpu_temp_c", "gpu_temp_c", "server_w", "gpu_w")
# The ACPI power meter re-runs its ACPI method on a read once the driver's cache is old (~10 ms on
# bot-server, every 2 s read), and its value is an average over minutes (iLO: 300 s). Read it at
# most this often; the samples in between repeat the last reading.
POWER_METER_EVERY_S = 10.0
# Chips, labels and limits do not change while the host runs; they are rescanned this often (a
# sample then reads ~40 small files instead of ~80: each costs ~0.1 ms on this 1.7 GHz Xeon).
RESCAN_S = 60.0

_CARD = re.compile(r"^card\d+$")
_TEMP = re.compile(r"^temp(\d+)_input$")
_NUM = re.compile(r"(\d+)")


# --- the response model (REST only: not part of the WebSocket protocol, no gen_protocol) ---------


class Cpu(BaseModel):
    model: str | None = None
    cores: int | None = None
    busy_pct: float | None = None
    core_pct: list[float | None] = Field(default_factory=list)
    core_mhz: list[float | None] = Field(default_factory=list)
    mhz_source: str | None = None  # "cpufreq" | "cpuinfo"
    load: list[float] | None = None  # 1, 5, 15 min


class Memory(BaseModel):
    total_b: int | None = None
    available_b: int | None = None
    used_b: int | None = None  # total - available
    swap_total_b: int | None = None
    swap_used_b: int | None = None
    shmem_b: int | None = None  # host-wide Shmem: every tmpfs + shared mapping, not /dev/shm alone


class Filesystem(BaseModel):
    path: str  # the path statvfs was called on
    total_b: int
    used_b: int
    free_b: int  # available to an unprivileged writer (f_bavail)
    limit_b: int | None = None  # /dev/shm: rule 7's 4 GB


class Gpu(BaseModel):
    vendor: str
    driver: str
    card: str
    pci_id: str | None = None
    name: str | None = None
    temp_c: float | None = None
    power_w: float | None = None
    power_max_w: float | None = None
    fan_rpm: int | None = None
    freq_act_mhz: int | None = None
    freq_cur_mhz: int | None = None
    freq_max_mhz: int | None = None
    busy_pct: float | None = None  # from RC6 residency (Intel)
    vram_used_b: int | None = None
    vram_total_b: int | None = None


class Temp(BaseModel):
    chip: str
    label: str
    c: float
    max_c: float | None = None
    crit_c: float | None = None


class Power(BaseModel):
    server_w: float | None = None  # wall power of the whole server (hwmon power_meter)
    server_avg_s: float | None = None  # the meter's averaging interval
    gpu_w: float | None = None
    gpu_max_w: float | None = None
    cpu_pkg_w: float | None = None


class Sample(BaseModel):
    seq: int
    t_mono_ns: int
    t_wall: float  # display only
    read_ms: float  # how long the reads took (in the worker thread)
    cpu: Cpu
    memory: Memory
    shm: Filesystem | None = None
    disk: Filesystem | None = None
    gpu: Gpu | None = None
    temps: list[Temp] = Field(default_factory=list)
    power: Power
    na: dict[str, str] = Field(default_factory=dict)  # "<section>.<field>" -> why it is null


class History(BaseModel):
    # Seconds relative to the newest sample (<= 0), and one list per SERIES name, oldest first.
    t_s: list[float]
    series: dict[str, list[float | None]]


class HardwareView(BaseModel):
    t_mono_ns: int  # the backend's clock when this answer was built
    period_s: float
    history_len: int
    age_s: float | None  # of ``current`` on the backend's clock; None before the first sample
    current: Sample | None
    history: History


# --- reading --------------------------------------------------------------------------------------


class Unavailable(Exception):
    """A sensor that cannot be read, with the short reason the page shows ("n/a: <reason>")."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _denied(path: Path) -> str:
    try:
        st = path.stat()
    except OSError:
        return "permission denied"
    return "root only" if st.st_uid == 0 and not st.st_mode & 0o004 else "permission denied"


def read_text(path: Path) -> str:
    try:
        with open(path, "rb") as f:
            return f.read(MAX_READ).decode("utf-8", "replace").strip()
    except PermissionError:
        raise Unavailable(_denied(path)) from None
    except FileNotFoundError:
        raise Unavailable("absent") from None


def read_int(path: Path) -> int:
    return int(read_text(path))


def reason_of(exc: BaseException) -> str:
    if isinstance(exc, Unavailable):
        return exc.reason
    if isinstance(exc, OSError):
        return f"unreadable ({os.strerror(exc.errno) if exc.errno else type(exc).__name__})"
    if isinstance(exc, ValueError):
        return "unparsable"
    return f"error ({type(exc).__name__})"


class Probe:
    """One sample's reads: a failed read is None, and its reason goes into ``na``. Each sensor key
    is logged once per process (the ``logged`` set outlives the sample)."""

    def __init__(self, logged: set[str]) -> None:
        self.na: dict[str, str] = {}
        self._logged = logged

    def get[T](self, key: str, read: Callable[[], T]) -> T | None:
        try:
            return read()
        except Exception as exc:  # a sensor must never stop the sampler
            self.fail(key, exc)
            return None

    def fail(self, key: str, exc: BaseException) -> None:
        reason = reason_of(exc)
        self.na[key] = reason
        if key not in self._logged:
            self._logged.add(key)
            expected = isinstance(exc, Unavailable)
            log.log(
                logging.INFO if expected else logging.WARNING,
                "hardware sensor %s unavailable: %s (logged once)",
                key,
                reason,
            )

    def miss(self, key: str, reason: str) -> None:
        """An expected null that is not a failure (e.g. a rate's first reading): not logged."""
        self.na[key] = reason


def _round1(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def clamp_pct(value: float) -> float:
    return min(100.0, max(0.0, value))


def counter_rate(
    prev: tuple[int, int] | None, value: int, t_ns: int, *, wrap: int | None = None
) -> tuple[float | None, str | None]:
    """Units per second of a cumulative counter between two readings ``(value, t_mono_ns)``.

    None and why: the first reading ("warming up"), no time between them, or a counter that went
    back -- a reset ("counter reset"), unless ``wrap`` (the counter's range, e.g. RAPL's
    max_energy_range_uj) unwinds one wrap-around."""
    if prev is None:
        return None, "warming up"
    v0, t0 = prev
    dt = (t_ns - t0) / 1e9
    if dt <= 0:
        return None, "no time between samples"
    dv = value - v0
    if dv < 0:
        if not wrap:
            return None, "counter reset"
        dv += wrap
        if dv < 0:
            return None, "counter reset"
    return dv / dt, None


def cpu_times(stat: str) -> dict[str, tuple[int, int]]:
    """``{"cpu": (busy, total), "cpu0": ...}`` in jiffies from /proc/stat. busy excludes idle and
    iowait; guest time is already inside user/nice, so only the first 8 fields count."""
    out: dict[str, tuple[int, int]] = {}
    for line in stat.splitlines():
        if not line.startswith("cpu"):
            continue
        parts = line.split()
        fields = [int(x) for x in parts[1:9]]
        if len(fields) < 4:
            continue
        fields += [0] * (8 - len(fields))
        idle = fields[3] + fields[4]
        total = sum(fields)
        out[parts[0]] = (total - idle, total)
    return out


def busy_pct(prev: tuple[int, int] | None, cur: tuple[int, int]) -> float | None:
    if prev is None:
        return None
    d_busy, d_total = cur[0] - prev[0], cur[1] - prev[1]
    if d_total <= 0 or d_busy < 0:
        return None
    return clamp_pct(100.0 * d_busy / d_total)


def parse_meminfo(text: str) -> dict[str, int]:
    """/proc/meminfo in bytes (the kB lines; the few unitless ones are counts, kept as is)."""
    out: dict[str, int] = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if not parts:
            continue
        try:
            value = int(parts[0])
        except ValueError:
            continue
        out[key.strip()] = value * 1024 if parts[1:] == ["kB"] else value
    return out


def parse_loadavg(text: str) -> list[float]:
    one, five, fifteen = (float(x) for x in text.split()[:3])
    return [one, five, fifteen]


def parse_cpuinfo(text: str) -> tuple[str | None, list[float]]:
    """The first "model name" and every "cpu MHz", in processor order."""
    model: str | None = None
    mhz: list[float] = []
    for line in text.splitlines():
        key, _, value = line.partition(":")
        key = key.strip()
        if key == "model name" and model is None:
            model = value.strip() or None
        elif key == "cpu MHz":
            mhz.append(float(value))
    return model, mhz


def statvfs(path: Path, limit_b: int | None = None) -> Filesystem:
    try:
        st = os.statvfs(path)
    except FileNotFoundError:
        raise Unavailable(f"{path} absent") from None
    except PermissionError:
        raise Unavailable(f"{path} not readable") from None
    return Filesystem(
        path=str(path),
        total_b=st.f_blocks * st.f_frsize,
        used_b=(st.f_blocks - st.f_bfree) * st.f_frsize,
        free_b=st.f_bavail * st.f_frsize,
        limit_b=limit_b,
    )


def _natural(name: str) -> tuple[str, int]:
    m = _NUM.search(name)
    return (name[: m.start()] if m else name, int(m.group(1)) if m else -1)


def _listdir(path: Path) -> list[str]:
    try:
        return sorted(os.listdir(path), key=_natural)
    except OSError:
        return []


def hwmon_chips(root: Path) -> list[tuple[Path, str]]:
    """``(hwmon dir, name)`` of every chip, in hwmon index order."""
    base = root / "sys/class/hwmon"
    chips: list[tuple[Path, str]] = []
    for entry in _listdir(base):
        path = base / entry
        try:
            name = read_text(path / "name")
        except Unavailable:
            continue
        chips.append((path, name))
    return chips


def _temp_label(chip: Path, name: str, n: str, count: int) -> str:
    with contextlib.suppress(Unavailable, OSError):
        label = read_text(chip / f"temp{n}_label")
        if label:
            return label
    nets = _listdir(chip / "device/net")  # a NIC's sensor (tg3): name it by its interface
    if len(nets) == 1:
        return nets[0]
    return f"{name} temp{n}" if count > 1 else name


def _optional_c(path: Path) -> float | None:
    try:
        return read_int(path) / 1000
    except (Unavailable, ValueError, OSError):
        return None


class TempSensor(NamedTuple):
    """One hwmon temperature: what does not change between samples (rescanned each minute)."""

    chip: str  # the hwmon name, e.g. coretemp
    path: Path  # its tempN_input
    key: str  # its ``na`` key, e.g. temps.hwmon6.temp1
    label: str
    max_c: float | None
    crit_c: float | None


def scan_temps(chips: list[tuple[Path, str]]) -> list[TempSensor]:
    sensors: list[TempSensor] = []
    for chip, name in chips:
        inputs = [m.group(1) for f in _listdir(chip) if (m := _TEMP.match(f))]
        for n in inputs:
            sensors.append(
                TempSensor(
                    chip=name,
                    path=chip / f"temp{n}_input",
                    key=f"temps.{chip.name}.temp{n}",
                    label=_temp_label(chip, name, n, len(inputs)),
                    max_c=_optional_c(chip / f"temp{n}_max"),
                    crit_c=_optional_c(chip / f"temp{n}_crit"),
                )
            )
    return sensors


def read_temps(sensors: list[TempSensor], probe: Probe) -> list[Temp]:
    temps: list[Temp] = []
    for s in sensors:
        c = probe.get(s.key, partial(read_int, s.path))
        if c is not None:
            temps.append(Temp(chip=s.chip, label=s.label, c=c / 1000, max_c=s.max_c,
                              crit_c=s.crit_c))  # fmt: skip
    return temps


def cpu_temp(temps: list[Temp]) -> float | None:
    """The CPU's temperature for the sparkline: the hottest package sensor, else the hottest CPU
    sensor of any kind (coretemp cores, k10temp's Tctl)."""
    cpu = [t for t in temps if t.chip in CPU_CHIPS]
    package = [t.c for t in cpu if t.label.lower().startswith("package")]
    values = package or [t.c for t in cpu]
    return max(values) if values else None


# --- GPUs: one reader per driver (ADR-0022: vendor-neutral; Intel now) ---------------------------


class GpuReader(Protocol):
    card_dir: Path

    def read(self, probe: Probe, t_ns: int) -> Gpu: ...


class IntelI915:
    """An Intel discrete or integrated GPU on i915: hwmon (temp, energy, power limit, fan), the GT
    frequencies, and busy % from RC6 residency. There is no i915 PMU here (perf_event_paranoid is
    4) and no unprivileged VRAM figure (debugfs is root only)."""

    vendor = "intel"

    def __init__(self, card_dir: Path, *, driver: str, pci_id: str | None) -> None:
        self.card_dir = card_dir
        self.driver = driver
        self.pci_id = pci_id
        hwmons = _listdir(card_dir / "device/hwmon")
        self.hwmon: Path | None = card_dir / "device/hwmon" / hwmons[0] if hwmons else None
        gt0 = card_dir / "gt/gt0/rc6_residency_ms"
        self.rc6 = gt0 if gt0.exists() else card_dir / "power/rc6_residency_ms"
        self._energy: tuple[int, int] | None = None
        self._rc6: tuple[int, int] | None = None

    def _hw(self, name: str) -> int:
        if self.hwmon is None:
            raise Unavailable("no hwmon for the card")
        return read_int(self.hwmon / name)

    def read(self, probe: Probe, t_ns: int) -> Gpu:
        gpu = Gpu(
            vendor=self.vendor,
            driver=self.driver,
            card=self.card_dir.name,
            pci_id=self.pci_id,
            name=KNOWN_GPUS.get(self.pci_id or ""),
        )
        temp = probe.get("gpu.temp_c", lambda: self._hw("temp1_input"))
        gpu.temp_c = None if temp is None else temp / 1000
        energy = probe.get("gpu.power_w", lambda: self._hw("energy1_input"))  # µJ
        if energy is not None:
            rate, why = counter_rate(self._energy, energy, t_ns)
            self._energy = (energy, t_ns)
            gpu.power_w = None if rate is None else round(rate / 1e6, 2)
            if why:
                probe.miss("gpu.power_w", why)
        limit = probe.get("gpu.power_max_w", lambda: self._hw("power1_max"))  # µW
        gpu.power_max_w = None if limit is None else limit / 1e6
        gpu.fan_rpm = probe.get("gpu.fan_rpm", lambda: self._hw("fan1_input"))
        for field, name in (
            ("freq_act_mhz", "gt_act_freq_mhz"),
            ("freq_cur_mhz", "gt_cur_freq_mhz"),
            ("freq_max_mhz", "gt_max_freq_mhz"),
        ):
            setattr(gpu, field, probe.get(f"gpu.{field}", partial(read_int, self.card_dir / name)))
        rc6 = probe.get("gpu.busy_pct", lambda: read_int(self.rc6))  # ms in RC6 (idle)
        if rc6 is not None:
            rate, why = counter_rate(self._rc6, rc6, t_ns)  # ms of RC6 per second of wall time
            self._rc6 = (rc6, t_ns)
            gpu.busy_pct = None if rate is None else round(clamp_pct(100 - rate / 10), 1)
            if why:
                probe.miss("gpu.busy_pct", why)
        probe.miss("gpu.vram_used_b", VRAM_NA)
        probe.miss("gpu.vram_total_b", VRAM_NA)
        return gpu


GPU_READERS: dict[str, Callable[..., GpuReader]] = {"i915": IntelI915}
NO_READER = {"nvidia": "no reader for nvidia (by design: no nvidia-smi)"}


def find_gpu(root: Path) -> tuple[GpuReader | None, str | None]:
    """The first DRM card whose driver has a reader, or None and why."""
    base = root / "sys/class/drm"
    seen: list[str] = []
    for card in (c for c in _listdir(base) if _CARD.match(c)):
        path = base / card
        try:
            driver = os.path.basename(os.readlink(path / "device/driver"))
        except OSError:
            continue
        pci_id: str | None = None
        with contextlib.suppress(Unavailable, ValueError):
            vendor = read_text(path / "device/vendor").removeprefix("0x")
            device = read_text(path / "device/device").removeprefix("0x")
            pci_id = f"{vendor}:{device}"
        make = GPU_READERS.get(driver)
        if make is not None:
            return make(path, driver=driver, pci_id=pci_id), None
        seen.append(f"{card} {driver}")
    if not seen:
        return None, "no DRM card"
    for driver, why in NO_READER.items():
        if any(s.endswith(f" {driver}") for s in seen):
            return None, why
    return None, "no reader for " + ", ".join(seen)


# --- the sampler ----------------------------------------------------------------------------------


class HardwareMonitor:
    """Samples every ``period_s`` into a ring of ``history`` samples. ``sample()`` blocks (file
    reads) and runs in ONE worker thread at a time; ``record()`` and ``view()`` run on the event
    loop, so the ring is only ever touched there."""

    def __init__(
        self,
        root: Path = Path("/"),
        *,
        shm_path: Path | None = None,
        disk_path: Path | None = None,
        period_s: float = PERIOD_S,
        history: int = HISTORY_LEN,
        clock: Callable[[], int] = monotonic_ns,
        wall: Callable[[], float] = time.time,
    ) -> None:
        self.root = root
        self.shm_path = shm_path
        self.disk_path = disk_path
        self.period_s = period_s
        self._clock, self._wall = clock, wall
        self._history: deque[tuple[int, tuple[float | None, ...]]] = deque(maxlen=history)
        self._current: Sample | None = None
        self._seq = 0
        self._logged: set[str] = set()
        self._cpu_prev: dict[str, tuple[int, int]] = {}
        self._model: str | None = None
        self._gpu: GpuReader | None = None
        self._gpu_why: str | None = None
        self._gpu_checked_ns: int | None = None
        self._rapl: tuple[int, int] | None = None
        self._meter: tuple[int, float | None, float | None, str | None] | None = None
        self._scan: tuple[int, list[tuple[Path, str]], list[TempSensor]] | None = None
        self._task: asyncio.Task[None] | None = None

    # -- one sample (blocking) --

    def sample(self) -> Sample:
        t0 = time.perf_counter()
        t_ns = self._clock()
        probe = Probe(self._logged)
        # Each section is guarded too: a bug in one (an unexpected file layout) nulls that section
        # with its reason, never the whole sample.
        cpu = probe.get("cpu", partial(self._cpu, probe)) or Cpu()
        memory = probe.get("memory", partial(self._memory, probe)) or Memory()
        shm = self._fs(probe, "shm", self.shm_path, SHM_LIMIT_B,
                       "the host's /dev/shm is not mounted here")  # fmt: skip
        disk = self._fs(probe, "disk", self.disk_path, None, "no disk path configured")
        chips, sensors = probe.get("temps", partial(self._hwmon, t_ns)) or ([], [])
        temps = probe.get("temps", partial(read_temps, sensors, probe)) or []
        gpu = probe.get("gpu", partial(self._read_gpu, probe, t_ns))
        power = probe.get("power", partial(self._power, probe, t_ns, gpu, chips)) or Power()
        self._seq += 1
        return Sample(
            seq=self._seq,
            t_mono_ns=t_ns,
            t_wall=self._wall(),
            read_ms=round((time.perf_counter() - t0) * 1000, 2),
            cpu=cpu,
            memory=memory,
            shm=shm,
            disk=disk,
            gpu=gpu,
            temps=temps,
            power=power,
            na=probe.na,
        )

    def _hwmon(self, t_ns: int) -> tuple[list[tuple[Path, str]], list[TempSensor]]:
        if self._scan is None or t_ns - self._scan[0] > RESCAN_S * 1e9:
            chips = hwmon_chips(self.root)
            self._scan = (t_ns, chips, scan_temps(chips))
        return self._scan[1], self._scan[2]

    def _cpu(self, probe: Probe) -> Cpu:
        proc = self.root / "proc"
        cpu = Cpu()
        times = probe.get("cpu.busy_pct", lambda: cpu_times(read_text(proc / "stat")))
        cores = sorted((k for k in times or {} if k != "cpu"), key=_natural)
        if times:
            cpu.cores = len(cores) or None
            total = times.get("cpu")
            prev = self._cpu_prev.get("cpu")
            cpu.busy_pct = None if total is None else _round1(busy_pct(prev, total))
            cpu.core_pct = [_round1(busy_pct(self._cpu_prev.get(k), times[k])) for k in cores]
            if cpu.busy_pct is None:
                probe.miss("cpu.busy_pct", "warming up" if not self._cpu_prev else "counter reset")
            self._cpu_prev = times
        info: tuple[str | None, list[float]] | None = None
        if self._model is None:
            info = probe.get("cpu.model", lambda: parse_cpuinfo(read_text(proc / "cpuinfo")))
            self._model = info[0] if info else None
        cpu.model = self._model
        mhz: list[float | None] = []
        for core in cores:
            path = self.root / f"sys/devices/system/cpu/{core}/cpufreq/scaling_cur_freq"
            try:
                mhz.append(round(read_int(path) / 1000))
            except (Unavailable, ValueError, OSError):
                mhz.append(None)
        if mhz and any(m is not None for m in mhz):
            cpu.core_mhz, cpu.mhz_source = mhz, "cpufreq"
        else:
            if info is None:
                info = probe.get("cpu.core_mhz", lambda: parse_cpuinfo(read_text(proc / "cpuinfo")))
            if info and info[1]:
                cpu.core_mhz, cpu.mhz_source = [round(m) for m in info[1]], "cpuinfo"
            elif "cpu.core_mhz" not in probe.na:
                probe.miss("cpu.core_mhz", "absent")
        cpu.load = probe.get("cpu.load", lambda: parse_loadavg(read_text(proc / "loadavg")))
        return cpu

    def _memory(self, probe: Probe) -> Memory:
        info = probe.get("memory", lambda: parse_meminfo(read_text(self.root / "proc/meminfo")))
        if not info:
            return Memory()
        total, avail = info.get("MemTotal"), info.get("MemAvailable")
        swap_total, swap_free = info.get("SwapTotal"), info.get("SwapFree")
        return Memory(
            total_b=total,
            available_b=avail,
            used_b=None if total is None or avail is None else total - avail,
            swap_total_b=swap_total,
            swap_used_b=None if swap_total is None or swap_free is None else swap_total - swap_free,
            shmem_b=info.get("Shmem"),
        )

    def _fs(
        self, probe: Probe, key: str, path: Path | None, limit: int | None, unset: str
    ) -> Filesystem | None:
        if path is None:
            probe.miss(key, unset)
            return None
        return probe.get(key, lambda: statvfs(path, limit))

    def _read_gpu(self, probe: Probe, t_ns: int) -> Gpu | None:
        stale = self._gpu is not None and not self._gpu.card_dir.exists()
        recheck = self._gpu is None and (
            self._gpu_checked_ns is None or t_ns - self._gpu_checked_ns > 60 * 10**9
        )
        if stale or recheck:  # found once; looked for again if it vanishes, or each minute if none
            self._gpu, self._gpu_why = find_gpu(self.root)
            self._gpu_checked_ns = t_ns
        if self._gpu is None:
            probe.miss("gpu", self._gpu_why or "no GPU")
            return None
        return self._gpu.read(probe, t_ns)

    def _power(
        self, probe: Probe, t_ns: int, gpu: Gpu | None, chips: list[tuple[Path, str]]
    ) -> Power:
        power = Power(
            gpu_w=gpu.power_w if gpu else None, gpu_max_w=gpu.power_max_w if gpu else None
        )
        if gpu is None:
            probe.miss("power.gpu_w", "no GPU")
        elif gpu.power_w is None:
            probe.miss("power.gpu_w", probe.na.get("gpu.power_w", "absent"))
        power.server_w, power.server_avg_s = self._server_w(probe, t_ns, chips)
        power.cpu_pkg_w = self._rapl_w(probe, t_ns)
        return power

    def _server_w(
        self, probe: Probe, t_ns: int, chips: list[tuple[Path, str]]
    ) -> tuple[float | None, float | None]:
        """The whole server's wall power (W) and the meter's averaging interval (s)."""
        last = self._meter
        if last is not None and t_ns - last[0] < POWER_METER_EVERY_S * 1e9:
            if last[3] is not None:
                probe.miss("power.server_w", last[3])
            return last[1], last[2]
        meter = next((p for p, name in chips if name == "power_meter"), None)
        watts: float | None = None
        interval: float | None = None
        if meter is None:
            probe.miss("power.server_w", "no ACPI power meter")
        else:
            uw = probe.get("power.server_w", partial(read_int, meter / "power1_average"))
            watts = None if uw is None else round(uw / 1e6, 1)
            with contextlib.suppress(Unavailable, ValueError, OSError):
                interval = read_int(meter / "power1_average_interval") / 1000
        self._meter = (t_ns, watts, interval, probe.na.get("power.server_w"))
        return watts, interval

    def _rapl_w(self, probe: Probe, t_ns: int) -> float | None:
        zone = self.root / "sys/class/powercap/intel-rapl:0"
        if zone.is_symlink() and not zone.exists():
            # Docker masks /sys/devices/virtual/powercap (the RAPL side channel, CVE-2020-8694).
            probe.miss("power.cpu_pkg_w", "masked in this container (root only on the host)")
            return None
        uj = probe.get("power.cpu_pkg_w", lambda: read_int(zone / "energy_uj"))
        if uj is None:
            return None
        wrap: int | None = None
        with contextlib.suppress(Unavailable, ValueError, OSError):
            wrap = read_int(zone / "max_energy_range_uj")
        rate, why = counter_rate(self._rapl, uj, t_ns, wrap=wrap)
        self._rapl = (uj, t_ns)
        if why:
            probe.miss("power.cpu_pkg_w", why)
        return None if rate is None else round(rate / 1e6, 2)

    # -- the ring and the answer (event loop) --

    def record(self, sample: Sample) -> None:
        self._current = sample
        mem = sample.memory
        mem_pct = (
            100.0 * mem.used_b / mem.total_b if mem.used_b is not None and mem.total_b else None
        )
        gpu = sample.gpu
        row = (
            sample.cpu.busy_pct,
            mem_pct,
            gpu.busy_pct if gpu else None,
            cpu_temp(sample.temps),
            gpu.temp_c if gpu else None,
            sample.power.server_w,
            sample.power.gpu_w,
        )
        self._history.append((sample.t_mono_ns, row))

    def view(self, now_ns: int | None = None) -> HardwareView:
        now = self._clock() if now_ns is None else now_ns
        current = self._current
        rows = list(self._history)
        newest = rows[-1][0] if rows else now
        series = {name: [_round1(r[i]) for _, r in rows] for i, name in enumerate(SERIES)}
        return HardwareView(
            t_mono_ns=now,
            period_s=self.period_s,
            history_len=self._history.maxlen or 0,
            age_s=None if current is None else round((now - current.t_mono_ns) / 1e9, 2),
            current=current,
            history=History(t_s=[round((t - newest) / 1e9, 1) for t, _ in rows], series=series),
        )

    # -- the task --

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        next_at = loop.time()
        while True:
            try:
                self.record(await asyncio.to_thread(self.sample))
            except asyncio.CancelledError:
                raise
            except Exception:  # a bug here must not end the monitor: log once, keep sampling
                if "sampler" not in self._logged:
                    self._logged.add("sampler")
                    log.exception("hardware sample failed (logged once; the sampler goes on)")
            next_at += self.period_s
            now = loop.time()
            if next_at < now:  # a slow read: skip the missed slots instead of bursting
                next_at = now + self.period_s
            await asyncio.sleep(next_at - now)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self.run(), name="hardware-monitor")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


def main() -> None:
    """One real reading of THIS host (two samples, ``period_s`` apart, so the rates are filled):
    python -m poring_backend.hardware [ROOT] [--shm PATH] [--disk PATH]."""
    import argparse

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("root", nargs="?", default="/", type=Path)
    parser.add_argument("--shm", type=Path, default=None)
    parser.add_argument("--disk", type=Path, default=None)
    parser.add_argument("--period", type=float, default=PERIOD_S)
    args = parser.parse_args()
    monitor = HardwareMonitor(args.root, shm_path=args.shm, disk_path=args.disk)
    monitor.record(monitor.sample())
    time.sleep(args.period)
    monitor.record(monitor.sample())
    print(monitor.view().model_dump_json(indent=1))


if __name__ == "__main__":
    main()
