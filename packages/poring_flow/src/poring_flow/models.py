"""The trained models as sensor devices (Batt 2026-11-09; ADR-0020 Amendment B).

`models()` reads models.yaml (the committed catalogue: ids, kinds, statuses, files, sha256
prefixes, class names reused from where the repo records them). Two catalogue sensors read them
(blocks.yaml): `detector_sees(model, label)` (a question: True when the model boxes that class in
the frame) and `detector_count(model, label)` (how many boxes of that class). They are ordinary
`Sense` expressions, so the IR (IR 2), its schema, its hash and the Python view's grammar are
unchanged; the linter checks the model and the class (lint/detectors.py), and SIMULATE takes a
detector's counts from the scenario (trace.Change.detects), like `sees`.

Nothing here loads a model or reads a frame: perception is the executor's (MW3), through
scripts/unit_detector.py and scripts/mvp_watch.py, pixels in only (rule 1).
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import cache
from importlib import resources
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]  # no stubs in the dev env
from pydantic import BaseModel, ConfigDict, Field, model_validator

from poring_flow import ir

MODEL_ID = r"^[a-z][a-z0-9_-]{0,31}$"
CLASS_KEY = r"^[a-z][a-z0-9_]{0,47}$"
SENSORS = ("detector_sees", "detector_count")  # the two catalogue sensors that read a model

_CFG = ConfigDict(extra="forbid", frozen=True)


class ModelSpec(BaseModel):
    model_config = _CFG
    kind: Literal["detector", "boss_recognizer"]
    status: Literal["live", "not_adopted"]
    file: str = Field(pattern=r"^[A-Za-z0-9_.\-]{1,80}$")
    sha256: str = Field(pattern=r"^[0-9a-f]{12}$")
    maps: list[str] = []
    classes: list[str] = Field(min_length=1)
    untrained: list[str] = []
    mobs: dict[str, list[int]] = {}
    why: str = Field(max_length=400)

    @model_validator(mode="after")
    def _classes(self) -> ModelSpec:
        import re

        names = [*self.classes, *self.untrained]
        bad = [c for c in names if not re.match(CLASS_KEY, c)]
        if bad or len(set(names)) != len(names):
            raise ValueError(f"classes are distinct keys: {bad or names}")
        if set(self.mobs) - set(self.classes):
            raise ValueError("mobs name classes the model has")
        if self.kind == "boss_recognizer" and len(self.classes) != 1:
            raise ValueError("a boss recognizer answers one question: one class")
        return self

    @property
    def available(self) -> bool:
        return self.status == "live"

    @property
    def counts(self) -> bool:
        """A detector boxes every instance; a recognizer only says seen / not seen."""
        return self.kind == "detector"


class ModelCatalogue(BaseModel):
    model_config = _CFG
    version: int
    models: dict[str, ModelSpec]

    @model_validator(mode="after")
    def _ids(self) -> ModelCatalogue:
        import re

        bad = [m for m in self.models if not re.match(MODEL_ID, m)]
        if bad:
            raise ValueError(f"model ids: {bad}")
        return self


def _handler_exprs(h: ir.Handler) -> Iterator[Any]:
    yield h.when
    if h.until is not None:
        yield h.until
    if h.rearm is not None:
        yield h.rearm


def uses(flow: ir.Flow) -> Iterator[tuple[str, ir.Sense, ir.MapBlock | None]]:
    """(node path, a detector sensor, its map block) everywhere a flow holds an expression."""
    for site in ir.sites(flow):
        for _, e in ir.stmt_exprs(site.stmt):
            for x in ir.sub_exprs(e):
                if isinstance(x, ir.Sense) and x.sensor in SENSORS:
                    yield site.path, x, site.block
    for label, h, block, _ in ir.handler_bodies(flow):
        for e in _handler_exprs(h):
            for x in ir.sub_exprs(e):
                if isinstance(x, ir.Sense) and x.sensor in SENSORS:
                    yield label, x, block
    tops: list[tuple[str, Any]] = [(f"assumes.{i}", a) for i, a in enumerate(flow.assumes)]
    if flow.stop_when is not None:
        tops.append(("stop_when", flow.stop_when))
    for where, e in tops:
        for x in ir.sub_exprs(e):
            if isinstance(x, ir.Sense) and x.sensor in SENSORS:
                yield where, x, None


def literal(e: Any) -> str | None:
    """The text of a string literal, else None."""
    return e.value if isinstance(e, ir.Lit) and isinstance(e.value, str) else None


def detector_keys(flow: ir.Flow) -> list[str]:
    """Every "<model>/<class>" a flow reads with text literals (SIMULATE starts them at 0)."""
    keys = set()
    for _, s, _ in uses(flow):
        model, label = literal(s.args.get("model")), literal(s.args.get("label"))
        if model is not None and label is not None:
            keys.add(f"{model}/{label}")
    return sorted(keys)


@cache
def models() -> ModelCatalogue:
    text = (resources.files("poring_flow") / "models.yaml").read_text(encoding="utf-8")
    return ModelCatalogue.model_validate(yaml.safe_load(text))


def document(cat: ModelCatalogue | None = None) -> dict[str, Any]:
    """The catalogue for the editor (GET /flows/catalogue `models`)."""
    cat = models() if cat is None else cat
    return {
        name: {**m.model_dump(mode="json"), "available": m.available, "counts": m.counts}
        for name, m in cat.models.items()
    }
