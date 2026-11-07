#!/usr/bin/env python3
"""Is poring-lab whole on bot-server? (docs/planning/bot-server-cutover.md; Batt 2026-11-07: "a
script that checks the move and its completeness, the agent included")

    python3 scripts/migration_check.py manifest --out M.json [--hash-data]   # on VM 103, the source
    python3 scripts/migration_check.py check --manifest M.json --phase prep|final   # on bot-server

Stdlib only: both hosts' bare python3. bot-server has no way back to VM 103, so the manifest is
pushed there (scp) and checked there.

- The manifest records what must arrive:
  - the repo's HEAD;
  - `.env` KEY BY KEY as salted sha256 (never a value);
  - `settings/`, `state/`, `data/` and `~/.cache/poring-lab` file by file (size, plus sha256
    for the small trees; `--hash-data` hashes `data/` too);
  - the database's exact row counts;
  - the agent: memory files, the history's sizes and counts, the global CLAUDE.md, the skills.
- The check compares those and adds the target's own readiness:
  - Docker's address pools and the networks pinned off 192.168 / 172.16; the VLAN route via the
    router;
  - the images built; the containers healthy (final);
  - the Intel GPU's render node;
  - the NAS mounts;
  - `HOST_LAN_IP`; `WIN_HOST` empty in "prep" (else the desktop takes the ONE Windows session),
    set in "final".
- Rows are PASS / FAIL / SKIP; the exit code is 1 on any FAIL.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
HOME = Path.home()
SOURCE_HOST, TARGET_HOST, TARGET_IP = "ubuntu-docker", "bot-server", "192.168.1.228"
PROJECT_KEYS = {"source": "-home-batt-docker-poring-lab", "target": "-home-bot-docker-poring-lab"}
# .env keys allowed (expected) to differ on the target
ENV_DIFFERS = {"HOST_LAN_IP": "the target's own address", "WIN_HOST": "empty until the cutover",
               "VISION_MAX_VRAM_FRACTION": "1.0: nothing else on the target's GPU"}  # fmt: skip
TARGET_PROFILE = "dedicated-intel"  # ADR-0022: scripts/host_profile.py
SMALL_TREES = ("settings", "state")
SKIP_STATE = ("state/train-duty",)  # the duty level: written by the running guard, not moved
DB_TABLES = ("login", "char", "inventory", "cart_inventory", "storage", "skill", "party",
             "guild", "global_acc_reg_num", "global_acc_reg_str", "char_reg_num", "char_reg_str",
             "acc_reg_num", "acc_reg_str", "mail", "hotkey", "quest", "chatlog")  # fmt: skip
NAS_MOUNTS = ("/mnt/poring-lab-datasets", "/mnt/poring-locale-packs", "/mnt/poring-thai-src")
# The RAM run-time inputs (CLAUDE.md rule 7: the GAT maps, sprites, calibrations, the chat guard;
# the KB, the rathena source it reads, the detector's models), file by file with sha256 (RAM).
# scripts/runtime_sync.py pushes them RAM to RAM. Not here: scratch, logs, locks, test leftovers,
# VM 103's own state (Frigate's baseline, the clean room), and the packet-table generator's cache
# (bot-server generates its own table: byte-identical, 2026-11-07).
SHM = Path("/dev/shm")
RUNTIME = ("poring-lab-kb", "poring-lab-rathena-src", "poring-lab-detector/model",
           "poring-lab-tmp/gat", "poring-lab-tmp/sprites", "poring-lab-tmp/hotbar-cal",
           "poring-lab-tmp/talk-cal", "poring-lab-tmp/walk5-cal", "poring-lab-tmp/collect-v2",
           "poring-lab-tmp/stage-gef10", "poring-lab-tmp/xmas-det",
           "poring-lab-tmp/chat-guard.json")  # fmt: skip
DETECTOR_PY = SHM / "poring-lab-detector" / ".venv" / "bin" / "python"
SKILLS = ("bilingual-report", "research-doc-metadata", "roadmap-format", "craft-prompt",
          "claude-code-restart")  # fmt: skip
PREFACE_MARK = "# READ FIRST on bot-server"
FORBIDDEN_NETS = (ipaddress.ip_network("192.168.0.0/16"), ipaddress.ip_network("172.16.0.0/12"))
POOL = ipaddress.ip_network("10.210.0.0/16")
# ADR-0022: the target runs the Intel vision image where the source ran the NVIDIA one
IMAGE_SUBSTITUTES = {"poring-lab/vision:local": "poring-lab/vision-intel:local"}

Row = dict[str, str]


# --- pure helpers -------------------------------------------------------------------------------
def parse_env(text: str) -> dict[str, str]:
    """PURE: KEY=value lines (comments and blanks skipped; the first occurrence wins)."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out.setdefault(k.strip(), v)
    return out


