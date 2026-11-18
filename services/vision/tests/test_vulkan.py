"""poring_vision.vulkan (ADR-0022 Amendment 2026-11-18b): the CPU Vulkan drivers kept out of the
loader's list, and the devices it lists read from VkPhysicalDeviceProperties."""

from __future__ import annotations

import struct

from poring_vision import vulkan


def props(vendor: int, device: int, kind: int, name: bytes) -> bytes:
    """A VkPhysicalDeviceProperties as the driver fills it: the head, then the name, then the rest
    (limits, sparse properties) we never read."""
    head = struct.pack("<5I", (1 << 22) | (4 << 12), 7, vendor, device, kind)
    return head + name.ljust(vulkan.NAME_SIZE, b"\0") + b"\xff" * 548


def test_the_cpu_drivers_join_the_disable_list_once_after_a_persons_own() -> None:
    assert vulkan.without_cpu_drivers(None) == "*lvp*,*swiftshader*"
    assert vulkan.without_cpu_drivers("") == "*lvp*,*swiftshader*"
    assert vulkan.without_cpu_drivers("*nouveau*") == "*nouveau*,*lvp*,*swiftshader*"
    once = vulkan.without_cpu_drivers("*lvp*")
    assert once == "*lvp*,*swiftshader*" and vulkan.without_cpu_drivers(once) == once


def test_the_properties_head_names_the_device() -> None:
    """The three devices bot-server and an AMD host list: lavapipe is a CPU type, never a GPU."""
    arc = vulkan.parse_properties(props(0x8086, 0x56A5, 2, b"Intel(R) Arc(tm) A380 Graphics (DG2)"))
    assert arc == {"name": "Intel(R) Arc(tm) A380 Graphics (DG2)", "type": "discrete",
                   "vendor": "Intel", "device_id": "0x56a5"}  # fmt: skip
    amd = vulkan.parse_properties(props(0x1002, 0x7480, 2, b"AMD Radeon RX 7600 (RADV NAVI33)"))
    assert (amd["vendor"], amd["type"]) == ("AMD", "discrete")
    apu = vulkan.parse_properties(props(0x1002, 0x15BF, 1, b"AMD Radeon 780M (RADV PHOENIX)"))
    cpu = vulkan.parse_properties(props(0x10005, 0, 4, b"llvmpipe (LLVM 21.1.8, 256 bits)"))
    assert (cpu["type"], cpu["vendor"]) == ("cpu", "0x10005")
    odd = vulkan.parse_properties(props(0x1234, 1, 9, b"x"))
    assert (odd["type"], odd["vendor"]) == ("other", "0x1234")
    assert vulkan.gpus([arc, cpu, amd, odd, apu]) == [arc, amd, apu]


def test_no_loader_means_the_loader_cannot_be_asked() -> None:
    assert vulkan.devices("libvulkan-that-does-not-exist.so.1") is None
