"""poring-lab Phase 2 offline foundation (docs/phase2-plan.md, ADR-0010).

OFFLINE ONLY. Recorded sessions (frames + packet events) in, labelled datasets out. Packet data is
ground truth for TRAINING labels; it never reaches the agent at decision time (ADR-0007):
poring_env and vision never import this package (tests/test_guards.py).
"""
