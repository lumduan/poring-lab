"""route_rec: the console's "Record route" button, the host side (docs/planning/
waypoints-npc-recording.md Amendment 11) -- the request parser, the readiness of one frame
(synthetic frames drawn by the readers' own rules: no client pixels), the minutes that fit above
the recorder's floor, the guide's rules over scripted reads (a map change shown once, indoors, a
one-read misread that is no change), the manifest and the index, and the helper end to end with a
fake host (no frame grabbed, no process started, no input: the helper never sends any)."""

from __future__ import annotations

import ast
import importlib.util
import json
import signal
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
import dataset_ship  # noqa: E402
import route_rec as rr  # noqa: E402

from poring_env import panelfind as pf  # noqa: E402
from poring_env import selfpos  # noqa: E402


def _load(path: Path, name: str) -> ModuleType:
    """A sibling test module's drawers (synthetic windows drawn by the readers' own rules)."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TS = _load(REPO / "packages/poring_env/tests/test_selfpos.py", "route_rec_selfpos_drawers")
TP = _load(REPO / "packages/poring_env/tests/test_panelfind.py", "route_rec_panelfind_drawers")
TC = _load(Path(__file__).parent / "test_chat_window.py", "route_rec_chat_drawers")


# --- the request ----------------------------------------------------------------------------------


def test_the_request_parser_takes_check_start_stop_and_nothing_else() -> None:
    assert rr.parse_request('{"id": "abcdefgh", "action": "check", "at": 1}') == {
        "id": "abcdefgh", "action": "check"}  # fmt: skip
    assert rr.parse_request('{"id": "abcdefgh", "action": "stop"}') == {
        "id": "abcdefgh", "action": "stop"}  # fmt: skip
    got = rr.parse_request('{"id": "abcdefgh", "action": "start", "map": "xmas_dun02"}')
    assert got == {"id": "abcdefgh", "action": "start", "map": "xmas_dun02"}
    assert rr.parse_request('{"id": "abcdefgh", "action": "start"}') == {
        "id": "abcdefgh", "action": "start", "map": None}  # fmt: skip
    for text, why in (
        ("not json", "unparsable"),
        ("[1]", "unparsable"),
        ('{"id": "short", "action": "check"}', "bad request id"),
        ('{"id": "abcdefgh", "action": "record"}', "unknown action"),
        ('{"id": "abcdefgh", "action": "check", "map": "prt_fild08"}', "carries nothing else"),
        ('{"id": "abcdefgh", "action": "start", "argv": ["--x"]}', "carries nothing else"),
        ('{"id": "abcdefgh", "action": "start", "map": "../etc"}', "map name"),
        ('{"id": "abcdefgh", "action": "start", "map": "Prt_Fild08"}', "map name"),
        ('{"id": "abcdefgh", "action": "start", "map": 7}', "map name"),
    ):
        got = rr.parse_request(text)
        assert isinstance(got, str) and why in got, (text, got)


# --- one frame's readiness and minimap (synthetic frames) --------------------------------------


@pytest.fixture(scope="module")
def digits() -> selfpos.DigitTemplates:
    """Templates fitted as test_selfpos fits them (its made-up font, many labelled readouts)."""
    rng = np.random.default_rng(0)
    rects, labels = [], []
    for _ in range(40):
        for d in range(10):
            frame = TS.scene(rng, paving=False)
            x = 111 * d if d else 100
            TS.draw_text(frame, f"{x} {d}", rng)
            rects.append(TS.rect_of(frame))
            labels.append((x, d))
    fitted, _ = selfpos.fit_templates(rects, labels, TS.LAYOUT)
    return fitted


def game_frame(size: tuple[int, int] = (1280, 720), *, readout: str | None = "93 82",
               basic: bool = True, chat: bool = True, seed: int = 3) -> np.ndarray:  # fmt: skip
    """A REAL client frame of ``size``: a busy scene, Basic Info at the top-left, a 6-line chat
    window docked bottom-left, the minimap readout at the top-right (RO keeps it there: at 1080 the
    virtual client's panel sits 640 px further right) or none (indoors)."""
    w, h = size
    rng = np.random.default_rng(seed)
    out = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
    mm = TS.scene(rng, paving=False)  # the 1280x720 picture the readout is drawn in
    if readout is not None:
        TS.draw_text(mm, readout, rng)
    vx, vy, vw, vh = rr.rt.MINIMAP_PANEL[1]
    out[vy : vy + vh, w - (1280 - vx) : w - (1280 - vx) + vw] = mm[vy : vy + vh, vx : vx + vw]
    if basic:
        lum = TP.world(pf.BASIC_H, pf.BASIC_W, seed)
        TP.draw_basic(lum, (0, 0))
        out[: pf.BASIC_H, : pf.BASIC_W] = lum.astype(np.uint8)[..., None]
    if chat:
        win = TC.draw_any(0, h - 1, 6, h=h, w=w)
        mask = np.any(win != np.array(TC.SCENE, np.uint8), axis=-1)
        out[mask] = win[mask]
    return out


@pytest.mark.parametrize("size", [(1280, 720), (1920, 1080)])
def test_a_frame_in_game_is_ready_and_its_readout_reads(
    size: tuple[int, int], digits: selfpos.DigitTemplates
) -> None:
    img = game_frame(size)
    seen = rr.look_ready(img)
    assert (seen["basic_info"], seen["chat_window"]) == (True, True)
    assert set(seen["places"]) == {"basic_info", "chat"}
    assert rr.recheck_ready(img, seen["places"]) is not None  # the cheap re-check at the place
    mm = rr.look_minimap(img, digits)
    assert (mm["minimap"], mm["xy"]) == ("present", [93, 82]), mm
    assert ("virtual client" in mm["view"]) == (size == (1920, 1080))
    assert rr.readiness(SimpleNamespace(backend="rdp", phase="steady"), seen) == []


def test_a_frame_without_basic_info_or_chat_is_not_ready_and_indoors_is(
    digits: selfpos.DigitTemplates,
) -> None:
    steady = SimpleNamespace(backend="console", phase="steady")
    no_basic = game_frame(basic=False)
    assert rr.readiness(steady, rr.look_ready(no_basic)) == ["basic_info"]
    no_chat = game_frame(chat=False)
    assert rr.readiness(steady, rr.look_ready(no_chat)) == ["chat_window"]
    indoors = game_frame(readout=None)  # Amendment 10: no minimap window at all
    assert rr.readiness(steady, rr.look_ready(indoors)) == []  # never required
    assert rr.look_minimap(indoors, digits)["minimap"] == "absent"
    moved = rr.look_ready(game_frame())["places"]
    assert rr.recheck_ready(no_basic, moved) is None  # gone from its place: search again
    switching = SimpleNamespace(backend="rdp", phase="switching")
    assert rr.readiness(switching, rr.look_ready(game_frame())) == ["capture_lock"]
    assert rr.readiness(SimpleNamespace(backend="hold", phase="steady"), None) == [
        "capture_lock", "frame"]  # fmt: skip
    assert "status window" in rr.missing_words(["basic_info"])


def test_absent_means_no_parser_saw_a_glyph() -> None:
    assert rr.minimap_present("ok")
    assert rr.minimap_present("ambiguous")
    assert rr.minimap_present("uncovered_ink", "light_failed", "uncovered_ink")
    # Amendment 10's bright town: the readout is drawn, the light fallback saw its ink
    assert rr.minimap_present("no_glyph", "light_failed", "uncovered_ink")
    assert not rr.minimap_present("no_glyph")
    assert not rr.minimap_present("no_glyph", "light_failed", "no_glyph")
    assert not rr.minimap_present("rect_outside_frame")


# --- the disk -----------------------------------------------------------------------------------


GB = 10**9


def test_the_minutes_that_fit_above_the_floor() -> None:
    e = rr.estimate(100 * GB, 30 * GB, 41e6, "src")
    assert (e["usable_bytes"], e["minutes"], e["verdict"]) == (70 * GB, 1707, "ok")
    warn = rr.estimate(30 * GB + 300_000_000, 30 * GB, 41e6, "src")
    assert (warn["minutes"], warn["verdict"]) == (7, "warn")  # fewer than 10 warns
    assert rr.estimate(29 * GB, 30 * GB, 41e6, "src")["verdict"] == "refuse"  # below the floor
    assert rr.estimate(30 * GB + 10**6, 30 * GB, 41e6, "src")["verdict"] == "refuse"  # 0 minutes
    unknown = rr.estimate(100 * GB, 30 * GB, None, "not measured yet")
    assert (unknown["minutes"], unknown["verdict"]) == (None, "unknown")
    assert rr.estimate(29 * GB, 30 * GB, None, "x")["verdict"] == "refuse"  # no room, rate or not
    assert rr.estimate(31 * GB, 30 * GB, 41e6, "x", rr.RecSettings(warn_minutes=30))[
        "verdict"] == "warn"  # fmt: skip


def test_the_floor_is_the_recorders_own() -> None:
    """record_session refuses below dataset_ship.MIN_FREE_BYTES (its --min-free-gb default); the
    helper's floor is the same function, not a copied number."""
    assert rr.LiveHost().floor() == dataset_ship.min_free_bytes() == dataset_ship.MIN_FREE_BYTES


def test_the_rate_is_this_installs_median_else_the_formats_default_else_unknown() -> None:
    fin = {"end": "t", "fps": 5.0, "format": "h264"}
    index = {"recordings": [
        {**fin, "mb_per_min": 40.0, "seconds": 600.0},
        {**fin, "bytes": 60 * 10**6 * 10, "seconds": 600.0},  # 60 MB/min from its bytes
        {**fin, "bytes": 999 * 10**6, "seconds": 30.0},  # too short to set the rate
        {**fin, "fps": 1.0, "mb_per_min": 5.0, "seconds": 600.0},  # another fps
        {**fin, "format": "png", "mb_per_min": 124.0, "seconds": 600.0},  # another format
        {**fin, "end": None, "mb_per_min": 300.0, "seconds": 600.0},  # not finished
        {**fin, "refused": True, "mb_per_min": 300.0, "seconds": 600.0},
    ]}  # fmt: skip
    rate, src = rr.rate_of(index, "h264", 5.0)
    assert rate == 50e6 and "median" in src and "2 finished" in src
    assert rr.rate_of({"recordings": []}, "h264", 5.0) == rr.DEFAULT_RATES["h264"]
    assert rr.DEFAULT_RATES["h264"][0] == 41e6
    rate, src = rr.rate_of({}, "vpp-hevc444-10-q20", 5.0)  # the rdp video: not measured yet
    assert rate is None and "not measured yet" in src


# --- the guide's rules over scripted reads --------------------------------------------------------


Read = tuple[float, bool | None, tuple[int, int] | None]


def walk(t0: float, n: int, start: tuple[int, int], dt: float = 0.5) -> list[Read]:
    """n reads at 5 cells a second east (well under the 10 cells/s walk cap)."""
    return [(t0 + i * dt, True, (start[0] + int(2.5 * i), start[1])) for i in range(n)]


def absent(t0: float, n: int, dt: float = 0.5) -> list[Read]:
    return [(t0 + i * dt, False, None) for i in range(n)]


def run(reads: list[Read], s: rr.RecSettings = rr.DEFAULTS) -> tuple[list[Any], list[Any]]:
    w = rr.MapWatch(s)
    marks, notes = [], []
    for t, present, xy in reads:
        m, n = w.feed(t, present, xy)
        marks += [(t, x.kind, x.shown) for x in m]
        notes += [(t, k) for k in n]
    return marks, notes


def test_walking_and_an_unread_readout_are_no_map_change() -> None:
    reads = walk(0, 40, (50, 50))
    reads[10] = (reads[10][0], True, None)  # present, its numbers unread
    reads[11] = (reads[11][0], None, None)  # no reading at all (a failed grab)
    assert run(reads) == ([], [])


def test_a_one_read_misread_jump_is_not_a_map_change() -> None:
    reads = walk(0, 20, (50, 50))
    t = reads[8][0]
    reads[8] = (t, True, (150, 150))  # one misread far away, then back on the walk
    assert run(reads) == ([], [])


def test_a_jump_held_for_two_reads_is_a_map_change_shown_once() -> None:
    reads = walk(0, 10, (50, 50)) + walk(5.0, 10, (150, 150))  # a warp with no loading picture
    marks, notes = run(reads)
    assert notes == [(5.5, "map_change")]  # the second read at the new place
    assert marks == [(5.5, "jump", True)]


def test_a_warp_through_a_loading_screen_is_one_notification() -> None:
    """The minimap gone for the loading (a change), back at once (a change inside the quiet time:
    logged, not shown)."""
    reads = walk(0, 10, (50, 50)) + absent(5.0, 4) + walk(7.0, 10, (120, 40))
    marks, notes = run(reads)
    assert notes == [(5.5, "map_change")]
    assert marks == [(5.5, "minimap_gone", True), (7.5, "minimap_appeared", False)]


def test_a_flicker_of_one_read_is_no_change() -> None:
    reads = walk(0, 20, (50, 50))
    reads[7] = (reads[7][0], False, None)
    assert run(reads) == ([], [])


def test_indoors_a_reminder_every_minute_while_it_stays_absent() -> None:
    reads = walk(0, 10, (50, 50)) + absent(5.0, 260) + walk(135.0, 4, (60, 60))
    marks, notes = run(reads)
    assert notes == [(5.5, "map_change"), (65.5, "indoors"), (125.5, "indoors"),
                     (135.5, "map_change")]  # fmt: skip
    assert [k for _, k, _ in marks] == ["minimap_gone", "minimap_appeared"]
    _, off = run(reads, rr.RecSettings(indoor_every_s=0))  # the reminder is a setting: off
    assert [k for _, k in off] == ["map_change", "map_change"]


def test_a_recording_that_starts_indoors_reminds_without_a_change() -> None:
    _, notes = run(absent(0, 150))
    assert notes == [(60.5, "indoors")]  # settled at the 2nd read (0.5 s), first reminder 60 s on


def test_the_quiet_time_and_a_second_change_later() -> None:
    reads = walk(0, 10, (50, 50)) + walk(5.0, 6, (150, 150)) + walk(8.0, 30, (30, 160))
    marks, notes = run(reads)
    assert notes == [(5.5, "map_change")]  # the second jump 3 s later: inside the quiet time
    assert [(k, shown) for _, k, shown in marks] == [("jump", True), ("jump", False)]
    later = walk(0, 10, (50, 50)) + walk(5.0, 30, (150, 150)) + walk(20.0, 4, (30, 160))
    assert [k for _, k in run(later)[1]] == ["map_change", "map_change"]  # 15 s apart


def test_readiness_lost_for_a_minute_stops_once() -> None:
    w = rr.ReadyWatch()
    assert w.feed(0.0, ["basic_info"]) is None
    assert w.feed(59.9, ["basic_info"]) is None
    why = w.feed(60.0, ["basic_info"])
    assert why is not None and "60 s" in why and "status window" in why
    assert w.feed(65.0, ["basic_info"]) is None  # said once
    assert w.feed(70.0, []) is None  # back: the clock restarts
    assert w.feed(100.0, ["chat_window"]) is None
    assert w.feed(159.0, ["chat_window"]) is None


def test_low_disk_at_ten_and_two_minutes_left_each_once() -> None:
    w = rr.DiskWatch()
    assert [w.feed(m) for m in (None, 30.0, 12.0, 9.5, 9.0, 3.0, 1.5, 1.0)] == [
        None, None, None, 10.0, None, None, 2.0, None]  # fmt: skip
    w2 = rr.DiskWatch()
    assert w2.feed(1.0) == 2.0 and w2.feed(0.5) is None  # past both at once: the urgent one


# --- the folder, the recorder, the split, the manifest, the index ---------------------------------


LIM = rr.Limits(3570.0, 8192)


def test_the_folder_is_amendment_8s_layout() -> None:
    when = datetime(2026, 11, 22, 15, 4, 5)
    root = Path("/store/recordings")
    assert rr.route_dir(root, when, "xmas_dun02") == root / "2026-11-22" / (
        "20261122T150405-xmas_dun02-route")  # fmt: skip
    assert rr.route_dir(root, when, None).name == "20261122T150405-route-route"


def test_the_recorder_argv_and_its_caps() -> None:
    out = Path("/store/recordings/2026-11-22/20261122T150405-route-route")
    argv = rr.recorder_argv("py", "rdp", out, 5.0, 3600.0, 70 * GB)
    assert argv == ["py", rr.RECORDER, "--backend", "rdp", "--label", "route", "--fps", "5",
                    "--seconds", "3600", "--max-bytes", str(70 * GB),
                    "--out", str(out)]  # fmt: skip
    assert "--format" not in argv  # its default format
    assert rr.recorder_seconds(rr.DEFAULTS, "vpp-hevc444-10-q20", LIM) == 3600.0  # 60 min
    assert rr.recorder_seconds(rr.DEFAULTS, "h264", LIM) == 3570.0  # the S2 client's cap
    assert rr.recorder_max_bytes(70 * GB, "h264", LIM) == 8192 * 10**6
    assert rr.recorder_max_bytes(70 * GB, "vpp-hevc444-10-q20", LIM) == 70 * GB


def test_the_h264_caps_are_record_sessions_own() -> None:
    import argparse

    import record_session as rs

    assert rr.LiveHost().limits() == rr.Limits(float(rs.H264_MAX_SECONDS), rs.H264_MAX_MB)
    ok = argparse.Namespace(backend="console", format=None, out=Path("/x"), also_png=False,
                            seconds=rr.recorder_seconds(rr.DEFAULTS, "h264", LIM),
                            max_bytes=rr.recorder_max_bytes(70 * GB, "h264", LIM),
                            idr_every=1.0)  # fmt: skip
    rs.resolve_format(ok)  # the clamped values pass
    with pytest.raises(SystemExit, match="at most 3570 s"):
        rs.resolve_format(argparse.Namespace(**{**vars(ok), "format": None, "seconds": 3600.0}))


def test_the_rdp_video_default_cannot_record_into_the_route_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins the conflict this phase reports (record_session unchanged): its rdp default records
    only into dataset_ship.LOCAL_ROOT, so Amendment 8's folder under the storage setting is
    refused in record_session's own words; the console's h264 needs its S2 dir beside it."""
    import record_session as rs

    folder = tmp_path / "recordings" / "2026-11-22" / "20261122T150405-route-route"
    fmt, why = rr.preflight("rdp", folder)
    assert fmt == rs.VIDEO_FORMAT and why is not None and "--out must be" in why
    assert rr.preflight("rdp", dataset_ship.LOCAL_ROOT) == (rs.VIDEO_FORMAT, None)
    monkeypatch.setenv("S2_REC_DIR", str(tmp_path / "s2"))
    fmt, why = rr.preflight("console", folder)
    assert fmt == "h264" and why is not None and "does not exist" in why
    (tmp_path / "s2").mkdir()
    assert rr.preflight("console", folder) == ("h264", None)  # the same filesystem: a rename


def test_the_split_is_decided_at_the_start_from_the_earlier_ones() -> None:
    def idx(n: int, **kw: Any) -> dict[str, Any]:
        return {"recordings": [{"purpose": "route", **kw} for _ in range(n)]}

    assert rr.decide_split(idx(0))[0] == "held-out"  # Amendment 9's route-H1..H3
    assert rr.decide_split(idx(2))[0] == "held-out"
    assert rr.decide_split(idx(3))[0] == "train"
    assert rr.decide_split(idx(7))[0] == "held-out"  # the 8th: every 5th after the first 3
    assert rr.decide_split(idx(5, refused=True))[0] == "held-out"  # a refused start never counts
    assert rr.decide_split(idx(9, purpose="ml"))[0] == "held-out"
    assert rr.decide_split(idx(7), rr.RecSettings(held_out_every=0))[0] == "train"


def test_the_manifest_its_end_and_the_index() -> None:
    folder = Path("/store/recordings/2026-11-22/20261122T150405-xmas_dun02-route")
    man = rr.manifest("20261122T150405", folder, map_name="xmas_dun02", backend="console",
                      fmt="h264", fps=5.0, split=("held-out", "rule"), start="2026-11-22T15:04:05",
                      t0_mono_ns=1, argv=["py", "x"], max_bytes=10, max_s=3570.0, check=None,
                      s=rr.DEFAULTS)  # fmt: skip
    assert (man["purpose"], man["keep"], man["split"], man["end"]) == (
        "route", False, "held-out", None)  # fmt: skip
    assert (man["format"], man["fps"], man["stop_reason"], man["bytes"]) == (
        "h264", 5.0, None, None)  # fmt: skip
    res = {"dir": "/s", "bytes": 123_000_000, "mb_per_min": 41.0,
           "stop_reason": "stopped by signal"}  # fmt: skip
    end = rr.ended(man, end="2026-11-22T15:07:05", t1_mono_ns=2, stop_reason="you pressed Stop",
                   rc=0, result=res, seconds=180.04, refused=False)  # fmt: skip
    assert (end["end"], end["stop_reason"], end["bytes"], end["seconds"]) == (
        "2026-11-22T15:07:05",
        "you pressed Stop",
        123_000_000,
        180.0,
    )  # h264's result: no seconds
    assert end["recorder"]["rc"] == 0 and end["recorder"]["session"] == "/s"
    e = rr.index_entry(end, "2026-11-22/" + folder.name)
    assert e["mb_per_min"] == 41.0 and e["dir"].startswith("2026-11-22/") and not e["refused"]
    idx = rr.index_put({"recordings": [{"dir": "other"}]}, rr.index_entry(man, e["dir"]))
    idx = rr.index_put(idx, e)  # the end replaces the start's entry
    assert [x["dir"] for x in idx["recordings"]] == ["other", e["dir"]]
    assert idx["recordings"][1]["end"] == "2026-11-22T15:07:05"


def test_words_for_the_person() -> None:
    assert rr.recorder_words("duration") == "the maximum length was reached"
    assert rr.recorder_words("local_cap: only 29 GB free") == (
        "the disk check stopped it: only 29 GB free")  # fmt: skip
    assert rr.recorder_words("something new") == "something new"
    assert rr.note_text("stopped", why="you pressed Stop", by_person=True)[0] == "info"
    assert rr.note_text("stopped", why="x")[0] == "warn"
    assert rr.note_text("low_disk", minutes=9.7) == (
        "warn", "Low disk: about 10 minutes of recording left.")  # fmt: skip
    assert rr.note_text("low_disk", minutes=0.6)[1] == "Low disk: about 1 minute of recording left."
    assert rr.note_text("map_change") == ("action", "New map: type /where in the chat.")
    assert "/where" in rr.note_text("indoors")[1] and "/where" in rr.note_text("started")[1]


def test_the_settings_file_overrides_checked(tmp_path: Path) -> None:
    f = tmp_path / "settings.json"
    assert rr.load_settings(f) == (rr.DEFAULTS, None)
    f.write_text(json.dumps({"quiet_s": 5, "low_disk_minutes": [15, 5], "indoor_every_s": 0}))
    s, note = rr.load_settings(f)
    assert note is None and (s.quiet_s, s.low_disk_minutes, s.indoor_every_s) == (5, (15, 5), 0)
    for bad in ({"nope": 1}, {"fps": 0}, {"confirm_reads": 1.5}, [1]):
        f.write_text(json.dumps(bad))
        s, note = rr.load_settings(f)
        assert s == rr.DEFAULTS and note is not None and "defaults apply" in note, bad
    f.write_text("{")
    assert rr.load_settings(f)[0] == rr.DEFAULTS
    assert rr.settings_problem(rr.DEFAULTS) is None


def test_the_helper_sends_no_input() -> None:
    """Static: the only ro_agent names it uses are a grabber, the client's region and the window
    finders' places; nothing of chat_window but its read-only finder."""
    tree = ast.parse((REPO / "scripts" / "route_rec.py").read_text())
    used: dict[str, set[str]] = {"ro_agent": set(), "cw": set()}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id in used):  # fmt: skip
            used[node.value.id].add(node.attr)
    assert used["ro_agent"] == {
        "Screen",
        "real_game_region",
        "panel_places",
        "_panel_still_there",
    }  # a positive case: the walk sees them
    assert used["cw"] == {"find_any"}
    text = (REPO / "scripts" / "route_rec.py").read_text()
    for word in ("send_input", "send_many", ".click(", ".press(", "xdotool", "Agent("):
        assert word not in text, word


