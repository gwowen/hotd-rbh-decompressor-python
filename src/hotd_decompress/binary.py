"""Little-endian readers and 4-char PIFF tags."""

from __future__ import annotations

import struct
from typing import Final

NULL: Final = 0xFFFFFFFF


def u8(data: bytes, offset: int) -> int:
    return data[offset]


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def s16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<h", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def s32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def f32(data: bytes, offset: int) -> float:
    return struct.unpack_from("<f", data, offset)[0]


def read_tag(data: bytes, offset: int) -> str:
    return data[offset : offset + 4].decode("latin-1")


def encode_tag(tag: str) -> bytes:
    if len(tag) != 4:
        raise ValueError(f"Chunk tag must be 4 chars, got {tag!r}")
    return tag.encode("latin-1")
