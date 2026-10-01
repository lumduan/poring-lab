"""ClipboardService logic against a fake X side that behaves like xfreerdp 3.15 (ADR-0004).

The real python-xlib adapter is exercised by scripts/clipboard_x11_check.py (test_clipboard_x11.py
runs it when Xvfb is installed; it also runs by hand inside the backend container)."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest

from poring_backend.clipboard import (
    OFFERED_TARGETS,
    ClipboardService,
    ConvertRequest,
    OwnerChanged,
    OwnershipLost,
    PasteOutcome,
    SelectionIO,
)

TEXT = "hello สวัสดีครับ\nline 2"


Make = Callable[..., ClipboardService]


@pytest.fixture
async def make() -> AsyncIterator[Make]:
    services: list[ClipboardService] = []

    def factory(io: SelectionIO | None = None, **kwargs: float) -> ClipboardService:
        opts: dict[str, float] = {
            "targets_timeout_s": 0.3,
            "settle_s": 0.01,
            "data_timeout_s": 0.3,
            "linger_s": 0.05,
            "reconnect_s": 0.05,
        }
        opts.update(kwargs)
        if io is None:

            def broken() -> SelectionIO:
                raise OSError("no X display")

            service = ClipboardService(broken, **opts)
        else:
            service = ClipboardService(lambda: io, **opts)
        service.start()
        services.append(service)
        return service

    yield factory
    for service in services:
        await asyncio.to_thread(service.stop)


async def eventually(pred: Callable[[], bool], timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not pred():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.01)


async def test_paste_is_offered_injected_served_and_released(
    make: Make, make_xfreerdp: Callable[..., Any]
) -> None:
    fake = make_xfreerdp()
    service = make(fake)
    injected = 0

    async def inject() -> str | None:
        nonlocal injected
        injected += 1
        fake.ctrl_v()
        return None

    assert await service.paste(TEXT, inject) == PasteOutcome(True, "ok")
    assert injected == 1
    assert ("targets", OFFERED_TARGETS) in fake.replies
    assert ("data", TEXT.encode()) in fake.replies
    # Served, released, then scrubbed: re-owned with nothing so xfreerdp announces an empty offer
    # that replaces Windows' copy (ADR-0004 amendment), and released again.
    assert fake.history == ["own", "release", "own", "release"] and fake.current_owner == 0
    assert [r for r in fake.replies if r[0] == "targets"] == [("targets", OFFERED_TARGETS)] * 2
    assert service.scrub_incomplete == 0


async def test_no_ctrl_v_when_xfreerdp_is_not_listening(
    make: Make, make_xfreerdp: Callable[..., Any]
) -> None:
    fake = make_xfreerdp(listening=False)  # e.g. RDP_CLIPBOARD=off on the desktop side
    service = make(fake)
    injected = 0

    async def inject() -> str | None:
        nonlocal injected
        injected += 1
        return None

    outcome = await service.paste(TEXT, inject)
    assert outcome == PasteOutcome(False, "rdp_clipboard_not_listening")
    assert injected == 0, "a Ctrl+V without our offer would paste whatever Windows holds"
    assert fake.current_owner == 0


async def test_a_ctrl_v_nobody_pastes_times_out_and_releases(
    make: Make, make_xfreerdp: Callable[..., Any]
) -> None:
    fake = make_xfreerdp()
    service = make(fake)

    async def inject() -> str | None:
        return None  # the focused window ignores Ctrl+V (e.g. the game)

    assert await service.paste(TEXT, inject) == PasteOutcome(False, "no_data_request")
    assert fake.current_owner == 0 and ("data", TEXT.encode()) not in fake.replies


async def test_a_mux_refusal_aborts_and_releases(
    make: Make, make_xfreerdp: Callable[..., Any]
) -> None:
    fake = make_xfreerdp()
    service = make(fake)

    async def inject() -> str | None:
        return "mode=BOT"

    assert await service.paste(TEXT, inject) == PasteOutcome(False, "mode=BOT")
    assert fake.current_owner == 0 and not any(kind == "data" for kind, _ in fake.replies)


async def test_losing_ownership_before_the_ctrl_v_means_no_ctrl_v(
    make: Make, make_xfreerdp: Callable[..., Any]
) -> None:
    fake = make_xfreerdp()
    service = make(fake, settle_s=0.3)
    injected = 0

    async def inject() -> str | None:
        nonlocal injected
        injected += 1
        return None

    task = asyncio.create_task(service.paste(TEXT, inject))
    await eventually(lambda: ("targets", OFFERED_TARGETS) in fake.replies)
    fake.take_by_foreign(0xBAD)
    assert await task == PasteOutcome(False, "ownership_taken")
    assert injected == 0, "the foreign owner's content must never be pasted"


async def test_other_targets_are_refused(make: Make, make_xfreerdp: Callable[..., Any]) -> None:
    fake = make_xfreerdp()
    service = make(fake)

    async def inject() -> str | None:
        fake.push(ConvertRequest("image/png"))
        fake.ctrl_v()
        return None

    assert (await service.paste(TEXT, inject)).ok
    assert ("refuse", "image/png") in fake.replies


async def test_requests_while_idle_are_refused(
    make: Make, make_xfreerdp: Callable[..., Any]
) -> None:
    fake = make_xfreerdp()
    make(fake)
    fake.push(ConvertRequest("UTF8_STRING"))
    await eventually(lambda: ("refuse", "UTF8_STRING") in fake.replies)


async def test_pastes_are_serialised(make: Make, make_xfreerdp: Callable[..., Any]) -> None:
    fake = make_xfreerdp()
    service = make(fake)

    async def inject() -> str | None:
        fake.ctrl_v()
        return None

    first, second = await asyncio.gather(service.paste("one", inject), service.paste("two", inject))
    assert first.ok and second.ok
    assert fake.history == ["own", "release", "own", "release"] * 2  # each paste + its scrub
    assert [d for kind, d in fake.replies if kind == "data"] == [b"one", b"two"]


async def test_a_data_request_during_the_scrub_gets_nothing(
    make: Make, make_xfreerdp: Callable[..., Any]
) -> None:
    """Windows may fetch the (scrub) offer at once: it must get an empty payload, never the text."""
    fake = make_xfreerdp()
    service = make(fake)
    plain_own = fake.own
    owns = 0

    def own_then_fetch() -> bool:
        nonlocal owns
        owns += 1
        ok = plain_own()
        if owns == 2:  # the scrub
            fake.push(ConvertRequest("UTF8_STRING"))
        return ok

    fake.own = own_then_fetch

    async def inject() -> str | None:
        fake.ctrl_v()
        return None

    assert await service.paste(TEXT, inject) == PasteOutcome(True, "ok")
    assert [d for kind, d in fake.replies if kind == "data"] == [TEXT.encode(), b""]
    assert fake.current_owner == 0


async def test_an_incomplete_scrub_is_counted_not_a_failed_paste(
    make: Make, make_xfreerdp: Callable[..., Any]
) -> None:
    """xfreerdp gone quiet after serving: the paste still succeeded, but it is never silent."""
    fake = make_xfreerdp()
    service = make(fake)

    async def inject() -> str | None:
        fake.ctrl_v()
        fake.listening = False  # no TARGETS request for the scrub's re-own
        return None

    assert await service.paste(TEXT, inject) == PasteOutcome(True, "ok")
    assert service.scrub_incomplete == 1
    assert fake.current_owner == 0


async def test_watchdog_clears_foreign_owners_and_warns_once_per_burst(
    make: Make, make_xfreerdp: Callable[..., Any], caplog: pytest.LogCaptureFixture
) -> None:
    fake = make_xfreerdp(listening=False)
    service = make(fake)
    with caplog.at_level(logging.WARNING, logger="poring_backend.clipboard"):
        for owner in range(0x900, 0x905):
            fake.take_by_foreign(owner)
            await eventually(lambda: fake.current_owner == 0)
        await eventually(lambda: service.foreign_owner_clears == 5)
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "0x900" in warnings[0]


async def test_our_own_ownership_changes_are_not_foreign(
    make: Make, make_xfreerdp: Callable[..., Any]
) -> None:
    fake = make_xfreerdp()
    service = make(fake)
    fake.push(OwnerChanged(fake.window), OwnerChanged(0))
    await asyncio.sleep(0.1)
    assert service.foreign_owner_clears == 0


async def test_x_unavailable_is_an_outcome_not_an_exception(make: Make) -> None:
    service = make(None)

    async def inject() -> str | None:
        raise AssertionError("must not inject without X")

    assert await service.paste(TEXT, inject) == PasteOutcome(False, "x_unavailable")
    assert not service.connected


async def test_a_stale_selection_clear_from_our_own_release_is_ignored(
    make: Make, make_xfreerdp: Callable[..., Any]
) -> None:
    """A real X server delivers the SelectionClear of a release AFTER a quick re-own (the scrub,
    or the next queued paste). We still own CLIPBOARD: that must not abort anything."""
    fake = make_xfreerdp()
    service = make(fake)
    plain_own = fake.own
    owns = 0

    def own_with_late_clear() -> bool:
        nonlocal owns
        owns += 1
        ok = plain_own()
        if owns == 2:  # the scrub's re-own, chased by the clear of the release just before it
            fake.push(OwnershipLost())
        return ok

    fake.own = own_with_late_clear

    async def inject() -> str | None:
        fake.ctrl_v()
        return None

    assert await service.paste(TEXT, inject) == PasteOutcome(True, "ok")
    assert service.scrub_incomplete == 0
    assert fake.history == ["own", "release", "own", "release"]
