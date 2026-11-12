"""chatjudge: the LAST green line of a Chat-tab crop (chat_shot.py's 600 x 150), aligned, against templates."""
import numpy as np
from PIL import Image

def last_green_line(path_or_arr, h=13, w=260):
    a = np.asarray(Image.open(path_or_arr).convert("RGB") if isinstance(path_or_arr, str) else path_or_arr).astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    green = (g > 140) & (r < 140) & (b < 140) & (g - r > 50)
    rows = green[:, :w].sum(axis=1)
    ys = [y for y in range(rows.size) if rows[y] >= 3]
    if not ys:
        return None
    bottom = ys[-1]
    top = bottom
    while top - 1 >= 0 and rows[top - 1] >= 1 and bottom - top < h + 2:
        top -= 1
    y0 = max(0, bottom - h + 1)
    return green[y0:bottom + 1, :w].astype(float)

def dist(a, b):
    if a is None or b is None or a.shape != b.shape:
        return 1e9
    return float(np.abs(a - b).mean())

def judge(path, templates, margin=0.04):
    x = last_green_line(path)
    ds = {k: dist(x, t) for k, t in templates.items()}
    best = min(ds, key=ds.get)
    rest = sorted(ds.values())
    ok = len(rest) < 2 or rest[1] - rest[0] >= margin
    return (best if ok and ds[best] < 0.15 else "unknown"), ds
