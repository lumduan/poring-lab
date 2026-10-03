#!/usr/bin/env python3
"""The capture-backend benchmark (docs/benchmarks/SPEC.md, v1): one fixed procedure for every
backend, so RDP, Sunshine S1/S2 and later phases compare like with like.

    bench.py run --backend rdp|console --label NAME [--walks 40] [--keys 40] [--rotate 60]
                 [--idle 120]
    bench.py reference              # lossless UI crops over RDP_GFX=off (RDP mode only)
    bench.py validate-reference PNG # one-time: a CopyFromScreen PNG vs the RDP-off crops
    bench.py table                  # regenerate docs/benchmarks/README.md from the run JSONs

Rules (scripts/ro_agent.py): input only through /internal/agent in ASSIST, waiting out a human
lease; in-game input only while the GM is online=1; the capture-backend lock must say --backend,
steady, and the host file must agree with /health (ADR-0009). Scratch and raw evidence go to
/dev/shm and data/bench/ (gitignored); results (JSON + markdown) go to docs/benchmarks/.
"""

import argparse
import bisect
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchlib  # noqa: E402
import measure_delay  # noqa: E402
import measure_motion  # noqa: E402
import ro_agent as r  # noqa: E402

from poring_backend.capture_lock import read_lock  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs" / "benchmarks"
EVIDENCE = ROOT / "data" / "bench"  # gitignored (data/)
SCRATCH = Path(os.environ.get("SCRATCH", "/dev/shm/poring-lab-tmp"))

# --- SPEC v2 constants (docs/benchmarks/SPEC.md) ------------------------------------------------
SCENES = {"outdoor": ("prt_fild08", 170, 375), "indoor": ("prt_church", 99, 112)}
# A map change resets the camera rotation; a same-map @warp does not (verified 2026-10-02).
RESET_VIA = {"outdoor": "prt_church 99 112", "indoor": "prt_fild08 170 375"}
# UI crops (client-relative x, y, w, h): static UI, identical in every backend's session. The
# in-game windows kept their client positions at 1280x720 (v2), so the boxes are v1's.
CROPS = {
    "hp_sp_panel": (2, 19, 216, 110),  # the Basic Information window: name, HP/SP bars + text
    "skill_bar": (230, 1, 290, 65),  # the hotkey bar
    "chat": (4, 549, 580, 46),  # the 3 system lines every map change prints
}
# Key -> paint: Escape toggles the client-local "Game option" window (client 505,450 280x138 at
# 1280x720; 257,391 in v1). Never Enter while it is open: its first button returns to char select.
KEY_REGION = (518, 459, 250, 120)
FPS_LIMIT = 30  # dgVoodoo FPSLimit; window 1296x759 = client 1280x720 (rathena-client.md)
WATCH = measure_delay.WATCH
MOVED = 0.10


# --- preflight and config -------------------------------------------------------------------------


def preflight(agent: r.Agent, screen: r.Screen, backend: str) -> dict[str, Any]:
    host = read_lock(ROOT / "state")
    if host.backend != backend or host.phase != "steady":
        raise r.Stop(f"the lock says {host.backend}/{host.phase}, not {backend}/steady")
    if getattr(agent, "backend", None) != backend:
        raise r.Stop(f"the backend reports {getattr(agent, 'backend', None)}, not {backend}")
    if not r.online_chars("gm"):
        raise r.Stop("the GM is not online=1 on our rAthena: no in-game input")
    r.minimize_consoles(agent, screen)
    return {
        "lock_seq": host.seq,
        "viewers": agent.status.get("viewers"),
        "mode": agent.status.get("mode"),
    }


def _exec(container: str, *cmd: str) -> str:
    res = subprocess.run(["docker", "exec", container, *cmd], capture_output=True, text=True)
    return (res.stdout + res.stderr).strip()


