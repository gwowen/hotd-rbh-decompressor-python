# Sprites (`spr.rbh`)

`assets/sprite/spr.rbh` is **sprite metadata**: UV rectangles and VVTP page ids. It does not contain pixels. Draw with a `.vmc` bank (`pageId` → `page_XXXX.png`).

Decomp: sprite records are reached via `DAT_005ce544` (`GetSpriteRecord` (`FUN_004430a4`) getter, `StampScrollSprite` (`FUN_004434b0`) scroll-sprite helper).

## Container

RBHF, typically RBHH `flags=2`, one `BODY`, one `RELC`. BODY0 is a pointer table then packed `SpriteRecord`s.

Retail `spr.rbh` has **1640** slots (`firstPtr / 4`).

## Pointer table

```
u32 spritePtr[count]
```

`count = firstPtr / 4`. The first record begins immediately after the table (at `firstPtr`). A `0` pointer is an empty slot (this tool skips it). Pointers are BODY-relative.

## SpriteRecord

```
offset  size  field
0x00    2     u16 frameCount
0x02    2     u16 unk
0x04    2     u16 u0
0x06    2     u16 v0
0x08    2     u16 u1
0x0A    2     u16 v1          header UV / extent
0x0C    2     u16 width
0x0E    2     u16 height
0x10    …     frameCount × 16-byte frames
```

Record size = `16 + frameCount * 16`.

## Frame (16 bytes)

```
offset  size  field
0x00    2     u16 u0
0x02    2     u16 v0
0x04    2     u16 u1
0x06    2     u16 v1          pixel rect on the VVTP page
0x08    2     u16 unk0
0x0A    2     u16 unk1
0x0C    2     u16 pageId      same id as -p page_XXXX
0x0E    2     u16 flags
```

`(u0,v0)–(u1,v1)` is a rectangle in **page pixel space** (pages are 256×256). `pageId` indexes the VVTP bank, not a file offset.

## What this is not

- Not a texture atlas file — pixels are in `.vmc`.
- Not a mesh — no vertices.
- PNG export (`-p`) on `spr.rbh` will not produce sprite images; run `-p` on a `.vmc` and `-s` on `spr.rbh`, then composite using `pageId` + UV rects.

## How the tool works

```text
uv run hotd-decompress -s|--sprites <file.rbh> [outdir]
```

`convert_sprites_to_json` (`src/hotd_decompress/sprite.py`) uses `load_rbh` (no PACK expand).

1. Require exactly one BODY.
2. `is_sprite_body`: first `u32` is a 4-aligned offset into the BODY; `frameCount` at that record is ≤ 4096.
3. `count = firstPtr / 4`. For each slot, `ptr == 0` → skip (counted as `skippedNull`); else parse the record and its frames.
4. Write `sprites.json`. Default dir: `decompressed_assets/<stem>_spr/` (so `spr.rbh` → `spr_spr/`).

JSON: `source`, `count`, `skippedNull`, `sprites[]` with header UVs, size, and per-frame rect / `pageId` / flags. Written by `jsonutil.write_json` (whole floats print as `n.0`).

Stdout: sprite count, skipped null slots, output path.

This does **not** emit PNGs. `-p` on `spr.rbh` finds no VVTP pages and exits 1. Decompress a `.vmc` with `-p`, then crop using `pageId` + `(u0,v0)–(u1,v1)`.