def salted(salt: str, value: str) -> str:
    return hashlib.sha256((salt + "\0" + value).encode()).hexdigest()


def env_rows(want: Mapping[str, str], have: Mapping[str, str], salt: str,
             phase: str) -> list[Row]:  # fmt: skip
    """PURE: compare the manifest's salted hashes with the target's values, key by key."""
    rows: list[Row] = []
    missing = sorted(set(want) - set(have))
    rows.append(row("env: every key present", not missing, f"missing {missing}" if missing
                    else f"{len(want)} keys"))  # fmt: skip
    same = [k for k in want if k in have and k not in ENV_DIFFERS
            and salted(salt, have[k]) == want[k]]  # fmt: skip
    differ = sorted(k for k in want if k in have and k not in ENV_DIFFERS and k not in same)
    rows.append(row("env: the values equal (salted hashes)", not differ and bool(same),
                    f"differ: {differ}" if differ else f"{len(same)} equal"))  # fmt: skip
    rows.append(row("env: HOST_LAN_IP is the target's", have.get("HOST_LAN_IP") == TARGET_IP,
                    f"HOST_LAN_IP={have.get('HOST_LAN_IP')!r}"))  # fmt: skip
    prof = have.get("LAB_HOST_PROFILE")
    rows.append(row(f"env: LAB_HOST_PROFILE={TARGET_PROFILE} (ADR-0022)", prof == TARGET_PROFILE,
                    f"LAB_HOST_PROFILE={prof!r}"))  # fmt: skip
    cap = have.get("VISION_MAX_VRAM_FRACTION")
    rows.append(row("env: VISION_MAX_VRAM_FRACTION=1.0 (a dedicated GPU)", cap == "1.0",
                    f"VISION_MAX_VRAM_FRACTION={cap!r}"))  # fmt: skip
    win = have.get("WIN_HOST", "")
    if phase == "prep":
        rows.append(row("env: WIN_HOST EMPTY before the cutover (ADR-0001: one session)",
                        not win, "set" if win else "empty"))  # fmt: skip
    else:
        rows.append(
            row("env: WIN_HOST set after the cutover", bool(win), "set" if win else "empty")
        )
    return rows


def tree_rows(name: str, want: Mapping[str, Mapping[str, Any]],
              have: Mapping[str, Mapping[str, Any]]) -> list[Row]:  # fmt: skip
    """PURE: every manifest file present with the same size (and sha256 when both have one)."""
    missing = sorted(set(want) - set(have))
    wrong = sorted(f for f in want if f in have and (
        want[f]["size"] != have[f]["size"]
        or (want[f].get("sha256") and have[f].get("sha256")
            and want[f]["sha256"] != have[f]["sha256"])))  # fmt: skip
    ok = bool(want) and not missing and not wrong  # an empty source item proves nothing
    detail = (f"{len(want)} files" if ok else "the source has no file here" if not want else
              f"missing {len(missing)} {missing[:3]}; differ {len(wrong)} {wrong[:3]}")  # fmt: skip
    return [row(f"{name}: every file arrived, the same", ok, detail)]


def pinned(subnets: Iterable[str]) -> tuple[bool, list[str]]:
    """PURE: every subnet inside 10.210.0.0/16 and none in 192.168/16 or 172.16/12."""
    bad = []
    for s in subnets:
        n = ipaddress.ip_network(s, strict=False)
        if any(n.overlaps(f) for f in FORBIDDEN_NETS) or not n.subnet_of(POOL):  # type: ignore[arg-type]
            bad.append(s)
    return not bad, bad


def row(item: str, ok: bool | None, detail: str = "") -> Row:
    return {"item": item, "status": "SKIP" if ok is None else ("PASS" if ok else "FAIL"),
            "detail": detail}  # fmt: skip


# --- probes -------------------------------------------------------------------------------------
def run(cmd: Sequence[str], stdin: str | None = None, timeout: float = 60) -> tuple[int, str]:
    try:
        r = subprocess.run(list(cmd), input=stdin, capture_output=True, text=True,
                           timeout=timeout, check=False)  # fmt: skip
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, str(exc)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree(root: Path, rel_to: Path, hash_files: bool, skip: Sequence[str] = ()) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        rel = str(p.relative_to(rel_to))
        if not p.is_file() or p.is_symlink() or any(rel.startswith(s) for s in skip):
            continue
        rec: dict[str, Any] = {"size": p.stat().st_size}
        if hash_files:
            rec["sha256"] = sha256_file(p)
        out[rel] = rec
    return out


