"""poring-lab environment contract: observe through ``grab()`` pixels, act through ``send_input()``
mouse/keyboard events. The X11 and remote implementations live in ``poring_env.x11`` /
``poring_env.remote`` (optional extras) so importing the contract never needs a display."""

from poring_env.clock import FrameCounter, monotonic_ns
from poring_env.env import CompositeEnv, Env, FrameSource, InputSink
from poring_env.frame import Frame
from poring_env.protocol import NO_FRAME, InputEvent, Mode

__all__ = [
    "NO_FRAME",
    "CompositeEnv",
    "Env",
    "Frame",
    "FrameCounter",
    "FrameSource",
    "InputEvent",
    "InputSink",
    "Mode",
    "monotonic_ns",
]