def run_config(backend: str) -> dict[str, Any]:
    env = r.env()
    if backend == "rdp":
        version = _exec("poring-lab-desktop-1", "xfreerdp3", "--version").splitlines()[0]
        logs = subprocess.run(
            ["docker", "logs", "--tail", "400", "poring-lab-desktop-1"],
            capture_output=True, text=True,
        )  # fmt: skip
        lines = [ln for ln in (logs.stderr + logs.stdout).splitlines() if "connecting to" in ln]
        codec = re.search(r"gfx=(\S+)", lines[-1]).group(1) if lines else "unknown"  # type: ignore[union-attr]
        client = {"name": "xfreerdp", "version": version, "codec": codec}
    else:
        # The lab client the variant file names (ADR-0009 clean room): Moonlight-qt, or the S2
        # client (s2spike) painting X (V3) or writing the frame bus (V3b, PAINT=bus).
        variant = dict(
            line.split("=", 1)
            for line in (ROOT / "state" / "gamestream-variant").read_text().splitlines()
            if "=" in line
        ) if (ROOT / "state" / "gamestream-variant").exists() else {}  # fmt: skip
        if variant.get("CLIENT") == "s2spike":
            version = "moonlight-common-c " + _exec(
                "poring-lab-gamestream-1", "cat", "/opt/s2spike/MLCC_SHA"
            )
            client = {"name": "s2spike", "version": version, "codec": "H.264",
                      "paint": variant.get("PAINT") or "x11"}  # fmt: skip
        else:
            version = _exec("poring-lab-gamestream-1", "gamestream-version")
            client = {"name": "moonlight-qt", "version": version, "codec": "H.264"}
    return {
        "spec": benchlib.SPEC_VERSION,
        "backend": backend,
        "client": client,
        "xvfb": env.get("XVFB_RESOLUTION", "1920x1200x24"),
        # the Windows session at the canvas' top-left: what is streamed, grabbed and clicked
        "session": env.get("SESSION_SIZE", "1440x900"),
        "game_region": env.get("GAME_REGION"),
        "fps_limit": FPS_LIMIT,
        "scenes": {k: list(v) for k, v in SCENES.items()},
    }


# --- scene control --------------------------------------------------------------------------------


def close_chat(agent: r.Agent, screen: r.Screen) -> None:
    if r.is_state(screen, "chat_open"):
        agent.keys("Enter")  # an EMPTY open input: Enter closes it
        time.sleep(0.8)


def enter_scene(agent: r.Agent, screen: r.Screen, scene: str) -> None:
    """Camera reset = a map change: warp to the other scene's map, then to this scene."""
    mapname, x, y = SCENES[scene]
    r.gm(agent, screen, f"@warp {RESET_VIA[scene]}")
    time.sleep(6)
    r.gm(agent, screen, f"@warp {mapname} {x} {y}")
    time.sleep(7)
    close_chat(agent, screen)
    r.activate_client(agent, screen)
    time.sleep(3)


def idle_cost(agent: r.Agent, seconds: float) -> dict[str, float]:
    before, t0 = measure_motion.usage_us(), time.monotonic()
    agent.idle(seconds)  # no input; keeps reading the agent socket
    after, t1 = measure_motion.usage_us(), time.monotonic()
    return measure_motion.cores_between(before, after, t1 - t0)


def grab_client(screen: r.Screen) -> np.ndarray:
    gx, gy, gw, gh = r.game_region()
    return screen.grab(gx, gy, gw, gh)[1][:, :, :3].copy()


def crops_of(frame: np.ndarray) -> dict[str, np.ndarray]:
    return {name: frame[y : y + h, x : x + w] for name, (x, y, w, h) in CROPS.items()}


