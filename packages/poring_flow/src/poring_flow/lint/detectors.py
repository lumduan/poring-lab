"""Linter layer 1: the TRAINED MODELS a flow reads (Batt 2026-11-09; ADR-0020 Amendment B).

`detector_sees(model, label)` and `detector_count(model, label)` name a model of models.yaml and
one of its classes. Rules:
- detector_literal (error): the model and the class are written as text, so they can be checked;
- detector_model (error): the model is in the catalogue;
- detector_not_adopted (error): the model is LIVE (a not-adopted model is not a working sensor:
  the Stormy Knight recognizer's round 1 failed its held-out bar);
- detector_class (error): the class is one of the model's trained classes (an EMPTY class, trained
  on no example, never fires);
- detector_count_kind (error): only a detector counts; a boss recognizer says seen / not seen;
- detector_map (warning): a model trained for some maps, read in a map block on another map.
"""

from __future__ import annotations

from poring_flow.lint.common import Ctx
from poring_flow.models import ModelCatalogue, literal, models, uses


def check(ctx: Ctx, cat: ModelCatalogue | None = None) -> None:
    cat = models() if cat is None else cat
    known = ", ".join(cat.models)
    for path, s, block in uses(ctx.flow):
        if "model" not in s.args or "label" not in s.args:
            continue  # structure's unknown_sensor names the missing parameter
        model, label = literal(s.args["model"]), literal(s.args["label"])
        if model is None or label is None:
            ctx.add(
                "detector_literal",
                "error",
                1,
                path,
                f'{s.sensor}(): write the model and the class as text, e.g. {s.sensor}("v1", '
                '"monster"), so they can be checked',
            )
            continue
        spec = cat.models.get(model)
        if spec is None:
            ctx.add(
                "detector_model", "error", 1, path, f"there is no trained model {model} ({known})"
            )
            continue
        if not spec.available:
            ctx.add(
                "detector_not_adopted",
                "error",
                1,
                path,
                f"the model {model} is not adopted, so it is not a working sensor: {spec.why}",
            )
        if label in spec.untrained:
            ctx.add(
                "detector_class",
                "error",
                1,
                path,
                f"{model}'s {label} class was trained on no example: it never fires",
            )
        elif label not in spec.classes:
            ctx.add(
                "detector_class",
                "error",
                1,
                path,
                f"{model} has no class {label} (its classes: {', '.join(spec.classes)})",
            )
        if s.sensor == "detector_count" and not spec.counts:
            ctx.add(
                "detector_count_kind",
                "error",
                1,
                path,
                f"{model} is a boss recognizer: it says seen or not seen and does not count "
                "(use detector_sees)",
            )
        if spec.maps and block is not None and block.map.map not in spec.maps:
            ctx.add(
                "detector_map",
                "warning",
                1,
                path,
                f"{model} is trained for {', '.join(spec.maps)} only; the map block {block.name} "
                f"is on {block.map.map}",
            )
