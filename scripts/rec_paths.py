"""The recording paths the label, cache and scoring tools read (fail closed).

Two paths (docs/planning/xmas02-1080-detector.md section 3, T-V2):

* ``lab-720``: the lab's 1280x720 client on RDP (game_region [80, 77, 1280, 720]), lab rAthena,
  PNG frames, recorder v5 to v8. Unchanged from map_labels' 3c path.
* ``virtual-1080``: the 1920x1080 fullscreen client, recorded as the bot sees it: the VIRTUAL
  1280x720 picture (ro_agent.game_region() at VIRTUAL_X0; the world resampled by 1/1.5 about
  the centre, the panels pasted at native size). Recorder v8 only, because only v8 writes the
  view (``client_view``) the frames were made by.

Anything else is refused. The GPU video stays refused on both (ADR-0024's parity check).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

VIRTUAL_X0 = 100_000  # ro_agent.VIRTUAL_X0 (a test pins the two equal)
PNG_ONLY = ("png",)
LAB_720 = {"backend": "rdp", "game_region": [80, 77, 1280, 720], "server": "lab-rathena"}
LAB_720_VERSIONS = (5, 6, 7, 8)
VIRTUAL_1080 = {"backend": "rdp", "game_region": [VIRTUAL_X0, 0, 1280, 720],
                "server": "lab-rathena"}  # fmt: skip
VIRTUAL_VERSIONS = (8,)
# the 1080 view the plan's data were recorded through (the client_view's fixed fields)
VIEW_1080 = {"rect": [0, 0, 1920, 1080], "mode": "fullscreen", "world_scale": 1.5}

Rect = tuple[int, int, int, int]


def _mismatch(manifest: Mapping[str, Any], want: Mapping[str, Any],
              versions: Sequence[int]) -> dict[str, Any]:  # fmt: skip
    bad = {k: manifest.get(k) for k, v in want.items() if manifest.get(k) != v}
    if manifest.get("format") not in PNG_ONLY:
        bad["format"] = manifest.get("format")
    if manifest.get("recorder_version") not in versions:
        bad["recorder_version"] = manifest.get("recorder_version")
    return bad


def _view_mismatch(manifest: Mapping[str, Any]) -> dict[str, Any]:
    view = manifest.get("client_view")
    if not isinstance(view, Mapping):
        return {"client_view": view}
    return {f"client_view.{k}": view.get(k) for k, v in VIEW_1080.items() if view.get(k) != v}


def problems(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """PURE: {} when the manifest is one of the two paths; else what differs from the nearer one
    (the virtual path when its game_region is the virtual client's, else the lab's 720)."""
    if manifest.get("game_region") == VIRTUAL_1080["game_region"]:
        return {**_mismatch(manifest, VIRTUAL_1080, VIRTUAL_VERSIONS), **_view_mismatch(manifest)}
    return _mismatch(manifest, LAB_720, LAB_720_VERSIONS)


def path_of(manifest: Mapping[str, Any]) -> str | None:
    """PURE: ``lab-720``, ``virtual-1080`` or None (refused)."""
    if problems(manifest):
        return None
    return (
        "virtual-1080" if manifest.get("game_region") == VIRTUAL_1080["game_region"] else "lab-720"
    )


def panel_rects(manifest: Mapping[str, Any]) -> tuple[Rect, ...]:
    """PURE (T-V3): the pasted panels' virtual boxes (x0, y0, x1, y1) of a virtual session, the
    pointer's patch left out; () for the 720 path. They are UI to the label rule: their pixels are
    the real client's, unscaled. They hold the layout's 720 windows whole (nested_rects drops
    those); Basic Info's box and the hotbar's still share a 4 x 40 px strip (226-230, 0-40), which
    covered_fraction counts twice (it SUMS overlaps): reported, not corrected."""
    if path_of(manifest) != "virtual-1080":
        return ()
    out: list[Rect] = []
    for p in manifest["client_view"].get("panels") or []:
        name, (x, y, w, h) = p["name"], p["virtual"]
        if name != "cursor":
            out.append((int(x), int(y), int(x) + int(w), int(y) + int(h)))
    return tuple(out)


def view_record(view: Any) -> dict[str, Any]:
    """A poring_env ClientView -> the manifest's ``client_view`` (T-V1): the real rect, the mode,
    the world's scale and centre, and every panel (name, virtual box, real top-left)."""
    centre = view.centre  # the real-client point of the virtual centre (measured, else the middle)
    return {"rect": [int(v) for v in view.rect], "mode": view.mode,
            "world_scale": round(float(view.world_scale), 6),
            "world_centre": [round(float(c), 3) for c in centre],
            "panels": [{"name": p.name, "virtual": [int(v) for v in p.virtual],
                        "real_xy": [int(v) for v in p.real_xy]} for p in view.panels]}  # fmt: skip
