"""Perception: pixels in, boxes out. Only placeholders live here for now."""

from pathlib import Path
from typing import Protocol

from poring_env.frame import Frame
from poring_env.protocol import Box


class Detector(Protocol):
    def detect(self, frame: Frame) -> list[Box]: ...


class NullDetector:
    """Sees nothing. The default until a trained model exists."""

    def detect(self, frame: Frame) -> list[Box]:
        return []


class DebugBoxDetector:
    """Reports one fixed box every frame (``VISION_DEBUG_BOX=true``) -- proves the path
    vision -> /internal/agent -> backend -> /ws/stream -> overlay canvas without any model."""

    def detect(self, frame: Frame) -> list[Box]:
        return [Box(x1=0.4, y1=0.4, x2=0.6, y2=0.6, cls="debug", conf=1.0)]


class YoloDetector:
    """TODO(detection): not implemented in the scaffold.

    Intent: load ultralytics YOLO weights from ``/data/weights/<name>.pt`` (gitignored), run
    them on ``cuda:0`` in half precision over ``frame.bgr()`` (BGR, the ultralytics convention,
    no copy), and map each result to a ``Box`` with corners normalized by the frame size.
    Dataset capture, labelling and training live elsewhere (also TODO); this class only does
    inference. Import torch/ultralytics lazily inside ``__init__`` so the loop stays importable
    without the GPU stack.
    """

    def __init__(self, weights: Path) -> None:
        raise NotImplementedError("YOLO detection is not implemented yet (scaffold)")

    def detect(self, frame: Frame) -> list[Box]:
        raise NotImplementedError
