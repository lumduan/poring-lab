#!/usr/bin/env python3
"""Record a session for Phase 2 (ADR-0010): lossless GAME_REGION frames + the packet events.

    record_session.py --backend rdp --label calib --seconds 120 [--fps 10] [--out DIR]
                      [--max-bytes 2G]

* Frames: GAME_REGION grabbed inside the backend container (ro_agent.Screen: same CLOCK_MONOTONIC
  as the packets), at most --fps, and only when the picture changed (a still scene costs nothing).
  Lossless PNG in WebDataset-style tar shards (poring_dataset.shards).
  In console mode (S2, ADR-0014) the frames come from the S2 frame bus: each record carries the
  bus writer's `bus_frame_id`, `source` and the decode-complete time as `t_mono_ns`, and the
  recording STOPS on the first non-bus frame (an X grab there is a black or foreign picture).
  RDP mode grabs X (`source` x11, `bus_frame_id` -1).
* Packets: after the run, the sniffer's events for [t0 - 5 s, t1 + 5 s], with every name and chat
  line of anyone but the lab's own accounts replaced by an HMAC pseudonym (CLAUDE.md rule 9; the
  salt lives in data/dataset-pseudonym.salt, gitignored, never in a shard).
* Safety: the capture-backend lock must say --backend (ADR-0009); the quant IO guard
  (guarded_build's Guard, tolerant rule) stops the recording on a breach; a hard size cap.
* Sink (ADR-0010): the VM's local disk, /home/batt/poring-lab-rec (never ./data: vision mounts it).
  It is a buffer on the disk shared with live capture, so it is capped -- refused at the start, and
  stopped cleanly mid-recording, when the filesystem has < --min-free-gb free or more than
  --max-unshipped-gb of sessions wait under the root. scripts/dataset_ship.py ships them to the
  TrueNAS cold store (checksummed, verified, then deleted locally). A warning during SET hours.
"""

import argparse
import gzip
import hashlib
import hmac
import importlib.util
import io
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dataset_ship  # noqa: E402
import measure_delay  # noqa: E402
import ro_agent as r  # noqa: E402

from poring_backend.capture_lock import read_lock  # noqa: E402
from poring_dataset.shards import ShardWriter, write_manifest  # noqa: E402
from poring_dataset.timeline import session_events  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SALT = ROOT / "data" / "dataset-pseudonym.salt"
RECORDER_VERSION = 3  # v3: bus frame ids + source per frame (S2); v2: the packet anchor
CAP_CHECK_S = 5.0  # how often the local caps are re-checked while recording


