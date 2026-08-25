"""Shared test helpers: asset discovery and a tiny PNG decoder."""

from __future__ import annotations

import os
import shutil
import struct
import zlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TS_ROOT = REPO_ROOT.parent.parent / "typescript" / "hotd-decompress"


def find_assets() -> Path | None:
    env = os.environ.get("HOTD_ASSETS")
    if env:
        path = Path(env)
        if path.is_dir():
            return path
    for candidate in (REPO_ROOT / "assets", TS_ROOT / "assets"):
        if candidate.is_dir():
            return candidate
    return None


ASSETS = find_assets()
HAS_ASSETS = ASSETS is not None
HAS_BUN = shutil.which("bun") is not None and TS_ROOT.is_dir()

requires_assets = pytest.mark.skipif(not HAS_ASSETS, reason="assets/ not found")
requires_bun = pytest.mark.skipif(not HAS_BUN, reason="bun / TypeScript tree not found")


def asset(*parts: str) -> Path:
    assert ASSETS is not None
    return ASSETS.joinpath(*parts)


def decode_png_rgba(data: bytes) -> tuple[int, int, bytes]:
    """Decode a filter-0 RGBA8 PNG (matches this project's encoder)."""
    signature = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
    if data[:8] != signature:
        raise ValueError("not a PNG")
    offset = 8
    width = height = 0
    idat = bytearray()
    while offset + 12 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        typ = data[offset + 4 : offset + 8]
        chunk = data[offset + 8 : offset + 8 + length]
        if typ == b"IHDR":
            width, height = struct.unpack_from(">II", chunk, 0)
        elif typ == b"IDAT":
            idat += chunk
        elif typ == b"IEND":
            break
        offset += 12 + length
    raw = zlib.decompress(bytes(idat))
    stride = width * 4
    rgba = bytearray(width * height * 4)
    for y in range(height):
        row = y * (stride + 1)
        if raw[row] != 0:
            raise ValueError(f"unsupported PNG filter {raw[row]}")
        rgba[y * stride : (y + 1) * stride] = raw[row + 1 : row + 1 + stride]
    return width, height, bytes(rgba)
