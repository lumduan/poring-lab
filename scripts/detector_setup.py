#!/usr/bin/env python3
"""Set up the CPU detector on a fresh install (Batt 2026-11-17: "no GPU -> use the CPU"; the starter
model is v1 from the teaching-kit branch: "ได้").

The CPU detector (scripts/detector_worker.py, run by scripts/unit_detector.py) needs only numpy and
onnxruntime in its OWN environment, plus a model. Every install can run it: it is the detector on a
host without a GPU, and the one behind the GPU detect server everywhere else.

    python3 scripts/detector_setup.py            # create what is missing, then check it
    python3 scripts/detector_setup.py --check    # read-only: say what is there (exit 0 = ready)

What it makes, under the detector folder (lab_env.detector_dir(): DETECTOR_DIR, else
~/.local/share/<project>/detector):
    .venv/                              numpy + onnxruntime (uv, Python 3.12; ~100-200 MB)
    model/v1png-last-736x1280.onnx      v1 (player / monster / npc), sha256 pinned below
and a copy of the same ONNX in the storage folder's archive/models/ (lab_env.store()), where the
vision worker's OpenVINO detect server reads deployed models (/datasets/archive/models).

The model comes from the `teaching-kit` branch of this repository (`v1.onnx`, published by Batt's
decision 2026-11-06): the local ref first, else one `git fetch --depth 1` of that branch. A file
whose sha256 is not the pin is never installed. Nothing here needs root, Docker or a GPU.
Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_env  # noqa: E402

REPO = lab_env.REPO
# v1 (labels v1, 30 epochs; LIVE since 2026-10-13): the SAME file as the lab's
# model/v1png-last-736x1280.onnx -- unit_detector.GPU_WEIGHTS["v1"].onnx_sha256 (test-pinned equal).
V1_ONNX = "v1png-last-736x1280.onnx"
V1_SHA256 = "32b448a1d197ded289f53ca9cb306f536ebfc0eb701ebdeaa94ab9e7800a3ba4"
KIT_BRANCH = "teaching-kit"
KIT_PATH = "v1.onnx"
PACKAGES = ("numpy", "onnxruntime")
PYTHON_VERSION = "3.12"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def model_ok(path: Path) -> bool:
    return path.is_file() and sha256(path) == V1_SHA256


def venv_python(folder: Path) -> Path:
    return folder / ".venv" / "bin" / "python"


def venv_ok(folder: Path) -> bool:
    py = venv_python(folder)
    if not py.exists():
        return False
    r = subprocess.run([str(py), "-c", "import numpy, onnxruntime"], capture_output=True,
                       timeout=120)  # fmt: skip
    return r.returncode == 0


def status(folder: Path, store_models: Path) -> dict[str, bool]:
    return {
        "venv": venv_ok(folder),
        "model": model_ok(folder / "model" / V1_ONNX),
        "store_model": model_ok(store_models / V1_ONNX),
    }


def make_venv(folder: Path) -> None:
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit(
            "uv is not installed: ./setup.sh installs it (or https://docs.astral.sh/uv/)"
        )
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="detector-uv-") as cache:
        env = {**os.environ, "UV_CACHE_DIR": cache, "UV_LINK_MODE": "copy"}
        for cmd in ([uv, "venv", "-q", "--allow-existing", str(folder / ".venv"),
                     "--python", PYTHON_VERSION],
                    [uv, "pip", "install", "-q", "--python", str(venv_python(folder)),
                     *PACKAGES]):  # fmt: skip
            r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=1800)
            if r.returncode != 0:
                raise SystemExit(f"{' '.join(cmd[:3])} failed:\n{r.stderr[-1500:]}")


def _git(*args: str, timeout: int = 300) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, timeout=timeout)


def fetch_model(dest: Path) -> None:
    """v1.onnx from the teaching-kit branch into ``dest``, only if its sha256 is the pin."""
    blob = None
    for ref in (f"origin/{KIT_BRANCH}", KIT_BRANCH):
        r = _git("show", f"{ref}:{KIT_PATH}")
        if r.returncode == 0:
            blob = r.stdout
            break
    if blob is None:
        r = _git("fetch", "--depth", "1", "origin", f"refs/heads/{KIT_BRANCH}")
        if r.returncode != 0:
            raise SystemExit(f"could not fetch the {KIT_BRANCH} branch from origin:\n"
                             f"{r.stderr.decode(errors='replace')[-800:]}")  # fmt: skip
        r = _git("show", f"FETCH_HEAD:{KIT_PATH}")
        if r.returncode != 0:
            raise SystemExit(f"the {KIT_BRANCH} branch has no {KIT_PATH}")
        blob = r.stdout
    if hashlib.sha256(blob).hexdigest() != V1_SHA256:
        raise SystemExit(f"{KIT_BRANCH}:{KIT_PATH} is not the pinned v1 "
                         f"(sha256 {V1_SHA256[:12]}...): not installed")  # fmt: skip
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, dest)


def install_copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.tmp")
    shutil.copyfile(src, tmp)
    if sha256(tmp) != V1_SHA256:
        tmp.unlink()
        raise SystemExit(f"the copy to {dest} does not match the pin: not installed")
    os.replace(tmp, dest)


def smoke(folder: Path) -> str:
    """One onnxruntime session on the model in the detector's own environment: its input shape."""
    code = ("import sys, onnxruntime as ort; s = ort.InferenceSession(sys.argv[1], "
            "providers=['CPUExecutionProvider']); print(s.get_inputs()[0].shape)")  # fmt: skip
    r = subprocess.run([str(venv_python(folder)), "-c", code, str(folder / "model" / V1_ONNX)],
                       capture_output=True, text=True, timeout=300)  # fmt: skip
    if r.returncode != 0:
        raise SystemExit(f"the detector's environment cannot load v1:\n{r.stderr[-1200:]}")
    return r.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dir", type=Path, default=None,
                    help="the detector folder (default: DETECTOR_DIR, else "
                    "~/.local/share/<project>/detector)")  # fmt: skip
    ap.add_argument(
        "--store-models",
        type=Path,
        default=None,
        help="where deployed models live (default: <LAB_STORE_DIR>/archive/models)",
    )
    ap.add_argument("--check", action="store_true", help="read-only: report, exit 0 when ready")
    a = ap.parse_args(argv)
    folder = a.dir or lab_env.detector_dir()
    store_models = a.store_models or lab_env.store("archive", "models")
    before = status(folder, store_models)
    print(f"detector folder {folder}: " + ", ".join(f"{k} {'ok' if v else 'missing'}"
                                                   for k, v in before.items()))  # fmt: skip
    if a.check:
        return 0 if all(before.values()) else 1
    if not before["venv"]:
        print(f"creating its environment ({', '.join(PACKAGES)}; Python {PYTHON_VERSION})")
        make_venv(folder)
    model = folder / "model" / V1_ONNX
    if not before["model"]:
        if model_ok(store_models / V1_ONNX):
            install_copy(store_models / V1_ONNX, model)
        else:
            print(f"fetching v1 from the {KIT_BRANCH} branch")
            fetch_model(model)
    if not model_ok(store_models / V1_ONNX):
        install_copy(model, store_models / V1_ONNX)
    after = status(folder, store_models)
    if not all(after.values()):
        print("NOT ready: " + ", ".join(k for k, v in after.items() if not v))
        return 1
    print(f"ready: v1 (sha256 {V1_SHA256[:12]}...) loads, input {smoke(folder)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