# --- the helper end to end, with a fake host ------------------------------------------------------


class Shot:
    """A fake frame: what the two readers would say about it (they are patched to read it)."""

    shape = (720, 1280, 3)

    def __init__(self, basic: bool = True, chat: bool = True, minimap: str | None = "present",
                 xy: tuple[int, int] | None = (50, 50)) -> None:  # fmt: skip
        self.basic, self.chat, self.minimap, self.xy = basic, chat, minimap, xy


class FakeProc:
    pid = 4242

    def __init__(self, log: Path) -> None:
        self.log: Path = log
        self.rc: int | None = None
        self.signals: list[int] = []

    def poll(self) -> int | None:
        return self.rc

    def send_signal(self, sig: int) -> None:
        self.signals.append(sig)

    def end(self, rc: int, line: str) -> None:
        with open(self.log, "a") as fh:
            fh.write(line + "\n")
        self.rc = rc


class FakeHost:
    def __init__(self, clock: Any) -> None:
        self.clock = clock
        self.script: Any = lambda t: Shot()
        self.lock_ = SimpleNamespace(backend="console", phase="steady")
        self.free_ = 100 * GB
        self.ps_: list[str] = []
        self.fmt, self.problem = "h264", None
        self.spawned: list[tuple[list[str], FakeProc]] = []
        self.released = 0

    def grab(self) -> Shot:
        return self.script(self.clock.t)

    def release(self) -> None:
        self.released += 1

    def digits(self) -> Any:
        return object()

    def lock(self) -> Any:
        return self.lock_

    def free(self, path: Path) -> int:
        return self.free_

    def floor(self) -> int:
        return 30 * GB

    def ps(self) -> list[str]:
        return self.ps_

    def limits(self) -> rr.Limits:
        return LIM

    def preflight(self, backend: str, out: Path) -> tuple[str | None, str | None]:
        return self.fmt, self.problem

    def spawn(self, argv: list[str], log: Path) -> FakeProc:
        p = FakeProc(log)
        self.spawned.append((list(argv), p))
        return p


