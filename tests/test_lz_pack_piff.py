from __future__ import annotations

import struct

from hotd_decompress.lz import decompress_lz, read_varint
from hotd_decompress.pack import unpack_pack
from hotd_decompress.piff import decompress_piff, load_piff, serialize_piff


def encode_varint(value: int) -> bytes:
    sign_bit = 0x40 if value < 0 else 0
    mag = abs(value)
    first = sign_bit | (mag & 0x3F)
    mag >>= 6
    out = bytearray()
    if mag:
        first |= 0x80
    out.append(first)
    while mag:
        nxt = mag & 0x7F
        mag >>= 7
        if mag:
            nxt |= 0x80
        out.append(nxt)
    return bytes(out)


def test_varint_round_trip() -> None:
    for value in (0, 1, 63, 64, 1000, -1, -4, -63, -64, -1000):
        encoded = encode_varint(value)
        read = read_varint(encoded, 0)
        assert read.value == value
        assert read.next == len(encoded)


def test_lz_literals() -> None:
    payload = encode_varint(3) + b"ABC"
    out, consumed = decompress_lz(payload, 3)
    assert out == b"ABC"
    assert consumed == len(payload)


def test_lz_overlapping_backref() -> None:
    # Literal 'X', then copy 4 bytes from offset 0 (RLE).
    payload = encode_varint(1) + b"X" + encode_varint(-4) + encode_varint(0)
    out, consumed = decompress_lz(payload, 5)
    assert out == b"XXXXX"
    assert consumed == len(payload)


def test_pack_hunk_terminator() -> None:
    inner = encode_varint(4) + b"WXYZ"
    payload = struct.pack("<HH", 4, len(inner)) + inner + struct.pack("<H", 0)
    result = unpack_pack(payload)
    assert result.data == b"WXYZ"
    assert len(result.hunks) == 1
    assert result.bytesConsumed == len(payload)


def test_piff_odd_size_chunks_no_padding() -> None:
    raw = serialize_piff("TEST", [("ABCD", b"\xaa"), ("BODY", b"xyz")])
    # 12 (header) + 8+1 + 8+3 = 32, no pad byte after the 1-byte chunk.
    assert len(raw) == 32
    file = load_piff(raw)
    assert file.form == "TEST"
    assert file.chunks[0].size == 1
    assert file.chunks[0].data == b"\xaa"
    assert file.chunks[1].data == b"xyz"
    assert serialize_piff(file.form, [(c.tag, c.data) for c in file.chunks]) == raw


def test_piff_pack_to_body() -> None:
    inner = encode_varint(2) + b"OK"
    pack = struct.pack("<HH", 2, len(inner)) + inner + struct.pack("<H", 0)
    raw = serialize_piff("VVTP", [("PACK", pack)])
    result = decompress_piff(load_piff(raw))
    assert result.packedChunks == 1
    assert result.chunks[0].tag == "BODY"
    assert result.chunks[0].data == b"OK"
    rebuilt = load_piff(result.bytes)
    assert rebuilt.chunks[0].tag == "BODY"
