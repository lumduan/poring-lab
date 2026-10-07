#!/usr/bin/env python3
"""LABEL-QA: qwen3-vl as a second-opinion FLAGGER, measured on the gold set first (phase3-plan §6,
pre-registered in b9d3aee, Batt 2026-10-07). A FLAGGER, never ground truth: packets and the
hand-checked set stay the references, and a disagreement only sends a label to human review.

    .venv/bin/python scripts/vlm_flag.py measure SESSION OUT.jsonl [--limit N]
        Every hand-checked monster box of SESSION's gold frames, plus as many seeded random EMPTY
        crops of the same sizes that touch no hand box, each at two crop sizes (tight, +50 %
        context per side), asked once each. One JSON line per answer: the crop, the truth (monster
        / empty, species from the position-matched v1 label), the answer, seconds, the prompt
        sha256 and the model digest.
    .venv/bin/python scripts/vlm_flag.py score OUT.jsonl
        The pre-registered bar per crop size: monster-present recall >= 0.90 AND false-"monster"
        rate on the empty crops <= 0.10; species accuracy and the occluded/UI/dead answers are
        reported without a bar.

HOST script only: Ollama listens on 127.0.0.1:11434 and no poring-lab container joins its network
(ADR-0005). The GPU sharing rules apply (scripts/frigate_r3.py):
- R2: refused while another model is loaded or any job of ours is on the GPU; a model other
  than ours loading mid-run stops it;
- R3, PAIRED (docs/operations/r3-paired.md): from the first answer (the model is loaded), ON
  windows send requests and OFF windows send none, 180 s each; the run stops on the paired
  median delta > 5 ms, INCONCLUSIVE, Frigate unreachable, or (hard) a camera dropping frames.
temperature 0, think false, keep_alive 10 min (the model stays loaded across an OFF window, so
an ON window never measures a reload; ~4.7 GB, R1-safe alone), and an explicit unload at the end.
The gold frames are client-derived pixels: crops stay in RAM, and nothing is written but the
answers (OUT on /dev/shm).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import random
import sys
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import frigate_r3  # noqa: E402
import label_iou  # noqa: E402
import qa_export  # noqa: E402

MODEL = "qwen3-vl:4b"
DIGEST = "1343d82ebee38e26a4dd6b0180b915eb91550184e67c505dea97509571c8f683"
GOLD = ROOT / "data" / "train" / "eval" / "gold"
SEED = 20261007
CONTEXT = {"tight": 0.0, "context50": 0.5}
SPECIES = ["poring", "lunatic", "fabre", "pupa", "drops", "chonchon", "willow", "roda frog",
           "rocker", "condor", "picky", "thief bug", "other", "unknown"]  # fmt: skip
PROMPT = (
    "This is a crop from a Ragnarok Online game screenshot. Answer about the CENTRE of the crop. "
    "monster: is a monster (not a player character, not an NPC, not scenery) at the centre? "
    f"species: if a monster, which one, from: {', '.join(SPECIES)}; otherwise 'none'. "
    "occluded: is it partly hidden behind scenery or another sprite? "
    "under_ui: is it partly covered by a game window or interface element? "
    "dead: is it dying or lying dead? Reply in JSON only."
)
SCHEMA = {
    "type": "object",
    "properties": {"monster": {"type": "boolean"}, "species": {"type": "string"},
                   "occluded": {"type": "boolean"}, "under_ui": {"type": "boolean"},
                   "dead": {"type": "boolean"}},
    "required": ["monster", "species", "occluded", "under_ui", "dead"],
}  # fmt: skip
KEEP_ALIVE = "10m"  # longer than an OFF window (180 s): no reload inside an ON window
PROMPT_SHA = hashlib.sha256((PROMPT + json.dumps(SCHEMA, sort_keys=True)).encode()).hexdigest()


def post(path: str, body: dict[str, Any], timeout: float = 120) -> dict[str, Any]:
    req = Request(f"{frigate_r3.OLLAMA}{path}", data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"})  # fmt: skip
    with urlopen(req, timeout=timeout) as r:  # noqa: S310 (fixed loopback URL)
        return json.load(r)  # type: ignore[no-any-return]


def ask(png: bytes) -> tuple[dict[str, Any], float]:
    t0 = time.monotonic()
    res = post("/api/generate", {
        "model": MODEL, "prompt": PROMPT, "images": [base64.b64encode(png).decode()],
        "format": SCHEMA, "stream": False, "think": False, "keep_alive": KEEP_ALIVE,
        "options": {"temperature": 0, "seed": 0},
    })  # fmt: skip
    return json.loads(res["response"]), time.monotonic() - t0


def unload() -> None:
    post("/api/generate", {"model": MODEL, "keep_alive": 0}, timeout=30)


def crop_png(img: Any, box: tuple[float, float, float, float], ctx: float) -> bytes:
    x0, y0, x1, y1 = box
    pw, ph = (x1 - x0) * ctx, (y1 - y0) * ctx
    w, h = img.size
    c = img.crop((max(0, int(x0 - pw)), max(0, int(y0 - ph)),
                  min(w, int(x1 + pw + 0.999)), min(h, int(y1 + ph + 0.999))))  # fmt: skip
    buf = io.BytesIO()
    c.save(buf, format="PNG")
    return buf.getvalue()


def overlaps(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def species_of(lab: qa_export.Labeler, t: int, box: dict[str, Any]) -> str:
    """The position-matched v1 label's species (aegis name, lower case), or 'unknown'."""
    auto = lab.boxes(t) or []
    mons = [b for b in auto if b["cls"] == "monster"]
    cx, cy = (box["x1"] + box["x2"]) / 2, (box["y1"] + box["y2"]) / 2
    best = None
    for b in mons:
        bx, by = (b["x1"] + b["x2"]) / 2, (b["y1"] + b["y2"]) / 2
        if box["x1"] <= bx <= box["x2"] and box["y1"] <= by <= box["y2"]:
            d = (bx - cx) ** 2 + (by - cy) ** 2
            if best is None or d < best[0]:
                best = (d, b)
    if best is None:
        return "unknown"
    world = lab.timeline.frame_world(t - int(lab.offset_ms * 1e6))
    job = next((e.job for e in world.entities if e.gid == best[1]["gid"]), None)
    return qa_export.job_aegis().get(int(job), "unknown").lower() if job is not None else "unknown"


