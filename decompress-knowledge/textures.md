# Textures (VVTP / `.vmc`)

Texture **pixels** live in PIFF form **VVTP** files, usually with a `.vmc` extension. They are not RBHF. Sprite UVs in `spr.rbh` only *name* pages in these banks.

Decomp: `LoadPiffVvtp` (`FUN_00576610`) loads PIFF+VVTP and registers BODY pages; `PackRgb555` (`FUN_0045640c`) packs RGB555 with the `0x8000` bit; `GenerateTextures` (`FUN_0041a220`) remaps colours (“Generating Textures”).

## File

```
PIFF
  form = VVTP
  BODY or PACK   one chunk per texture page
```

Packed banks (`B_RED.VMC` and siblings) store each page as `PACK`. Uncompressed banks (`bigger.vmc`) store `BODY`. After LZ, every page BODY has the same layout.

The game load path is `ART\STAGE1\CREATURE\texture.VMC`. In this tree `TEXTURE.VMC` may be a stub; the full banks are `bigger.vmc` and the `B_*` colour variants.

## Page layout

Each BODY is one page: a **0x40-byte header** then tightly packed 16-bit pixels (`width * height * 2` bytes). No extra stride.

```
offset  size  field
0x00    4     headerSize     always 0x40
0x04    4     pageId         used as PNG name page_XXXX
0x08    2     width          typically 256
0x0A    2     height         typically 256
0x0C    4     flags          observed 0x100003 (16-bit)
0x10    4     priority/alpha mask   0x8000
0x14    4     red mask              0x7C00
0x18    4     green mask            0x03E0
0x1C    4     blue mask             0x001F
0x20    …     (rest of 0x40 header; unused by this tool)
0x40    w*h*2 pixels, RGB555, row-major
```

Detection used by `src/hotd_decompress/texture.py`: `headerSize == 0x40`, non-zero size ≤ 4096, RGB masks as above, and payload long enough for the pixel array.

## Pixel format

Engine format is **RGB555 plus bit 15** (`PackRgb555` (`FUN_0045640c`) ORs `0x8000` onto packed colours):

```
15        10  9         5  4         0
[ 1 ] [   R 5   ] [   G 5   ] [   B 5   ]
```

This tool expands 5-bit channels to 8-bit as `(c << 3) | (c >> 2)`.

### Clear / transparent

Two values are treated as transparent (engine clear colours):

| Word | Role |
|------|------|
| `0x0000` | Clear |
| `0x8421` | Clear (`TEXTURE_CLEAR` in `src/hotd_decompress/texture.py`) |

`GenerateTextures` (`FUN_0041a220`) seeds a 64K remap table with `table[0] = 0x8421` and `table[0x8000] = 0x8421`, then applies blood-colour overrides.

## Creature banks

Under `assets/art/stage1/creature/`:

| File | Storage | Notes |
|------|---------|-------|
| `TEXTURE.VMC` | Game load name | May be a stub here |
| `bigger.vmc` | Uncompressed `BODY` | Full bank, ~53 MB, **421 pages**. Not byte-identical to a decompressed `B_*` |
| `B_RED` / `B_GREEN` / `B_BLUE` / `B_YELLO` / `B_PURPL` | LZ-`PACK`ed | Same 421-page bank, pre-baked for PC **blood colour** (registry `bloodcolor`, 5 options). Differ mainly on ~38 blood pages; other pages match |

The exe can remap `texture.VMC` at runtime instead of shipping the `B_*` files.

## Relation to other assets

- Mesh prims store a `texPageId` and pixel-space UVs on a 256×256 page (`MESH_PAGE_SIZE`).
- Sprite frames store `pageId` plus a pixel rectangle `(u0,v0)–(u1,v1)` on that page.
- Page bands in this bank: **1–337** sprites, **338–511** unused, **512–546** world, **547–595** creature skins. Species → page: [creatures.md](creatures.md).
## How the tool works

```text
uv run hotd-decompress -p|--png <file.vmc|file.rbh> [outdir]
```

`convert_textures_to_png` (`src/hotd_decompress/texture.py`):

1. `load_piff` + `decompress_piff` — packed `B_*` pages become BODY in memory.
2. Keep chunks tagged `BODY` whose payload passes `is_texture_page` (0x40 header, RGB555 masks, size fits).
3. `parse_texture_page` → `rgb555_to_rgba` (`0x0000` and `0x8421` → alpha 0) → `encode_png` (`src/hotd_decompress/png.py`).
4. Write `page_<pageId padded to 4 digits>.png`. Default dir: `decompressed_assets/<stem>_png/`.

`encode_png` writes 8-bit RGBA, filter 0. IDAT is `zlib.compress`. The TypeScript port uses Node `deflateSync`, so the PNG file bytes differ while the RGBA pixels match.

Stdout: page count, first page `width×height`, skipped non-texture chunks, files written.

If **zero** pages match, the CLI exits 1 and reminds you that `spr.rbh` is metadata — use a `.vmc`. A batch walk (`-p --all`, or `-p` on a directory) counts that as a skip. Running `-p` on an RBHF that is not VVTP pages fails the same way.

`-d` on the same `.vmc` writes a decompressed PIFF (`*.decomp.VMC`) with one BODY per page; `-p` does not write that PIFF, only PNGs.

Page ids in PNG names are the header `pageId` field, not the chunk index. Mesh `texPageId` and sprite `pageId` use the same numbers.