def runtime_tree(name: str, shm: Path = SHM) -> dict[str, Any]:
    """One RUNTIME item (a directory or a single file), keyed relative to /dev/shm, hashed."""
    root = shm / name
    if root.is_file() and not root.is_symlink():
        return {name: {"size": root.stat().st_size, "sha256": sha256_file(root)}}
    return tree(root, shm, True)


def db_counts(env: Mapping[str, str]) -> dict[str, int] | str:
    """Exact row counts of the lab's key tables, through the db container (the root password goes
    on stdin as an option file, never an argv)."""
    db = env.get("DB_NAME", "ragnarok")
    sql = " UNION ALL ".join(f"SELECT '{t}', COUNT(*) FROM `{db}`.`{t}`" for t in DB_TABLES)
    cnf = f"[client]\nuser=root\npassword={env.get('DB_ROOT_PASSWORD', '')}\n"
    # the SQL as a plain argv (no shell: its backticks stay literal); the password on stdin
    code, out = run(["docker", "exec", "-i", "poring-lab-db-1", "mariadb",
                     "--defaults-extra-file=/dev/stdin", "-N", "-e", sql], stdin=cnf)  # fmt: skip
    if code != 0:
        return f"db unreadable (rc {code}): {out.strip()[:120]}"
    counts: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[1].strip().isdigit():
            counts[parts[0]] = int(parts[1])
    return counts


def count(d: Path) -> int:
    return len(list(d.glob("*"))) if d.exists() else 0


def claude_side(key: str) -> dict[str, Any]:
    base = HOME / ".claude"
    proj = base / "projects" / key
    hist = {p.name: p.stat().st_size for p in proj.glob("*.jsonl")}
    sessions: dict[str, dict[str, int]] = {}
    if proj.exists():
        for d in proj.iterdir():
            if d.is_dir() and d.name != "memory":
                sessions[d.name] = {"subagents": count(d / "subagents"),
                                    "tool_results": count(d / "tool-results")}  # fmt: skip
    mem_dir = proj / "memory"
    mem = {p.name: sha256_file(p) for p in sorted(mem_dir.glob("*.md"))} if mem_dir.exists() else {}
    claude_md = base / "CLAUDE.md"
    skills: dict[str, dict[str, str]] = {}
    for s in SKILLS:
        sd = base / "skills" / s
        if sd.exists():
            skills[s] = {f.name: sha256_file(f) for f in sorted(sd.glob("*")) if f.is_file()}
    return {"history": hist, "sessions": sessions, "memory": mem,
            "claude_md": claude_md.read_text() if claude_md.exists() else "",
            "skills": skills}  # fmt: skip


def claude_rows(want: Mapping[str, Any], have: Mapping[str, Any]) -> list[Row]:
    """PURE: the agent arrived whole: memory identical, every transcript at least as long, every
    session's subagents and tool results there, Batt's CLAUDE.md verbatim under the preface, the
    skills identical."""
    rows = []
    wm, hm = want["memory"], have["memory"]
    diff = sorted(k for k in wm if hm.get(k) != wm[k])
    rows.append(row("agent: memory files identical", not diff and bool(wm),
                    f"{len(wm)} files" if not diff else f"missing/differ {diff[:4]}"))  # fmt: skip
    hh = have["history"]
    short = sorted(k for k, v in want["history"].items() if hh.get(k, -1) < v)
    n_hist = len(want["history"])
    rows.append(row("agent: the history (every transcript, at least as long)", not short,
                    f"{n_hist} transcripts" if not short else f"short {short}"))  # fmt: skip
    hs = have["sessions"]
    lack = sorted(k for k, v in want["sessions"].items()
                  if any(hs.get(k, {}).get(f, -1) < n for f, n in v.items()))  # fmt: skip
    n_sub = sum(v["subagents"] for v in want["sessions"].values())
    rows.append(row("agent: subagent transcripts and tool results", not lack,
                    f"{n_sub} subagent files" if not lack else f"short {lack}"))  # fmt: skip
    cm = have["claude_md"]
    ok_md = cm.startswith(PREFACE_MARK) and want["claude_md"].strip() in cm
    why = "" if ok_md else "preface missing, or the source text not contained"
    rows.append(row("agent: Batt's CLAUDE.md verbatim under the bot-server preface", ok_md, why))
    sk = sorted(s for s in want["skills"] if have["skills"].get(s) != want["skills"][s])
    rows.append(row("agent: the skills identical", not sk,
                    f"{len(want['skills'])} skills" if not sk else f"differ {sk}"))  # fmt: skip
    return rows


