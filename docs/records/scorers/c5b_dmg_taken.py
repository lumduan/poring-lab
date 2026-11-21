"""Per 5b run: damage the Rogue took (act packets onto 2000002), heals used (use_item_result 504), minutes.
Offline, report-only (C3's stock-out ruling, cursor-1080 Amendment 12)."""
import gzip, json, sys, glob, collections
ME = 2000002
for lab in sys.argv[1:]:
    ds = sorted(glob.glob(f"/dev/shm/poring-lab-demo/*-{lab}-r01B-hunt1"))
    if not ds: print(lab, "no session"); continue
    t0 = t1 = None; dmg = hits = 0; heal = 0; src = collections.Counter(); spawn = {}
    for l in gzip.open(ds[-1] + "/packets.jsonl.gz", "rt"):
        d = json.loads(l); t = d.get("t_mono_ns")
        if t: t0 = t if t0 is None else min(t0, t); t1 = t if t1 is None else max(t1, t)
        if d.get("type") == "act" and d.get("target_gid") == ME and (d.get("damage") or 0) > 0:
            dmg += d["damage"] + (d.get("damage2") or 0); hits += 1; src[d.get("src_gid")] += d["damage"]
        if d.get("type") == "use_item_result" and d.get("item_id") == 504 and d.get("ok"):
            heal += 1
        if d.get("mob_id") and d.get("gid"): spawn[d["gid"]] = d["mob_id"]
    m = (t1 - t0) / 6e10
    top = [(spawn.get(g, "?"), v) for g, v in src.most_common(3)]
    print(f"{lab:8s} {m:5.1f} min  hits {hits:4d}  dmg {dmg:6d}  dmg/min {dmg/m:6.0f}  heals {heal:2d}  top {top}")