class Clock:
    t = 0.0


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(rr, "look_ready", lambda f: {
        "basic_info": f.basic, "chat_window": f.chat, "places": {}})  # fmt: skip
    monkeypatch.setattr(rr, "recheck_ready", lambda f, places: None)
    monkeypatch.setattr(rr, "look_minimap", lambda f, d: {
        "minimap": f.minimap, "xy": None if f.xy is None else list(f.xy), "reason": "ok",
        "view": "test"})  # fmt: skip
    clk = Clock()
    host = FakeHost(clk)
    d = tmp_path / "settings" / "routerec"
    d.mkdir(parents=True)
    root = tmp_path / "store" / "recordings"
    h = rr.Helper(d, host, root, clock=lambda: clk.t, wall=lambda: 1_763_798_400.0 + clk.t)
    return SimpleNamespace(h=h, host=host, clk=clk, d=d, root=root)


def ask(rig: Any, action: str, rid: str, **kw: Any) -> None:
    (rig.d / "request.json").write_text(json.dumps({"id": rid, "action": action, **kw}))
    req = rig.h.take_request()
    assert req is not None and not (rig.d / "request.json").exists()  # consumed once
    rig.h.handle(req)


def advance(rig: Any, to: float, step: float = 0.5) -> None:
    while rig.clk.t < to - 1e-9:
        rig.clk.t = round(rig.clk.t + step, 6)
        rig.h.tick()


