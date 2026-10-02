"""Label quality (B6): box IoU and greedy matching per class -> precision, recall, mean IoU.

The benchmark's `label_iou` (docs/benchmarks/SPEC.md) is the mean IoU of the auto-labels against a
hand-checked set, matched greedily per class at IoU >= 0.5.
"""

from collections.abc import Sequence
from dataclasses import dataclass

Box = tuple[str, float, float, float, float]  # (class, x0, y0, x1, y1)


def iou(a: Box, b: Box) -> float:
    ix = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    iy = max(0.0, min(a[4], b[4]) - max(a[2], b[2]))
    inter = ix * iy
    union = (a[3] - a[1]) * (a[4] - a[2]) + (b[3] - b[1]) * (b[4] - b[2]) - inter
    return inter / union if union > 0 else 0.0


@dataclass(frozen=True)
class Match:
    tp: int
    fp: int
    fn: int
    ious: tuple[float, ...]

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def mean_iou(self) -> float:
        return sum(self.ious) / len(self.ious) if self.ious else 0.0


def match(truth: Sequence[Box], predicted: Sequence[Box], threshold: float = 0.5) -> Match:
    """Greedy: highest-IoU same-class pairs first; each box matches at most once."""
    pairs = sorted(
        ((iou(t, p), i, j) for i, t in enumerate(truth) for j, p in enumerate(predicted)
         if t[0] == p[0]),
        reverse=True,
    )  # fmt: skip
    used_t: set[int] = set()
    used_p: set[int] = set()
    ious: list[float] = []
    for value, i, j in pairs:
        if value < threshold:
            break
        if i in used_t or j in used_p:
            continue
        used_t.add(i)
        used_p.add(j)
        ious.append(value)
    return Match(len(ious), len(predicted) - len(ious), len(truth) - len(ious), tuple(ious))