def load_guard() -> Any:
    spec = importlib.util.spec_from_file_location(
        "guarded_build", ROOT / "scripts" / "guarded_build.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Guard(module.cgroup_paths(), 10.0, 10.0, sustain=30.0, spike=25.0)


def parse_size(text: str) -> int:
    m = re.fullmatch(r"(\d+)([KMG]?)", text.upper())
    if m is None:
        raise SystemExit(f"bad size {text!r}")
    return int(m.group(1)) * {"": 1, "K": 1 << 10, "M": 1 << 20, "G": 1 << 30}[m.group(2)]


def pseudonymiser() -> Any:
    SALT.parent.mkdir(parents=True, exist_ok=True)
    if not SALT.exists():
        SALT.write_text(secrets.token_hex(32))
        SALT.chmod(0o600)
    key = bytes.fromhex(SALT.read_text().strip())
    env = r.env()
    lab = {env.get("RATHENA_GM_CHAR", ""), env.get("RATHENA_AGENT_CHAR", "")} - {""}

    def name(value: str) -> str:
        if not value or value in lab:
            return value
        return "p_" + hmac.new(key, value.encode(), hashlib.sha256).hexdigest()[:10]

    def event(e: dict[str, Any]) -> dict[str, Any]:
        e = dict(e)
        if e.get("type") == "entity_appear" and e.get("objtype") == 0:
            e["name"] = name(str(e.get("name", "")))
        if e.get("type") == "chat":
            speaker = str(e.get("speaker") or "")
            if speaker not in lab:
                e["speaker"] = name(speaker)
                e["text"] = "<pseudonymised>"
                e["raw_hex"] = ""
        return e

    return event


LOOKBACK_S = 30 * 60  # how far before t0 to look for the anchor (the last map change)


def packets_for(t0_ns: int, t1_ns: int) -> list[dict[str, Any]]:
    """The sniffer's events for [t0 - 5 s, t1 + 5 s] (the measurement window)."""
    return _events_since(t0_ns, 5, t0_ns - 5_000_000_000, t1_ns)


def session_packets(t0_ns: int, t1_ns: int) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """A recording's events: from the last map change before t0 (so the player's position and the
    entities already on screen are known) through t1 + 5 s. See timeline.session_events."""
    events = _events_since(t0_ns, LOOKBACK_S + 5, t0_ns - (LOOKBACK_S + 5) * 1_000_000_000, t1_ns)
    return session_events(events, t0_ns, t1_ns, lookback_ns=LOOKBACK_S * 1_000_000_000)


def _events_since(t0_ns: int, back_s: float, lo_ns: int, t1_ns: int) -> list[dict[str, Any]]:
    since_wall = time.time() - (r.ns() - t0_ns) / 1e9
    files = measure_delay.events_files(since_wall - back_s)
    if not files:
        return []
    raw = subprocess.run(
        ["docker", "exec", "poring-lab-sniffer-1", "cat", *files], capture_output=True, check=True
    ).stdout
    out: list[dict[str, Any]] = []
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as fh:
        try:
            for line in fh:
                e = json.loads(line)
                if lo_ns <= int(e.get("t_mono_ns", 0)) <= t1_ns + 5_000_000_000:
                    out.append(e)
        except EOFError:
            pass
    return out


def record(a: argparse.Namespace) -> dict[str, Any]:
    lock = read_lock(ROOT / "state")
    if lock.backend != a.backend or lock.phase != "steady":
        raise r.Stop(f"the lock says {lock.backend}/{lock.phase}, not {a.backend}/steady")
    import bench  # the same config + hash as the benchmark

    caps = {"min_free": int(a.min_free_gb * 1e9), "max_unshipped": int(a.max_unshipped_gb * 1e9)}
    unshipped = dataset_ship.unshipped_bytes(a.out)
    refused = dataset_ship.local_caps(a.out, unshipped=unshipped, **caps)
    if refused:
        raise r.Stop(f"not recording: {refused}")
    if dataset_ship.in_set_hours():
        print("WARNING: SET hours -- the quant stack is busiest now; the IO guard stays armed",
              file=sys.stderr)  # fmt: skip
    config = bench.run_config(a.backend)
    chash = bench.benchlib.config_hash(config)
    session_id = f"{time.strftime('%Y%m%dT%H%M%S')}-{a.backend}-{a.label}"
    out = a.out / session_id
    writer = ShardWriter(out)
    guard = load_guard()
    gx, gy, gw, gh = r.game_region()
    period = 1.0 / a.fps
    screen = r.Screen()
    stop_reason = "duration"
    t0 = r.ns()
    t_end = time.monotonic() + a.seconds
    prev: np.ndarray | None = None
    frame_id = skipped = repeats = 0
    last_bus_id = -1
    sources: dict[str, int] = {}
    next_cap_check = time.monotonic() + CAP_CHECK_S
    try:
        with subprocess.Popen(["ionice", "-c3", "-p", str(os.getpid())]) as p:
            p.wait()
        next_t = time.monotonic()
        while time.monotonic() < t_end:
            t_cap, img, bus_id, source = screen.grab_meta(gx, gy, gw, gh)
            sources[source] = sources.get(source, 0) + 1
            if a.backend == "console" and source != "bus":
                stop_reason = "non_bus_frame: the S2 frame bus went away (console mode)"
                break
            bgr = img[:, :, :3].copy()
            if source == "bus" and bus_id == last_bus_id:
                repeats += 1  # no new decoded frame since the last grab
            elif prev is not None and np.array_equal(bgr, prev):
                skipped += 1
            else:
                writer.add(frame_id, t_cap, bgr, t_wall=time.strftime("%FT%T%z"),
                           bus_frame_id=bus_id, source=source)  # fmt: skip
                frame_id += 1
                prev = bgr
            last_bus_id = bus_id
            if writer.bytes > a.max_bytes:
                stop_reason = "size_cap"
                break
            hit = guard.breach()
            if hit:
                stop_reason = f"io_guard: {hit[0]} {hit[1]:.1f}% ({hit[2]})"
                break
            if time.monotonic() >= next_cap_check:
                next_cap_check += CAP_CHECK_S
                full = dataset_ship.local_caps(
                    a.out, unshipped=unshipped, extra=writer.bytes, **caps
                )
                if full:
                    stop_reason = f"local_cap: {full}"
                    break
            next_t += period
            time.sleep(max(0.0, next_t - time.monotonic()))
    finally:
        writer.close()
        screen.close()
    t1 = r.ns()
    events, anchor = write_packets(out, t0, t1)
    seconds = (t1 - t0) / 1e9
    manifest = {
        "session_id": session_id, "recorder_version": RECORDER_VERSION,
        "backend": a.backend, "lock_seq": lock.seq, "config": config, "config_hash": chash,
        "game_region": [gx, gy, gw, gh], "fps_cap": a.fps, "shards": writer.shards,
        "frames": writer.frames, "unchanged_skipped": skipped, "bus_repeats": repeats,
        "frame_sources": sources, "bytes": writer.bytes,
        "t0_mono_ns": t0, "t1_mono_ns": t1, "seconds": round(seconds, 1),
        "mb_per_min": round(writer.bytes / 1e6 / max(seconds / 60, 1e-9), 1),
        "stop_reason": stop_reason, "guard": guard.summary(), "packet_events": len(events),
        "packet_anchor": anchor, "pseudonymised": True,
        "sink": {"root": str(a.out), **caps},
    }  # fmt: skip
    write_manifest(out, manifest)
    keys = ("frames", "bytes", "mb_per_min", "stop_reason", "packet_events")
    return {"dir": str(out), **{k: manifest[k] for k in keys}}


def write_packets(
    out: Path, t0: int, t1: int
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    events, anchor = session_packets(t0, t1)
    pseudo = pseudonymiser()
    with gzip.open(out / "packets.jsonl.gz", "wt") as fh:
        for e in events:
            fh.write(json.dumps(pseudo(e), sort_keys=True) + "\n")
    return events, anchor


def repack(session: Path) -> dict[str, Any]:
    """Rebuild a session's packets.jsonl.gz from the sniffer's archive (kept 7 days) with the
    current window rule, and update the manifest. Frames are untouched."""
    manifest = json.loads((session / "manifest.json").read_text())
    events, anchor = write_packets(session, manifest["t0_mono_ns"], manifest["t1_mono_ns"])
    manifest.update(
        packet_events=len(events), packet_anchor=anchor, recorder_version=RECORDER_VERSION
    )
    write_manifest(session, manifest)
    return {"dir": str(session), "packet_events": len(events), "packet_anchor": anchor}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--repack", type=Path, help="rebuild an existing session's packets file")
    ap.add_argument("--backend", choices=["rdp", "console"])
    ap.add_argument("--label")
    ap.add_argument("--seconds", type=float, default=120.0)
    ap.add_argument("--fps", type=float, default=10.0)
    ap.add_argument("--out", type=Path, default=dataset_ship.LOCAL_ROOT)
    ap.add_argument(
        "--max-bytes",
        type=parse_size,
        required=True,
        help="hard size cap for this session, e.g. 12G (explicit: no default)",
    )
    ap.add_argument(
        "--min-free-gb",
        type=float,
        default=dataset_ship.MIN_FREE_BYTES / 1e9,
        help="refuse / stop below this much free space on --out's filesystem",
    )
    ap.add_argument(
        "--max-unshipped-gb",
        type=float,
        default=dataset_ship.MAX_UNSHIPPED_BYTES / 1e9,
        help="refuse / stop above this much unshipped data under --out",
    )
    a = ap.parse_args()
    if a.repack:
        print(json.dumps(repack(a.repack)))
        return 0
    if not a.backend or not a.label:
        raise r.Stop("--backend and --label are required to record")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", a.label):
        raise r.Stop("label: letters, digits, _ . - only")
    if str(a.out.resolve()).startswith(str((ROOT / "data").resolve())):
        raise r.Stop("never under ./data: vision mounts it (ADR-0010)")
    print(json.dumps(record(a)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