def fidelity(frame: np.ndarray, reference_dir: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, crop in crops_of(frame).items():
        ref_path = reference_dir / f"{name}.npy"
        if not ref_path.exists():
            out[name] = None
            continue
        ref = np.load(ref_path)
        out[name] = {
            "psnr_db": round(benchlib.psnr(ref, crop), 2),
            "ssim": round(benchlib.ssim(ref, crop), 4),
        }
        mask_path = reference_dir / f"{name}_static.npy"
        if mask_path.exists():
            mask = np.load(mask_path)
            out[name]["psnr_static_db"] = round(benchlib.psnr(ref[mask], crop[mask]), 2)
    return out


def key_to_paint(agent: r.Agent, screen: r.Screen, trials: int) -> dict[str, Any]:
    """Escape (Game option window) open/close; first grab differing from the last pre-press grab."""
    gx, gy, _, _ = r.game_region()
    x, y, w, h = KEY_REGION
    region = (gx + x, gy + y, w, h)
    r.activate_client(agent, screen)
    if r.any_console(screen):
        raise r.Stop("a PowerShell console is visible: no game keys (minimise it first)")
    close_chat(agent, screen)
    watcher = subprocess.Popen(
        ["docker", "exec", "-i", r.BACKEND, "python", "-u", "-c", WATCH,
         *(str(v) for v in region), str(trials * 1.6 + 6)],
        stdout=subprocess.PIPE, text=True,
    )  # fmt: skip
    lines: list[str] = []
    assert watcher.stdout is not None
    reader = threading.Thread(target=lambda: lines.extend(watcher.stdout), daemon=True)
    reader.start()
    time.sleep(2)
    sends: list[int] = []
    for _ in range(trials):
        sends.append(r.ns())
        agent.keys("Escape")
        time.sleep(1.5)
    watcher.wait(timeout=120)
    reader.join(timeout=10)
    grabs, sources = measure_delay.parse_watch("".join(lines))
    times = [t for t, _ in grabs]
    delays: list[float] = []
    for ts in sends:
        i = bisect.bisect_left(times, ts)
        if i == 0 or i >= len(grabs):
            continue
        ref = grabs[i - 1][1]
        for t, thumb in grabs[i:]:
            if t - ts > 1_500_000_000:
                break
            if float((np.abs(thumb - ref) > 24).mean()) >= MOVED:
                delays.append((t - ts) / 1e6)
                break
    if trials % 2:
        agent.keys("Escape")  # leave the Game option window closed
    return {"key": "Escape", "region": region, **benchlib.delay_summary(delays, trials=trials),
            "frame_sources": sources, "raw_ms": [round(d, 1) for d in delays]}  # fmt: skip


# --- commands -------------------------------------------------------------------------------------


def cmd_run(a: argparse.Namespace) -> int:
    config = run_config(a.backend)
    chash = benchlib.config_hash(config)
    run_id = f"{time.strftime('%Y-%m-%d')}-{a.backend}-{chash}-{a.label}"
    evidence = EVIDENCE / "runs" / run_id
    evidence.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "run_id": run_id,
        "label": a.label,
        "config": config,
        "config_hash": chash,
        "t_wall_start": time.strftime("%FT%T%z"),
    }
    with r.session("bench") as (agent, screen):
        result["preflight"] = preflight(agent, screen, a.backend)
        scenes: dict[str, Any] = {}
        for scene in ("outdoor", "indoor"):
            r.log(f"bench: scene {scene}")
            enter_scene(agent, screen, scene)
            res: dict[str, Any] = {}
            frame = grab_client(screen)
            r.to_png(np.dstack([frame, np.full(frame.shape[:2], 255, np.uint8)]),
                     evidence / f"{scene}.png")  # fmt: skip
            res["fidelity"] = fidelity(frame, EVIDENCE / "reference")
            rot = measure_motion.measure_rotation(agent, screen, a.rotate, f"{run_id}-{scene}")
            res["delivery_fps"] = benchlib.fps_summary(rot["frames_per_s"])  # type: ignore[arg-type]
            res["frame_sources"] = {"rotation": rot["frame_sources"]}
            res["lab_cores_motion"] = rot["lab_cores"]
            enter_scene(agent, screen, scene)  # undo the rotation before anything else
            res["idle_cores"] = idle_cost(agent, a.idle)
            if scene == "outdoor":
                walks = measure_delay.measure_walks(agent, screen, a.walks)
                res["packet_to_frame_ms"] = walks["packet_to_frame_ms"]
                res["click_sent_to_packet_ms_p50"] = walks["click_sent_to_packet_ms_p50"]
                res["frame_sources"]["walks"] = walks["frame_sources"]
                (evidence / "walks_raw.json").write_text(json.dumps(walks["raw"]))
                enter_scene(agent, screen, scene)
                res["key_to_paint_ms"] = key_to_paint(agent, screen, a.keys)
                res["frame_sources"]["keys"] = res["key_to_paint_ms"]["frame_sources"]
            scenes[scene] = res
        result["scenes"] = scenes
    result["t_wall_end"] = time.strftime("%FT%T%z")
    result["label_iou"] = None  # Phase 2 placeholder (SPEC)
    result["ocr_cer"] = None  # OCR-track placeholder (SPEC)
    result["windows_side"] = None  # filled by `bench.py annotate` from the typeperf shot (SPEC)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{run_id}.json").write_text(json.dumps(result, indent=1) + "\n")
    (RESULTS / f"{run_id}.md").write_text(render_run(result))
    cmd_table()
    print(json.dumps({"run_id": run_id, "written": str(RESULTS / f"{run_id}.json")}))
    return 0


