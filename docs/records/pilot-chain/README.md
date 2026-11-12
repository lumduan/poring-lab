# The night chain's pilot scripts, verbatim (a RECORD, not an install path)

Copied 2026-11-12 20:15 ICT (from `date`) from `/dev/shm/poring-lab-tmp/` on bot-server while
the night series ran (rogue-xmas02.md 4DD / 4DH). `SHA256SUMS` matched the live files at that
moment. The live copies stay scratch: these are never edited (a running bash script must not be
edited in place), and a change to the chain is a new file there, then a new copy here.

Why (docs/planning/second-install-gaps.md row Q): the xmas_dun02 base command lived only in
these scratch files, so the setup manual's section 10 had to compose it by hand, and it was
wrong in one flag (`--steal`, which the chain never passes).

| File | What it is |
|---|---|
| `chain.py` | the detached night chain: `queue.txt` lines `LABEL\|REC\|FLAGS\|MIN`, the weight check and clear-bag between runs, the MVP / immunity steps (`--mvp-live`, `--no-immunity` since 4DF), the post step (ship, score, `econ_db.py update`) |
| `chatjudge.py` | the chain's Chat-tab judge for the immunity answer line |
| `pilot_rec2.sh` | one 25-min pilot beside its 1-fps recorder; holds the `BASE` flag list |
| `pilot_rec_min.sh` | the same with another length |
| `run_pilot_v3.sh` | the detect server (serve-cmd, FP32, the GPU clock floor read from the unit), then the run: the fixed `dungeon_hunt.py run ...` part |
| `score.sh`, `score_full.sh` | every scorer of one run into `/dev/shm/poring-lab-tmp/<LABEL>/` (judge, lock study, D1, supply, W1, ...) |

**The full pilot command** = `run_pilot_v3.sh`'s fixed part + `pilot_rec2.sh`'s `BASE` + the queue
line's FLAGS (4DD's arm A: `--value-target --hud --hud-fast 0.2`). The setup manual's section 10
carries it written out.

Bot-server specifics inside: the repo at `/home/bot/docker/poring-lab`, `/dev/shm` paths, the
Intel GPU clock floor (`gt_min_freq_mhz`, 2450) in the listening check, the seed 20261105. On
another host these differ.

Note 4DI: the fixed part carries `--clear-map`, whose setup types `@killmonster2` at every run
start (the MVP included). Whether the chain's "normal player" runs drop it is Batt's open question.
