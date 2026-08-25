"""
HotD / Tantalus VVTP texture pages (from .vmc PACK/BODY chunks).

Header (0x40 bytes) then tightly packed 16-bit pixels:
  +0x00 u32 headerSize (0x40)
  +0x04 u32 pageId
  +0x08 u16 width
  +0x0a u16 height
  +0x0c u32 flags (observed 0x100003 for 16-bit)
  +0x10 u32 priority/alpha mask (0x8000)
  +0x14 u32 red mask   (0x7c00)
  +0x18 u32 green mask (0x03e0)
  +0x1c u32 blue mask  (0x001f)

Pixel format matches hotd-decomp FUN_0045640c (RGB555 + 0x8000 bit).
0x0000 and 0x8421 are treated as transparent (engine clear color).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hotd_decompress.binary import u16, u32
from hotd_decompress.piff import Source, decompress_piff, load_piff
from hotd_decompress.png import encode_png

TEXTURE_CLEAR = 0x8421


@dataclass
class TexturePage:
    pageId: int
    width: int
    height: int
    flags: int
    """Raw RGB555 pixels, width*height entries."""
    pixels: list[int]
    sourceTag: str
    sourceIndex: int


def is_texture_page(data: bytes) -> bool:
    """True if a BODY/PACK payload looks like a VVTP RGB555 texture page."""
    if len(data) < 0x40:
        return False
    header_size = u32(data, 0)
    if header_size != 0x40:
        return False
    width = u16(data, 0x08)
    height = u16(data, 0x0A)
    if width == 0 or height == 0 or width > 4096 or height > 4096:
        return False
    red = u32(data, 0x14)
    green = u32(data, 0x18)
    blue = u32(data, 0x1C)
    if red != 0x7C00 or green != 0x03E0 or blue != 0x001F:
        return False
    return len(data) >= header_size + width * height * 2


def parse_texture_page(
    data: bytes,
    source_tag: str = "BODY",
    source_index: int = 0,
) -> TexturePage:
    if not is_texture_page(data):
        raise ValueError("Not a VVTP RGB555 texture page")

    header_size = u32(data, 0)
    page_id = u32(data, 0x04)
    width = u16(data, 0x08)
    height = u16(data, 0x0A)
    flags = u32(data, 0x0C)
    pixel_bytes = data[header_size : header_size + width * height * 2]
    pixels = [u16(pixel_bytes, i * 2) for i in range(width * height)]

    return TexturePage(
        pageId=page_id,
        width=width,
        height=height,
        flags=flags,
        pixels=pixels,
        sourceTag=source_tag,
        sourceIndex=source_index,
    )


def rgb555_to_rgba(pixel: int, *, clear_color: int = TEXTURE_CLEAR) -> tuple[int, int, int, int]:
    """Expand one RGB555 pixel to RGBA8."""
    if pixel == 0 or pixel == clear_color:
        return (0, 0, 0, 0)

    r = (pixel >> 10) & 0x1F
    g = (pixel >> 5) & 0x1F
    b = pixel & 0x1F
    # 5-bit → 8-bit
    return (
        (r << 3) | (r >> 2),
        (g << 3) | (g >> 2),
        (b << 3) | (b >> 2),
        255,
    )


def texture_page_to_rgba(page: TexturePage, *, clear_color: int = TEXTURE_CLEAR) -> bytes:
    rgba = bytearray(page.width * page.height * 4)
    for i, pixel in enumerate(page.pixels):
        r, g, b, a = rgb555_to_rgba(pixel, clear_color=clear_color)
        o = i * 4
        rgba[o] = r
        rgba[o + 1] = g
        rgba[o + 2] = b
        rgba[o + 3] = a
    return bytes(rgba)


def texture_page_to_png(page: TexturePage, *, clear_color: int = TEXTURE_CLEAR) -> bytes:
    return encode_png(page.width, page.height, texture_page_to_rgba(page, clear_color=clear_color))


@dataclass
class ExtractTexturesResult:
    pages: list[TexturePage]
    skippedChunks: int


def extract_texture_pages(source: Source) -> ExtractTexturesResult:
    """Load a PIFF (.vmc / decompressed) file and extract texture pages."""
    file = load_piff(source)
    decompressed = decompress_piff(file)
    pages: list[TexturePage] = []
    skipped_chunks = 0

    for index, chunk in enumerate(decompressed.chunks):
        if chunk.tag != "BODY":
            skipped_chunks += 1
            continue
        if not is_texture_page(chunk.data):
            skipped_chunks += 1
            continue
        pages.append(parse_texture_page(chunk.data, chunk.originalTag, index))

    return ExtractTexturesResult(pages=pages, skippedChunks=skipped_chunks)


@dataclass
class WriteTexturesResult:
    pages: list[TexturePage]
    written: list[str]
    skippedChunks: int


def convert_textures_to_png(source: Source, out_dir: str) -> WriteTexturesResult:
    """Extract texture pages from a PIFF file and write one PNG per page."""
    result = extract_texture_pages(source)
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for page in result.pages:
        name = f"page_{page.pageId:04d}.png"
        path = str(Path(out_dir) / name)
        Path(path).write_bytes(texture_page_to_png(page))
        written.append(path)

    return WriteTexturesResult(
        pages=result.pages,
        written=written,
        skippedChunks=result.skippedChunks,
    )