def cmd_reference() -> int:
    if read_lock(ROOT / "state").backend != "rdp":
        raise r.Stop("the lossless reference is captured over RDP (RDP_GFX=off): lock must be rdp")
    ref = EVIDENCE / "reference"
    ref.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(ROOT / "scripts" / "rdp_reconnect.sh"), "off"], check=True)
    try:
        time.sleep(10)
        with r.session("bench-reference") as (agent, screen):
            enter_scene(agent, screen, "outdoor")
            time.sleep(3)  # legacy bitmaps: let the static UI arrive in full
            frame = grab_client(screen)
            enter_scene(agent, screen, "indoor")  # the same UI over a different background
            time.sleep(3)
            again = grab_client(screen)
            enter_scene(agent, screen, "outdoor")
        static = {}
        pairs = zip(crops_of(frame).items(), crops_of(again).values(), strict=True)
        for (name, crop), other in pairs:
            np.save(ref / f"{name}.npy", crop)
            # SPEC v2 static mask: pixels identical in lossless captures of the two scenes. The
            # semi-transparent UI shows a different background through it, so those pixels differ.
            mask = (crop == other).all(axis=2)
            np.save(ref / f"{name}_static.npy", mask)
            static[name] = round(float(mask.mean()), 4)
        r.to_png(np.dstack([frame, np.full(frame.shape[:2], 255, np.uint8)]), ref / "frame.png")
        (ref / "meta.json").write_text(json.dumps({
            "captured": time.strftime("%FT%T%z"), "via": "RDP_GFX=off (planar/interleaved)",
            "crops": CROPS, "scene": "outdoor", "spec": benchlib.SPEC_VERSION,
            "static_mask": "identical in RDP-off captures of the outdoor and the indoor scene",
            "static_fraction": static,
        }, indent=1))  # fmt: skip
        print(json.dumps({"reference": str(ref), "static_fraction": static}))
    finally:
        subprocess.run([str(ROOT / "scripts" / "rdp_reconnect.sh"), "-"], check=True)
    return 0


def cmd_validate_reference(png: Path) -> int:
    """Compare Batt's hand-copied CopyFromScreen PNG (game client area) with the RDP-off crops."""
    from poring_dataset.shards import decode_png

    win = decode_png(png.read_bytes())[:, :, :3]  # BGR like our grabs (Windows saves 32-bit ARGB)
    ref = EVIDENCE / "reference"
    out = {}
    for name, (x, y, w, h) in CROPS.items():
        lab = np.load(ref / f"{name}.npy")
        crop = win[y : y + h, x : x + w]
        diff = np.abs(lab.astype(int) - crop.astype(int))
        static = (diff == 0).all(axis=2)
        # The static mask: pixels identical in the RDP-off reference AND Windows' own capture. Semi-
        # transparent UI shows the animated scene through it; those pixels vary between any two
        # captures, so fidelity is also reported over the static pixels only (SPEC 3).
        np.save(ref / f"{name}_static.npy", static)
        out[name] = {
            "identical": bool((diff == 0).all()),
            "max_abs_diff": int(diff.max()),
            "psnr_db": benchlib.psnr(lab, crop),
            "static_fraction": round(float(static.mean()), 4),
        }
    print(json.dumps(out, indent=1, default=str))
    return 0 if all(v["identical"] for v in out.values()) else 1


# --- rendering ------------------------------------------------------------------------------------


