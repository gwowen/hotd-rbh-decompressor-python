"""
Sprite metadata bank (assets/sprite/spr.rbh).

BODY0: u32 spritePtr[count] then SpriteRecord[].
count = firstPtr / 4 (1640 in retail spr.rbh).

SpriteRecord:
  +0x00 u16 frameCount
  +0x02 u16 unk
  +0x04 u16 u0, v0, u1, v1   // header UV / extent
  +0x0C u16 width, height
  then frameCount × 16-byte frames:
    +0x00 u16 u0, v0, u1, v1  // pixel rect on VVTP page
    +0x08 u16 unk0, unk1
    +0x0C u16 pageId          // VVTP page id (same as -p page_XXXX)
    +0x0E u16 flags

Pixels live in .vmc banks, not this file (`GetSpriteRecord` (`FUN_004430a4`) / `StampScrollSprite` (`FUN_004434b0`)).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hotd_decompress.binary import u16, u32
from hotd_decompress.jsonutil import write_json
from hotd_decompress.piff import Source
from hotd_decompress.rbh import RbhFile, load_rbh


@dataclass
class SpriteFrame:
    u0: int
    v0: int
    u1: int
    v1: int
    unk0: int
    unk1: int
    pageId: int
    flags: int


@dataclass
class SpriteRecord:
    id: int
    offset: int
    frameCount: int
    unk: int
    u0: int
    v0: int
    u1: int
    v1: int
    width: int
    height: int
    frames: list[SpriteFrame]


@dataclass
class SpriteBank:
    sprites: list[SpriteRecord]
    skipped: int
    path: str | None = None


def is_sprite_body(data: bytes) -> bool:
    """True if BODY0 looks like a spr.rbh pointer table."""
    if len(data) < 8:
        return False
    first = u32(data, 0)
    if first == 0 or first % 4 != 0:
        return False
    if first >= len(data):
        return False
    count = first // 4
    if count < 1 or count > 100_000:
        return False
    # First record should sit at `first` and have a sane frameCount.
    if first + 16 > len(data):
        return False
    frames = u16(data, first)
    return frames <= 4096


def parse_sprite_at(body: bytes, id: int, offset: int) -> SpriteRecord:
    if offset + 16 > len(body):
        raise ValueError(f"Sprite {id} header @ 0x{offset:x} past end")

    frame_count = u16(body, offset)
    record_size = 16 + frame_count * 16
    if offset + record_size > len(body):
        raise ValueError(
            f"Sprite {id} @ 0x{offset:x} extends past BODY ({frame_count} frames)"
        )

    frames: list[SpriteFrame] = []
    for i in range(frame_count):
        at = offset + 16 + i * 16
        frames.append(
            SpriteFrame(
                u0=u16(body, at),
                v0=u16(body, at + 2),
                u1=u16(body, at + 4),
                v1=u16(body, at + 6),
                unk0=u16(body, at + 8),
                unk1=u16(body, at + 10),
                pageId=u16(body, at + 12),
                flags=u16(body, at + 14),
            )
        )

    return SpriteRecord(
        id=id,
        offset=offset,
        frameCount=frame_count,
        unk=u16(body, offset + 2),
        u0=u16(body, offset + 4),
        v0=u16(body, offset + 6),
        u1=u16(body, offset + 8),
        v1=u16(body, offset + 10),
        width=u16(body, offset + 12),
        height=u16(body, offset + 14),
        frames=frames,
    )


def parse_sprite_bank(file: RbhFile) -> SpriteBank:
    if len(file.bodies) != 1:
        raise ValueError(f"Expected 1 BODY for sprite bank, got {len(file.bodies)}")
    body = file.bodies[0].data
    if not is_sprite_body(body):
        raise ValueError("BODY does not look like a sprite pointer table")

    count = u32(body, 0) // 4
    sprites: list[SpriteRecord] = []
    skipped = 0

    for id_ in range(count):
        ptr = u32(body, id_ * 4)
        if ptr == 0:
            skipped += 1
            continue
        sprites.append(parse_sprite_at(body, id_, ptr))

    return SpriteBank(path=file.path, sprites=sprites, skipped=skipped)


def extract_sprites(source: Source) -> SpriteBank:
    return parse_sprite_bank(load_rbh(source))


@dataclass
class WriteSpritesResult:
    bank: SpriteBank
    written: list[str]


def convert_sprites_to_json(source: Source, out_dir: str) -> WriteSpritesResult:
    """Write sprites.json under outDir."""
    bank = extract_sprites(source)
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    payload = {
        "source": bank.path,
        "count": len(bank.sprites),
        "skippedNull": bank.skipped,
        "sprites": bank.sprites,
    }

    path = str(Path(out_dir) / "sprites.json")
    write_json(path, payload)
    return WriteSpritesResult(bank=bank, written=[path])
