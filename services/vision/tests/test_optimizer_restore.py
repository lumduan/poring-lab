"""The optimizer restore against real torch (2026-10-09; re-proof 2 in
docs/operations/mid-epoch-checkpoints.md). Proof 1's B2 crashed on its first step after a bitwise
restore: fused AdamW refused optimizer state saved contiguous (`to_cpu`) for the channels_last
parameters ultralytics trains on CUDA.

These tests need torch, so they are SKIPPED on the host (no torch there). On the CPU they check
the layout of the restored state and that a resumed step equals the uninterrupted one bit for bit.
The CUDA case (proof 1's exact error) runs only with PORING_CUDA_TESTS=1, inside a guarded vision
step: GPU work stays under R1-R3."""

from __future__ import annotations

import io
import os
from copy import deepcopy
from typing import Any

import pytest

torch = pytest.importorskip("torch", minversion="2.4")  # fused AdamW on the CPU: torch >= 2.4

from poring_vision.midckpt import load_optimizer, tensor_bytes, to_cpu  # noqa: E402

DEVICES = ["cpu"] + (["cuda"] if os.environ.get("PORING_CUDA_TESTS") == "1" else [])
KERNELS = {"fused": {"fused": True}, "foreach": {"foreach": True}}


def net(device: str) -> Any:
    """A 3x3 conv (its channels_last strides differ from NCHW's), a BatchNorm and a 1x1 conv, put
    in channels_last as ultralytics 8.4.165's `_setup_train` puts the model on CUDA."""
    if device == "cuda" and not torch.cuda.is_available():
        pytest.skip("no CUDA here")
    torch.manual_seed(0)
    m = torch.nn.Sequential(torch.nn.Conv2d(3, 8, 3), torch.nn.BatchNorm2d(8),
                            torch.nn.Conv2d(8, 4, 1))  # fmt: skip
    return m.to(device).to(memory_format=torch.channels_last)


def adamw(m: Any, kernel: dict[str, bool]) -> Any:
    """Two groups (decay, no decay) and the kernel passed to the constructor, as build_optimizer."""
    decay = [p for p in m.parameters() if p.ndim > 1]
    rest = [p for p in m.parameters() if p.ndim <= 1]
    groups = [{"params": decay, "weight_decay": 0.05}, {"params": rest, "weight_decay": 0.0}]
    return torch.optim.AdamW(groups, lr=0.01, **kernel)


def step(m: Any, opt: Any, seed: int) -> None:
    """One optimizer step on fixed gradients, laid out like their parameters (autograd's layout
    contract), so nothing but the optimizer differs between runs."""
    g = torch.Generator().manual_seed(seed)
    for p in m.parameters():
        p.grad = torch.empty_like(p).copy_(torch.randn(p.shape, generator=g))
    opt.step()


def trained(device: str, kernel: dict[str, bool]) -> Any:
    """A model and its optimizer after one step. A torch whose kernel refuses channels_last
    parameters on this device is not ultralytics' path (CUDA): skipped, saying so, not failed."""
    m = net(device)
    opt = adamw(m, kernel)
    try:
        step(m, opt, 1)
    except RuntimeError as e:
        pytest.skip(f"this torch's {kernel} AdamW refuses channels_last on {device}: {e}")
    return m, opt


def saved(m: Any, opt: Any) -> dict[str, Any]:
    """Saved as midckpt saves (`to_cpu`, torch.save), read back as a resume reads (to the CPU)."""
    buf = io.BytesIO()
    torch.save({"model": to_cpu(m.state_dict()), "optimizer": to_cpu(opt.state_dict())}, buf)
    buf.seek(0)
    return torch.load(buf, map_location="cpu", weights_only=False)


def stock_restore(opt: Any, sd: dict[str, Any]) -> None:
    """Proof 1's restore: torch's load_state_dict alone (the strides stay as saved)."""
    sd = deepcopy(sd)
    for s, group in zip(sd["param_groups"], opt.param_groups, strict=True):
        s["fused"] = group.get("fused")
    opt.load_state_dict(sd)


def resumed(device: str, kernel: dict[str, bool], ck: dict[str, Any], restore: Any) -> Any:
    """A fresh process's view: the model built and its optimizer made BEFORE the restore."""
    m = net(device)
    opt = adamw(m, kernel)
    m.load_state_dict(ck["model"])
    restore(opt, ck["optimizer"])
    return m, opt


def states(m: Any, opt: Any) -> list[tuple[Any, dict[str, Any]]]:
    return [(p, opt.state[p]) for p in m.parameters()]


@pytest.mark.parametrize("device", DEVICES)
@pytest.mark.parametrize("kernel", list(KERNELS.values()), ids=list(KERNELS))
def test_the_restored_state_is_laid_out_as_its_parameters(device: str, kernel: Any) -> None:
    ck = saved(*trained(device, kernel))
    m2, opt2 = resumed(device, kernel, ck, load_optimizer)
    for p, st in states(m2, opt2):
        for k in ("exp_avg", "exp_avg_sq"):
            assert (st[k].dtype, st[k].device, st[k].stride()) == (p.dtype, p.device, p.stride())
        want = p.device if kernel.get("fused") else torch.device("cpu")
        assert (st["step"].dtype, st["step"].device) == (torch.float32, want)
    # the positive case: proof 1's restore leaves the 3x3 conv's state NCHW-strided
    m3, opt3 = resumed(device, kernel, ck, stock_restore)
    w = next(p for p in m3.parameters() if p.ndim == 4 and p.shape[-1] > 1)
    assert opt3.state[w]["exp_avg"].stride() != w.stride()


@pytest.mark.parametrize("device", DEVICES)
@pytest.mark.parametrize("kernel", list(KERNELS.values()), ids=list(KERNELS))
def test_a_resumed_step_equals_the_uninterrupted_one_bitwise(device: str, kernel: Any) -> None:
    a, a_opt = trained(device, kernel)  # uninterrupted: two steps
    step(a, a_opt, 2)
    ck = saved(*trained(device, kernel))  # interrupted after one step, restored into a fresh model
    b, b_opt = resumed(device, kernel, ck, load_optimizer)
    step(b, b_opt, 2)  # proof 1 raised here on CUDA
    for pa, pb in zip(a.parameters(), b.parameters(), strict=True):
        assert tensor_bytes(pa) == tensor_bytes(pb) and pa.stride() == pb.stride()
    for (_, sa), (_, sb) in zip(states(a, a_opt), states(b, b_opt), strict=True):
        assert sa.keys() == sb.keys()
        for key in sa:
            assert tensor_bytes(sa[key]) == tensor_bytes(sb[key]), key
            assert sa[key].stride() == sb[key].stride() and sa[key].device == sb[key].device, key


@pytest.mark.skipif("cuda" not in DEVICES, reason="PORING_CUDA_TESTS=1 only (a guarded step)")
def test_proof_1s_restore_reproduces_its_crash_on_cuda() -> None:
    ck = saved(*trained("cuda", KERNELS["fused"]))
    b, b_opt = resumed("cuda", KERNELS["fused"], ck, stock_restore)
    with pytest.raises(RuntimeError, match="same dtype, device, and layout"):
        step(b, b_opt, 2)
