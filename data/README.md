# data/ (gitignored)

Runtime data lives here and is never committed (see `.gitignore`):

| Path | Written by | What |
|---|---|---|
| `input_log/YYYY-MM-DD.jsonl` | backend | every input decision, `source=human\|bot`, accepted or dropped (ADR-0002) |
| `captures/` | sniffer (TODO) | passive packet captures -- **contain credentials** |
| `weights/` | you | YOLO weights (`*.pt`) for the vision service |
| `datasets/` | you / TODO | frames + labels for training |

The backend and vision containers run as uid 1000 and bind-mount this directory.