def events(folder: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in (folder / "events.jsonl").read_text().splitlines()]


def test_a_check_writes_its_answer_with_the_request_id(rig: Any) -> None:
    ask(rig, "check", "check0001")
    c = rig.h.check
    assert c["id"] == "check0001" and c["ready"] and c["can_start"]
    assert (c["format"], c["disk"]["minutes"], c["disk"]["verdict"]) == ("h264", 1707, "ok")
    assert c["minimap"] == "present" and c["xy"] == [50, 50] and c["frame"] == [1280, 720]
    rig.host.script = lambda t: Shot(basic=False, minimap="absent", xy=None)
    ask(rig, "check", "check0002")
    c = rig.h.check
    assert not c["ready"] and c["missing"] == ["basic_info"] and not c["can_start"]
    assert c["minimap"] == "absent" and "status window" in c["words"]
    rig.host.fmt, rig.host.problem = "vpp-hevc444-10-q20", "--out must be /home/bot/poring-lab-rec"
    rig.host.script = lambda t: Shot()
    ask(rig, "check", "check0003")
    c = rig.h.check
    assert c["ready"] and not c["can_start"] and c["recorder"].startswith("--out must be")
    assert c["disk"]["minutes"] is None and c["disk"]["verdict"] == "unknown"  # not measured yet
    rig.h.write_status()
    st = json.loads((rig.d / "status.json").read_text())
    assert st["check"]["id"] == "check0003" and st["state"] == "idle" and st["recording"] is None


