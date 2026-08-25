"""
Tantalus / House of the Dead LZ codec.

Ported from hotd-decomp (FUN_00410818 / FUN_00410d3c / FUN_00585aa0):
signed 6+7-bit varints; negative tokens are back-references into the
absolute output buffer; positive tokens are literal runs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VarintRead:
    value: int
    next: int


def read_varint(data: bytes, offset: int) -> VarintRead:
    """Read a signed variable-length integer (FUN_00410818)."""
    if offset >= len(data):
        raise ValueError("Unexpected end of compressed stream while reading varint")

    pos = offset
    b = data[pos]
    pos += 1
    sign = -1 if (b & 0x40) != 0 else 1
    value = b & 0x3F
    shift = 6

    while (b & 0x80) != 0:
        if pos >= len(data):
            raise ValueError("Unexpected end of compressed stream in varint continuation")
        b = data[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        shift += 7

    return VarintRead(value=sign * value, next=pos)


def decompress_lz(input: bytes, uncompressed_size: int) -> tuple[bytes, int]:
    """
    Decompress one LZ hunk into a buffer of exactly `uncompressed_size` bytes.
    `input` is only the compressed payload (no size headers).

    Returns (output, input_bytes_consumed).
    """
    output = bytearray(uncompressed_size)
    out_pos = 0
    in_pos = 0

    while out_pos < uncompressed_size:
        token = read_varint(input, in_pos)
        in_pos = token.next

        if token.value < 0:
            length = -token.value
            offset_tok = read_varint(input, in_pos)
            in_pos = offset_tok.next
            offset = offset_tok.value

            if offset < 0 or offset > out_pos:
                raise ValueError(f"Invalid back-reference offset {offset} at out={out_pos}")
            if out_pos + length > uncompressed_size:
                raise ValueError(f"Back-reference length {length} exceeds remaining output")

            # Overlapping copies are intentional (RLE-style matches).
            for i in range(length):
                output[out_pos + i] = output[offset + i]
            out_pos += length
        else:
            length = token.value
            if in_pos + length > len(input):
                raise ValueError(f"Literal run of {length} exceeds compressed input")
            if out_pos + length > uncompressed_size:
                raise ValueError(f"Literal run of {length} exceeds remaining output")
            output[out_pos : out_pos + length] = input[in_pos : in_pos + length]
            in_pos += length
            out_pos += length

    return bytes(output), in_pos
