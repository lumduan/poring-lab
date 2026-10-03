"""S2 spike (clean-room variant V3, ADR-0009 / docs/s2-plan.md step 1).

An in-process GameStream client: moonlight-common-c (ctypes) receives the H.264 stream, PyAV decodes
it ONCE into numpy BGRA frames. No Moonlight-qt, no SDL, no GL. It is the first piece of S2 and is
kept; what is NOT S2 is `x11_mirror_shim.py` -- a spike-only compatibility shim that blits frames
into the lab's Xvfb so the console, rdp-loop's interlock and /health see V3 during the experiment,
and that forwards X input (mux -> XTest -> its window) to LiSend*. Final S2: a frame bus, JPEG for
humans from that bus, no Xvfb in the GameStream path, input mux -> S2 client -> Sunshine.
"""
