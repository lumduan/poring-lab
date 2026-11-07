# Licences of this kit

This kit is the `teaching-kit` branch of [lumduan/poring-lab](https://github.com/lumduan/poring-lab).
Its files have different licences:

| File | Licence | Why |
|---|---|---|
| `simple_bot.py`, `README.md`, `NOTICE.md` | Apache-2.0 ([LICENSE](LICENSE)) | Our own code and text. `simple_bot.py` uses numpy, onnxruntime and pywin32; it never imports Ultralytics. |
| `v1.onnx` | AGPL-3.0 ([LICENSE-AGPL-3.0.txt](LICENSE-AGPL-3.0.txt)) | A YOLO11n detector trained with Ultralytics (AGPL-3.0), starting from Ultralytics' pretrained `yolo11n.pt`. Ultralytics licenses models trained with its software under AGPL-3.0, and so do we (the repository's ADR-0018). Its corresponding source is the training code, the AGPL-3.0 component [`services/vision`](https://github.com/lumduan/poring-lab/tree/main/services/vision) on the main branch. The run (frame cache `v1png-20261008`, 30 epochs) started on 2026-10-08 after 23:44 ICT, when that code was at commit `05b8cff`. |
| `samples/*.jpg` | Not licensed by us | Frames of Ragnarok Online running on our own lab server, showing only our own characters. The game's art belongs to its rights holders (Gravity Co., Ltd. and its licensors). They are here only so that `--replay samples` has something to read. |

Using `simple_bot.py` with `v1.onnx` (loading the model at run time) does not change the licence of
`simple_bot.py`. If you share the model, or a model trained from it, the AGPL-3.0 applies to it.
