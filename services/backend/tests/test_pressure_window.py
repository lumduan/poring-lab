"""scripts/pressure_sampler.py window: the STALL WINDOW Batt backfills from AWS (2026-10-03) --
10 s bins where quant-postgres or quant-orderbook-engine io_full > 25 %, ICT and UTC."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "pressure_sampler.py"


@pytest.fixture(scope="module")
def ps() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pressure_sampler", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def csv_with(tmp_path: Path, ps: ModuleType, stall: dict[str, tuple[int, int, float]]) -> Path:
    """60 one-second samples from 03:40:00; stall[name] = (from s, to s, io_full share 0..1)."""
    names = [*ps.QUANT, ps.CRON]
    metrics = ("cpu_some", "cpu_full", "io_some", "io_full")
    header = ["t_mono", "t_wall"] + [f"{n}.{m}" for n in names for m in metrics]
    totals = dict.fromkeys(names, 0.0)
    lines = [",".join(header)]
    for t in range(60):
        row = [f"{1000 + t:.3f}", f"03:40:{t:02d}"]
        for n in names:
            lo, hi, share = stall.get(n, (0, 0, 0.0))
            totals[n] += (share if lo <= t < hi else 0.01) * 1e6  # us of full stall per second
            row += ["0", "0", "0", f"{totals[n]:.0f}"]
        lines.append(",".join(row))
    path = tmp_path / "p.csv"
    path.write_text("\n".join(lines) + "\n")
    return path


def test_the_window_is_the_bins_over_25_percent_in_ict_and_utc(
    ps: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = csv_with(tmp_path, ps, {
        "quant-postgres": (10, 30, 0.86),
        "quant-orderbook-engine": (20, 40, 0.77),
        "quant-mongo": (20, 30, 0.40),
    })  # fmt: skip
    ps.stall_window(path, "03:40:00", "03:41:00", "2026-10-04", 10, 25.0)
    out = capsys.readouterr().out
    assert "STALL WINDOW: 2026-10-04 03:40:10 ICT = 2026-10-03 20:40:10 UTC" in out
    assert "-> 2026-10-04 03:40:40 ICT = 2026-10-03 20:40:40 UTC" in out
    assert "3 bin(s) of 10 s" in out
    assert "quant-mongo, quant-orderbook-engine, quant-postgres" in out


def test_mongo_alone_does_not_open_the_window(
    ps: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = csv_with(tmp_path, ps, {"quant-mongo": (0, 60, 0.9)})
    ps.stall_window(path, "03:40:00", "03:41:00", "2026-10-04", 10, 25.0)
    assert "STALL WINDOW: none" in capsys.readouterr().out