def test_a_start_is_refused_while_a_bot_plays_or_the_game_is_not_ready(rig: Any) -> None:
    rig.host.ps_ = ["python scripts/flow_play.py play settings/flowrun/project.json"]
    ask(rig, "start", "start0001")
    assert not rig.host.spawned and "bot of ours" in rig.h.detail
    rig.h.busy_tick()
    assert rig.h.state == "busy" and rig.h.busy
    rig.host.ps_ = []
    rig.h.busy_tick()
    assert rig.h.state == "idle"
    rig.host.script = lambda t: Shot(chat=False)
    ask(rig, "start", "start0002")
    assert not rig.host.spawned and "chat window" in rig.h.detail
    rig.host.script = lambda t: Shot()
    rig.host.free_ = 29 * GB  # below the recorder's floor
    ask(rig, "start", "start0003")
    assert not rig.host.spawned and "no room" in rig.h.detail
    assert not rig.root.exists()  # nothing was made
    assert rig.host.released == 3  # each refused start closed the grab helper again


def test_a_recording_end_to_end(rig: Any) -> None:
    """Start (the check first), the recorder's argv, the manifest and the index at the start; the
    guide while it records (started, a map change once, indoors); Stop = SIGINT to its PID; the
    end in the manifest, the index and the status."""
    ask(rig, "start", "start0001", map="xmas_dun02")
    ((argv, proc),) = rig.host.spawned
    folder = rig.h.rec.dir
    assert folder.parent.parent == rig.root and folder.name.endswith("-xmas_dun02-route")
    assert argv[argv.index("--backend") + 1] == "console" and argv[argv.index("--fps") + 1] == "5"
    assert argv[argv.index("--seconds") + 1] == "3570"  # 60 min, the h264 cap
    assert argv[argv.index("--max-bytes") + 1] == str(8192 * 10**6)
    assert argv[argv.index("--out") + 1] == str(folder) and "--format" not in argv
    man = json.loads((folder / "manifest.json").read_text())
    assert (man["purpose"], man["keep"], man["split"], man["end"]) == (
        "route", False, "held-out", None)  # fmt: skip
    idx = json.loads((rig.root / "index.json").read_text())
    assert [e["dir"] for e in idx["recordings"]] == [f"{folder.parent.name}/{folder.name}"]
    assert rig.h.state == "starting"

    def script(t: float) -> Shot:  # walk, a warp held for two reads at 20 s, indoors from 40 s
        if t < 20:
            return Shot(xy=(50 + int(2 * t), 50))
        if t < 40:
            return Shot(xy=(150 + int(2 * (t - 20)), 150))
        return Shot(minimap="absent", xy=None)

    rig.host.script = script
    advance(rig, 120.0)
    assert rig.h.state == "recording"
    kinds = [n["kind"] for n in rig.h.notes]
    assert kinds == ["started", "map_change", "map_change", "indoors"], kinds
    assert len({n["id"] for n in rig.h.notes}) == len(kinds)  # each its own id
    rs = rig.h.rec_status()
    assert rs["minimap"] == "absent" and rs["ready"] and rs["elapsed_s"] == 120.0

    ask(rig, "stop", "stop00001")
    assert proc.signals == [signal.SIGINT] and rig.h.state == "stopping"
    ask(rig, "stop", "stop00002")  # a second Stop: nothing more is sent
    assert proc.signals == [signal.SIGINT]
    result = {"dir": str(folder / "x"), "bytes": 300_000_000, "mb_per_min": 41.0,
              "stop_reason": "stopped by signal", "format": "h264"}  # fmt: skip
    proc.end(0, json.dumps(result))
    advance(rig, 121.0)
    assert rig.h.rec is None and rig.h.state == "ended" and rig.host.released == 1  # at the end
    man = json.loads((folder / "manifest.json").read_text())
    assert (man["stop_reason"], man["bytes"], man["recorder"]["rc"]) == (
        "you pressed Stop", 300_000_000, 0)  # fmt: skip
    assert man["end"] is not None and man["split"] == "held-out"
    (entry,) = json.loads((rig.root / "index.json").read_text())["recordings"]
    assert entry["bytes"] == 300_000_000 and entry["mb_per_min"] == 41.0 and entry["end"]
    last = rig.h.notes[-1]
    assert (last["kind"], last["level"]) == ("stopped", "info")
    assert "you pressed Stop" in last["text"]
    ev = [e["kind"] for e in events(folder)]
    assert ev[0] == "start" and ev[-1] == "end" and "stop" in ev and "jump" in ev
    assert "minimap_gone" in ev and ev.count("notification") == 5
    rig.h.write_status()
    st = json.loads((rig.d / "status.json").read_text())
    assert st["last"]["stop_reason"] == "you pressed Stop" and st["recording"] is None
    assert [n["kind"] for n in st["notifications"]][-1] == "stopped"