def r3_wait(r3: Any, sleep: Any = time.sleep) -> tuple[str, str, bool] | None:
    """Poll Frigate, advance the paired schedule, and idle through an OFF window (no requests).
    Returns a breach, or None when a request may go out (ON, or the schedule not started)."""
    while True:
        r3.poll()
        act = r3.tick()
        if act:
            state = "OFF: no requests" if act == "pause" else "ON: requests"
            print(f"[{frigate_r3.stamp()}] R3 {state}", flush=True)
        hit: tuple[str, str, bool] | None = r3.breach()
        if hit or r3.phase != "off":
            return hit
        sleep(2.0)


def gate() -> str | None:
    why = frigate_r3.prestart(None)
    if why:
        return why
    tags = frigate_r3.fetch_json(f"{frigate_r3.OLLAMA}/api/tags") or {}
    digests = {m.get("name"): m.get("digest") for m in tags.get("models") or []}
    if digests.get(MODEL) != DIGEST:
        return f"{MODEL} digest {digests.get(MODEL)} != the licence-checked {DIGEST[:12]}"
    return None


def measure(session: str, out: Path, limit: int | None) -> int:
    from PIL import Image

    why = gate()
    if why:
        print(f"[{frigate_r3.stamp()}] REFUSED: {why}", flush=True)
        return 3
    r3 = frigate_r3.PairedR3(short=False, cam_ref=frigate_r3.camera_reference(), started=False,
                             allow_models=[MODEL])  # fmt: skip
    hand = json.loads((label_iou.HANDCHECK / f"{session}.json").read_text())
    index = {
        int(t): fid for fid, t in json.loads((GOLD / session / "index.json").read_text()).items()
    }
    found = label_iou.find_session(
        session, label_iou.dataset_ship.NAS_ROOT, ROOT / "data" / "datasets"
    )
    lab = qa_export.Labeler(found, "auto", labels="v1", k=0.140)
    rng = random.Random(SEED)
    jobs: list[dict[str, Any]] = []
    for fr in hand["frames"]:
        fid = index.get(int(fr["t_mono_ns"]))
        if fid is None:
            continue
        boxes = [(b["x1"], b["y1"], b["x2"], b["y2"]) for b in fr["boxes"]]
        for b in fr["boxes"]:
            if b["cls"] != "monster":
                continue
            sp = species_of(lab, int(fr["t_mono_ns"]), b)
            box = [b["x1"], b["y1"], b["x2"], b["y2"]]
            jobs.append({"fid": fid, "truth": "monster", "box": box, "species": sp})
            w, h = b["x2"] - b["x1"], b["y2"] - b["y1"]
            for _ in range(200):  # an empty crop of the same size touching no hand box
                x0, y0 = rng.uniform(0, 1280 - w * 2), rng.uniform(0, 720 - h * 2)
                e = (x0, y0, x0 + w, y0 + h)
                grown = (e[0] - w / 2, e[1] - h / 2, e[2] + w / 2, e[3] + h / 2)
                if not any(overlaps(grown, hb) for hb in boxes):
                    jobs.append({"fid": fid, "truth": "empty", "box": list(e), "species": "none"})
                    break
    if limit:
        jobs = jobs[:limit]
    print(f"[{frigate_r3.stamp()}] {len(jobs)} boxes x {len(CONTEXT)} crop sizes", flush=True)
    with out.open("w") as fh:
        try:
            for i, j in enumerate(jobs):
                img = Image.open(GOLD / session / "frames" / f"{j['fid']}.png").convert("RGB")
                for size, ctx in CONTEXT.items():
                    hit = r3_wait(r3)
                    if hit:
                        hard = " (R3-HARD)" if hit[2] else ""
                        print(
                            f"[{frigate_r3.stamp()}] ABORT vlm_flag: R3 {hit[0]}: {hit[1]}{hard}",
                            flush=True,
                        )
                        return 1
                    answer, secs = ask(crop_png(img, tuple(j["box"]), ctx))
                    if not r3.started:
                        r3.start()  # the model is loaded: the first ON window opens now
                        print(f"[{frigate_r3.stamp()}] R3 schedule started", flush=True)
                    fh.write(
                        json.dumps(
                            {
                                **j,
                                "crop": size,
                                "answer": answer,
                                "seconds": round(secs, 2),
                                "model": MODEL,
                                "digest": DIGEST,
                                "prompt_sha256": PROMPT_SHA,
                            }
                        )
                        + "\n"
                    )
                    fh.flush()
                if i % 20 == 0:
                    print(f"[{frigate_r3.stamp()}] {i + 1}/{len(jobs)}", flush=True)
        finally:
            unload()
            print(f"[{frigate_r3.stamp()}] R3 summary: {json.dumps(r3.summary())}", flush=True)
    return 0


