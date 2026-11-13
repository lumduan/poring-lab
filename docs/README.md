# poring-lab documentation

The root [README](../README.md) is the quick start. Everything else lives here.

## Setting up

| Document | What it covers |
|---|---|
| [setup/new-lab-host.md](setup/new-lab-host.md) | **The full manual:** Ubuntu and Docker from scratch, `.env`, your own configuration and `git pull`, the host profile, starting the services, the Windows game PC, client-derived data, choosing the detector, a new game server, player mode |
| [windows-setup.md](windows-setup.md) | The Windows game PC for a learner: the game client and Sunshine |
| [setup/windows-lab-host.md](setup/windows-lab-host.md) | The lab's own Windows checklist (RDP as the human's admin path) |
| [client/rathena-client.md](client/rathena-client.md) | The rAthena client copy: the exe, data, patches, settings, the RDP wrapper, Thai locale |
| [setup/game-accounts.md](setup/game-accounts.md) | The game accounts the lab creates, and the RDP credentials |
| [services-and-ports.md](services-and-ports.md) | Every service and compose profile, every port, and what is exposed |

## Using it

| Document | What it covers |
|---|---|
| [console.md](console.md) | The web console: the stream and input, Watch only, Hardware, Economy, the HUD, secret typing, clipboard and files, Settings, Flows and Maps (Save / Load, the Run button) |
| [econ/economics.md](econ/economics.md) | The Economy page's numbers: prices, formulas, checks |
| [troubleshooting.md](troubleshooting.md) | The client, RDP, FreeRDP flags, the GPU, rAthena, Thai text, paste and files |

## How it works

| Document | What it covers |
|---|---|
| [architecture.md](architecture.md) | The topology, the pixel and input paths, the bot's isolated network, datasets, the environment interlock |
| [adr/](adr/) | Every architecture decision (ADR-0001 onward) |
| [knowledge/README.md](knowledge/README.md) | The skill concepts the blocks are built from |

## Developing

| Document | What it covers |
|---|---|
| [development.md](development.md) | The guarded build steps, dev mode, the GPU check and training, the long-lived vision worker, the tools, tests and linters |
| [operations/](operations/) | Runbooks: the detectors, the vision worker, the console display, disk audits, the NAS |

## Research

| Document | What it covers |
|---|---|
| [ROADMAP.md](ROADMAP.md) | The research phases, their status and the ordered plan |
| [planning/](planning/) | Each phase's plans, pre-registrations and verdicts (e.g. [planning/rogue-xmas02.md](planning/rogue-xmas02.md)) |
| [demonstrations.md](demonstrations.md) | The recorded demonstrations and playable demos |
| [benchmarks/](benchmarks/README.md) | Capture and latency benchmarks |
| [environments/community-server.md](environments/community-server.md) | The community server's permission evidence |
