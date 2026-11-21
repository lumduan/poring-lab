"""The /economy page's saved prices (Batt 2026-11-21): "a drop whose price is unknown: blank or 0 for
the user to type; the system remembers it when Update is pressed, so next time it need not be
typed again".

    GET /settings/econ-prices   the saved prices (none when no file), the revision, ok / default /
                                unreadable
    PUT /settings/econ-prices   {base_revision, sell: {"<id>": z}, buy: {"<id>": z}} -- the whole
                                set (the page's Update)

The store is ``settings/econ-prices.json`` (poring_env.econprices). This module is its ONLY writer.
Writes pass routes_settings.write_gate unchanged (a console browser with the console's Origin and
the CSRF token; never the lab host or the Windows host; rate-limited; refusals audited). Every save
is in the Settings audit log. Prices are display data: nothing the bot decides reads them.
"""

from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from poring_backend.routes_settings import Who, _who, browser_gate, write_gate
from poring_backend.state import AppState
from poring_env import econprices as ep

router = APIRouter(prefix="/settings")

SUBJECT = "The economy prices"
_LOCK = threading.Lock()


class PricesPut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=0)
    sell: dict[str, StrictInt]  # never a true / 1.0 coerced to a price
    buy: dict[str, StrictInt]


def store_file(state: AppState) -> Path:
    return state.settings.settings_dir / ep.FILE_NAME


def load(state: AppState) -> tuple[ep.Store, str, str | None]:
    f = store_file(state)
    try:
        text = f.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ep.DEFAULT, "default", None
    except (OSError, UnicodeDecodeError) as e:
        return ep.DEFAULT, "unreadable", f"{f.name} cannot be read ({type(e).__name__})"
    got = ep.parse(text)
    if isinstance(got, str):
        return ep.DEFAULT, "unreadable", f"{f.name}: {got}"
    return got, "ok", None


def view(state: AppState, **extra: Any) -> dict[str, Any]:
    store, status, problem = load(state)
    return {"store": status, "problem": problem, **store.as_json(), **extra}


def write(state: AppState, store: ep.Store) -> None:
    """Atomic, then READ BACK: a save is reported only when the file parses to the same store."""
    f = store_file(state)
    if not f.parent.is_dir():  # never create the mount
        raise HTTPException(503, {"reason": "settings_store_missing"})
    tmp = f.with_name(f".{f.name}.{uuid.uuid4().hex}")
    tmp.write_text(ep.dumps(store), encoding="utf-8")
    os.replace(tmp, f)
    if ep.parse(f.read_text(encoding="utf-8")) != store:
        raise HTTPException(500, {"reason": "read_back_failed"})


def refuse(state: AppState, status: int, reason: str, detail: Any = None) -> HTTPException:
    state.drops.record("settings_http", reason, "econ_prices")
    return HTTPException(status, {"reason": reason, **({"detail": detail} if detail else {})})


def words(s: ep.Store) -> list[str]:
    return [f"{len(s.sell)} sell price(s)", f"{len(s.buy)} buy price(s)"]


def changed(a: ep.Store, b: ep.Store) -> str:
    """PURE: the items whose price changed, in words (the audit's note)."""
    out = []
    for side, x, y in (("sell", a.sell, b.sell), ("buy", a.buy, b.buy)):
        for k in sorted(set(x) | set(y), key=int):
            if x.get(k) != y.get(k):
                out.append(f"{side} #{k}: {x.get(k, '-')} -> {y.get(k, '-')}")
    return "; ".join(out[:40]) + (f"; +{len(out) - 40} more" if len(out) > 40 else "")


def audit(state: AppState, who: Who, rev: tuple[int, int], before: ep.Store,
          after: ep.Store) -> None:  # fmt: skip
    state.allowlist_audit.write(
        action="econ_prices", kind="normal", env_id=None, entry=SUBJECT,
        revision_before=rev[0], revision_after=rev[1], before=words(before), after=words(after),
        ok=True, reason="page", note=changed(before, after)[:1000], **who.model_dump(),
    )  # fmt: skip


@router.get("/econ-prices")
def get_prices(state: AppState = Depends(browser_gate)) -> dict[str, Any]:
    return view(state)


@router.put("/econ-prices")
def put_prices(body: PricesPut, request: Request,
               state: AppState = Depends(write_gate)) -> dict[str, Any]:  # fmt: skip
    who = _who(request)
    with _LOCK:
        store, status, _ = load(state)
        if status != "unreadable" and body.base_revision != store.revision:
            raise refuse(state, 409, "revision_conflict", store.revision)
        why = ep.side_problem(body.sell, "sell") or ep.side_problem(body.buy, "buy")
        if why:
            raise refuse(state, 400, "bad_prices", why)
        base_rev = store.revision if status != "unreadable" else body.base_revision
        new = ep.Store(base_rev + 1, dict(body.sell), dict(body.buy))
        if status == "ok" and (new.sell, new.buy) == (store.sell, store.buy):
            return view(state, saved=False)
        write(state, new)
        audit(state, who, (base_rev, new.revision), store, new)
    return view(state, saved=True)
