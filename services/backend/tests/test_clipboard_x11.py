"""The clipboard service against a real Xvfb (skipped when Xvfb is not installed -- as on the lab
host, where scripts/clipboard_x11_check.py runs inside the backend container instead)."""

import os
import runpy
import shutil
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "clipboard_x11_check.py"
DISPLAY_NUMBER = 197

needs_xvfb = pytest.mark.skipif(shutil.which("Xvfb") is None, reason="Xvfb is not installed")


@pytest.fixture
def xvfb() -> Iterator[str]:
    proc = subprocess.Popen(
        ["Xvfb", f":{DISPLAY_NUMBER}", "-nolisten", "tcp", "-ac", "-screen", "0", "64x64x24"]
    )
    socket = Path(f"/tmp/.X11-unix/X{DISPLAY_NUMBER}")
    deadline = time.monotonic() + 10
    while not socket.exists():
        if time.monotonic() > deadline or proc.poll() is not None:
            proc.kill()
            pytest.fail("Xvfb did not start")
        time.sleep(0.05)
    yield f":{DISPLAY_NUMBER}"
    proc.terminate()
    proc.wait(timeout=5)


@needs_xvfb
async def test_clipboard_service_on_a_real_x_server(xvfb: str) -> None:
    check = runpy.run_path(str(SCRIPT))["check"]
    assert await check(xvfb) == []


def test_script_is_where_the_docs_say() -> None:
    assert SCRIPT.is_file() and os.access(SCRIPT, os.R_OK)
