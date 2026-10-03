"""scripts/grf_des.py: our own GRF header-DES from the FIPS 46-3 tables (Batt, 2026-10-03)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"

PC1 = (57, 49, 41, 33, 25, 17, 9, 1, 58, 50, 42, 34, 26, 18, 10, 2, 59, 51, 43, 35, 27, 19, 11, 3,
       60, 52, 44, 36, 63, 55, 47, 39, 31, 23, 15, 7, 62, 54, 46, 38, 30, 22, 14, 6, 61, 53, 45, 37,
       29, 21, 13, 5, 28, 20, 12, 4)  # fmt: skip
PC2 = (14, 17, 11, 24, 1, 5, 3, 28, 15, 6, 21, 10, 23, 19, 12, 4, 26, 8, 16, 7, 27, 20, 13, 2,
       41, 52, 31, 37, 47, 55, 30, 40, 51, 45, 33, 48, 44, 49, 39, 56, 34, 53, 46, 42, 50, 36,
       29, 32)  # fmt: skip
SHIFTS = (1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1)


@pytest.fixture(scope="module")
def des() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("grf_des", SCRIPTS / "grf_des.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def full_des(des: ModuleType, key: int, block: int) -> int:
    """Textbook 16-round DES built from the module's tables (the test-only key schedule)."""
    k = des.permute(key, PC1, 64)
    c, d = k >> 28, k & 0xFFFFFFF
    x = des.permute(block, des.IP, 64)
    left, right = x >> 32, x & 0xFFFFFFFF
    for shift in SHIFTS:
        c = ((c << shift) | (c >> (28 - shift))) & 0xFFFFFFF
        d = ((d << shift) | (d >> (28 - shift))) & 0xFFFFFFF
        sub = des.permute((c << 28) | d, PC2, 56)
        left, right = right, left ^ des.feistel(right, sub)
    return des.permute((right << 32) | left, des.FP, 64)


def test_the_tables_reproduce_the_classic_des_vector(des: ModuleType) -> None:
    assert full_des(des, 0x133457799BBCDFF1, 0x0123456789ABCDEF) == 0x85E813540F0AB405


def test_the_grf_round_is_its_own_inverse_and_only_touches_20_blocks(des: ModuleType) -> None:
    data = bytes(range(256)) * 2
    once = des.decode_header(data)
    assert once != data and once[160:] == data[160:]
    assert des.decode_header(once) == data
    assert des.decode_header(data[:12])[8:] == data[8:12]  # a partial block stays as it is
