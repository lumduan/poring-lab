"""poring-lab Phase 1: passive capture and decoding of our own rAthena traffic (ADR-0007).

OFFLINE GROUND TRUTH ONLY. Nothing here may reach the agent's decision loop: vision never imports
this package, never mounts the `captures` volume, and the agent channel cannot carry its events
(guarded by tests in poring_env and the backend).
"""
