# PIFF container, PACK, and LZ

How bytes sit on disk before any asset-specific parse. RBHF (`.rbh`) and VVTP (`.vmc`) both use this layer.

Decomp anchors: `FUN_00410e68` (PACK unpack), `FUN_00410818` / `FUN_00410d3c` / `FUN_00585aa0` (LZ), `FUN_005769c0` (PIFF+RBHF probe), `FUN_00576610` (PIFF+VVTP load).

## PIFF file

```
offset  size  field
0x00    4     magic "PIFF"
0x04    4     size     = fileLength - 8
0x08    4     form     e.g. "RBHF" or "VVTP"
0x0C    …     chunks
```

The size field is the number of bytes **after** the 8-byte PIFF header (form tag + all chunks), matching RIFF’s convention.

### Chunks

Each chunk is:

```
offset  size  field
0x00    4     tag      ASCII fourcc ("RBHH", "BODY", "PACK", "RELC", …)
0x04    4     size     payload byte length
0x08    size  payload
```

The next chunk starts immediately at `payload end`. **HotD PIFF does not insert a pad byte after odd-sized chunks.** Re-serializing with RIFF padding will break the file.

The parser walks until EOF. Trailing bytes after the last chunk are an error.

### Forms seen in this tree

| Form (ASCII) | u32 as read LE | Used by |
|--------------|----------------|---------|
| `PIFF` | `0x46464950` | File magic |
| `RBHF` | `0x46484252` | `.rbh` (decomp comments sometimes write this as “FBHR”) |
| `VVTP` | `0x50545656` | `.vmc` texture banks |
| `BODY` | `0x59444f42` | Uncompressed payload |
| `PACK` | | Compressed BODY (Tantalus LZ) |
| `RBHH` | | RBHF header table |
| `RELC` | | Relocation offset lists |

## PACK → BODY

A `PACK` chunk is a compressed `BODY`. Unpack (`FUN_00410e68`) concatenates **hunks** until a terminator:

```
repeat:
  u16 uncompressedSize
  if uncompressedSize == 0: end
  u16 compressedSize
  compressedSize bytes of LZ payload
```

Each hunk decompresses to exactly `uncompressedSize` bytes. The LZ decoder must consume exactly `compressedSize` input bytes.

Hunks are concatenated in order to form the BODY. Occasional trailing zero padding after the terminator is tolerated; non-zero leftover bytes are not.

Uncompressed files already store `BODY` and never go through this path. Sound RBHs in `assets/sound/` are in that category.

## Tantalus LZ

Codec used inside each PACK hunk. Stream of **signed varints**; negative tokens are back-references, non-negative tokens are literal runs.

### Signed varint (`FUN_00410818`)

First byte:

| Bits | Meaning |
|------|---------|
| `0x80` | More bytes follow |
| `0x40` | Sign: set → negative |
| `0x3f` | Low 6 bits of magnitude |

Continuation bytes: `0x80` = more, low 7 bits appended with a running shift of 6, then +7 per extra byte.

`value = sign * magnitude`.

### Tokens (`FUN_00410d3c`)

While output is shorter than `uncompressedSize`:

1. Read a varint **token**.
2. If `token < 0`:
   - Copy length = `-token`.
   - Read a second varint **offset** (absolute index into the output buffer so far).
   - Copy `length` bytes from `output[offset]`. Overlapping copies are intentional (RLE-style).
3. If `token >= 0`:
   - Copy the next `token` bytes from the compressed stream as literals.

Offsets are **absolute** in the current hunk’s output, not distances backward from the write head.

## How the tool works

This layer is the only place that **decompresses** Tantalus LZ. Typed decoders (`-p`, `-w`) call it first; `-d` is this layer by itself.

### Modules

| File | Role |
|------|------|
| `src/piff.ts` | `loadPiff` / `serializePiff` / `decompressPiff` |
| `src/pack.ts` | Walk hunk headers, call LZ per hunk, concatenate |
| `src/lz.ts` | `readVarint` + `decompressLz` |

### `-d` / `--decompress`

```text
bun run index.ts -d <file> [output]
```

1. `loadPiff` — require magic `PIFF`, size field `== fileLength - 8`, walk chunks with **no** odd-size pad.
2. `decompressPiff` — each `PACK` → `unpackPack` → `BODY`; other tags copied as-is.
3. `serializePiff` — rewrite `PIFF` + same form + new chunk list (still unpadded).
4. Write bytes. Default: `decompressed_assets/<name>.decomp.<ext>` (parent dir created).

Stdout: form, how many PACK chunks expanded, unpacked BODY bytes, tag counts, output path.

A file that is already all `BODY` still round-trips (0 PACK expanded). Trailing zeros after a PACK terminator are ignored; leftover non-zero bytes abort.

### In-memory use (no `-d` write)

`-p` and `-w` call `decompressPiff` on the loaded file, then parse the resulting `BODY`s. They do not write a `.decomp.*` PIFF unless you also run `-d`.

Inspect / `-m` / `-s` / `-e` / `-c` use `loadRbh` and **do not** expand PACK. Packed mesh/sprite/evt/cam files need `-d` first.