def render_run(res: dict[str, Any]) -> str:
    cfg = res["config"]
    rows = []
    for scene, s in res["scenes"].items():
        fps = s["delivery_fps"]
        rows.append([scene, fps["median"], fps["p10"], fps["p90"],
                     s["lab_cores_motion"].get("total"), s["idle_cores"].get("total")])  # fmt: skip
    out = [
        f"# Benchmark run {res['run_id']}",
        "",
        f"- SPEC v{cfg['spec']}, backend **{cfg['backend']}**, client {cfg['client']}, "
        f"config hash `{res['config_hash']}`",
        f"- {res['t_wall_start']} → {res['t_wall_end']}; preflight {res['preflight']}",
        "",
        "## Delivery and cost",
        "",
        benchlib.markdown_table(
            ["scene", "fps median", "p10", "p90", "lab cores (motion)", "idle cores"], rows
        ),
        "",
    ]
    o = res["scenes"].get("outdoor", {})
    lat = []
    for metric in ("packet_to_frame_ms", "key_to_paint_ms"):
        d = o.get(metric)
        if d:
            lat.append([metric, f"{d['matched']}/{d['trials']}", d["p50"], d["p75"], d["p90"],
                        d["p95"], d["p99"]])  # fmt: skip
    out += ["## Latency (outdoor)", "",
            benchlib.markdown_table(["metric", "matched", "p50", "p75", "p90", "p95", "p99"], lat),
            "", "## Fidelity vs the lossless reference (outdoor)", ""]  # fmt: skip
    fid = o.get("fidelity") or {}
    out.append(benchlib.markdown_table(
        ["crop", "PSNR dB", "SSIM"],
        [[k, (v or {}).get("psnr_db"), (v or {}).get("ssim")] for k, v in fid.items()],
    ))  # fmt: skip
    return "\n".join(out) + "\n"


def cmd_table() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    runs = sorted(RESULTS.glob("*.json"))
    rows = []
    for path in runs:
        res = json.loads(path.read_text())
        o, i = res["scenes"].get("outdoor", {}), res["scenes"].get("indoor", {})
        p2f, k2p = o.get("packet_to_frame_ms") or {}, o.get("key_to_paint_ms") or {}
        hp = (o.get("fidelity") or {}).get("hp_sp_panel") or {}
        fps_out = (o.get("delivery_fps") or {}).get("median")
        fps_in = (i.get("delivery_fps") or {}).get("median")
        cores = (o.get("lab_cores_motion") or {}).get("total")
        idle = (o.get("idle_cores") or {}).get("total")
        rows.append([
            f"[{res['run_id']}]({path.stem}.md)", f"v{res['config']['spec']}",
            res["config"]["backend"], fps_out, fps_in,
            cores, idle, p2f.get("p50"), p2f.get("p95"), k2p.get("p50"), k2p.get("p95"),
            hp.get("psnr_db"),
        ])  # fmt: skip
    table = benchlib.markdown_table(
        ["run", "spec", "backend", "fps out", "fps in", "cores", "idle", "p→f p50", "p→f p95",
         "k→p p50", "k→p p95", "HP/SP PSNR"], rows,
    )  # fmt: skip
    (RESULTS / "README.md").write_text(
        "# Capture-backend benchmark: running table\n\n"
        "Generated by `scripts/bench.py table` from the run JSONs in this directory; the procedure "
        "is [SPEC.md](SPEC.md). fps = delivered frames/s during full-scene motion (median); cores "
        "= lab-side display-path cores; p→f = packet→frame ms; k→p = key→paint ms. Rows of "
        "different SPEC versions are never compared: an older version is history.\n\n"
        + table
        + "\n"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--backend", required=True, choices=["rdp", "console"])
    run.add_argument("--label", required=True)
    run.add_argument("--walks", type=int, default=40)
    run.add_argument("--keys", type=int, default=40)
    run.add_argument("--rotate", type=float, default=60.0)
    run.add_argument("--idle", type=float, default=120.0)
    sub.add_parser("reference")
    val = sub.add_parser("validate-reference")
    val.add_argument("png", type=Path)
    sub.add_parser("table")
    a = ap.parse_args()
    if a.cmd == "run":
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", a.label):
            raise r.Stop("label: letters, digits, _ . - only")
        return cmd_run(a)
    if a.cmd == "reference":
        return cmd_reference()
    if a.cmd == "validate-reference":
        return cmd_validate_reference(a.png)
    return cmd_table()


if __name__ == "__main__":
    sys.exit(main())