# --- the two commands ---------------------------------------------------------------------------
def make_manifest(hash_data: bool) -> dict[str, Any]:
    env_text = (REPO / ".env").read_text()
    env = parse_env(env_text)
    salt = secrets.token_hex(16)
    code, head = run(["git", "-C", str(REPO), "rev-parse", "HEAD"])
    return {
        "made": time.strftime("%FT%T%z"), "host": socket.gethostname(), "repo_head": head.strip(),
        "salt": salt, "env": {k: salted(salt, v) for k, v in env.items()},
        "trees": {t: tree(REPO / t, REPO, True, SKIP_STATE) for t in SMALL_TREES}
        | {"data": tree(REPO / "data", REPO, hash_data)},
        "cache": tree(HOME / ".cache" / "poring-lab", HOME / ".cache" / "poring-lab", True),
        "runtime": {n: runtime_tree(n) for n in RUNTIME},
        "db": db_counts(env), "claude": claude_side(PROJECT_KEYS["source"]),
        "images": source_images(),
    }  # fmt: skip


def source_images() -> list[str]:
    """The images of every poring-lab container on the source (running or not)."""
    code, out = run(["docker", "ps", "-a", "--format", "{{.Names}} {{.Image}}"])
    return sorted({ln.split()[1] for ln in out.splitlines()
                   if ln.startswith("poring-lab-") and len(ln.split()) == 2})  # fmt: skip


def image_rows(want: Sequence[str], have: Iterable[str]) -> list[Row]:
    """PURE: every image the source ran is on the target (vision as its Intel image)."""
    have_set = set(have) | {f"{h}:latest" for h in have if ":" not in h}
    need = [IMAGE_SUBSTITUTES.get(i, i) for i in want]
    missing = [i for i in need if i not in have_set]
    return [row("docker: every image the source ran, built here (vision: Intel)",
                bool(need) and not missing,
                f"missing {missing}" if missing else f"{len(need)} images")]  # fmt: skip


def check(manifest: Mapping[str, Any], phase: str) -> list[Row]:
    rows: list[Row] = []
    host = socket.gethostname()
    rows.append(row("the target is bot-server", host == TARGET_HOST, host))
    code, head = run(["git", "-C", str(REPO), "merge-base", "--is-ancestor",
                      str(manifest["repo_head"]), "HEAD"])  # fmt: skip
    rows.append(row("repo: at or after the source's HEAD", code == 0, manifest["repo_head"][:12]))
    code, hooks = run(["git", "-C", str(REPO), "config", "core.hooksPath"])
    rows.append(row("repo: the pre-commit guards active (core.hooksPath .githooks)",
                    hooks.strip() == ".githooks", hooks.strip() or "unset"))  # fmt: skip
    env = parse_env((REPO / ".env").read_text()) if (REPO / ".env").exists() else {}
    rows += env_rows(manifest["env"], env, manifest["salt"], phase)
    for t in SMALL_TREES:
        rows += tree_rows(t, manifest["trees"][t], tree(REPO / t, REPO, True, SKIP_STATE))
    want_data = manifest["trees"]["data"]
    hashed = any("sha256" in v for v in want_data.values())
    rows += tree_rows("data", want_data, tree(REPO / "data", REPO, hashed))
    rows += tree_rows(
        "~/.cache/poring-lab",
        manifest["cache"],
        tree(HOME / ".cache" / "poring-lab", HOME / ".cache" / "poring-lab", True),
    )
    for n in RUNTIME:
        rows += tree_rows(f"/dev/shm/{n}", manifest.get("runtime", {}).get(n, {}), runtime_tree(n))
    code, _ = run([str(DETECTOR_PY), "-c", "import onnxruntime, numpy"])
    rows.append(row("runtime: the CPU detector's environment imports onnxruntime", code == 0,
                    str(DETECTOR_PY)))  # fmt: skip
    rows += docker_rows(phase)
    code, imgs = run(["docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}"])
    rows += image_rows(manifest.get("images", []), imgs.split())
    if phase == "final":
        have = db_counts(env)
        want = manifest["db"]
        ok = isinstance(have, dict) and isinstance(want, dict) and have == want
        rows.append(row("db: every key table's exact row count equal", ok,
                        f"{sum(want.values())} rows in {len(want)} tables" if ok and
                        isinstance(want, dict) else f"have {have} want {want}"[:200]))  # fmt: skip
    else:
        rows.append(row("db: row counts (at the cutover)", None, "phase prep"))
    rows.append(row("GPU: the Intel render node usable", os.access("/dev/dri/renderD128", os.R_OK
                    | os.W_OK), "/dev/dri/renderD128"))  # fmt: skip
    for m in NAS_MOUNTS:
        try:
            ok_m = bool(os.listdir(m))
        except OSError as exc:
            ok_m, m = False, f"{m}: {exc}"
        rows.append(row(f"NAS: {m.split(':')[0]} readable", ok_m, m))
    rows += claude_rows(manifest["claude"], claude_side(PROJECT_KEYS["target"]))
    return rows