def test_readiness_lost_for_a_minute_stops_the_recording_with_the_reason(rig: Any) -> None:
    ask(rig, "start", "start0001")
    ((_, proc),) = rig.host.spawned
    rig.host.script = lambda t: Shot(basic=t < 30)  # a logout at 30 s
    advance(rig, 89.0)
    assert proc.signals == []
    advance(rig, 96.0)  # read every 5 s: lost at 30, a minute later
    assert proc.signals == [signal.SIGINT]
    why = rig.h.rec.stop_reason
    assert why.startswith("the game was not ready for 60 s") and "status window" in why
    proc.end(0, json.dumps({"bytes": 10, "seconds": 95.0, "stop_reason": "stopped by signal"}))
    advance(rig, 97.0)
    stopped = rig.h.notes[-1]
    assert stopped["kind"] == "stopped" and stopped["level"] == "warn"
    kinds = [e["kind"] for e in events(Path(rig.h.last["dir"]))]
    assert "ready_lost" in kinds and kinds[-1] == "end"


def test_a_recorder_that_refuses_at_its_start_is_reported_and_never_counts(rig: Any) -> None:
    ask(rig, "start", "start0001")
    ((_, proc),) = rig.host.spawned
    proc.end(1, "the lock says rdp/switching, not console/steady")
    advance(rig, 1.0)
    assert rig.h.state == "failed" and rig.h.last["refused"]
    assert "refused to start" in rig.h.notes[-1]["text"] and "switching" in rig.h.notes[-1]["text"]
    assert not any(n["kind"] == "started" for n in rig.h.notes)
    idx = json.loads((rig.root / "index.json").read_text())
    assert idx["recordings"][0]["refused"] is True
    assert rr.decide_split(idx)[1].startswith("route recording 1 ")  # it did not count