def score(out: Path) -> int:
    rows = [json.loads(x) for x in out.open() if x.strip()]
    res: dict[str, Any] = {"prompt_sha256": rows[0]["prompt_sha256"], "digest": rows[0]["digest"]}
    for size in CONTEXT:
        r = [x for x in rows if x["crop"] == size]
        mon = [x for x in r if x["truth"] == "monster"]
        emp = [x for x in r if x["truth"] == "empty"]
        recall = sum(x["answer"]["monster"] for x in mon) / max(1, len(mon))
        false_mon = sum(x["answer"]["monster"] for x in emp) / max(1, len(emp))
        known = [x for x in mon if x["species"] != "unknown"]
        per_sp: dict[str, list[int]] = {}
        for x in known:
            per_sp.setdefault(x["species"], []).append(
                int(x["answer"]["species"].strip().lower() == x["species"])
            )
        res[size] = {
            "monster_crops": len(mon), "empty_crops": len(emp),
            "monster_recall": round(recall, 3), "false_monster_rate": round(false_mon, 3),
            "useful_as_flagger": recall >= 0.90 and false_mon <= 0.10,
            "species_accuracy": {sp: round(sum(v) / len(v), 3) for sp, v in per_sp.items()},
            "species_unknown_truth": len(mon) - len(known),
            "said_occluded": round(sum(x["answer"]["occluded"] for x in mon) / max(1, len(mon)), 3),
            "said_under_ui": round(sum(x["answer"]["under_ui"] for x in mon) / max(1, len(mon)), 3),
            "said_dead": round(sum(x["answer"]["dead"] for x in mon) / max(1, len(mon)), 3),
            "seconds_median": sorted(x["seconds"] for x in r)[len(r) // 2] if r else None,
        }  # fmt: skip
    print(json.dumps(res, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("session")
    m.add_argument("out", type=Path)
    m.add_argument("--limit", type=int)
    s = sub.add_parser("score")
    s.add_argument("out", type=Path)
    a = ap.parse_args()
    if a.cmd == "measure":
        if not str(a.out).startswith("/dev/shm/"):
            sys.exit("keep the answers on /dev/shm (CLAUDE.md rule 7)")
        return measure(a.session, a.out, a.limit)
    return score(a.out)


if __name__ == "__main__":
    sys.exit(main())
