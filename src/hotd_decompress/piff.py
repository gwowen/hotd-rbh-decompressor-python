"""
Generic PIFF container (RIFF-like) used by HotD assets.
Forms include RBHF (.rbh) and VVTP (.vmc), among others.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hotd_decompress.binary import encode_tag, read_tag, u32
from hotd_decompress.pack import unpack_pack

type Source = str | Path | bytes


@dataclass(frozen=True)
class PiffChunk:
    tag: str
    """File offset of the chunk tag."""
    offset: int
    size: int
    data: bytes


@dataclass(frozen=True)
class PiffFile:
    byteLength: int
    form: str
    chunks: list[PiffChunk]
    path: str | None = None


@dataclass(frozen=True)
class DecompressedChunk:
    originalTag: str
    tag: str
    data: bytes
    hunks: int


@dataclass(frozen=True)
class DecompressPiffResult:
    form: str
    chunks: list[DecompressedChunk]
    """Rebuilt PIFF bytes with PACK expanded to BODY."""
    bytes: bytes
    packedChunks: int
    unpackedBytes: int
    source: PiffFile | None = None


def _read_bytes(source: Source) -> tuple[bytes, str | None]:
    if isinstance(source, (str, Path)):
        path = str(source)
        return Path(path).read_bytes(), path
    return bytes(source), None


def load_piff(source: Source) -> PiffFile:
    """Load any PIFF container."""
    raw, path = _read_bytes(source)

    if len(raw) < 12:
        raise ValueError("PIFF file too small")

    magic = read_tag(raw, 0)
    if magic != "PIFF":
        raise ValueError(f"Expected PIFF magic, got {magic!r}")

    size_field = u32(raw, 4)
    if size_field != len(raw) - 8:
        raise ValueError(f"PIFF size field {size_field} does not match file length {len(raw)}")

    form = read_tag(raw, 8)
    chunks: list[PiffChunk] = []
    offset = 12

    while offset + 8 <= len(raw):
        tag = read_tag(raw, offset)
        size = u32(raw, offset + 4)
        data_start = offset + 8
        data_end = data_start + size

        if data_end > len(raw):
            raise ValueError(f"Chunk {tag} at 0x{offset:x} extends past end of file")

        chunks.append(
            PiffChunk(
                tag=tag,
                offset=offset,
                size=size,
                data=raw[data_start:data_end],
            )
        )

        # HotD PIFF does not use RIFF odd-size padding between chunks.
        offset = data_end

    if offset != len(raw):
        raise ValueError(f"Trailing {len(raw) - offset} bytes after last chunk")

    return PiffFile(path=path, byteLength=len(raw), form=form, chunks=chunks)


def serialize_piff(form: str, chunks: list[tuple[str, bytes]]) -> bytes:
    """Serialize a PIFF form + chunks back to bytes."""
    payload = 4  # form
    for _tag, data in chunks:
        payload += 8 + len(data)

    out = bytearray(8 + payload)
    out[0:4] = encode_tag("PIFF")
    out[4:8] = (payload).to_bytes(4, "little")
    out[8:12] = encode_tag(form)

    offset = 12
    for tag, data in chunks:
        out[offset : offset + 4] = encode_tag(tag)
        out[offset + 4 : offset + 8] = len(data).to_bytes(4, "little")
        out[offset + 8 : offset + 8 + len(data)] = data
        offset += 8 + len(data)

    return bytes(out)


def decompress_piff(file: PiffFile) -> DecompressPiffResult:
    """
    Expand PACK chunks to BODY (`UnpackPackToBody` (`FUN_00410e68`) unpack path).
    Already-uncompressed BODY/other chunks are passed through.
    """
    chunks: list[DecompressedChunk] = []
    packed_chunks = 0
    unpacked_bytes = 0

    for chunk in file.chunks:
        if chunk.tag == "PACK":
            unpacked = unpack_pack(chunk.data)
            if unpacked.bytesConsumed != len(chunk.data):
                # Trailing padding after terminator is unusual but tolerate zeros.
                rest = chunk.data[unpacked.bytesConsumed :]
                if any(b != 0 for b in rest):
                    leftover = len(chunk.data) - unpacked.bytesConsumed
                    raise ValueError(f"PACK chunk left {leftover} unconsumed bytes")
            chunks.append(
                DecompressedChunk(
                    originalTag="PACK",
                    tag="BODY",
                    data=unpacked.data,
                    hunks=len(unpacked.hunks),
                )
            )
            packed_chunks += 1
            unpacked_bytes += len(unpacked.data)
        else:
            chunks.append(
                DecompressedChunk(
                    originalTag=chunk.tag,
                    tag=chunk.tag,
                    data=chunk.data,
                    hunks=0,
                )
            )

    return DecompressPiffResult(
        form=file.form,
        chunks=chunks,
        bytes=serialize_piff(file.form, [(c.tag, c.data) for c in chunks]),
        packedChunks=packed_chunks,
        unpackedBytes=unpacked_bytes,
    )


def decompress_piff_file(source: Source) -> DecompressPiffResult:
    """Load a PIFF file and return its decompressed form."""
    source_file = load_piff(source)
    result = decompress_piff(source_file)
    return DecompressPiffResult(
        form=result.form,
        chunks=result.chunks,
        bytes=result.bytes,
        packedChunks=result.packedChunks,
        unpackedBytes=result.unpackedBytes,
        source=source_file,
    )
