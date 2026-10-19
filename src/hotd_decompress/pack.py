"""
PACK chunk unpacking (BODY ← PACK).

Layout from hotd-decomp `UnpackPackToBody` (`FUN_00410e68`) pack/unpack path:
  repeat:
    u16 uncompressedSize
    if 0: end
    u16 compressedSize
    compressedSize bytes of LZ payload
"""

from __future__ import annotations

from dataclasses import dataclass

from hotd_decompress.binary import u16
from hotd_decompress.lz import decompress_lz


@dataclass(frozen=True)
class PackHunk:
    uncompressedSize: int
    compressedSize: int
    compressedOffset: int


@dataclass(frozen=True)
class UnpackPackResult:
    data: bytes
    hunks: list[PackHunk]
    bytesConsumed: int


def unpack_pack(payload: bytes) -> UnpackPackResult:
    """Decompress a PACK chunk payload into raw BODY bytes."""
    parts: list[bytes] = []
    hunks: list[PackHunk] = []
    pos = 0
    total = 0

    while pos + 2 <= len(payload):
        uncompressed_size = u16(payload, pos)
        pos += 2

        if uncompressed_size == 0:
            break

        if pos + 2 > len(payload):
            raise ValueError("PACK hunk missing compressed size")

        compressed_size = u16(payload, pos)
        pos += 2

        if pos + compressed_size > len(payload):
            raise ValueError(
                f"PACK hunk compressed data exceeds chunk ({compressed_size} bytes at {pos})"
            )

        compressed_offset = pos
        compressed = payload[pos : pos + compressed_size]
        pos += compressed_size

        output, input_bytes_consumed = decompress_lz(compressed, uncompressed_size)

        if input_bytes_consumed != compressed_size:
            raise ValueError(
                f"PACK hunk consumed {input_bytes_consumed}/{compressed_size} compressed bytes"
            )

        hunks.append(
            PackHunk(
                uncompressedSize=uncompressed_size,
                compressedSize=compressed_size,
                compressedOffset=compressed_offset,
            )
        )
        parts.append(output)
        total += len(output)

    data = b"".join(parts)
    return UnpackPackResult(data=data, hunks=hunks, bytesConsumed=pos)
