"""Minimal PNG encoder (RGBA8) using zlib deflate."""

from __future__ import annotations

import struct
import zlib


def _chunk(type: str, data: bytes) -> bytes:
    type_bytes = type.encode("ascii")
    crc = zlib.crc32(type_bytes + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + type_bytes + data + struct.pack(">I", crc)


def encode_png(width: int, height: int, rgba: bytes) -> bytes:
    """Encode an RGBA8 image as a PNG file."""
    if len(rgba) != width * height * 4:
        raise ValueError(f"RGBA buffer size {len(rgba)} does not match {width}x{height}")

    stride = width * 4
    raw = bytearray((stride + 1) * height)
    for y in range(height):
        row_start = y * (stride + 1)
        raw[row_start] = 0  # filter none
        raw[row_start + 1 : row_start + 1 + stride] = rgba[y * stride : (y + 1) * stride]

    ihdr = struct.pack(">II", width, height) + bytes([8, 6, 0, 0, 0])
    signature = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
    return (
        signature
        + _chunk("IHDR", ihdr)
        + _chunk("IDAT", zlib.compress(bytes(raw)))
        + _chunk("IEND", b"")
    )
