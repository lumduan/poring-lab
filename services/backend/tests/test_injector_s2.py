"""ADR-0014 (S2 step 3): the Injector -- still the ONE input writer -- sends to XTest or to the S2
input socket. Console mode + a live S2 socket -> S2; anything else -> X. A switch releases what
the old sink held; an S2 failure resets that sink and never falls back to X with the same batch."""

import collections
from pathlib import Path

import pytest

from poring_backend.state import Injector
from poring_env.protocol import InputEvent, Key, ReleaseAll


class Sink:
    def __init__(self, name: str, *, fail: bool = False) -> None:
        self.name, self.fail = name, fail
        self.events: list[InputEvent] = []
        self.closed = False
        self.leg_ns: collections.deque[int] = collections.deque(maxlen=8)
        self.refused = 0

    def send_many(self, events: list[InputEvent]) -> None:
        if self.fail:
            raise OSError("no ack")
        self.events.extend(events)
        self.leg_ns.append(2_000_000)

    def pointer(self) -> tuple[int, int]:
        return (1, 2)

    def has_window_class(self, needle: str) -> bool:
        return needle == "moonlight"

    def close(self) -> None:
        self.closed = True


def down(code: str = "KeyW") -> list[InputEvent]:
    return [Key(t_mono_ns=1, code=code, action="down")]


@pytest.fixture
def rig(tmp_path: Path):  # type: ignore[no-untyped-def]
    sock = tmp_path / "input.sock"
    state = {"console": False}
    x, s2s = Sink("x11"), []

    def s2_factory() -> Sink:
        s2s.append(Sink("s2"))
        return s2s[-1]

    inj = Injector(lambda: x, s2_factory=s2_factory, s2_socket=sock,
                   console_mode=lambda: state["console"])  # fmt: skip
    return inj, x, s2s, sock, state


async def test_rdp_mode_and_a_missing_socket_stay_on_x(rig) -> None:  # type: ignore[no-untyped-def]
    inj, x, s2s, sock, state = rig
    await inj.apply(down())
    sock.touch()  # the S2 client's socket, but the lock says rdp
    await inj.apply(down("KeyA"))
    state["console"], _ = True, sock.unlink()  # console (V3b / Moonlight-qt): no S2 socket
    await inj.apply(down("KeyS"))
    assert [e.code for e in x.events] == ["KeyW", "KeyA", "KeyS"] and s2s == []  # type: ignore[union-attr]
    assert (await inj.snapshot())["active"] == "x11"
    await inj.close()


async def test_console_with_the_s2_socket_goes_to_s2_and_releases_x_first(rig) -> None:  # type: ignore[no-untyped-def]
    inj, x, s2s, sock, state = rig
    await inj.apply(down())  # held on X
    state["console"] = True
    sock.touch()
    await inj.apply(down("KeyA"))
    assert isinstance(x.events[-1], ReleaseAll)  # the X sink released before the switch
    assert [type(e).__name__ for e in s2s[0].events] == ["Key"]
    snap = await inj.snapshot()
    assert (snap["active"], snap["switches"], snap["s2_acks"], snap["s2_leg_ms_p50"]) == (
        "s2", 1, 1, 2.0,
    )  # fmt: skip
    # back to RDP: the S2 sink is released and closed
    state["console"] = False
    await inj.apply(down("KeyD"))
    assert isinstance(s2s[0].events[-1], ReleaseAll) and s2s[0].closed
    assert x.events[-1].code == "KeyD"  # type: ignore[union-attr]
    await inj.close()


async def test_an_s2_failure_resets_the_sink_and_never_retries_on_x(rig) -> None:  # type: ignore[no-untyped-def]
    inj, x, s2s, sock, state = rig
    state["console"] = True
    sock.touch()
    await inj.apply(down())
    s2s[0].fail = True
    with pytest.raises(OSError):
        await inj.apply(down("KeyA"))
    assert s2s[0].closed and all(getattr(e, "code", "") != "KeyA" for e in x.events)
    await inj.apply(down("KeyS"))  # the next batch opens a new connection
    assert len(s2s) == 2 and s2s[1].events[0].code == "KeyS"  # type: ignore[union-attr]
    snap = await inj.snapshot()
    assert snap["s2_errors"] == 1 and snap["s2_acks"] == 2
    await inj.close()


async def test_window_polls_and_the_pointer_stay_on_x(rig) -> None:  # type: ignore[no-untyped-def]
    inj, x, s2s, sock, state = rig
    state["console"] = True
    sock.touch()
    await inj.apply(down())
    assert await inj.stream_window_present() is True  # the X sink's answer (the presence marker)
    assert await inj.pointer() == (1, 2)
    assert x.events == [] and len(s2s) == 1
    await inj.close()


def test_without_an_s2_factory_the_injector_is_x_only() -> None:
    inj = Injector(lambda: Sink("x11"), s2_socket=Path("/"), console_mode=lambda: True)
    assert inj._want_s2() is False
