"""What the Vulkan loader sees: the GPUs a WebGPU session (onnxruntime-webgpu's Dawn) can run on.

ADR-0022 Amendment 2026-11-18b (Batt chose AMD option (b), "one build for every vendor"): the detect
server's ``--backend onnxruntime --device webgpu`` runs the deployed ONNX through Vulkan. Two traps
were seen on bot-server's Arc the same day:

- Mesa ships lavapipe, a Vulkan driver that runs ON THE CPU (llvmpipe). With no GPU reachable
  (no render node passed in, the wrong driver), Dawn picks it: the session still names
  WebGpuExecutionProvider first, and a forward takes 835 ms instead of 46 ms (the CPU provider:
  75-90 ms). ``without_cpu_drivers`` keeps such drivers out of the loader's list
  (``VK_LOADER_DRIVERS_DISABLE``, Vulkan loader 1.3.234 and newer), so a missing GPU fails the
  session instead; onnxruntime then falls back to its CPU provider, which ``OrtNet`` refuses.
- The session does not say which adapter it took. ``devices`` asks the loader itself (ctypes,
  stdlib only), so the start line names the GPUs it could pick from, and a list with no GPU in it
  refuses before the session is made.
"""

from __future__ import annotations

import ctypes
import struct
from typing import Any

DISABLE_KEY = "VK_LOADER_DRIVERS_DISABLE"
# Vulkan drivers that run on the CPU: Mesa's lavapipe (libvulkan_lvp.so, lvp_icd.json), and
# Google's SwiftShader where an image ships it
CPU_DRIVERS = ("*lvp*", "*swiftshader*")
# VkPhysicalDeviceType
TYPES = {0: "other", 1: "integrated", 2: "discrete", 3: "virtual", 4: "cpu"}
GPU_TYPES = frozenset({"integrated", "discrete", "virtual"})
# PCI vendor ids (VkPhysicalDeviceProperties.vendorID)
VENDORS = {0x1002: "AMD", 0x8086: "Intel", 0x10DE: "NVIDIA"}
# sizeof(VkPhysicalDeviceProperties) is 824 on x86-64 (the limits are most of it); room to spare
PROPS_SIZE = 1024
HEAD = struct.Struct("<5I")  # apiVersion, driverVersion, vendorID, deviceID, deviceType
NAME_SIZE = 256  # VK_MAX_PHYSICAL_DEVICE_NAME_SIZE, right after the head
VK_SUCCESS, VK_INCOMPLETE = 0, 5
VK_ERROR_INCOMPATIBLE_DRIVER = -9  # vkCreateInstance with no driver at all


def without_cpu_drivers(current: str | None) -> str:
    """PURE: the loader's disable list (comma-separated globs) with CPU_DRIVERS added; a person's
    own entries are kept, in their order."""
    items = [s for s in (current or "").split(",") if s]
    items += [g for g in CPU_DRIVERS if g not in items]
    return ",".join(items)


def parse_properties(buf: bytes) -> dict[str, str]:
    """PURE: the head of a VkPhysicalDeviceProperties -> {name, type, vendor, device_id}."""
    _api, _drv, vendor, device, kind = HEAD.unpack_from(buf, 0)
    raw = buf[HEAD.size : HEAD.size + NAME_SIZE].split(b"\0", 1)[0]
    return {
        "name": raw.decode("utf-8", "replace"),
        "type": TYPES.get(kind, "other"),
        "vendor": VENDORS.get(vendor, f"0x{vendor:04x}"),
        "device_id": f"0x{device:04x}",
    }


def gpus(devices: list[dict[str, str]]) -> list[dict[str, str]]:
    """PURE: the devices that are GPUs (not CPU drivers, not 'other')."""
    return [d for d in devices if d.get("type") in GPU_TYPES]


class _InstanceCreateInfo(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("flags", ctypes.c_uint32),
        ("pApplicationInfo", ctypes.c_void_p),
        ("enabledLayerCount", ctypes.c_uint32),
        ("ppEnabledLayerNames", ctypes.c_void_p),
        ("enabledExtensionCount", ctypes.c_uint32),
        ("ppEnabledExtensionNames", ctypes.c_void_p),
    ]


def devices(lib: str = "libvulkan.so.1") -> list[dict[str, str]] | None:
    """The physical devices the Vulkan loader lists in this process (its environment applies, so
    set DISABLE_KEY first); [] = asked, none; None = the loader cannot be asked (no libvulkan)."""
    try:
        vk: Any = ctypes.CDLL(lib)
    except OSError:
        return None
    vk.vkCreateInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    vk.vkCreateInstance.restype = ctypes.c_int32
    vk.vkEnumeratePhysicalDevices.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    vk.vkEnumeratePhysicalDevices.restype = ctypes.c_int32
    vk.vkGetPhysicalDeviceProperties.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    vk.vkGetPhysicalDeviceProperties.restype = None
    vk.vkDestroyInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    vk.vkDestroyInstance.restype = None
    info = _InstanceCreateInfo(sType=1)  # VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO
    inst = ctypes.c_void_p()
    rc = vk.vkCreateInstance(ctypes.byref(info), None, ctypes.byref(inst))
    if rc == VK_ERROR_INCOMPATIBLE_DRIVER:
        return []
    if rc != VK_SUCCESS:
        return None
    try:
        n = ctypes.c_uint32(0)
        if vk.vkEnumeratePhysicalDevices(inst, ctypes.byref(n), None) not in (
            VK_SUCCESS,
            VK_INCOMPLETE,
        ):
            return []  # the loader found no usable device (it says why on stderr)
        handles = (ctypes.c_void_p * max(n.value, 1))()
        if n.value and vk.vkEnumeratePhysicalDevices(inst, ctypes.byref(n), handles) not in (
            VK_SUCCESS,
            VK_INCOMPLETE,
        ):
            return []
        out = []
        for i in range(n.value):
            buf = ctypes.create_string_buffer(PROPS_SIZE)
            vk.vkGetPhysicalDeviceProperties(handles[i], buf)
            out.append(parse_properties(buf.raw))
        return out
    finally:
        vk.vkDestroyInstance(inst, None)
