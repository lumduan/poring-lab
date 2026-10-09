"""Training availability per window = compute-equivalent seconds / wall seconds (read-only).
compute-equivalent: running, not R3-paused time at duty level l, times c / (c + sleep_l); c = the fitted
pure compute per batch. Stopped time (aborts, quiet waits, IO pauses, timeouts) counts 0."""
import re, sys
from datetime import datetime, timedelta
C = float(sys.argv[1]); FILES = sys.argv[2:]
S = {0: 0.1, 1: 0.2, 2: 0.4, 3: 0.8, 4: 2.0}
segs, pauses = [], []  # (level, a, b); (a, b)
for f in FILES:
    day = datetime(2026, 10, 7) if "night" in f else datetime(2026, 10, 8)
    last, cur, t_cur, p0, end = None, None, None, None, None
    for l in open(f, errors="replace").read().replace("\r", "\n").splitlines():
        m = re.match(r"\[(\d\d:\d\d:\d\d)\]", l)
        if not m: continue
        t = day + (datetime.strptime(m.group(1), "%H:%M:%S") - datetime(1900, 1, 1))
        if last and t < last - timedelta(hours=1): day += timedelta(days=1); t += timedelta(days=1)
        last = end = t
        if (a := re.search(r"DUTY start level (\d)", l)): cur, t_cur = int(a.group(1)), t
        elif (b := re.search(r"DUTY level (\d) -> (\d)", l)) and cur is not None:
            segs.append((cur, t_cur, t)); cur, t_cur = int(b.group(2)), t
        elif re.search(r"R3 pause ", l): p0 = t
        elif re.search(r"R3 unpause ", l) and p0: pauses.append((p0, t)); p0 = None
        elif re.search(r"ABORT|STOP VERIFIED|rc=", l) and cur is not None and "ABORT" in l:
            segs.append((cur, t_cur, t)); cur = None
    if cur is not None: segs.append((cur, t_cur, end))
    if p0: pauses.append((p0, end))
def ov(a, b, c, d): return max(0.0, (min(b, d) - max(a, c)).total_seconds())
def window(a, b):
    comp = run = paused = 0.0
    for lv, x, y in segs:
        r = ov(x, y, a, b)
        p = sum(ov(max(x, pa), min(y, pb), a, b) for pa, pb in pauses if pb > x and pa < y)
        run += r; paused += p; comp += (r - p) * C / (C + S[lv])
    wall = (b - a).total_seconds()
    return wall, run, paused, comp
D = lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M")
for name, a, b in [("evening 10-07 17:09-20:00", "2026-10-07 17:09", "2026-10-07 20:00"),
                   ("NIGHT  10-07 20:00-05:00", "2026-10-07 20:00", "2026-10-08 05:00"),
                   ("DAY    10-08 05:00-10:30", "2026-10-08 05:00", "2026-10-08 10:30"),
                   ("  of which 05:00-09:00", "2026-10-08 05:00", "2026-10-08 09:00"),
                   ("  of which 09:00-10:30", "2026-10-08 09:00", "2026-10-08 10:30")]:
    w, r, p, c = window(D(a), D(b))
    print(f"{name:<27} wall {w/3600:5.2f} h  running {r/w:5.1%}  R3-paused {p/w:5.1%}  availability {c/w:5.2f}")
# partial epochs discarded by a stop (epoch end -> the stop), from results.csv times + train.log stops
LOST = [("2026-10-08 04:40:53", "2026-10-08 05:09:39"), ("2026-10-08 05:10:28", "2026-10-08 05:36:19"),
        ("2026-10-08 09:11:52", "2026-10-08 09:32:53"), ("2026-10-08 09:48:41", "2026-10-08 10:03:10")]
P = lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
print("--- effective (discarded partial epochs removed)")
for name, a, b in [("NIGHT  10-07 20:00-05:00", "2026-10-07 20:00", "2026-10-08 05:00"),
                   ("DAY    10-08 05:00-10:30", "2026-10-08 05:00", "2026-10-08 10:30")]:
    w, r, p, c = window(D(a), D(b))
    lost = sum(window(max(P(x), D(a)), min(P(y), D(b)))[3] for x, y in LOST if P(y) > D(a) and P(x) < D(b))
    print(f"{name:<27} availability {c/w:5.2f} -> effective {(c-lost)/w:5.2f}  (discarded {lost/3600:4.2f} compute-h)")
