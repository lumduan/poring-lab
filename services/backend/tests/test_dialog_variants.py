"""scripts/dialog_variants.py: the L3 extract of the delivery dialog's pages, on a SYNTHETIC NPC
script in rAthena's syntax (invented lines, maps, numbers) -- no rAthena text is committed (GPL)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]


def load() -> ModuleType:
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "dialog_variants", ROOT / "scripts" / "dialog_variants.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["dialog_variants"] = mod
    spec.loader.exec_module(mod)
    return mod


dvs = load()
from poring_env import dialog_variant as dv  # noqa: E402

BODY = """{
	if (Upper == 1) {
		for (.@i = 0; .@i < 3; .@i++) mes "Never run.";
		close;
	}
	else if (job_merchant_q2 && job_merchant_q > 0 && job_merchant_q < 7) {
		mes "[Clerk]";
		if (job_merchant_q2 == 1 || job_merchant_q2 == 2) {
			mes "Go north.";
			next;
			mes "[Clerk]";
			if (job_merchant_q2 == 1) mes "Code ^3355FF111^000000.";
			else mes "Code ^3355FF222^000000.";
		}
		else if (job_merchant_q2 == 3 || job_merchant_q2 == 4) {
			mes "Go south.";
			next;
			if (job_merchant_q2 == 3) {
				mes "[Clerk]";
				mes "Code ^3355FF333^000000.";
			}
			else {
				mes "[Clerk]";
				mes "Code ^3355FF444^000000.";
			}
		}
		next;
		mes "[Clerk]";
		mes "Bye.";
		close;
	}
	else {
		mes "[Clerk]"; // a comment
		mes "Hello.";
		switch(select("Join:Leave")) {
		case 1:
			mes "[Clerk]";
			mes "Hmm, " + strcharinfo(0) + "...";
			next;
			if (select("Yes:No") == 1) {
				set Zeny, Zeny - 10;
			}
			else {
				close;
			}
			mes "[Clerk]";
			mes "Fee?";
			next;
			switch(select("Pay:Quit")) {
			case 1:
				set job_merchant_q,2;
				break;
			case 2:
				close;
			}
			mes "[Clerk]";
			switch(rand(1,2)) {
			case 1:
				mes "Go north.";
				callsub S_Code,111,1,222,2,1001;
				break;
			case 2:
				mes "Go south.";
				callsub S_Code,333,3,444,4,1002;
				break;
			}
			next;
			mes "[Clerk]";
			mes "Bye.";
			close;
		case 2:
			close;
		}
	}

S_Code:
	next;
	mes "[Clerk]";
	mes "Code";
	if (rand(2)) {
		mes "^3355FF"+getarg(0)+"^000000.";
		set job_merchant_q2,getarg(1);
	}
	else {
		mes "^3355FF"+getarg(2)+"^000000.";
		set job_merchant_q2,getarg(3);
	}
	setquest getarg(4);
	return;
}"""

DEST = {1: "north_map", 2: "north_map", 3: "south_map", 4: "south_map"}


@pytest.fixture(scope="module")
def doc() -> dict[str, object]:
    return dict(dvs.extract(BODY, DEST))


def test_every_random_path_is_one_variant(doc: dict[str, object]) -> None:
    v = doc["variants"]
    assert doc["problems"] == [] and set(v) == {"north_map/1", "north_map/2", "south_map/1",
                                                 "south_map/2"}  # type: ignore[arg-type]  # fmt: skip
    assert [(v[k]["value"], v[k]["quest"], v[k]["coloured"]) for k in sorted(v)] == [  # type: ignore[index]
        (1, 1001, ["111"]), (2, 1001, ["222"]), (3, 1002, ["333"]), (4, 1002, ["444"])]  # fmt: skip


def test_pages_carry_the_variants_that_show_them(doc: dict[str, object]) -> None:
    pages = {tuple(p["lines"]): p for p in doc["pages"]}  # type: ignore[attr-defined]
    north = pages[("[Clerk]", "Go north.")]
    assert north["variants"] == ["north_map/1", "north_map/2"]
    assert sorted(north["roles"]) == ["assign", "remind"]  # the same page in both
    assert pages[("[Clerk]", "Code", "^3355FF333^000000.")]["variants"] == ["south_map/1"]
    assert pages[("[Clerk]", "Code ^3355FF444^000000.")]["variants"] == ["south_map/2"]
    assert len(pages[("[Clerk]", "Bye.")]["variants"]) == 4
    assert not any(dvs.NAME in x for p in doc["pages"] for x in p["lines"])  # type: ignore[attr-defined]
    s = dvs.summary(doc)
    assert s["page_kinds"] == {"variant": 8, "destination": 2, "generic": 3}
    assert s["quests"] == [1001, 1002]
    ex = dvs.expected_pages(doc)
    assert all(isinstance(p, dv.ExpectedPage) for p in ex) and len(ex) == len(pages)


def test_the_kb_side_and_unsupported_paths() -> None:
    kb = {"scope": {"merchant": {"home": "home_in", "npcs": [
        {"key": "npc/x.txt:3", "map": "home_in", "role": "job_change",
         "tests": {"job_merchant_q2": [1, 2, 3, 4]}},
        {"key": "npc/x.txt:90", "map": "north_map", "role": "quest",
         "tests": {"job_merchant_q2": [1, 2]}},
        {"key": "npc/y.txt:9", "map": "south_map", "role": "function_caller",
         "tests": {"job_merchant_q2": [3, 4]}},
    ]}}}  # fmt: skip
    assert dvs.job_changer(kb) == ("npc/x.txt", 3)
    assert dvs.destinations(kb, "home_in") == DEST
    top, _ = dvs.parse_block(dvs.tokenize('{ mes "a"; input .@x; close; }'), 0)
    with pytest.raises(dvs.Unsupported):
        dvs.run_paths(top, {}, [], {})


def test_shown_pages_and_the_judge() -> None:
    ev = [{"type": "npc_contact", "t_mono_ns": 1},
          {"type": "npc_say", "text": "[Clerk]", "t_mono_ns": 2},
          {"type": "npc_say", "text": "Go north.", "t_mono_ns": 2},
          {"type": "npc_wait", "t_mono_ns": 2},
          {"type": "npc_next_click", "t_mono_ns": 900},
          {"type": "npc_say", "text": "Bye.", "t_mono_ns": 901},
          {"type": "npc_close", "t_mono_ns": 901}]  # fmt: skip
    shown = dvs.shown_pages(ev)
    assert [(s.lines, s.t_done, s.t_next, s.conversation) for s in shown] == [
        (("[Clerk]", "Go north."), 2, 900, 1), (("Bye.",), 901, 1 << 62, 1)]  # fmt: skip
    dest = dv.ExpectedPage("d", frozenset({"north_map/1", "north_map/2"}), ("x",))
    serial = dv.ExpectedPage("s", frozenset({"north_map/2"}), ("y",))
    generic = dv.ExpectedPage("g", frozenset({"north_map/1", "south_map/1"}), ("z",))
    read = dv.VariantRead
    assert dvs.judge(read(None, "destination_only", "north_map"), dest) == "right"
    assert dvs.judge(read(None, "destination_only", "south_map"), dest) == "wrong"
    assert dvs.judge(read("north_map/1", "ok", "north_map"), serial) == "wrong"
    assert dvs.judge(read(None, "destination_only", "north_map"), serial) == "unknown"
    assert dvs.judge(read(None, "line1:unknown_glyph"), dest) == "unknown"
    assert dvs.judge(read(None, "no_variant_info"), generic) == "right"