def test_low_disk_while_recording_with_an_unknown_rate_uses_its_own(rig: Any) -> None:
    rig.host.fmt = "vpp-hevc444-10-q20"  # no measured rate: the minutes are unknown at the start
    rig.host.free_ = 45_100_000_000  # 15.1 GB above the 30 GB floor
    ask(rig, "start", "start0001")
    assert rig.h.check["disk"]["minutes"] is None
    free0 = rig.host.free_

    def shrink(t: float) -> Shot:  # 1 GB a minute: 15.1 - t / 60 minutes left
        rig.host.free_ = free0 - int(GB * t / 60)
        return Shot()

    rig.host.script = shrink
    advance(rig, 900.0, step=5.0)
    lows = [(round(rig.clk.t), n["text"]) for n in rig.h.notes if n["kind"] == "low_disk"]
    assert [text for _, text in lows] == [
        "Low disk: about 10 minutes of recording left.",  # 9.93 at 310 s: 10 crossed
        "Low disk: about 2 minutes of recording left.",  # 1.93 at 790 s: 2 crossed
    ]
    assert rig.h.rec_status()["minutes_left"] == 0  # past the floor: record_session's own stop


def test_a_storage_folder_that_cannot_be_written_refuses_the_start_in_words(
    rig: Any, tmp_path: Path
) -> None:
    """The storage folder may be a NAS mount that is away: the start is refused, never a crash of
    the helper's loop (its heartbeat goes on)."""
    blocked = tmp_path / "not-a-folder"
    blocked.write_text("x")
    rig.h.root = blocked
    ask(rig, "start", "start0001")
    assert not rig.host.spawned and rig.h.rec is None
    assert rig.h.detail.startswith("not started: the recordings folder could not be written")