def docker_rows(phase: str) -> list[Row]:
    rows: list[Row] = []
    code, pools = run(["docker", "info", "--format", "{{json .DefaultAddressPools}}"])
    try:
        bases = [p["Base"] for p in json.loads(pools or "null") or []]
    except ValueError:
        bases = []
    rows.append(row("docker: default-address-pools inside 10.210.0.0/16",
                    bool(bases) and pinned(bases)[0], str(bases)))  # fmt: skip
    code, nets = run(["docker", "network", "ls", "--format", "{{.Name}}"])
    subnets: list[str] = []
    for n in nets.split():
        if n in ("host", "none"):
            continue
        c2, out = run(["docker", "network", "inspect", "-f",
                       "{{range .IPAM.Config}}{{.Subnet}} {{end}}", n])  # fmt: skip
        subnets += [s for s in out.split() if "/" in s and ":" not in s and n != "bridge"]
    ok, bad = pinned(subnets)
    rows.append(row("docker: every network off 192.168/16 and 172.16/12 (pinned 10.210.x)", ok,
                    f"{len(subnets)} subnets" if ok else f"bad {bad}"))  # fmt: skip
    code, route = run(["ip", "route", "get", "192.168.110.55"])
    rows.append(row("network: the VLAN route via the router", "via 192.168.1.1" in route,
                    route.split("\n")[0][:80]))  # fmt: skip
    code, br = run(["docker", "network", "inspect", "-f",
                    "{{range .IPAM.Config}}{{.Subnet}} {{end}}", "bridge"])  # fmt: skip
    b = [s for s in br.split() if "/" in s and ":" not in s]
    ok_b = bool(b) and not any(ipaddress.ip_network(s, strict=False).overlaps(f)
                               for s in b for f in FORBIDDEN_NETS)  # fmt: skip
    rows.append(row("docker: docker0 (bip) off 192.168/16 and 172.16/12", ok_b, str(b)))
    if phase == "final":
        code, ps = run(["docker", "ps", "--format", "{{.Names}} {{.Status}}"])
        lab = [ln for ln in ps.splitlines() if ln.startswith("poring-lab-")]
        unhealthy = [ln for ln in lab if "unhealthy" in ln or "Restarting" in ln]
        rows.append(row("docker: the lab's containers up, none unhealthy",
                        bool(lab) and not unhealthy, f"{len(lab)} up" if not unhealthy
                        else str(unhealthy)))  # fmt: skip
    return rows


def render(rows: Sequence[Row]) -> str:
    w = max(len(r["item"]) for r in rows)
    lines = [f"{r['status']:4}  {r['item']:<{w}}  {r['detail']}" for r in rows]
    n = {s: sum(1 for r in rows if r["status"] == s) for s in ("PASS", "FAIL", "SKIP")}
    return "\n".join(lines + [f"PASS {n['PASS']}  FAIL {n['FAIL']}  SKIP {n['SKIP']}"])


def main(argv: list[str] | None = None,
         out: Callable[[str], None] = print) -> int:  # fmt: skip
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("manifest")
    m.add_argument("--out", type=Path, required=True)
    m.add_argument("--hash-data", action="store_true", help="sha256 every data/ file too")
    c = sub.add_parser("check")
    c.add_argument("--manifest", type=Path, required=True)
    c.add_argument("--phase", choices=["prep", "final"], required=True)
    c.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    if a.cmd == "manifest":
        man = make_manifest(a.hash_data)
        a.out.write_text(json.dumps(man))
        os.chmod(a.out, 0o600)
        out(f"manifest {a.out}: env {len(man['env'])} keys, data {len(man['trees']['data'])} "
            f"files, db {man['db'] if isinstance(man['db'], str) else len(man['db'])}, "
            f"memory {len(man['claude']['memory'])}")  # fmt: skip
        return 0
    rows = check(json.loads(a.manifest.read_text()), a.phase)
    if a.json:
        a.json.write_text(json.dumps(rows, indent=1))
    out(render(rows))
    return 1 if any(r["status"] == "FAIL" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
