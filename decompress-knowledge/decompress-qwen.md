# Decompress knowledge

How *The House of the Dead* (PC / Tantalus) stores assets, and how this CLI decompresses them.

Formats come from `hotd-decomp/THOTD-exe-named.c` / `THOTD-exe-commented.c` and the parsers in `src/hotd_decompress/`. All multi-byte integers are **little-endian**.

This file is the combined form of the notes under `decompress-knowledge/`.

## Contents

- [Reports](#reports)
- [How the tool works](#how-the-tool-works)
- [Two containers, many payloads](#two-containers-many-payloads)
- [Asset map (on disk)](#asset-map-on-disk)
- [PIFF container, PACK, and LZ](#piff-container-pack-and-lz)
- [RBH / RBHF](#rbh-rbhf)
- [Textures (VVTP / `.vmc`)](#textures-vvtp-vmc)
- [Audio (digital SFX)](#audio-digital-sfx)
- [Meshes (`world*.rbh`, `CREAT*.rbh`)](#meshes-worldrbh-creatrbh)
- [Creatures (exe types → CREAT ids → VVTP pages)](#creatures-exe-types-creat-ids-vvtp-pages)
- [Motion clips (`THOTD.exe`)](#motion-clips-thotdexe)
- [Sprites (`spr.rbh`)](#sprites-sprrbh)
- [Events (`evtALL.rbh`)](#events-evtallrbh)
- [Events in detail (VM, opcodes, spawns, cameras)](#events-in-detail-vm-opcodes-spawns-cameras)
- [Cameras (`camALL.rbh`)](#cameras-camallrbh)
- [Cutscenes (`THOTD.exe`)](#cutscenes-thotdexe)
- [Cutscene audio cue sheet](#cutscene-audio-cue-sheet)
- [Game rendering (`THOTD.exe`)](#game-rendering-thotdexe)
- [Enemy spawn, AI, scoring, and collision (`THOTD.exe`)](#enemy-spawn-ai-scoring-and-collision-thotdexe)

---

## Reports

Each note covers **on-disk layout** and **what the tool does** (modules, flags, output names). Exe functions are cited as `` `Name` (`FUN_00xxxxxx`) ``, matching `THOTD-exe-named.c`. Combined dump: [decompress-qwen.md](decompress-qwen.md).

| File | Subject | Flag |
|------|---------|------|
| [piff.md](piff.md) | PIFF container, `PACK` hunks, Tantalus LZ | `-d` |
| [rbh.md](rbh.md) | RBHF (`.rbh`) — headers, BODY, RELC, pointer graphs | *(inspect)* |
| [textures.md](textures.md) | VVTP texture banks (`.vmc`) | `-p` |
| [audio.md](audio.md) | Digital SFX (`O_*.rbh`, `gamesnds.rbh`) | `-w` |
| [meshes.md](meshes.md) | Stage / creature meshes (`world*.rbh`, `CREAT*.rbh`) | `-m` |
| [creatures.md](creatures.md) | Exe types → CREAT ids → VVTP pages (species map) | *(exe tables)* |
| [motion.md](motion.md) | Exe `MO_*` clips + 3×4 bone playback | *(exe tables)* |
| [sprites.md](sprites.md) | Sprite UV/page metadata (`spr.rbh`) | `-s` |
| [events.md](events.md) | Event scripts (`evtALL.rbh`) | `-e` |
| [events-detailed.md](events-detailed.md) | Event VM, opcodes, spawns, `CCTB` → `camALL` | `-e` |
| [cameras.md](cameras.md) | Camera rails (`camALL.rbh`) | `-c` |
| [cutscenes.md](cutscenes.md) | In-engine cutscene playback (evt + cam + draw) | *(exe runtime)* |
| [cutscene-audio.md](cutscene-audio.md) | `SNDON` → `O_*` / `gamesnds` / CD cue join | *(exe table)* |
| [game-rendering.md](game-rendering.md) | Exe draw path (backends, view, prims, VRAM) | *(exe runtime)* |
| [enemy-systems.md](enemy-systems.md) | Spawn, AI, scoring, gun collision (`THOTD.exe`) | *(exe runtime)* |

## How the tool works

`src/hotd_decompress/cli.py` is the only CLI (`uv run hotd-decompress`). It never writes into `assets/` unless you pass an output path there. Defaults land under `decompressed_assets/` (gitignored).

```
assets/  (read-only game files)
    │
    ▼
cli.py  ── flag ──►  src/hotd_decompress/*.py
    │
    ▼
decompressed_assets/
```

| Flag | Module | What it does |
|------|--------|----------------|
| `-d` / `--decompress` | `src/hotd_decompress/piff.py` + `pack.py` + `lz.py` | Expand every `PACK` → `BODY`, rewrite PIFF |
| *(none)* `<file.rbh>` | `src/hotd_decompress/rbh.py` | Print RBHH / BODY / PACK / RELC / pointer-root summary (no write) |
| `-p` / `--png` | `src/hotd_decompress/texture.py` + `png.py` | Decompress PIFF, decode VVTP pages → PNG |
| `-w` / `--wav` | `src/hotd_decompress/audio.py` + `wav.py` | Parse sound RBH → 8-bit mono WAV |
| `-m` / `--mesh` | `src/hotd_decompress/mesh.py` | Parse world/CREAT RBH → OBJ + `ids.json` |
| `-s` / `--sprites` | `src/hotd_decompress/sprite.py` | Parse `spr.rbh` → `sprites.json` |
| `-e` / `--evt` | `src/hotd_decompress/event.py` | Parse event graph + opcodes → `events.json` |
| `-c` / `--cam` | `src/hotd_decompress/camera.py` | Parse camera rails → `cameras.json` |
| `-a` / `--all` | `src/hotd_decompress/discover.py` | Walk a tree and run the matching decoders |

Two load paths:

1. **PIFF decompress** (`load_piff` → `decompress_piff`) — used by `-d`, `-p`, `-w`. Packed pages/clips become `BODY` in memory first.
2. **RBHF parse** (`load_rbh`) — used by inspect, `-m`, `-s`, `-e`, `-c`. Expects `BODY` already (retail mesh/sprite/evt/cam files are uncompressed). Run `-d` first if you have a packed copy.

JSON dumps (`ids.json`, `sprites.json`, `events.json`, `cameras.json`) go through `jsonutil.write_json`: indent 2, a trailing newline, unset optional dataclass fields omitted, and `NaN` / `Infinity` written as `null`. Whole floats print as `n.0` (`json.dumps`). The records match the TypeScript port; that port's `JSON.stringify` prints the same values as `n`.

Default output names (`<stem>` = input filename without extension):

| Flag | Default path |
|------|----------------|
| `-d` | `decompressed_assets/<name>.decomp.<ext>` |
| `-p` | `decompressed_assets/<stem>_png/page_XXXX.png` |
| `-w` | `decompressed_assets/<stem>_wav/*.wav` |
| `-m` | `decompressed_assets/<stem>_mesh/ids.json` + `node_XXXXXX.obj` |
| `-s` | `decompressed_assets/<stem>_spr/sprites.json` |
| `-e` | `decompressed_assets/<stem>_evt/events.json` |
| `-c` | `decompressed_assets/<stem>_cam/cameras.json` |

Inspect with no path defaults to `assets/evt/allstage/evtALL.rbh`.

### `--all` / directory walk

`--all` / `-a` walks `.rbh` and `.vmc` under a root (default `assets`) and writes under an out root (default `decompressed_assets`). A type flag given a directory does the same walk (`uv run hotd-decompress -p assets/art`). Suffixes and names are matched case-insensitively.

Bare `--all` runs the typed kinds only: png, wav, mesh, sprites, evt, cam. `-d` is included only with `-d --all` (or `-d` on a directory).

`discover.matches_kind` classifies each file:

| Kind | Match |
|------|--------|
| png | `.vmc` |
| wav | parent directory `sound`, or name `gamesnds.rbh`, or name `O_*` |
| mesh | stem `world*` or `creat*` |
| sprites | name `spr.rbh`, or parent directory `sprite` |
| evt | stem `evt*`, or parent directory `evt` |
| cam | stem `cam*`, or parent directory `cam` |

A file can match more than one kind. In a batch, these are skips: a `-d` file with no `PACK` chunk, a PNG with no pages, a WAV with no clips, and any `ValueError`. Any other exception fails the batch (exit 1). Single-file `-d` still writes a PIFF when the file has zero `PACK` chunks.

## Two containers, many payloads

Every asset this tool reads is a **PIFF** file (RIFF-like, but **not** odd-size padded). The 4-byte form after the PIFF header selects the payload family:

| Form | Extension | Typical contents |
|------|-----------|------------------|
| `RBHF` | `.rbh` | Meshes, sprites, events, cameras, digital SFX |
| `VVTP` | `.vmc` | Texture pages (256×256 RGB555) |

A compressed payload lives in a `PACK` chunk. After LZ expansion it is a `BODY` blob. Uncompressed files already store `BODY` and skip `PACK`.

CD music is MCI `cdaudio` in the exe. It is **not** in `assets/sound/`. `SNDON` kind 3 still requests a track — [cutscene-audio.md](cutscene-audio.md).

## Asset map (on disk)

| Path | Kind | Report |
|------|------|--------|
| `assets/art/stageN/world/worldN.rbh` | Stage geometry | [meshes.md](meshes.md) |
| `assets/art/stage1/creature/CREAT*.rbh` | Creature meshes | [meshes.md](meshes.md), [creatures.md](creatures.md) |
| `assets/art/stage1/creature/*.vmc` | Creature texture banks | [textures.md](textures.md), [creatures.md](creatures.md) |
| `assets/sprite/spr.rbh` | Sprite frame table | [sprites.md](sprites.md) |
| `assets/evt/…` | Event scripts | [events.md](events.md), [events-detailed.md](events-detailed.md) |
| `assets/cam/…` | Camera rails | [cameras.md](cameras.md) |
| `assets/sound/O_*.rbh` | Oneshoot SFX / voice | [audio.md](audio.md) |
| `assets/sound/gamesnds.rbh` | SFX bank + index | [audio.md](audio.md) |

`spr.rbh` is metadata only. Pixel data lives in `.vmc` banks.

How those files become a frame (DirectDraw / software rasterizer, mesh submit, VRAM pages): [game-rendering.md](game-rendering.md). How a scripted sequence plays (event VM + rails, no FMV): [cutscenes.md](cutscenes.md). Spawn, AI, scoring, and gun hits: [enemy-systems.md](enemy-systems.md).

---

## PIFF container, PACK, and LZ

How bytes sit on disk before any asset-specific parse. RBHF (`.rbh`) and VVTP (`.vmc`) both use this layer.

Decomp anchors: `UnpackPackToBody` (`FUN_00410e68`) (PACK unpack), `LzReadSignedVarint` (`FUN_00410818`) / `LzDecompressHunk` (`FUN_00410d3c`) / `LzDecompressBuffered` (`FUN_00585aa0`) (LZ), `LoadPiffRbh` (`FUN_005769c0`) (PIFF+RBHF probe), `LoadPiffVvtp` (`FUN_00576610`) (PIFF+VVTP load).

### PIFF file

```
offset  size  field
0x00    4     magic "PIFF"
0x04    4     size     = fileLength - 8
0x08    4     form     e.g. "RBHF" or "VVTP"
0x0C    …     chunks
```

The size field is the number of bytes **after** the 8-byte PIFF header (form tag + all chunks), matching RIFF’s convention.

#### Chunks

Each chunk is:

```
offset  size  field
0x00    4     tag      ASCII fourcc ("RBHH", "BODY", "PACK", "RELC", …)
0x04    4     size     payload byte length
0x08    size  payload
```

The next chunk starts immediately at `payload end`. **HotD PIFF does not insert a pad byte after odd-sized chunks.** Re-serializing with RIFF padding will break the file.

The parser walks until EOF. Trailing bytes after the last chunk are an error.

#### Forms seen in this tree

| Form (ASCII) | u32 as read LE | Used by |
|--------------|----------------|---------|
| `PIFF` | `0x46464950` | File magic |
| `RBHF` | `0x46484252` | `.rbh` (decomp comments sometimes write this as “FBHR”) |
| `VVTP` | `0x50545656` | `.vmc` texture banks |
| `BODY` | `0x59444f42` | Uncompressed payload |
| `PACK` | | Compressed BODY (Tantalus LZ) |
| `RBHH` | | RBHF header table |
| `RELC` | | Relocation offset lists |

### PACK → BODY

A `PACK` chunk is a compressed `BODY`. Unpack (`UnpackPackToBody` (`FUN_00410e68`)) concatenates **hunks** until a terminator:

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

### Tantalus LZ

Codec used inside each PACK hunk. Stream of **signed varints**; negative tokens are back-references, non-negative tokens are literal runs.

#### Signed varint (`LzReadSignedVarint` (`FUN_00410818`))

First byte:

| Bits | Meaning |
|------|---------|
| `0x80` | More bytes follow |
| `0x40` | Sign: set → negative |
| `0x3f` | Low 6 bits of magnitude |

Continuation bytes: `0x80` = more, low 7 bits appended with a running shift of 6, then +7 per extra byte.

`value = sign * magnitude`.

#### Tokens (`LzDecompressHunk` (`FUN_00410d3c`))

While output is shorter than `uncompressedSize`:

1. Read a varint **token**.
2. If `token < 0`:
   - Copy length = `-token`.
   - Read a second varint **offset** (absolute index into the output buffer so far).
   - Copy `length` bytes from `output[offset]`. Overlapping copies are intentional (RLE-style).
3. If `token >= 0`:
   - Copy the next `token` bytes from the compressed stream as literals.

Offsets are **absolute** in the current hunk’s output, not distances backward from the write head.

### How the tool works

This layer is the only place that **decompresses** Tantalus LZ. Typed decoders (`-p`, `-w`) call it first; `-d` is this layer by itself.

#### Modules

| File | Role |
|------|------|
| `src/hotd_decompress/piff.py` | `load_piff` / `serialize_piff` / `decompress_piff` |
| `src/hotd_decompress/pack.py` | Walk hunk headers, call LZ per hunk, concatenate |
| `src/hotd_decompress/lz.py` | `read_varint` + `decompress_lz` |

#### `-d` / `--decompress`

```text
uv run hotd-decompress -d <file> [output]
```

1. `load_piff` — require magic `PIFF`, size field `== fileLength - 8`, walk chunks with **no** odd-size pad.
2. `decompress_piff` — each `PACK` → `unpack_pack` → `BODY`; other tags copied as-is.
3. `serialize_piff` — rewrite `PIFF` + same form + new chunk list (still unpadded).
4. Write bytes. Default: `decompressed_assets/<name>.decomp.<ext>` (parent dir created).

Stdout: form, how many PACK chunks expanded, unpacked BODY bytes, tag counts, output path.

A file that is already all `BODY` still round-trips (0 PACK expanded). `-d --all` skips those files instead of writing them. Trailing zeros after a PACK terminator are ignored; leftover non-zero bytes abort.

#### In-memory use (no `-d` write)

`-p` and `-w` call `decompress_piff` on the loaded file, then parse the resulting `BODY`s. They do not write a `.decomp.*` PIFF unless you also run `-d`.

Inspect / `-m` / `-s` / `-e` / `-c` use `load_rbh` and **do not** expand PACK. Packed mesh/sprite/evt/cam files need `-d` first.

---

## RBH / RBHF

`.rbh` files are PIFF forms named **RBHF** (“RBH file”). The container is shared; the BODY payloads are not. This report covers the container. Payload layouts are in the per-type reports.

Decomp: `LoadPiffRbh` (`FUN_005769c0`) probes `PIFF` + `RBHF` (`0x46464950` / `0x46484252`). Mesh load goes through `LoadCreatMeshBank` (`FUN_00419cac`) / `LoadWorldMeshBank` (`FUN_00419cf4`) → `LoadPiffRbh` (`FUN_005769c0`).

### File shape

```
PIFF
  form = RBHF
  RBHH     header table (required)
  BODY|PACK  one or more payloads, in header order
  RELC     optional, usually one per relocatable BODY
```

Typical chunk sequences:

| Kind | Chunks (after RBHH) | RBHH flags |
|------|---------------------|------------|
| Oneshoot SFX `O_*.rbh` | `BODY` | `0` |
| `gamesnds.rbh` | `BODY` (index), `BODY` (samples) | `2`, `0` |
| `spr.rbh`, `evtALL.rbh`, `camALL.rbh` | `BODY` (+ often `RELC`) | `2` |
| `world*.rbh`, `CREAT*.rbh` | `BODY`, `BODY`, `BODY` (+ `RELC`s) | `2`, `0`, `0` |

Packed variants replace a `BODY` with `PACK`. After LZ the BODY size must match the corresponding RBHH `bodySize`.

### RBHH — header table

Required. Payload length is a multiple of **12**. One 12-byte row per BODY (or PACK that becomes a BODY):

```
offset  size  field
0x00    4     field0     unknown; usually 0
0x04    4     bodySize   uncompressed BODY byte length
0x08    4     flags      type / load hint
```

Observed `flags`:

| flags | Meaning in this tree |
|-------|----------------------|
| `0` | Raw blob: PCM, vertex pool, empty pad BODY |
| `2` | Pointer graph: id table, sprite table, event/camera roots, gamesnds index |

`field0` is unused by this tool.

### BODY

Opaque payload whose layout depends on the file. Pointers stored inside a BODY are **byte offsets from the start of that BODY**, not file offsets.

After load, the engine applies `RELC` so those offsets become real pointers. On disk they remain BODY-relative.

### RELC — relocations

Optional. Payload is a list of `u32` values. Non-zero entries are **BODY-relative offsets of fields that hold pointers** (or, for mesh BODY1, `vertBase` fields that index the vertex pool).

Zero slots are padding / unused. This tool counts non-zero entries only.

Mesh files typically have:

- `RELC0` — patch pointer fields in BODY0 (id table, node links, …)
- `RELC1` — mark `vertBase` fields (byte offsets into BODY1)

A file with a single pointer-graph BODY (events, cameras, sprites) usually has one `RELC` covering that BODY.

### Pointer tables

Many `flags=2` BODYs start with a table of `u32` offsets.

**Null terminator** is `0xFFFFFFFF` (not `0`). `0` is a real offset only when the format says so (world id-table node lists use `0` as end-of-list).

#### Simple table

Walk `u32`s until `0xFFFFFFFF` or a value that falls outside the BODY. Used for event scene/section lists.

#### Root table with holes

Event (and similar) **root** tables allow `0xFFFFFFFF` in the middle (unused stage slots). Length is implied by the first non-null child: the child table begins immediately after the root, so

```
slotCount = firstChildOffset / 4
```

Each slot is either a BODY offset or `0xFFFFFFFF`.

Sprite and camera roots use the same “first pointer / 4 = count” rule, but those tables are dense (no mid-list nulls in the retail files this tool was checked against). Camera groups skip a null root slot if one appears. Generic inspect can over-count a camera group’s child list by walking into key data; `-c` always finds six tracks per group (see [cameras.md](cameras.md)).

### How to tell types apart

The container does not store a type fourcc beyond `RBHF`. Heuristics used by this tool:

| Check | Type |
|-------|------|
| 1 BODY, starts with `u32 0x00082c30`, then `u16 2` | Oneshoot sound |
| 2 BODYs, index size `% 0x28 == 0`, rate `0x2b11` at `+0x08` | `gamesnds` |
| ≥2 BODYs, flags `2,0`, BODY1 size `% 12 == 0` | Mesh (then creat vs world by id table) |
| 1 BODY, first `u32 / 4` = count, record at that offset has a sane `frameCount` | Sprites |
| 1 BODY, small root (`firstPtr ≤ 0x400`), nested `0xFFFFFFFF`-terminated tables | Events |
| 1 BODY, groups of 6 Hermite tracks `{u16 keyCount, u16 log2(keyCount)}` | Cameras |

### How the tool works

#### Inspect (no flag)

```text
uv run hotd-decompress <file.rbh>
# no path → assets/evt/allstage/evtALL.rbh
```

`inspect_rbh` → `load_rbh` → `describe_rbh`. Prints to stdout; **does not write a file** and **does not expand PACK**.

The summary lists:

- file size and form (`RBHF`)
- chunk tags and sizes
- each RBHH row (`bodySize`, `flags`, `field0`)
- BODY / PACK / RELC offsets
- RELC non-zero entry counts
- if there is exactly one BODY that looks like a root pointer table: slot count, nulls, and the first 16 child groups

#### Typed decompress

The container parser does not pick a payload type. Other flags run their own heuristics (table above) and fail if the BODY does not match:

| Flag | Entry | Failure |
|------|--------|---------|
| `-w` | `src/hotd_decompress/audio.py` | no oneshoot / gamesnds BODY |
| `-m` | `src/hotd_decompress/mesh.py` | not flags `2,0` + float3 BODY1 |
| `-s` | `src/hotd_decompress/sprite.py` | not 1 BODY / not a sprite pointer table |
| `-e` | `src/hotd_decompress/event.py` | not 1 BODY / not a small root table |
| `-c` | `src/hotd_decompress/camera.py` | not 1 BODY / not a camera group table |

`-d` only rewrites PIFF (`PACK`→`BODY`); it does not interpret RBHH. See [piff.md](piff.md).

---

## Textures (VVTP / `.vmc`)

Texture **pixels** live in PIFF form **VVTP** files, usually with a `.vmc` extension. They are not RBHF. Sprite UVs in `spr.rbh` only *name* pages in these banks.

Decomp: `LoadPiffVvtp` (`FUN_00576610`) loads PIFF+VVTP and registers BODY pages; `PackRgb555` (`FUN_0045640c`) packs RGB555 with the `0x8000` bit; `GenerateTextures` (`FUN_0041a220`) remaps colours (“Generating Textures”).

### File

```
PIFF
  form = VVTP
  BODY or PACK   one chunk per texture page
```

Packed banks (`B_RED.VMC` and siblings) store each page as `PACK`. Uncompressed banks (`bigger.vmc`) store `BODY`. After LZ, every page BODY has the same layout.

The game load path is `ART\STAGE1\CREATURE\texture.VMC`. In this tree `TEXTURE.VMC` may be a stub; the full banks are `bigger.vmc` and the `B_*` colour variants.

### Page layout

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

### Pixel format

Engine format is **RGB555 plus bit 15** (`PackRgb555` (`FUN_0045640c`) ORs `0x8000` onto packed colours):

```
15        10  9         5  4         0
[ 1 ] [   R 5   ] [   G 5   ] [   B 5   ]
```

This tool expands 5-bit channels to 8-bit as `(c << 3) | (c >> 2)`.

#### Clear / transparent

Two values are treated as transparent (engine clear colours):

| Word | Role |
|------|------|
| `0x0000` | Clear |
| `0x8421` | Clear (`TEXTURE_CLEAR` in `src/hotd_decompress/texture.py`) |

`GenerateTextures` (`FUN_0041a220`) seeds a 64K remap table with `table[0] = 0x8421` and `table[0x8000] = 0x8421`, then applies blood-colour overrides.

### Creature banks

Under `assets/art/stage1/creature/`:

| File | Storage | Notes |
|------|---------|-------|
| `TEXTURE.VMC` | Game load name | May be a stub here |
| `bigger.vmc` | Uncompressed `BODY` | Full bank, ~53 MB, **421 pages**. Not byte-identical to a decompressed `B_*` |
| `B_RED` / `B_GREEN` / `B_BLUE` / `B_YELLO` / `B_PURPL` | LZ-`PACK`ed | Same 421-page bank, pre-baked for PC **blood colour** (registry `bloodcolor`, 5 options). Differ mainly on ~38 blood pages; other pages match |

The exe can remap `texture.VMC` at runtime instead of shipping the `B_*` files.

### Relation to other assets

- Mesh prims store a `texPageId` and pixel-space UVs on a 256×256 page (`MESH_PAGE_SIZE`).
- Sprite frames store `pageId` plus a pixel rectangle `(u0,v0)–(u1,v1)` on that page.
- Page bands in this bank: **1–337** sprites, **338–511** unused, **512–546** world, **547–595** creature skins. Species → page: [creatures.md](creatures.md).
### How the tool works

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

---

## Audio (digital SFX)

Digital sound effects live in RBHF files under `assets/sound/`. They are already uncompressed (`BODY` only, no `PACK`).

Stage / menu **music** is CD audio via MCI (`cdaudio`) in the exe. It is not in these files. Event scripts can still **request** it: `SNDON` kind 3 calls `PlayCdAudioTrack` (`FUN_00565d60`). See [cutscene-audio.md](cutscene-audio.md).

Decomp: `InitSoundMixer` (`FUN_00411f10`) inits the mixer at **11025 Hz, 8-bit, 3 voices**. The “3 channels” are mixer voices, not stereo in the files. Sample rate constant `_DAT_00c721e4 = 0x2b11`. Runtime oneshoots are requested as `sound\O_%s.rbh`.

### Shared PCM format

| Property | Value |
|----------|-------|
| Rate | 11025 Hz (`0x2B11`) |
| Width | Unsigned 8-bit |
| Channels | Mono |
| Silence | ≈ `0x80` |

This tool writes standard PCM WAVs (`src/hotd_decompress/wav.py`) with those parameters.

### Oneshoot — `O_*.rbh`

One clip per file. RBHH: a single row with `flags=0`. One `BODY`.

```
BODY:
  +0x00  u32  magic     0x00082C30
  +0x04  u16  0x0002
  +0x06  u16  soundId
  +0x08  u8[] unsigned PCM  (rest of BODY)
```

`0x00082C30` is also the **external-ref sentinel** in `gamesnds.rbh` (see below). `soundId` is how the bank points at a sibling `O_*` file.

Export: `uv run hotd-decompress -w assets/sound/O_HELP.rbh` → `decompressed_assets/O_HELP_wav/O_HELP.wav`.

### Bank — `gamesnds.rbh`

RBHH two rows: `flags=2` then `flags=0`. Two BODYs:

| BODY | Role |
|------|------|
| 0 | Index: `N` records of **0x28** bytes |
| 1 | Concatenated embedded PCM |

Index size must be a multiple of `0x28`. This tool requires `sampleRate` at `+0x08` of the first row to be `0x2B11`.

#### Index row (0x28 bytes)

Known fields used by `src/hotd_decompress/audio.py`:

```
offset  size  field
0x00    4     (unused by this tool)
0x04    4     size         PCM byte length
0x08    4     sampleRate   0x2B11
0x0C    8     (unused by this tool)
0x14    4     soundId      O_* id when external
0x18    4     offset       into BODY1, or sentinel
0x1C    12    (unused by this tool)
```

#### Embedded vs external

| `offset` (`+0x18`) | Meaning |
|--------------------|---------|
| Any other value | Byte offset into BODY1; take `size` bytes of PCM from there |
| `0x00082C30` | External: play the oneshoot whose `soundId` is at `+0x14` |

WAV export of the bank scans the same directory for `O_*.rbh`, keys them by `soundId`, and fills external rows. Missing siblings are skipped (`skippedExternal`).

Output names:

- Embedded: `clip_XXX.wav`
- External: `ext_XXX_O_NAME.wav`

### How the tool works

```text
uv run hotd-decompress -w|--wav <file.rbh> [outdir]
```

`convert_sounds_to_wav` (`src/hotd_decompress/audio.py` + `wav.py`):

1. `load_piff` + `decompress_piff` (sound files in this tree have no PACK; this is a no-op).
2. Collect `BODY` chunks.
3. **Oneshoot** if there is one BODY starting with `0x00082C30` / `u16 2`. Clip name = input stem (`O_HELP.rbh` → `O_HELP.wav`).
4. **gamesnds** if there are two BODYs, index length `% 0x28 == 0`, and `+0x08` of the first row is `0x2B11`. Then:
   - scan `dirname(input)` for `O_*.rbh`, parse each oneshoot, key by `soundId`;
   - embedded rows → slice BODY1, name `clip_XXX`;
   - external rows → copy the matching oneshoot, name `ext_XXX_O_NAME`; missing siblings increment `skippedExternal` and are omitted.
5. `encode_wav_pcm8_mono` — RIFF WAV, unsigned 8-bit, 1 channel, 11025 Hz.
6. Default dir: `decompressed_assets/<stem>_wav/`.

Stdout: clip count, format line, skipped external refs (if any), files written.

Zero clips → exit 1 (wrong file, or CD music path). A batch walk counts that as a skip (`WAV skip (no clips)`). The tool does not touch MCI `cdaudio`.

### Sound-request table (`THOTD.exe`)

`SNDON` in `evtALL.rbh` does **not** store a filename. The u32 arg indexes `DAT_005cbda8` (270 × `0x0C` rows). Kind 4 sprintf's `sound\O_%s.rbh`; kinds 1–2 play `gamesnds.rbh` row `extra`; kind 3 is a CD track. Cue join: [cutscene-audio.md](cutscene-audio.md). Parser: `src/hotd_decompress/sound_table.py` (not a CLI flag).

---

## Meshes (`world*.rbh`, `CREAT*.rbh`)

Stage geometry and creature models share one RBHF layout: a pointer graph plus a float3 vertex pool. Prim batches match `DispatchMeshPrims` (`FUN_00578bb0`). Load path: `LoadCreatMeshBank` (`FUN_00419cac`) / `LoadWorldMeshBank` (`FUN_00419cf4`) → `LoadPiffRbh` (`FUN_005769c0`).

### Container

RBHH flags **`2, 0, 0`**. Three BODYs (BODY2 is empty). Usually two `RELC` chunks.

| Chunk | flags | Contents |
|-------|-------|----------|
| BODY0 | 2 | Id table + mesh nodes + prim batches |
| BODY1 | 0 | Vertex pool: tightly packed `f32 x, y, z` (12 bytes each) |
| BODY2 | 0 | Empty |
| RELC0 | | Pointer fields in BODY0 |
| RELC1 | | `vertBase` fields (byte offsets into BODY1) |

BODY1 size is a multiple of 12. Vertices are already in **stage space**. World node `+0x20` XYZ is metadata — do **not** bake it as a translate when exporting.

### Id tables (start of BODY0)

Two layouts. This tool tries creat first, then world.

#### Creature (`CREAT*.rbh`)

Fixed 8-byte rows until `id == -1`:

```
offset  size  field
0x00    2     s16 id
0x02    2     s16 flag
0x04    4     u32 nodePtr    BODY0 offset of the mesh node
```

Each id maps to **one** node.

#### World (`world*.rbh`)

Variable-length rows until `id == 0`:

```
s16 id
s16 flag
u32 nodePtr, nodePtr, … , 0     (0 terminates the pointer list)
```

One world id can reference several nodes. `0` here is end-of-list, not `0xFFFFFFFF`.

### Mesh node

```
offset  size  field
0x00    4     link0
0x04    4     vertBase     byte offset into BODY1 (multiple of 12)
0x08    4     link2
0x0C    4     pad
0x10    4     fieldA
0x14    4     fieldC
0x18    4     f32 scale
0x1C    2     unk
0x1E    2     0xFFFF
```

Then:

| Kind | Next fields |
|------|-------------|
| World | `+0x20` `f32 posX, posY, posZ`; prim batches start at `+0x2C`. Some id-table tails point at header-only stubs (no pose / prims). |
| Creat | Prim batches start at `+0x20` (no position). |

`vertBase / 12` is the first vertex this node uses. Prim indices are **local** to that slice (index 0 = `pool[vertBase/12]`).

### Prim batches (`DispatchMeshPrims` (`FUN_00578bb0`))

A node is followed by zero or more batches until `count == 0` (or a negative `sizeShorts`).

Batch header (8 bytes):

```
offset  size  field
0x00    2     u16 count       number of prims
0x02    2     u16 flags
0x04    2     unk
0x06    2     s16 sizeShorts  payload size in 16-bit units
```

`kind = flags & 0x2007`. Payload is `sizeShorts * 2` bytes immediately after the header.

| kind | Type | Payload per prim | Notes |
|------|------|------------------|-------|
| `0` | Plain tri | 4 shorts (8 B) | `u16 i0, i1, i2` (+ 1 unused) |
| `1` | Plain tri | 4 shorts | Treated like `0` |
| `2` | Textured tri | 18 shorts (36 B) | See below |
| `0x2001` | Plain quad | 5 shorts (10 B) | `u16 i0..i3` (+ 1 unused) |
| `0x2004` | Textured quad | 22 shorts (44 B) | See below |

The renderer also uses other flag bits (e.g. `0x200` skips a facing test). This tool only needs `0x2007` to pick the record size.

#### Textured tri (36 bytes)

```
+0x00  u16 i0, i1, i2
+0x06  u16 texPageId
+0x08  (4 bytes unused by this tool)
+0x0C  f32 u0, v0
+0x14  f32 u1, v1
+0x1C  f32 u2, v2
```

#### Textured quad (44 bytes)

```
+0x00  u16 i0, i1, i2, i3
+0x08  u16 texPageId
+0x0A  (2 bytes unused by this tool)
+0x0C  f32 u0, v0 … u3, v3     (8 floats)
```

UVs are **pixel coordinates** on a 256×256 VVTP page (`MESH_PAGE_SIZE`). `texPageId` matches `page_XXXX` from `-p` on the matching `.vmc`. OBJ export converts to `0..1` and flips V (`(256 - v) / 256`) so OBJ’s V-up matches the page’s V-down.

### How the tool works

```text
uv run hotd-decompress -m|--mesh <file.rbh> [outdir]
```

`convert_meshes_to_obj` (`src/hotd_decompress/mesh.py`) uses `load_rbh` — **no PACK expand**. Retail `world*.rbh` / `CREAT*.rbh` are already BODY.

1. `is_mesh_rbh`: ≥2 header rows, flags `2` then `0`, BODY1 size `% 12 == 0`.
2. `detect_kind`: try creat id table (`id == -1` terminator), else world (`id == 0`).
3. Unique node offsets from the id table, sorted; parse each node’s batches.
4. Default dir: `decompressed_assets/<stem>_mesh/`.

Writes:

- `ids.json` — `kind`, id → `{offset, file}` map, per-node `vertBase` / scale / position / counts
- `node_<offset hex, 6 digits>.obj` — one file per unique node

OBJ details:

- `v` from the node’s BODY1 slice (no world `+0x20` bake)
- textured faces: `usemtl page_<texPageId>`, `vt` in 0..1 with V flipped
- untextured faces: `usemtl none` after a textured run
- comment lines for position (world) and scale

`ids.json` follows `jsonutil.write_json` (whole floats print as `n.0`). OBJ `v` / `vt` lines use the same number text for non-integers, so a tiny value can be scientific (`4.6e-05`). The TypeScript port prints a long decimal for that same float. Topology and UV counts match.

Stdout: `kind`, id count, node count, files written.

Pair OBJ materials with `-p` on the matching `.vmc` (`page_XXXX.png`). CREAT ids are body parts; the exe type table and skeleton trees that group them into named creatures are in [creatures.md](creatures.md).

`-m` writes every prim as an OBJ face (quads stay 4-gons). A dump of many **CREAT** nodes is a spike ball because the engine submits one bone mesh per frame ([game-rendering.md](game-rendering.md), [motion.md](motion.md)), not because the node bytes are wrong. World quads are strip-ordered; fanning `(0,1,2)+(0,2,3)` bowties them. CREAT quads are perimeter order and that fan is the exe split.

---

## Creatures (exe types → CREAT ids → VVTP pages)

On-disk creature data is **pooled**, not one file per enemy. Names live in `THOTD.exe` motion strings and a 94-row type table. Mesh parts are `CREAT1.RBH` / `CREAT2.rbh` ids; skins are VVTP pages in `texture.VMC` / `B_*`.

This note is **not** a CLI flag. `scripts/creature_map.py` joins the exe tables below to CREAT `texPageId`s and `evtALL` spawns. Decomp: `LoadStageAssets` (`FUN_00418aa0`) (load), `LoadCreatMeshBank` (`FUN_00419cac`) (CREAT id table → `DAT_00d53080`), `ApplyCreatureTypeStats` (`FUN_00483ad0`) (type → model id).

### Files are banks

| Asset | Role |
|--------|------|
| `CREAT1.RBH` | Creature/NPC mesh parts. 1397 ids, 917 nodes. Ids **0–6611**, no overlap with CREAT2. |
| `CREAT2.rbh` | Same layout. 2677 ids, 1517 nodes. Ids **55–7498**. |
| `texture.VMC` / `B_*` / `bigger.vmc` | One shared page bank. `B_RED`…`B_PURPL` are blood-colour remaps of the same 421 pages, not different species. |

`LoadStageAssets` (`FUN_00418aa0`) always loads `ART\STAGE1\CREATURE\CREAT1.RBH`, then `CREAT2.RBH`, then `texture.VMC`. There is no per-chapter creature file.

Each CREAT id is one **body-part node** (median ~20 verts), not a whole character. A creature is a skeleton of many ids.

`LoadCreatMeshBank` (`FUN_00419cac`) copies each CREAT id table into a global slot array:

```
for (id, nodePtr) in table until id == -1:
    DAT_00d53080[id] = nodePtr
```

CREAT2 is loaded second; ids do not collide, so both banks sit in one namespace. Draw looks up `DAT_00d53080[modelId]`. Spawn helpers also hardcode model ids (`0xb69`, `0x12c0`, `0xbb0`, …); those values are CREAT ids, not world ids.

### Exe tables (`THOTD.exe`)

PE: image base `0x400000`. DGROUP starts at VA `0x5A0000` (file offset `0x187400`). File offset = `0x187400 + (VA − 0x5A0000)`.

| VA | Layout | Role |
|----|--------|------|
| `DAT_005d46ac` | 94 × `0x4C` | Per-type stats (model, hit radius, scale, default motion) |
| `DAT_005efa58` | 94 × `s32` | Bone count |
| `DAT_005ef8e0` | 94 × pointer | Skeleton root (bone tree) |
| `DAT_005efbd0` | 674 × pointer | `MO_*` clip bases — [motion.md](motion.md) |
| `DAT_005f0658` | 674 × `s32` | Clip frame counts |
| `DAT_005f1258` | 674 × pointer | `MO_*` motion name strings |

**94 skeleton-backed types are not every actor.** `BindSpawnEventType` (`FUN_0047b2c4`) / `ApplyCreatureTypeStats` (`FUN_00483ad0`) index the `0x4C` stride with no visible 94-entry bounds check. Stage 1 has ten slot-128 occurrences with selector **107**; that row has model 0, radius 0, scale 1 and is a controller/special type, not permission to walk past the 94-entry skeleton arrays. Thirteen of the 94 trees also reference a CREAT id absent from both banks — some handlers reject selectors, some nodes are conditional. Keep the declared bone stride even when a walk finds fewer nodes (types 41/42/43/44/46/66 have 12 reachable nodes on an 18-bone stride; type 91 has 16/18).

Ghidra often reads the 16-bit type at `entity+0xd4` as `*(int*)(entity+0xd2) >> 16`. Motion id is the 16-bit at `+0xd8` (`>> 16` of `+0xd6`). Do not model `+0xd4` and that overlapping load as two independent simultaneous fields without tracing lifetimes.

#### Type row (`0x4C`)

```
offset  size  field
0x00    4     u32 modelId     root / display id (may be absent from CREAT; bones have the real ids)
0x14    4     f32 hitRadius   copied to entity+0x98; gun sphere in `SphereHitTest` (`FUN_00414aac`) (not combat HP)
0x28    4     f32 scale
0x2C    4     f32 yOffset
0x30    4     f32 (extra)
0x44    4     u32 defaultMotion   index into DAT_005f1258
```

`ApplyCreatureTypeStats` (`FUN_00483ad0`) copies `+0x00` → `entity+0x5c` (model id), `+0x14` → `+0x98` (hit-sphere radius), `+0x28` → `+0x9c` (scale). Combat HP is the ENTB u16 at record `+0x22` → `entity+0x78` — [enemy-systems.md](enemy-systems.md).

`defaultMotion` is often a **shared idle** (`MO_b3_pose_2`, `MO_b1_atk_a`), not the species walk set. Species clips (`MO_ebitb_*`, `MO_k_*`, …) are selected at runtime by AI, so type index → Ebitan/Kageo is **not** a single column.

#### Skeleton node (`DAT_005ef8e0[type]`)

```
offset  size  field
0x00    4     u32 meshId      CREAT id; 0 = dummy root
0x04    12    f32 xyz         local bone offset
0x14    4     bone index
0x18    4     u32 childCount  (0..8)
0x1C    4×N   child pointers
```

Walk only `+0x00` as the mesh id and `+0x1C` for `childCount` children. Treating every word as an id pulls in unrelated meshes (including id 0 → page 589). `+0x14` indexes the per-bone `s16` triplet in a `MO_*` frame ([motion.md](motion.md)).

Union of those mesh ids, then OBJ `usemtl page_N`, is the type’s skin set.

### Motion names (species roster)

674 strings at `DAT_005f1258`. Prefix is the developer name; Sega English names in the right column are inferred.

| Prefix | Clips | Index range (main run) | Likely character |
|--------|------:|------------------------|------------------|
| `z` | 196 | 467–650 | generic zombie |
| `k` | 80 | 211–288 | **Kageo** |
| `p` | 53 | 339–384 | player |
| `saru` | 49 | 403–451 | **Saruzou** |
| `ebitb` | 39 | 138–176 | **Ebitan** |
| `boss4` | 32 | 66–97 | **Magician** (stage 4) |
| `b3` | 28 | 38–65 | **Hermit** (`tojo_ana` = emerge from a hole) |
| `b1` | 23 | 0–21 | **Chariot** (`yoroi` = armor) |
| `dog` / `inu` | 23 | 100–210 | **Kenfis** |
| `dr` | 20 | 118–137 | **Drake** (knife/throw) |
| `s` | 18 | 385–402 | scientist / civilian (`help`) |
| `b2` | 16 | 22–37 | **Hangedman** (`fly` / `glider` / `bat`) |
| `mol` | 13 | 300–312 | **Murrer** (hole-emerge) |
| `gman` | 12 | 188–199 | **Goldman** |
| `kyu` / `kyuri` | 12 | 289–299 | **Cyril** |
| `frog` | 11 | 177–187 | **Bouere** |
| `tom` | 8 | 459–466 | **Thomas Rogan** |
| `hiru` | 6 | 200–205 | **Name** (leech / slug) |
| `mrg` | 4 | 332–335 | **G** |
| `onozonbia` | 3 | 336–338 | Cyril axe walk |
| `taraba` | 3 | 453–455 | **Taran** (crab) |
| `tekk` | 3 | 456–458 | **Robert** (iron arm) |

`O_*.rbh` names (`O_ST4BO1`, `O_ENEMY1`, `O_INU`, `O_FROG2`) are mixer labels (`sound\O_%s.rbh`), not CREAT or page keys.

### VVTP page bands

The creature `.vmc` is a **whole-game atlas**. Page ids (header `pageId`, same numbers as `-p` PNG names):

| Pages | Used by |
|------:|---------|
| 1–337 | `spr.rbh` frames |
| 338–511 | unused gap (174 missing ids in `B_RED`) |
| 512–546 | `world*.rbh` |
| **547–595** | **CREAT mesh skins** |

Page 18 is a sprite page, not a creature skin.

### Official roster → engine types

Sega names and A–G codes from the Saturn manual / Curien report. Engine types from `DAT_005d46ac` + CREAT skeleton pages + slot-128 `spawnEventId` (that field *is* the type for `BindSpawnEventType` (`FUN_0047b2c4`)). Default motions are often a shared idle (`MO_b3_pose_2`); species clips live in the 674-name `MO_*` list.

| Sega | Name | Chapters | Type(s) | Conf. | Evidence |
|------|------|----------|---------|-------|----------|
| A-1 | **Sam** | 1–4 | **16**, 91 | high | Exe logs `ENGuard_BO_zonbiman` when type `== 0x10`; grey muscular page 556 |
| A-2 | Neil | 1–3 | 11? | medium | Stronger Sam; type 11 is scale 1.2 on the green-flesh + civilian mix |
| A-3 | **Cyril** | 1–3 | **18** | high | Grey suit + chest wound, radius 9, `MO_kyu_*` / `MO_onozonbia_*` |
| B-1 / B-2 | Kageo / Bourbon | 1, 3 | 3, 4 | medium | Green rotting page 550; `MO_k_*` is the largest non-generic clip set |
| B-3 / B-4 | Ebitan a / b | 1–3 | 87 | medium | Green cracked 575/583; `MO_ebitb_*` and `MO_d_sakaoli` (hang) |
| C-1 / C-2 | Samson / Bentley | 1–4 | 71, 73 | medium | Stony muscular + belt on page 578 |
| C-3 | Burner | 3 | 74? | low | Blowtorch Samson; red muscular page 580 |
| D-1 | Simon | 1–2 | 82 | medium | Grey muscular grinning; shoulder-tackle type |
| D-2 | Gilmore | 2, 4 | — | — | Sledgehammer; not pinned |
| D-3 | Harris | 3–4 | — | — | Ball and chain; not pinned |
| D-4 | Robert | 3–4 | — | — | Metal arm; `MO_tekk_*` |
| E-1 | Rubin | 2 | — | — | Rolls / claws; not pinned |
| E-2 | **Drake** | 2 | **83**, 84 | high | Default motion `MO_dr_l_nage`; grinning one-eyed page 574 |
| E-3 | Moody | 3–4 | — | — | Iron claw / wall; `MO_mood*` / `MO_monkabe*` |
| E-4 | Parlor | 3–4 | 84? | low | Drake-like; `MO_dr_knif_chaku` |
| F-1 | Kenfis | 1 | 75? | low | Hellhound; `MO_ddogg*` / `MO_inu*` |
| F-2 | **Saruzou** | 1 | **1** | high | Primate pages 582/585, scale 0.5; 68 Stage 01 slot-128 spawns |
| F-3 | Bouere | 1 | — | — | Water frog; `MO_frog_*` (not `MO_dr_*`) |
| F-4 | **Devilon** | 1, 2, 4 | **76** | high | Blue hexagonal demon, pages 557–558 |
| G-1 | Murrer | 1–2 | 60 / 75? | low | Hole-emerge; `MO_mol_hole_*` |
| G-2 | Name | 1 | 60 / 75? | low | Wall slug; `MO_hiru_*` |
| G-3 | Taran | 3 | — | — | Crawler; `MO_taraba_*` |
| other | kage / pdolob / neopetit / taalu | 1–3 | 86? | low | Unnamed in 1996 print; `MO_zonbi1/2/3` are background walkers |
| Type 27 | **Chariot** | 1, 4 | **35**, **36** | high | Armor pages 547–549; slot 37 writes type 35 (HP 480) |
| Type 041 | **Hangedman** | 1–2 | **6**, 7, 8, 38 | high | Bat-wing page 554; slots 35/36 hardcode type 6 |
| Type 6803 | **Hermit** | 3 | **64** | high | 28 bones; six-hole mask pages 561/562/591; `MO_b3_tojo_ana` |
| Type 0 | **Magician** | 4 | **51** | high | `MO_boss4_*`; grey bald page 569; radius 12 |
| NPC | **Goldman** | story | **2** | high | Brown coat, glasses, DBR badge; scale 1.4 |
| NPC | Scientists / civilians | 1–4 | 17, 19–28, 49, 65, 89 | high | Lab-coat page 551 cluster; civilian 552+568 |
| NPC | Rogan / G / Sophie / Curien | story | — | — | Single CREAT meshes from `DAT_005ce368` (Sophie = id **7482**, pages 559+560, scale 1.2). Clips `MO_p_*`, `MO_tom_*`, `MO_mrg_*`, `MO_synd_demo` exist but have no type-row skeleton. |

`DAT_005ce368` slot 5 ("Researcher", CREAT id **7483**, scale 0.8) is **not a character mesh**. Its 17 verts split into two mirrored clusters, and the UV patch on page 566 is a small ring (a lens), not skin. The name in the story-NPC table does not mean the CREAT id is a full body.

### Type → page (all 94)

Skeleton walk → unique pages, then checked against `B_RED` PNGs. Hit radius / scale from `DAT_005d46ac`. Bone count from `DAT_005efa58`. Radius is the gun hit-sphere, not combat HP.

High-confidence rows:

| Type | Pages | Bones | Radius | Scale | Identification |
|-----:|-------|------:|---:|------:|----------------|
| 1 | 582, 585 | 16 | 8 | 0.5 | **Saruzou** |
| 2 | 560, 565, 571 | 20 | 5 | 1.4 | **Goldman** |
| 6 | 554 | 10 | 7 | 1.0 | **Hangedman** (slots 35/36 write this; default motion is Hermit `MO_b3_atk_l`, posed ref is motion 22) |
| 16 | 556 | 18 | 2 | 1.5 | **Sam** (`zonbiman`) |
| 17, 19–21, 24, 49 | 551 | 18–20 | ~5–8 | 1.0 | DBR lab-coat scientists |
| 18 | 563 | 16 | 9 | 1.0 | **Cyril** |
| 35 / 36 | 35: 547–549, 576; 36: 548–549 | 18 | 1.8 / 8 | 0.5 / 1.0 | **Chariot** |
| 51 | 569 | 18 | 12 | 1.0 | **Magician** |
| 64 | 561, 562, 591 | **28** | 2.6 | 1.0 | **Hermit** |
| 76 | 557, 558 | 16 | 2.8 | 1.2 | **Devilon** |
| 83 | 574 | 18 | 2.5 | 1.0 | **Drake** (`MO_dr_l_nage`) |

Hangedman's skeleton is a chain, not a biped: root part `1078` branches into a 5-link run (`1080→1082→1084→1086→1088`, each offset `+1.30` in local Z) plus a shorter branch (`1076→1092→1090`). Do not map type-6 bone ids onto arms, legs, or a head without checking each mesh. Species clips are `MO_b2_*`; the type-row default `MO_b3_atk_l` is a shared Hermit idle.

Medium / notable variants: 3–4 Kageo family (page 550); 7 Hangedman body (554+576); 8 Hangedman-sized Stage 02 (radius 12.5); 11 Neil/swamp mix; 23/25–27 civilians (552+568); 38 flying/Hangedman (558+569); 71/73 C-type (578); 82 Simon (573); 84 Drake/Parlor (`MO_dr_knif_chaku`); 87 Ebitan (575+583); 91 Sam variant (556+576).

Type 0 is an all-zero template (bones still 21). Types 5, 10, 39, 44, 52, 66, 75 have **no** VVTP pages on the skeleton walk — 75 (9 bones, scale 0.5) and 60 (scale 0.25) are the best animal/insect candidates.

There are 94 types. Many are clothing/damage/LOD variants that share a page set. Gilmore, Harris, Robert, Rubin, Moody, Kenfis, Bouere, Murrer, Name, Taran, and Curien still have motion sets but no unique type-row default. Sophie / Rogan / G story meshes are the character table at `DAT_005ce368` (not the 94-row type table): slot 4 is Sophie, CREAT id 7482.

### How to reproduce

`scripts/creature_map.py` reads `THOTD.exe` and the retail files under `assets/` (`CREAT1.RBH`, `CREAT2.rbh`, `evtALL.rbh`, `B_RED.VMC`). Skin pages are the CREAT `texPageId`s on the skeleton walk, so a prior `-m` / `-p` / `-e` run is not required.

Exe: `HOTD_EXE`, else `hotd-exe/THOTD.exe`, else `../typescript/hotd-decompress/hotd-exe/THOTD.exe`. Assets: `HOTD_ASSETS` or `assets/`.

1. `uv run python scripts/creature_map.py` — 94 type rows, skeleton mesh ids, CREAT page sets, spawn-fn table (`DAT_005d8118`), and evtALL usage. Writes `decompressed_assets/exe_tables/creature-map.json`.
2. `uv run python scripts/creature_map.py clusters` — group types by page set; histogram `spawnEventId`; list callers of `ApplyCreatureTypeStats` (`FUN_00483ad0`). Writes `creature-clusters.json`.
3. `uv run python scripts/creature_map.py more` — type rows 94–127 and the slot-128 prolog.
4. `uv run python scripts/creature_map.py hp` — spawns with `unk22 >= 10`, Stage 03/04 slot usage, slot 128 by `spawnEventId`.
5. `sample_motion_frame` in `src/hotd_decompress/motion.py` — one `MO_*` frame (Hangedman reference: motion 22, frame 0, 10 bones). See [motion.md](motion.md).

To join a type to a skin by hand: walk `DAT_005ef8e0[type]`, collect `meshId`s, look up that CREAT node's `usemtl page_N`.

JSON from the runner lands under `decompressed_assets/exe_tables/` (`creature-map.json`, `creature-clusters.json`). Gitignored, not a CLI output.

---

## Motion clips (`THOTD.exe`)

Creature animation is **not** a PIFF payload. The 674 `MO_*` clips live in `THOTD.exe` DGROUP: a name, a frame count, and a packed angle stream per bone. Mesh parts stay in `CREAT*.rbh`; bind-pose trees stay in the type table ([creatures.md](creatures.md)). This note is the clip bytes.

This note is **not** a CLI flag. `src/hotd_decompress/motion.py` samples one integer frame. It does not walk the skeleton or submit meshes. Decomp: `SampleSkeleton` (`FUN_004776c8`), `PlayClipSkeleton` (`FUN_00476b70`) / `ApplyFrameBoneRotates` (`FUN_00478448`), `CopyBoneAngleTriplets` (`FUN_00478324`).

PE map is the same as [creatures.md](creatures.md): image base `0x400000`, DGROUP VA `0x5A0000` (file `0x187400`).

### Tables

| VA | Layout | Role |
|----|--------|------|
| `DAT_005efbd0` | 674 × pointer | Clip base (first frame) |
| `DAT_005f0658` | 674 × `s32` | Frame count |
| `DAT_005f1258` | 674 × pointer | `MO_*` name strings |

Indexed by the 16-bit motion id at `entity+0xd8` (`>> 16` of `+0xd6`). Type-row `defaultMotion` (`DAT_005d46ac+0x44`) is often a **shared idle**, not the species walk set — [creatures.md](creatures.md). Type 6 (Hangedman) stores `MO_b3_atk_l` (Hermit); Hangedman clips are `MO_b2_*`. The posed reference frame is motion **22** (`MO_b2_base`), frame **0**.

Bone count for the stride comes from `DAT_005efa58[type]`, not from the clip.

### Frame layout

```
stride = (boneCount * 6 + 0x0F) & ~3
```

Same expression in `SampleSkeleton` (`FUN_004776c8`) / `CopyMotionFrame` (`FUN_004784d4`) (`iVar2 * 6 + 0xfU & 0xfffffffc`). Frame `f` starts at `clipBase + f * stride`.

```
offset  size  field
0x00    12    f32 x, y, z     root header (root translation / blend; often unused for display)
0x0C    6×N   per bone        s16 ax0, ax1, ax2
…       pad                   up to stride
```

Per-bone shorts are in **clip order 0..boneCount−1**. The skeleton node’s `+0x14` bone index selects the triplet (`ApplyFrameBoneRotates` (`FUN_00478448`): `frame+0x0C + boneIndex*6`). Dummy roots (`meshId == 0`) still have an index.

Angles are **16-bit full-circle** (`65536 = 360°`). The exe looks up sin/cos in `DAT_005697b0` (index `angle >> 4`).

### Playback (`PlayClipSkeleton` / `FUN_00476b70`)

Per bone, after a matrix push:

1. Translate local offset with **Z negated**: `MatrixTranslate(x, y, -z)` (`FUN_00474ecc`) (`WalkSkeletonNode` (`FUN_00477ec4`) does the same from the skeleton node).
2. Rotate, in this order, from the three shorts:

| Call | Axis | Clip short |
|------|------|------------|
| `MatrixRotateZ(-ax2)` (`FUN_004751f4`) | local **Z** | third `s16` |
| `MatrixRotateY(ax1)` (`FUN_004750ec`) | local **Y** | second `s16` |
| `MatrixRotateX(ax0)` (`FUN_00475380`) | local **X** | first `s16` |

That is `Rz(-ax2) · Ry(ax1) · Rx(ax0)` on the current 3×4. Ghidra comments that swapped these three axes are wrong; the matrix updates match Z / Y / X as named here.

The 3×4 is row-major 3×3 at `[0..8]`, translation at `[9,10,11]` (`DAT_012e27f0`, 12 floats). Then the bone’s CREAT mesh is submitted (`EnqueueOpaqueIfLive` (`FUN_0043d7f8`)) and children are walked.

`SampleSkeleton` (`FUN_004776c8`) can blend two frames (`InterpolateBoneKeyframes` (`FUN_004775f4`) per bone) when transition bits at `entity+0x3ce` are set. `sample_motion_frame` reads **one integer frame** (no blend).

### What the tool does

| Module | Role |
|--------|------|
| `src/hotd_decompress/creature_map.py` | Type rows + bind-pose mesh ids (`meshId`, children) |
| `src/hotd_decompress/motion.py` | Name / frame count / clip bytes → `ax0, ax1, ax2` on each bone |

`sample_motion_frame(exe_bytes, motion_index, frame, bone_count)` clamps `frame` into `0 .. frameCount-1`.

### How to reproduce

1. `-m` on `CREAT1.RBH` / `CREAT2.rbh` and `-p` on `B_RED.VMC` — same as [creatures.md](creatures.md).
2. Call `sample_motion_frame` with motion **22**, frame **0**, and type 6’s bone count (`DAT_005efa58[6]` = 10).

Prefix roster (`z`, `k`, `b2`, …) stays in [creatures.md](creatures.md). Spawn / AI that picks a motion id: [enemy-systems.md](enemy-systems.md). Draw submit after the bone matrix: [game-rendering.md](game-rendering.md).

---

## Sprites (`spr.rbh`)

`assets/sprite/spr.rbh` is **sprite metadata**: UV rectangles and VVTP page ids. It does not contain pixels. Draw with a `.vmc` bank (`pageId` → `page_XXXX.png`).

Decomp: sprite records are reached via `DAT_005ce544` (`GetSpriteRecord` (`FUN_004430a4`) getter, `StampScrollSprite` (`FUN_004434b0`) scroll-sprite helper).

### Container

RBHF, typically RBHH `flags=2`, one `BODY`, one `RELC`. BODY0 is a pointer table then packed `SpriteRecord`s.

Retail `spr.rbh` has **1640** slots (`firstPtr / 4`).

### Pointer table

```
u32 spritePtr[count]
```

`count = firstPtr / 4`. The first record begins immediately after the table (at `firstPtr`). A `0` pointer is an empty slot (this tool skips it). Pointers are BODY-relative.

### SpriteRecord

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

### Frame (16 bytes)

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

### What this is not

- Not a texture atlas file — pixels are in `.vmc`.
- Not a mesh — no vertices.
- PNG export (`-p`) on `spr.rbh` will not produce sprite images; run `-p` on a `.vmc` and `-s` on `spr.rbh`, then composite using `pageId` + UV rects.

### How the tool works

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

---

## Events (`evtALL.rbh`)

`assets/evt/allstage/evtALL.rbh` is a nested pointer graph of stage → scene → event **script streams**. One BODY (`flags=2`), typically with a `RELC`.

Opcodes, spawn records, and `CCTB` → `camALL` binds: [events-detailed.md](events-detailed.md). How those scripts play as in-engine cutscenes (no FMV): [cutscenes.md](cutscenes.md).

Decomp: root table `DAT_00d5a5d0`. `CountStagesForSelectUi` (`FUN_00422808`) counts scenes per stage for the debug UI (stops at the first `-1` / `0xFFFFFFFF`). Gameplay bind is `BindEventPlayhead` (`0x4c0d3c`); the tick at `TickEventVm` (`0x4c0db0`) dispatches `handlers[opcode]` at `0x005eeac0`.

### Container

```
PIFF RBHF
  RBHH   one row, flags=2
  BODY   pointer graph + opcode streams + spawn records
  RELC   pointer fields in that BODY
```

Already uncompressed in the files this tool was checked against.

### Graph

```
BODY0
  stagePtrs[]          length = firstPtr / 4; 0xFFFFFFFF slots allowed
    → scenePtrs[]      terminated by 0xFFFFFFFF
      → sectionPtrs[]  terminated by 0xFFFFFFFF
        → opcode stream
```

Retail: 9 stage slots (slot 7 empty, slot 8 extra), 66 scenes, 522 events.

#### Root (stages)

Unlike a simple null-terminated list, the **root may contain `0xFFFFFFFF` in the middle** (unused stage indices). Length is implied by the first child offset:

```
stageCount = firstChildOffset / 4
```

A null slot is an empty stage (no scenes). Non-null slots are BODY offsets of scene-pointer tables.

Exe debug names (`s_Stage_01_005ce918`): Stage 01, 02, 03, 04, tt, adv, end for slots 0–6.

#### Scenes

At each stage pointer: a list of `u32` scene offsets, stopped by `0xFFFFFFFF`. Labels from `PTR_s_Scene_000_005ceba4` (e.g. `Scene 000`, `Scene 02A`, `Scene XX`).

#### Sections (events)

At each scene pointer: a list of `u32` event offsets, stopped by `0xFFFFFFFF`. EventNo is this index.

Each event is a `u32` opcode stream. `0xFFFFFFFF` ends an `ENTB`-style pointer list **and**, at an instruction boundary, the event itself. Spawn records often sit in the bytes after the script until the next section. Do **not** treat the first `0xFFFFFFFF` as the event end — that was the old dump’s truncation.

Camera rails live in a separate bank (`camALL.rbh`). A `CCTB` job `0x40` names a group index + frame window — see [events-detailed.md](events-detailed.md) and [cameras.md](cameras.md).

### Null vs zero

Event tables use **`0xFFFFFFFF` as null / terminator**. Do not confuse with world mesh id tables, which use `0` to end a node-pointer list.

### How the tool works

```text
uv run hotd-decompress -e|--evt <file.rbh> [outdir]
```

`convert_events_to_json` (`src/hotd_decompress/event.py`) uses `load_rbh` (no PACK expand). Retail `evtALL.rbh` is already BODY.

1. Require one BODY whose first pointer looks like a root table (`firstPtr ≤ 0x400`, 4-aligned, in-range).
2. Read `firstPtr/4` stage slots, keeping mid-list `0xFFFFFFFF`.
3. For each live stage: `read_pointer_table` for scenes (stop at `0xFFFFFFFF`).
4. Collect every section offset; bound each by the next offset in BODY order.
5. Walk opcodes (names from exe `0x5a3a00`). Deref `ENTB*` spawn records and `CCTB` job `0x40` rail binds.
6. Write `events.json`. Default dir: `decompressed_assets/<stem>_evt/`.

Stdout: stage count, scene count, op / spawn / rail-bind counts, output path.

JSON shape:

```json
{
  "source": "…",
  "stageCount": 9,
  "opCount": 7660,
  "spawnCount": 1653,
  "railBindCount": 993,
  "stages": [
    {
      "index": 0,
      "name": "Stage 01",
      "offset": 36,
      "scenes": [
        {
          "index": 0,
          "name": "Scene 000",
          "offset": 304,
          "sections": [
            {
              "offset": 328,
              "words": [93],
              "ops": [{ "offset": 328, "op": 93, "name": "NEXTEV", "args": [] }]
            },
            {
              "offset": 332,
              "words": [16, 90, 2],
              "ops": [
                { "offset": 332, "op": 16, "name": "SCNINIT", "args": [] },
                { "offset": 336, "op": 90, "name": "SNDON", "args": [2] }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

`ops[].spawns` holds deref’d `ENTB*` records (`typeId`, XYZ floats, `rx`/`ry`/`rz` integer angle words, `spawnEventId`, …). `ops[].camera` on `CCTB` job `0x40` has `camGroup` / `startFrame` / `endFrame` / `flags` indexing `camALL.rbh`. Empty root slots appear as `"offset": null, "scenes": []`. The file is `jsonutil.write_json`: whole floats such as spawn XYZ print as `n.0`. Angle words print as integers.

---

## Events in detail (VM, opcodes, spawns, cameras)

Container and pointer graph: [events.md](events.md). Camera rails: [cameras.md](cameras.md). How a sequence plays (no FMV): [cutscenes.md](cutscenes.md).

This note is the **bytecode** inside each section: opcode names from `THOTD.exe`, spawn records, and how `CCTB` names a `camALL.rbh` group. Retail dump checked: 9 stage slots, 66 scenes, 522 events, 7660 ops, 1653 spawns, 993 rail binds.

### Runtime (`THOTD.exe`)

#### Load

`LoadStageAssets` (`FUN_00418aa0`) requests `evt\allstage\evtall.rbh`. `DAT_00d5a5d0 = *(handle + 4)` is the BODY base.

Packed playhead bytes:

| Address | Role |
|---------|------|
| `DAT_00da0cf4` | StageNo |
| `DAT_00da0cf3` | SceneNo |
| `DAT_00da0cf0` | EventNo (section index) |
| `DAT_00da0ab8` | PC (pointer into BODY) |

Bind (`BindEventPlayhead` (`0x4c0d3c`)):

```
PC = stages[StageNo][SceneNo][EventNo]
```

Debug UI names at `s_Stage_01_005ce918` / `PTR_s_Scene_000_005ceba4`:

| Slot | Name | Scenes |
|------|------|--------|
| 0 | Stage 01 | 20 (`Scene 000`…`003`, then `01`–`16`) |
| 1 | Stage 02 | 16 |
| 2 | Stage 03 | 8 |
| 3 | Stage 04 | 5 (`00`, `01`, `02`, `02A`, `03`) |
| 4 | Stage tt | 2 (`XX`, `00`) |
| 5 | Stage adv | 1 |
| 6 | Stage end | 8 |
| 7 | *(null)* | 0 |
| 8 | extra (no UI label) | 6 |

`CountStagesForSelectUi` (`FUN_00422808`) (stage-select) counts until the **first** `0xFFFFFFFF`, so it only sees slots 0–6. Gameplay indexes by StageNo directly; slot 8 is reachable if that byte is set.

#### Tick

`TickEventVm` (`0x4c0db0`): `opcode = *PC`; `call handlers[opcode]` at `DAT_005eeac0`. Names sit in DGROUP at `0x5a3a00` (`0x00 : nop` … `0x5d : NEXTEV`).

`DAT_00da0a98` is the yield flag. A wait op sets it and returns; the next frame retries the same opcode until the condition holds, then advances PC.

`NEXTEV` (`0x4c1948`) increments EventNo. If that slot is `-1`, a branch table at `0x5d3420` picks the next scene (fixed, indexed, or +1) and restarts at EventNo 1. If the scene pointer is `-1`, the stage is done.

EventNo is the **section index**. It is not the old JSON `eventId` field (that was a one-word opcode, usually `NEXTEV` / `CLTB` / `KGTB`).

A different id lives on spawned entities at `+0xd4` (from the spawn record’s `+0x24` byte). Enemy/prop helpers (`EnemyHelperBySpawnEventId` (`FUN_004812e4`), `SpawnSecondaryWave` (`FUN_00482bf8`)) switch on that.

### Stream layout

Each section is a `u32` opcode stream. `0xFFFFFFFF` ends an `ENTB`-style list **and**, as a word at an instruction boundary, the event itself.

The previous dump stopped at the first `0xFFFFFFFF`, which truncated most events after the first spawn list. The decoder now bounds each section by the next section start in BODY order and walks opcodes, treating a non-opcode word as trailing spawn-record bytes (not script).

Most immediates are `opcode + one u32` (PC += 8). `WAIT_CAMJOB` / `SCNINIT` / `NEXTEV` / `WAIT` take no extra word. Lists consume pointers until `0xFFFFFFFF`.

### Opcode table

Handler `EventVmNop` (`LAB_00471658`) is idle (does not advance PC). Those slots are **nop** in the exe strings and do not appear as real script ops. The tool stops if it hits an unknown word (spawn payload / padding).

| Op | Name | Encoding | Role |
|----|------|----------|------|
| `0x01`–`0x04` | `ET1PE`…`ET1P3` | list | 1P-gated spawn table |
| `0x05`–`0x08` | `ET2PE`…`ET2P3` | list | 2P-gated spawn table |
| `0x09` | `ENTBE` | list | Spawn (extended record) |
| `0x0a` | `ENTB` | list | Spawn (full record) |
| `0x0b` | `ENTB2` | list | Spawn (short record) |
| `0x0c` | `ENTB3` | list | Spawn (full + extra bytes) |
| `0x0d` | `SKPETO` | +1 | Skip rest of list if GMTAD ≥ arg |
| `0x0e` | `SKPETU` | +1 | Skip if GMTAD < arg |
| `0x0f` | `SKIP` | +1 | Skip-flag / branch helper |
| `0x10` | `SCNINIT` | 0 | Reset scene (camera slots, scores) |
| `0x14` | `BGTB` | +1 | Byte flag `DAT_00da0cf7` |
| `0x1a` | `EV3JP1` | +2 | Jump if item flag set (`PC = arg1` is a BODY offset at runtime) |
| `0x20` | `GMTMF` | +1 | Set global mode |
| `0x21` | `GMTAD` | +1 | Add to `DAT_00da0b34` |
| `0x22` | `CLRGFST` | 0 | Clear a gameplay flag bit |
| `0x28` | `WLTB` | +1 ptr | Load 6 floats (world/light) |
| `0x32` | `CLTB` | list | Capture id list (`DAT_00da0aa4`) |
| `0x33` | `KGTB` | list | Capture id list (`DAT_00da0ac8`) |
| `0x3c` | `CCTB` | variable | Queue camera job (see below) |
| `0x41` | `BSFT` | +1 | Blood-shift word |
| `0x42` | `CAMDR2` | +1 | Camera director (waits) |
| `0x43` | `PYPMD` | +1 | Player py/pm mode |
| `0x44` | `SHDWLT` | +2 | Shadow/light |
| `0x45` | `CGMFNSH` | +1 | Chapter-finish flag |
| `0x46` | `SKYKD` | +1 | Sky kind |
| `0x47` | `SKYTB` | +1 | Sky table |
| `0x48` | `FKRTB` | +1 ptr | Floor height float → `DAT_00da0b48` |
| `0x49` | `CHGSM` | +1 | Change system mode |
| `0x4a` | `NCHGCF` | +1 | Don’t-change-camera flag |
| `0x4b` | `CAMDR` | +1 | Camera director |
| `0x4c` | `GGCOL` | +2 | Skip 2 args (colour) |
| `0x4d` | `GGSET` | +1 | Skip 1 arg |
| `0x4e` | `REMFRM` | +1 | Remaining camera frames |
| `0x4f` | `TEXCHG` | +1 | Texture change (same size as `GGSET`) |
| `0x50` | `WAIT_ENNUM` | +1 | Wait until enemy count ≥ arg |
| `0x51` | `WAIT_FRM` | +1 | Wait N frames |
| `0x52` | `WAIT_ITEM` | +1 | Wait for item flag |
| `0x53` | `WAIT_CAMJOB` | 0 | Wait until camera ring drains |
| `0x54` | `WAIT_CAMFRM` | +1 | Wait until rail `t` ≥ arg (0 = remaining) |
| `0x55` | `WAIT_ENALV` | +1 | Wait until enemies-alive ≤ arg |
| `0x57` | `RNWCJ` | +2 | Renew camera job / bump wait counter (`arg1` often `0xFFFFFFFF`) |
| `0x58` | `ITEMON` | +1 | Enable item flag at `DAT_00d9f618[arg]` |
| `0x5a` | `SNDON` | +1 | Play a sound-request row (`PlayDigitalSfx` (`FUN_00412000`)). Arg is a `DAT_005cbda8` index, not a filename — [cutscene-audio.md](cutscene-audio.md) |
| `0x5b` | `ATCMD` | +1 | Attract-mode command |
| `0x5c` | `WAIT` | 0 | Yield forever (does not advance PC) |
| `0x5d` | `NEXTEV` | 0 | Next event / scene |

Retail histogram (top): `CCTB` 1718, `WAIT_CAMJOB` 728, `NEXTEV` 521, `WAIT_CAMFRM` 460, `CAMDR` 374, `WAIT_ENALV` 346, `ENTB` 334, `GGSET` 322, `SNDON` 272.

### Spawn records (`ENTB*`)

List operands are **BODY offsets**, not inline coordinates. `ENTB` (`EvtOpEntb` (`0x46e5c8`)) reads each pointer, looks up `DAT_005d8118[typeId]` (spawn function), and copies the record into a new entity (`AllocEntity` (`FUN_0043e400`)).

#### `ENTB` / `ET*` / `ENTB3` (0x28 bytes)

```
offset  size  field
0x00    4     u32 typeId     index into DAT_005d8118
0x04    4     u32 flags      OR 1 → entity+0x60
0x08    4     f32 x
0x0C    4     f32 y
0x10    4     f32 z
0x14    4     u32 rx         integer full-circle angle word → entity+0x34
0x18    4     u32 ry         integer full-circle angle word → entity+0x38
0x1C    4     u32 rz         integer full-circle angle word → entity+0x3C
0x20    1     posMode        low 2 bits: 0 = raw XYZ, 1/2 = transform
0x22    2     u16 combat HP  copied to entity+0x7a **and** +0x78 (drained on hit)
0x24    1     spawnEventId   → entity+0xd4
0x25    1     u8             → entity+0x6c
0x26    1     u8             ENTB3 → entity+0x328
0x27    1     u8             ENTB3 → entity+0x32c
```

`typeId` is a spawn-function index (**136** live slots in this `THOTD.exe`, max 256), **not** the 94-row creature table in [creatures.md](creatures.md). `spawnEventId` is the byte those creature helpers switch on.

XYZ are IEEE floats. **RX/RY/RZ are integer angle words**, not floats (`65536 = 360°`). `EvtOpEntb` (`FUN_0046e5c8`) at `0x46E749–0x46E758` copies the three dwords at record `+0x14/+0x18/+0x1C` directly to entity `+0x34/+0x38/+0x3C`. The corpus is dominated by full-circle values such as `0x4000` / `0x8000` / `0xC000`. Scene 002’s two slot-102 records use `(0, 0xD000, 0)` and `(0, 0x3000, 0)`. Exporting those words as `f32` yields ~`7.46e-41` / ~`1.72e-41`. `-e` keeps the integer bits.

This note is **bytecode decode**, not VM execution. The tool walks opcodes and writes JSON; it does not run `TickEventVm` (`FUN_004c0db0`). Zero `undecoded` words does not prove every payload byte was understood: the walker stops at an unsupported opcode and treats the rest as trailing spawn bytes.

#### `ENTB2` (8 bytes)

```
0x00  u32 typeId
0x04  u16 copied to entity+0x7a / +0x78
```

#### `ENTBE` (≥ 0x24 bytes)

Same XYZ floats and RX/RY/RZ integer angle words as `ENTB`, then `u16` at `+0x20`. The handler stores `record+0x24` at `entity+0x364` (extra payload pointer).

XYZ is stage space (same as world meshes / camera rails). Example from Stage 01 event 4: type 100 at `(17, -25, -1125)` and `(-30, -25, -1165)`, `spawnEventId` 19 and 17.

### `CCTB` → `camALL` groups

`CCTB` does not embed splines. It queues the current instruction onto a 16-slot ring (`DAT_00d9f1f0`). `DispatchCameraJob` (`FUN_0045f414`) reads `*(PC+4)` as a **camera job type** and dispatches `DAT_005d8418[job]`.

Word count including opcode:

```
n = ((job / 16) * 4 + 8) / 4
```

| Job | Words | Name in JSON | Payload after opcode+job |
|-----|-------|----------------|--------------------------|
| `0x10` | 3 | `flags` | 1 arg (bit flags) |
| `0x11` | 3 | `job11` | 1 arg |
| `0x12` | 3 | `callback` | 1 arg |
| `0x13` | 3 | `copyTable` | 1 arg |
| `0x14` | 3 | `countdown` | frames to wait |
| `0x15` | 3 | `camMode` | `DAT_00da0bd0` |
| `0x20` | 4 | `poseTable` | countdown + table index |
| `0x21` | 4 | `camMode2` | 2 args |
| `0x40` | 6 | `rail` | start, end, **camGroup**, flags |

Job `0x40` (`BindCameraRailJob` (`FUN_00460f88`) → `BindCameraRail` (`FUN_00460fd0`)) is the rail bind:

| Word | Copied to | Meaning |
|------|-----------|---------|
| start | `DAT_00d9ed04` / slot `+0x120` | Start frame (`−1` keeps current `t`) |
| end | `DAT_00d9ed08` / slot `+0x124` | End frame (tick while `t < end`) |
| camGroup | `DAT_00da0ca4` / slot `+0x128` | `camALL.rbh` group index 0–141 |
| flags | `DAT_00d9ed10` / slot `+0x12C` | Bind flags. The update at `0x461171` tests mask **4**. Mask **2** is common in rail data and is a different bit — do not collapse the two |

Retail: 993 `rail` binds, 117 distinct groups, indices 0–141 (the full `camALL` range). Typical pattern:

```
CCTB rail { start, end, camGroup, flags }
WAIT_CAMJOB
```

or `WAIT_CAMFRM` / `RNWCJ` when the script needs the remaining frame window (`DAT_00da0bf8`).

### Example (Stage 01, `Scene 000`, event 1)

```
SCNINIT
SNDON    2
SKYKD    0
SKYTB    2
SHDWLT   0xf000 0xd000
FKRTB    ptr → f32 -25
BGTB     1
CHGSM    5
ENTB2    spawn @ 0x548
WAIT_ITEM 248
CHGSM    5
NEXTEV
```

Event 4 later binds `camALL` group 0 at frames 741–770, spawns two type-100 enemies, then group 1 at 801–890.

### Example (Stage 01, `Scene 002` — gameplay corridor)

Scene-to-scene setup is event 0 (`SNDON 9` / `CHGSM 6` / `NEXTEV`). Events 1–2 are the corridor:

```
SCNINIT
FKRTB    ptr → floor Y
SKYTB    1
ENTB     typeId 102
CCTB rail g3 [0,80)
WAIT_CAMFRM 70 / RNWCJ
WAIT_ENALV 0
CAMDR    3
NEXTEV
```

Then another type-102 spawn, group 3 `[81,150)` with `WAIT_ENALV 0`, then a 9-frame exit `[151,160)`. Three rail binds. That is the `WAIT_ENALV`-after-rail pattern from [cutscenes.md](cutscenes.md). The two slot-102 records use angle words `(0, 0xD000, 0)` and `(0, 0x3000, 0)`.

### How the tool works

```text
uv run hotd-decompress -e|--evt <file.rbh> [outdir]
```

`convert_events_to_json` (`src/hotd_decompress/event.py`):

1. Same root/scene/section pointer walk as [events.md](events.md).
2. Collect every section offset; bound each by the next offset in BODY order (sections are not always sequential inside a scene).
3. Walk `u32` opcodes with the table above. List ops consume pointers until `0xFFFFFFFF`. `CCTB` size uses the job-type formula.
4. Deref `ENTB*` pointers into spawn records (XYZ floats, RX/RY/RZ integer angle words); deref `WLTB` / `FKRTB` pointers into floats.
5. Job `0x40` becomes `camera: { jobName: "rail", startFrame, endFrame, camGroup, flags }`.
6. Write `events.json`. Stdout also prints op / spawn / rail-bind counts.

JSON extras vs the raw tree: `name` on stages/scenes (from the exe strings), `ops[]` on each section, `spawns` / `camera` / `floats` on ops. `words` is the script slice only (internal list terminators kept; trailing spawn bytes omitted). The old one-word `eventId` field is gone — that word is `ops[0].name`. `jsonutil.write_json` prints whole floats as `n.0`.

---

## Cameras (`camALL.rbh`)

`assets/cam/allstage/camALL.rbh` is one bank of scripted on-rails **camera paths**. Each group is six Hermite scalar tracks: eye XYZ + look-at XYZ. The exe samples them at the current integer frame, aims the view, then plants the player on the stage floor under the camera.

Retail file checked: 142 groups, 852 tracks (always 6 per group). Already uncompressed (`BODY` + `RELC`).

Decomp / exe: `LoadStageAssets` (`FUN_00418aa0`) loads `cam\allstage\camall.rbh` into `DAT_00d5a5c8` (BODY pointer). `BindCameraRail` (`FUN_00460fd0`) binds a group + frame window. `TickCameraRail` (`FUN_004caa70`) ticks; `SampleCameraGroupTracks` (`FUN_00461980`) samples six tracks; `HermiteTrackLookup` (`FUN_00461858`) is the cubic Hermite lookup; `EyeLookAtToYawPitch` (`FUN_00461a30`) turns eye−look-at into yaw/pitch. Event VM + rail playback (title / attract / ending): [cutscenes.md](cutscenes.md).

### Container

Same outer shape as events: RBHF, one BODY (`flags=2`), pointer graph, usually one `RELC`.

```
PIFF RBHF
  RBHH   one row, flags=2
  BODY   pointer graph
  RELC   pointer fields in that BODY
```

### Graph

```
BODY0
  groupPtrs[N]     N = firstPtr / 4
    → trackPtrs[6]  first track sits immediately after the table
      → Track
```

Root slots that are `0xFFFFFFFF` are skipped. Group tables are dense: the first track begins immediately after the group’s pointer list, so the track count is implied by that gap (same “child sits right after the table” rule as sprite/event roots).

The exe always reads **six** pointers at group `+0,+4,+8,+0xC,+0x10,+0x14`. Retail `camALL.rbh` matches that (142 × 6). Generic RBH inspect (`read_pointer_table` until `0xFFFFFFFF` / out-of-BODY) can over-count by walking into key data — a track header `keyCount|channelId<<16` can look like an in-range pointer. Trust `-c` / `src/hotd_decompress/camera.py`, not the inspect entry count, for camera groups.

### Track

```
offset  size  field
0x00    2     u16 keyCount     power of two: 4, 8, 16, 32, or 64
0x02    2     u16 channelId    log2(keyCount), so 2..6 — not an axis id
0x04    …     Key[keyCount]
```

`HermiteTrackLookup` (`FUN_00461858`) uses the low u16 as the key count (binary search starts at `keyCount/2`) and the high u16 minus one as the search iteration count. On all 852 retail tracks, `channelId == log2(keyCount)`.

**Pose channels are track order**, not `channelId`:

| Slot | Written to | Role |
|------|------------|------|
| 0 | `DAT_00d9ed18` | Eye X |
| 1 | `DAT_00d9ed1c` | Eye Y (often held near −10 or 15) |
| 2 | `DAT_00d9ed20` | Eye Z |
| 3 | `DAT_00d9ed30` | Look-at X |
| 4 | `DAT_00d9ed34` | Look-at Y |
| 5 | `DAT_00d9ed38` | Look-at Z |

Values are stage-space floats (same space as world meshes). Y is height; X/Z run along the corridor.

### Key (16 bytes)

```
offset  size  field
0x00    4     f32 t          time in **frames** (may be fractional on disk)
0x04    4     f32 value
0x08    4     f32 slopeIn    incoming tangent (used as m1 of the span)
0x0C    4     f32 slopeOut   outgoing tangent (used as m0 of the next span)
```

Cubic Hermite between `keys[i-1]` and `keys[i]`: previous `slopeOut` + current `slopeIn`. Engine doubles at `0x005a2a0c` are `2.0`, `3.0`, `−2.0` (Hermite basis). The sampler converts the integer frame to float (`fild` / `FloatChop` (`FUN_00562400`) chop) before the lookup.

Retail spans: 60–2510 frames (mean ~573). Group 80 is the longest (2510). Most rails sit in the 240–960 band.

### Runtime (`THOTD.exe`)

#### Load

`LoadStageAssets` (`FUN_00418aa0`) (stage asset load) requests `cam\allstage\camall.rbh` via `LoadPiffRbh` (`FUN_005769c0`). `DAT_00d5a5c8 = *(handle + 4)` is the BODY base. `SampleCameraGroupTracks` (`FUN_00461980`) indexes `group = *(DAT_00d5a5c8 + groupIndex * 4)`.

#### Bind (event → rail)

Camera slots are 0x154 bytes at `DAT_00da01c0` (six slots). Event dispatch (`DispatchCameraJob` (`FUN_0045f414`)) copies a script record into slot 0; `BindCameraRail` (`FUN_00460fd0`) / `PromoteCameraSlotGlobals` (`FUN_004610b0`) promote those fields to the globals the tick uses:

| Slot offset | Copied to | Meaning |
|-------------|-----------|---------|
| +0x120 | `DAT_00d9ed04` | Start frame, or `−1` to keep current `t` |
| +0x124 | `DAT_00d9ed08` | End frame (tick while `t < end`) |
| +0x128 | `DAT_00da0ca4` | `camALL` group index (0–141) |
| +0x12C | `DAT_00d9ed10` | Flags. The bind-update at `0x461171` tests mask **4**. Mask **2** appears often in rail data and is a different bit — do not treat them as one bind-behaviour flag |
| +0x14C | — | Current `t` as float. When start is `−1`, `PromoteCameraSlotGlobals` (`FUN_004610b0`) at `0x4610AC` loads this word, converts to integer, **increments it**, and stores the global frame (`0x4610E3–0x4610F5`) |
| +0x60 / +0x78 | slot-local | Per-slot eye / look-at sample buffers |

Slot 0 is special: binding it also pokes the event-script state machine (`DAT_00da0ab0`). Remaining frames (`end − t`) live in `DAT_00da0bf8`.

Events and cameras stay in **separate files**. A `CCTB` job `0x40` names a group and a frame window; `evtALL.rbh` does not embed spline keys. Opcode layout: [events-detailed.md](events-detailed.md).

#### Tick

`TickCameraRail` (`FUN_004caa70`):

1. If `DAT_00d9ed04 < DAT_00d9ed08`, and the game is not paused (`DAT_00da0a80 == 0` and `DAT_00da0b5c ≠ 0`), increment the frame counter.
2. `EAX = DAT_00da0ca4` (group index); sample six tracks into `DAT_00d9ed18` (eye) and `DAT_00d9ed30` (look-at).
3. `EyeLookAtToYawPitch` (`FUN_00461a30`): direction = eye − look-at → fixed-point yaw/pitch (×16). Negate yaw, add `0x8000` to pitch, roll = 0.
4. `RaycastStageFloor` (`FUN_0048a15c`): raycast from `(eye.x, 32768, eye.z)` onto the stage mesh. Player XZ follows the camera; Y comes from the ground hit. Pitch copied to `DAT_00d9f048`.

Sibling `TickCameraRailPlantEye` (`FUN_004cab60`) does the same sample but copies eye XYZ into the player position (`DAT_00d9f038/03c/040`), with optional Y from `DAT_00da0b48` instead of the ground raycast.

#### Layers on top of the rail

These do **not** add tracks to `camALL.rbh`:

| System | Function | Behaviour |
|--------|----------|-----------|
| Six view slots | `BuildViewSlotMatrices` (`FUN_0045f140`) | Builds a view matrix per slot from `DAT_00da0220` (stride 0x154). `DAT_00da0bd0` is the live camera: 0 = gameplay (`GameplayCameraView` (`FUN_00461adc`)), 2 = title/alt (`TitleCameraView` (`FUN_00461b90`)). |
| 2P aim blend | `BlendTwoPlayerAim` (`FUN_004609e4`) | Averages P1/P2 entity points (`DAT_00da0044` / `0058` at +0x2DC) into `DAT_00da0c74`. Falls back to the rail look-at if neither gun entity is live. |
| Zoom / FOV | `UpdateCameraZoom` (`FUN_00461690`) | Compares camera-forward to that aim point. 16-bit zoom word in `DAT_00da0c04`, clamped to `0x10`–`0x40`. High half `0xFFFF` disables auto-zoom. |
| Shake | `ApplyCameraShake` (`FUN_004ca884`) | Decaying offset for 30 frames (`DAT_00d9ed5c`) into `DAT_00d9f038/03c/040` when `DAT_00d9ed54` is set. |
| Chase / panic | `StartChasePanicCamera` (`FUN_004bd4a8`) → `TickChasePanicCamera` (`FUN_004bd678`) | Separate entity state machine: ease aim toward the crosshair while path progress &lt; 1.0, then a timed wait and optional homing spawn. Hijacks the live camera entity. |
| Gun-aim jitter | `GunAimJitter` (`FUN_0049cad0`) | Same 6-track Hermite sampler on a **different** table, scaled into screen-space wobble by view quadrant. |

Projection scale at the camera object `+0x20` (X) and `+0x24` (Y) is what `ProjectVerticesWithClip` (`FUN_005792b0`) multiplies into screen X/Y. Those floats track live zoom from `UpdateCameraZoom` (`FUN_00461690`): the 16-bit word `DAT_00da0c04` is clamped to `0x10`–`0x40`, and `DAT_00da0c06` is an override. They are recomputed from the aim point (`BlendTwoPlayerAim` (`FUN_004609e4`)), which falls back to the rail look-at when no gun is live. They are not a stage FOV constant in `camALL.rbh`.

### How the tool works

```text
uv run hotd-decompress -c|--cam <file.rbh> [outdir]
```

`convert_cameras_to_json` (`src/hotd_decompress/camera.py`) uses `load_rbh` (no PACK expand). Retail `camALL.rbh` is already BODY.

1. Require one BODY that looks like a root pointer table (`firstPtr ≤ 0x1000`).
2. `groupCount = firstPtr / 4`. Skip `0xFFFFFFFF` slots.
3. Each group: `trackCount = (firstTrackPtr - groupPtr) / 4`, then parse tracks at those pointers.
4. Each track: `keyCount` / `channelId`, then `keyCount` × `{t, value, slopeIn, slopeOut}`.
5. Write `cameras.json`. Default dir: `decompressed_assets/<stem>_cam/`.

Stdout: group count, total tracks, output path.

The `-c` dump does not evaluate the Hermite spline; it writes keys. `sample_track` / `sample_camera_group` in `src/hotd_decompress/camera.py` implement `HermiteTrackLookup` (`FUN_00461858`) (cubic Hermite; previous `slopeOut` + current `slopeIn`). Pose channels are track order 0–2 eye, 3–5 look-at, not `channelId`. `channelId` is left numeric (`log2(keyCount)` in retail data). `cameras.json` is `jsonutil.write_json`, so whole-valued key floats print as `n.0`.

`src/hotd_decompress/rail_timeline.py` walks `evtALL` CCTB job-`0x40` binds in file order, resolves `startFrame == 0xFFFFFFFF` to the last end frame seen for that `camGroup`, and can sample `[start, end)`. Branch ops are ignored, so binds in one scene play back-to-back.

JSON shape:

```json
{
  "source": "…",
  "groupCount": N,
  "groups": [
    {
      "index": 0,
      "offset": 1234,
      "tracks": [
        {
          "offset": 5678,
          "keyCount": 4,
          "channelId": 2,
          "keys": [
            { "t": 0, "value": 1.0, "slopeIn": 0, "slopeOut": 0 }
          ]
        }
      ]
    }
  ]
}
```

To play a rail in a viewer: call `sample_camera_group` at integer frame `t`, place the camera at tracks 0–2, look at tracks 3–5 (Y-up as in the mesh exporter). `collect_rail_segments` resolves a `−1` start to the previous end for that group. Overlay zoom / shake / 2P blend only if matching the exe rather than the authored path.

---

## Cutscenes (`THOTD.exe`)

How the PC / Tantalus engine **plays** a scripted sequence. There is no FMV, AVI, or other movie file in the asset tree. A “cutscene” is the same 3D world as gameplay: an event script (`evtALL.rbh`) binds a camera rail (`camALL.rbh`), spawns actors, plays digital SFX, and the frame pump draws meshes / sprites as usual.

This note is **not** a CLI flag. On-disk layouts stay in [events.md](events.md), [events-detailed.md](events-detailed.md), and [cameras.md](cameras.md). The draw path is [game-rendering.md](game-rendering.md). Decomp: `hotd-decomp/THOTD-exe-commented.c`.

Retail dump checked: 9 stage slots, 66 scenes, 522 events, 993 rail binds, 142 `camALL` groups.

### No separate cutscene format

Every sequence the player watches is an **event section** (opcode stream) under `assets/evt/allstage/evtALL.rbh`. Camera motion is **not** embedded in that stream. A `CCTB` job `0x40` names a group index + frame window into `assets/cam/allstage/camALL.rbh`. The same pair drives:

| Kind | Typical wait | What it looks like |
|------|----------------|--------------------|
| Gameplay corridor | `WAIT_ENALV` / `WAIT_ENNUM` after a rail bind | Enemies spawn; rail keeps rolling; guns live |
| Staged intro / talky beat | `WAIT_CAMJOB` / `WAIT_CAMFRM` / `WAIT_FRM` | Camera and actors play out; combat waits |
| Title / attract / ending | Same ops, on stages `tt` / `adv` / `end` | No separate player plant into a fight |

The engine does not switch to a movie player. `CHGSM` (change system mode) and `ATCMD` (attract-mode command) only poke globals; they do not load another container.

CD music is MCI `cdaudio` in the exe. It is **not** in `assets/sound/` and is not keyed from `evtALL`. Digital voice / SFX in a sequence are `SNDON` → `PlayDigitalSfx` (`FUN_00412000`) (`O_*.rbh` / `gamesnds.rbh`).

### Who owns the playhead

Packed bytes ([events-detailed.md](events-detailed.md)):

| Address | Role |
|---------|------|
| `DAT_00da0cf4` | StageNo (root slot in `evtALL`) |
| `DAT_00da0cf3` | SceneNo |
| `DAT_00da0cf0` | EventNo (section index inside the scene) |
| `DAT_00da0ab8` | PC (pointer into the event BODY) |

Bind (`BindEventPlayhead` (`0x4c0d3c`)):

```
PC = stages[StageNo][SceneNo][EventNo]
```

`LoadStageAssets` (`FUN_00418aa0`) (stage asset load) fills the 7500-slot mesh table, then requests `cam\allstage\camall.rbh` (`DAT_00d5a5c8`) and `evt\allstage\evtall.rbh` (`DAT_00d5a5d0`). World mesh path is `ART\STAGE%d\WORLD\WORLD_%d.RBH` with the same StageNo (clamped: slots 0–3 → stages 1–4; slots 4–5 → stage 5; slot 6 → 6; anything else → 1). Title / attract / ending scripts still run against whatever world that clamp loaded.

Debug UI names (`s_Stage_01_005ce918` / `PTR_s_Scene_000_005ceba4`):

| Slot | Name | Scenes | Role in playback |
|------|------|--------|------------------|
| 0–3 | Stage 01…04 | 20 / 16 / 8 / 5 | Arcade chapters. Scene `000`/`00` is the start beat; later scenes are rooms / forks. |
| 4 | Stage tt | 2 (`XX`, `00`) | Title-style loop: one rail, then `WAIT` forever. |
| 5 | Stage adv | 1 | Attract / demo reel (scripted rails + spawns, no `CHGSM`). |
| 6 | Stage end | 8 | Ending variants (rails 117–141), then a `WAIT_ITEM 254` hold. |
| 7 | *(null)* | 0 | Unused. |
| 8 | extra | 6 | Reachable if StageNo is set; copies late Stage 01 scenes. |

`CountStagesForSelectUi` (`FUN_00422808`) (stage-select) only counts until the first `0xFFFFFFFF`, so the UI sees slots 0–6. Gameplay indexes StageNo directly.

### Per-frame playback

Idle pump `IdleFramePump` (`FUN_00562e30`) draws; gameplay tick `TickGameplay` (`FUN_00458b7c`) (from `TickGameplayParent` (`FUN_00458720`)) updates entities and camera **before** that draw. A scripted beat is four machines on the same frame:

```
event VM tick          camera job ring           rail sampler              draw pump
TickEventVm            DispatchCameraJob         TickCameraRail            DrawEnabledCameras
handlers[opcode]       DAT_005d8418[job]         six Hermite tracks        vtable +0x24
       │                      │                         │                        │
       ├─ CCTB 0x40 ──────────► bind group + [start,end]
       ├─ WAIT_CAMJOB ────────► yield until ring empty
       ├─ ENTB* ──────────────► spawn into DAT_00d53080 instances
       └─ SNDON ──────────────► PlayDigitalSfx
                                                        │
                                                        ├─ eye / look-at → yaw/pitch
                                                        ├─ plant player on floor
                                                        └─ view slots → rasterizer
```

#### 1. Event VM

Tick at `TickEventVm` (`0x4c0db0`): `opcode = *PC`; `call handlers[opcode]` at `DAT_005eeac0`. Names at `0x5a3a00`.

`DAT_00da0a98` is the yield flag. A wait op sets it and returns; the next frame retries the same opcode until the condition holds, then advances PC. That is how a cutscene **holds**: the script does not sleep the process; it spins on `WAIT_CAMJOB` / `WAIT_CAMFRM` / `WAIT_FRM` / `WAIT_ITEM` while the camera and entities keep ticking.

`NEXTEV` (`0x4c1948`) increments EventNo. If that slot is `-1`, a branch table at `0x5d3420` picks the next scene (fixed, indexed, or +1) and restarts at EventNo 1. If the scene pointer is `-1`, the stage is done. `SCNINIT` (`0x10`) resets camera slots and scores at scene start.

Typical **scene open** (Stage 01 `Scene 000` event 1):

```
SCNINIT
SNDON    2
SKYKD    0
SKYTB    2
SHDWLT   0xf000 0xd000
FKRTB    ptr → floor Y
BGTB     1
CHGSM    5
ENTB2    spawn
WAIT_ITEM 248
CHGSM    5
NEXTEV
```

Then later events bind rails and spawn enemies. Scene-to-scene setup events are often a short `SNDON` + `CHGSM 6` + `NEXTEV` before the `SCNINIT` body.

Retail `CHGSM` args (change system mode; 169 uses): **6** (69, scene-to-scene), **5** (35, start / wait-item intros), **8** (21, often next to `TEXCHG`), **7** (21), **1** (21), **3** (12). `ATCMD` is 0 or 1 (14 uses). `PYPMD` is almost unused (one `0`, one `1`). `WAIT` (yield forever, no PC advance) appears **once**: Stage tt `Scene 00`.

#### 2. Camera job ring

`CCTB` queues the current instruction onto a 16-slot ring (`DAT_00d9f1f0`). `DispatchCameraJob` (`FUN_0045f414`) reads `*(PC+4)` as the job type and dispatches `DAT_005d8418[job]`. Job `0x40` (`BindCameraRailJob` (`FUN_00460f88`) → `BindCameraRail` (`FUN_00460fd0`)) is the rail bind:

| Word | Copied to | Meaning |
|------|-----------|---------|
| start | `DAT_00d9ed04` | Start frame (`−1` keeps current `t`) |
| end | `DAT_00d9ed08` | End frame (tick while `t < end`) |
| camGroup | `DAT_00da0ca4` | `camALL.rbh` group index 0–141 |
| flags | `DAT_00d9ed10` | Bind flags. The update at `0x461171` tests mask **4**. Mask **2** is a different bit |

Slot 0 of the 0x154-byte camera slots (`DAT_00da01c0`) also pokes the event-script state machine (`DAT_00da0ab0`). Remaining frames (`end − t`) live in `DAT_00da0bf8` (`WAIT_CAMFRM 0` / `RNWCJ` read that).

The bread-and-butter cutscene pair:

```
CCTB rail { start, end, camGroup, flags }
WAIT_CAMJOB
```

Gameplay often uses the same bind, then `WAIT_ENALV` so the rail and the fight overlap. `CAMDR` / `CAMDR2` (374 + 5 retail uses, arg usually `3`) are camera-director waits on top of that.

#### 3. Rail sampler

`TickCameraRail` (`FUN_004caa70`) (paused when `DAT_00da0a80 != 0` or `DAT_00da0b5c == 0`):

1. If `start < end`, increment the integer frame counter.
2. Sample six Hermite tracks for group `DAT_00da0ca4` into eye XYZ (`DAT_00d9ed18`) and look-at XYZ (`DAT_00d9ed30`). Lookup is `HermiteTrackLookup` (`FUN_00461858`); pose channels are **track order**, not `channelId`.
3. `EyeLookAtToYawPitch` (`FUN_00461a30`): direction = eye − look-at → fixed-point yaw/pitch (×16). Roll = 0.
4. `RaycastStageFloor` (`FUN_0048a15c`): raycast `(eye.x, 32768, eye.z)` onto the stage mesh. Player XZ follows the camera; Y comes from the ground hit.

Zoom, 2P aim blend, and shake sit on top of the rail and do **not** add tracks ([cameras.md](cameras.md)). `DAT_00da0bd0` selects the live camera: `0` = gameplay (`GameplayCameraView` (`FUN_00461adc`)), `2` = title/alt (`TitleCameraView` (`FUN_00461b90`)).

#### 4. Draw

Same path as any other frame ([game-rendering.md](game-rendering.md)): instance queues → `DispatchMeshPrims` (`FUN_00578bb0`) prims → software scanline or D3D `DrawIndexedPrimitive`. Sky (`SKYKD` / `SKYTB`), lights (`SHDWLT` / `WLTB`), and `TEXCHG` are event ops that only change globals the submit path reads. Letterbox bands (`SetLetterboxViewport` (`FUN_0048769c`), height / `0x180`) and 2P split (`SetSplitScreenViewport` (`FUN_00487708`)) are viewport helpers, not a movie overlay.

`DAT_005cd35c != 0` skips 3D submit (load / fade). HUD stamps (`StampScrollSprite` (`FUN_004434b0`)) still run: stage-intro countdown `TickStageIntroCountdown` (`FUN_0051a8d0`) is a **separate** entity state machine (voice / `SPR_Num` bonus / camera tilt) on top of the event script, not an opcode.

### Special stages (title, attract, ending)

These are ordinary `evtALL` slots. They are the closest thing the bank has to “dedicated cutscenes”: almost no `WAIT_ENALV`, lots of `WAIT_CAMJOB` / `WAIT_FRM`, and `ENTB2` props rather than corridor spawn tables.

#### Stage tt (slot 4) — title loop

`Scene XX` event 1:

```
SCNINIT
SKYKD 0 / SKYTB 1 / CHGSM 6 / FKRTB / BGTB 2
CCTB rail group 106, frames 0–59
GGSET 29
ENTB  two spawns (typeId 129, 130)
WAIT_CAMJOB
WAIT_FRM 300
CCTB rail group 106, frames 60–175
WAIT_CAMJOB
CCTB camMode2
WAIT_FRM 9999
NEXTEV
```

`Scene 00` is a single `WAIT` — the VM yields forever. Title/attract UI mode 1 (`TitleAttractUiMode1` (`FUN_004210fc`)) and title camera matrices (`TitleCameraMatrices` (`FUN_00496f60`)) sit beside this script; they are not encoded in `evtALL`.

#### Stage adv (slot 5) — attract / demo reel

One scene, 11 events. No `CHGSM`. Pattern: spawn a few `ENTB2`/`ENTB`/`ENTB3` actors, bind a rail, `WAIT_CAMJOB`, `WAIT_FRM`, `NEXTEV`. Rails used: groups **107–116** (plus 115 with a long 121–520 window). `SNDON 263` opens most beats. Attract/demo tick `TickAttractDemo` (`FUN_00473e04`) / `TickAttractScroll` (`FUN_00458bd8`) can restart or take coin/start; `ATCMD` from scripts is the event-side hook (14 uses, mostly in chapter scenes, not in `adv` itself).

#### Stage end (slot 6) — ending variants

Eight scenes. Shared open: `SKYTB 1` / `SKYKD 5` / `SCNINIT` / `NEXTEV`, then a long event of `ENTB2` (typeIds 110, 161, 120, …) + rail slices + `WAIT_CAMJOB`.

| Scene | Rails (groups) | Notes |
|-------|----------------|-------|
| 00 | 117, 119 | Long first ending; `SNDON 69` then `70` / `14` |
| 01 | 117, 120, 121 | Same open, different later groups |
| 02 | 124, 123 | Same shape |
| 03 | 126–137, 140 | Many short 0–320 windows; sky/BGTB changes per beat |
| 04 | 140 (540–560) | Hold, then `WAIT_ITEM 254` |
| 05 / 06 | 140, 141 | Credits-like; `SNDON 44`; same `WAIT_ITEM 254` tail |
| 07 | — | `SCNINIT` / `NEXTEV` only |

`WAIT_ITEM 254` at the end of 04–06 is a hold until an item flag (continue / skip), not a movie stop.

### Attract, title, and intro overlays

These do **not** add tracks or opcodes. They run next to the VM:

| System | Function | Behaviour |
|--------|----------|-----------|
| Title / attract UI mode 1 | `TitleAttractUiMode1` (`FUN_004210fc`) | Main menu layout; optional stage-select `CountStagesForSelectUi` (`FUN_00422808`) |
| Attract/demo tick | `TickAttractDemo` (`FUN_00473e04`) | Demo input, stage restart, player-count transitions |
| Attract scroll / difficulty | `TickAttractScroll` (`FUN_00458bd8`) / `TickAttractDifficulty` (`FUN_00458c28`) | Called from the gameplay tick |
| Title camera matrices | `TitleCameraMatrices` (`FUN_00496f60`) | Fixed rotations for 1P vs 2P title layouts |
| Live camera = title/alt | `DAT_00da0bd0 == 2` | `TitleCameraView` (`FUN_00461b90`) instead of gameplay `GameplayCameraView` (`FUN_00461adc`) |
| Stage-intro countdown | `TickStageIntroCountdown` (`FUN_0051a8d0`) | HUD sprites + SFX; not an `evtALL` op |
| Route playback (intro/wait/active) | `DrawRoutePlaybackUi` (`FUN_004c608c`) | Sprite stamps for the route UI, not the 3D rail |

### Reconstructing a sequence (this tool)

No `-cutscene` flag. To replay one beat:

1. `-e` on `evtALL.rbh` — pick `stages[StageNo].scenes[SceneNo].sections[EventNo]`. Read `CCTB` `camera.camGroup` / `startFrame` / `endFrame`, plus `ENTB*` spawns and `SNDON` ids.
2. `-c` on `camALL.rbh` — evaluate that group’s six Hermite tracks at integer frame `t` in `[start, end)`. Camera at tracks 0–2, look-at 3–5 (Y-up).
3. `-m` on `worldN.rbh` and `CREAT1.RBH` / `CREAT2.rbh` — instance spawns by `typeId` → [creatures.md](creatures.md) (spawn `typeId` is the 137-slot function table, **not** the 94-row creature table).
4. `-p` on `B_RED.VMC` (or `bigger.vmc`) and `-s` on `spr.rbh` — pages + HUD / FX quads.
5. `-w` on `O_*.rbh` / `gamesnds.rbh` — `SNDON` args are sound ids, not filenames.

Hold the pose while the script would `WAIT_CAMJOB` (until `t` reaches `end`). Overlay zoom / shake / 2P blend / letterbox only if matching the exe rather than the authored rail. CD music has to come from the disc (MCI), not this CLI.

---

## Cutscene audio cue sheet

There is no FMV and no subtitle text. A “cutscene” is an `evtALL.rbh` event section: camera rail, actor spawns, and `SNDON`. This note is how those `SNDON` ops join to the clip `PlayDigitalSfx` (`FUN_00412000`) requests.

On-disk PCM: [audio.md](audio.md). Event VM / rails: [cutscenes.md](cutscenes.md), [events-detailed.md](events-detailed.md).

This is **not** a CLI flag. WAV export stays `-w`. The per-scene sheet is generated, not stored in this tree:

```text
uv run python scripts/cutscene_cues.py
```

That writes `decompressed_assets/exe_tables/cutscene-cues.json` (gitignored) from `evtALL.rbh` and `DAT_005cbda8`. Retail checks: 270 sound-request rows, 272 `SNDON` ops.

### `SNDON` → `PlayDigitalSfx` (`FUN_00412000`)

`SNDON` (`0x5a`) takes one `u32`. That value is an index into `DAT_005cbda8`, **not** an `O_*` `soundId` and **not** a `gamesnds` row.

```
DAT_005cbda8  270 × 0x0C
  +0x00  u32 kind     0 nop, 1 mixer, 2 mixerDrain, 3 mixer3 (CD via PlayCdAudioTrack), 4 oneshot, 5 stop
  +0x04  u32 namePtr  C string stem for kind 4 (sprintf "sound\\O_%s.rbh")
  +0x08  s32 extra    gamesnds index (kinds 1–2), CD gate (kind 3), mixer id (kind 4), or −1
```

PE: image base `0x400000`, DGROUP VA `0x5A0000` (file `0x187400`). File offset = `0x187400 + (VA − 0x5A0000)`.

| Kind | Name | What plays |
|------|------|------------|
| 0 | `nop` | Nothing (`extra` is usually `−1`) |
| 1 | `mixer` | `gamesnds.rbh` row `extra` (embedded PCM, or external `O_*` via `soundId`) |
| 2 | `mixerDrain` | Drain loop: `DispatchSoundCallback` (`FUN_005656d0`) until `−1` |
| 3 | `mixer3` | CD audio: `PlayDigitalSfx` (`FUN_00412000`) at `0x4120AA–0x4120EB` calls `PlayCdAudioTrack` (`FUN_00565d60`) when `DAT_00d5b214` is set and `extra != −1`. `extra` is not a `gamesnds` clip |
| 4 | `oneshot` | `sound\O_%s.rbh` from `namePtr`. `extra` is a mixer id, **not** the file `soundId` |
| 5 | `stop` | Stop / gate (`DispatchSoundCommand` (`FUN_00411f9c`)) |

Kind 4 `extra` is **not** the oneshoot header `soundId`. `O_HELP.rbh` is table id **123** (file `soundId` 28). `O_voc09.rbh` is table id **165**, the only `O_voc*` `SNDON` in `evtALL` (Stage 04 Scene 00). The other voc clips are fired from entity / player-voice code, not this opcode stream.

Stage **tt** (title) has no `SNDON`. Scene-open `SNDON 9` / `10` / `16` / `22` are per-chapter CD stingers (kind 3).

`scripts/cutscene_cues.py` records each `SNDON` as `{stage, scene, section, sndonId, kind, kindName, extra, sample}`. `sample` is `O_NAME.rbh`, `gamesnds[index]`, or `cdaudio[extra]`.

---

## Game rendering (`THOTD.exe`)

How the PC / Tantalus engine turns decompressed assets into a frame. On-disk layouts stay in the per-type notes; this note is the **runtime** path: backends, view, mesh submit, textures, sprites, and the software / Direct3D rasterizers.

This note is **not** a CLI flag. Pair `-m` / `-p` / `-s` / `-c` / `-e` with the exe tables below. Decomp: `hotd-decomp/THOTD-exe-commented.c`. WinMain is `WinMainEntry` (`LAB_00563440`) (recovered from `THOTD.exe` @ `0x563440`).

### Two backends

WinMain (`WinMainEntry` (`LAB_00563440`)) picks a renderer from the command line, then seeds `PTR_DAT_00c649e0` (the graphics vtable every draw call goes through):

| Cmdline | Init | Vtable | Path |
|---------|------|--------|------|
| `ddraw` or `d3d` | `InitDirect3DBackend` (`FUN_00573ca0`) | `DAT_00c66ef8` | DirectDraw + Direct3D 6 (`IDirect3DDevice3`) |
| *(else)* | `InitSoftwareBackend` (`FUN_00565e70`) | `DAT_00c652a4` | Software: lock the back-buffer and scanline-fill |

`InitDirect3DBackend` (`FUN_00573ca0`) enumerates adapters (`DirectDrawEnumerateA`), `DirectDrawCreate` → `DAT_00c64cac` (`IDirectDraw*`), queries a second interface into `DAT_00c66ecc`, and later binds `DAT_00c66ee8` as the D3D device. `InitSoftwareBackend` (`FUN_00565e70`) only swaps the vtable pointer.

Game code never calls DirectDraw / D3D directly for meshes. It calls vtable slots; the two backends implement the same offsets.

| Vtable offset | Role |
|---------------|------|
| `+0x04` | Renderer init (`InitRendererPrimPool` (`FUN_005627c0`)) |
| `+0x08` | Teardown |
| `+0x10` | Pause/resume around MessageBox |
| `+0x24` | Per-camera draw (`DrawCameraObject` (`FUN_005626d0`) → this) |
| `+0x34` | Palette / mode hook (stage load) |
| `+0x60` / `+0x64` | Allocate / free a VRAM texture slot |
| `+0x68` | Present / flip (`PresentFlip` (`FUN_00418434`)) |
| `+0x78` | Draw triangle (plain) |
| `+0x7c` | Draw quad (plain) |
| `+0x80` | Draw textured triangle |
| `+0x84` | Draw textured quad |
| `+0xbc` | 2D blit (UI glyphs) |

#### Software vtable (`DAT_00c652a4`, recovered)

Ghidra’s named export jumps from `FUN_0057c9b7` (`atoi`) to `FUN_00582ed0` (`D3dDrawIndexedPrimitive`). That **`0x57c9b7`–`0x582ed0` hole** is the software camera draw and the tri/quad setup that packs projected verts into the 0x224-byte prim record and calls clip + scanline. Dump from `THOTD.exe` (image base `0x400000`, RVA of the vtable **`0x8652a4`**):

| Slot | Software impl | Role |
|------|---------------|------|
| `+0x24` | `FUN_0057cce0` | Per-camera draw: lock buffer, walk depth buckets, clip, call scanlines |
| `+0x74` | `FUN_0057f3c0` | Alloc a 0x224 prim record; insert by truncated average depth |
| `+0x78` | `FUN_0057f230` | Plain tri setup |
| `+0x7c` | `FUN_0057f070` | Plain quad setup |
| `+0x80` | `FUN_0057eeb0` | Textured tri setup |
| `+0x84` | `FUN_0057ecb0` | Textured quad setup |

Type codes written at prim record `+0x08`: `0x52` / `0x62` flat, `0x92` / `0xa2` textured opaque, `0xc92` / `0xca2` textured transparent. Batch `flags & 0x100` selects the transparent filler; `flags & 0x200` skips `PrimFacingTest` (`FUN_00578f60`).

D3D device vtable (on `DAT_00c66ee8`) is the real COM object: `+0x24` `BeginScene`, `+0x28` `EndScene`, `+0x5c` `SetRenderState`, `+0x78` `DrawIndexedPrimitive`.

### Frame loop

Idle pump `IdleFramePump` (`FUN_00562e30`) (called while `DAT_00c64b14` bit 0 is set):

1. `PeekMessageA` — if a message is waiting, `GetMessageA` / `TranslateMessage` / `DispatchMessageA`.
2. Else, when the window is active (`DAT_00c64b2c`, `DAT_00c64b14` bit 1) and not paused (bit 10 clear):
   - `SyncSceneGraph` (`FUN_00568290`) — scene-graph sync: run pending `+0x18` callbacks, copy last-frame matrices.
   - `DrawEnabledCameras` (`FUN_00568350`) — for each camera object with draw-enable, `DrawCameraObject` (`FUN_005626d0`) → vtable `+0x24`.
   - `FlushDrawCallbacks` (`FUN_00579fa0`) flushes callback queues around those two.
   - Busy-wait `WaitForFrameDeadline` (`FUN_00578940`) until `DAT_00da69b4` (next-frame deadline). Deadline is `now + 1000 / fps`.

`DAT_005cd35c != 0` skips 3D submit (load / fade). Present is vtable `+0x68`.

Gameplay tick `TickGameplay` (`FUN_00458b7c`) (from `TickGameplayParent` (`FUN_00458720`)) updates entities and camera **before** the pump draws. Camera rails: [cameras.md](cameras.md). Event scripts that queue those rails: [events-detailed.md](events-detailed.md). Scripted playback (title / attract / ending, no FMV): [cutscenes.md](cutscenes.md).

### Display surface

`SetDirectDrawMode` (`FUN_005663d0`) sets the DirectDraw mode. Logical size is `DAT_00c64a00` × `DAT_00c64a04`; bpp is `DAT_00c64a14` / `DAT_00c64a08`.

| bpp | Flag in `DAT_00c649f4` | Pixels |
|-----|------------------------|--------|
| 8 | bit 1 (`2`) | Paletted; software flat-fill writes a byte index |
| 16 | bit 2 (`4`) | RGB555 (same packing as VVTP pages) |

Software path:

- Lock: `LockBackBuffer` (`FUN_005661f0`) — `IDirectDrawSurface::Lock` on `DAT_00da8980`. Pixel base `DAT_00c65380`, pitch `DAT_00c64cdc`, flag bit 7 (`0x80`).
- Unlock: `UnlockBackBuffer` (`FUN_005661a0`).
- Windowed vs fullscreen: `DAT_00c649f8 == 0` is windowed (`AdjustWindowedChrome` (`FUN_00574dc0`) adjusts for menu chrome).

Primitive pool: `InitRendererPrimPool` (`FUN_005627c0`) `GlobalAlloc`s `N * 0x224` bytes into `DAT_00c64a38`. Sorted draw lists live at `DAT_00c65390` (opaque) and `DAT_00c65394` (transparent); `WalkSortedDrawLists` (`FUN_0057a800`) walks both.

### Viewport

Clip rectangle in `DAT_00d53020` (x0), `DAT_00d53024` (y0), `DAT_00d53028` (x1), `DAT_00d5302c` (y1). Applied with `SetViewportClip` (`FUN_00568550`) (viewport) and `SetWindowedScissor` (`FUN_00568770`) (windowed scissor). `RecomputeViewportExtent` (`FUN_00568a00`) recomputes origin/extent.

| Helper | Layout |
|--------|--------|
| `SetFullscreenViewport` (`FUN_0048780c`) | Full screen (`0,0`–`W,H`) |
| `SetLetterboxViewport` (`FUN_0048769c`) | Letterbox bands from screen height / `0x180` |
| `SetSplitScreenViewport` (`FUN_00487708`) | 2P split: top band `(H * 0x28) / 0x180`, then two `SetWindowedScissor` (`FUN_00568770`) surfaces |

Projection scale for a camera object sits at `+0x20` (X) and `+0x24` (Y). Near clip is view-space `z < 1.0` (`0x3f800001`).

### View and transform stack

Stage space is the same as world meshes and camera rails: **Y up**, X/Z along the corridor. Do not bake world-node `+0x20` XYZ as a translate ([meshes.md](meshes.md)).

#### Camera → view

`TickCameraRail` (`FUN_004caa70`) samples `camALL.rbh` (eye XYZ + look-at XYZ), then:

1. `EyeLookAtToYawPitch` (`FUN_00461a30`) — direction = eye − look-at → fixed-point yaw/pitch (×16). Negate yaw, add `0x8000` to pitch, roll = 0.
2. `RaycastStageFloor` (`FUN_0048a15c`) — raycast `(eye.x, 32768, eye.z)` onto the stage mesh; player XZ follows the camera, Y from the ground hit.

`BuildViewSlotMatrices` (`FUN_0045f140`) rebuilds **six** view slots (stride `0x154` at `DAT_00da01c0`). `DAT_00da0bd0` selects the live camera: `0` = gameplay (`GameplayCameraView` (`FUN_00461adc`)), `2` = title/alt (`TitleCameraView` (`FUN_00461b90`)). Zoom, 2P aim blend, and shake sit on top of the rail and do not add tracks — [cameras.md](cameras.md).

#### Matrix stack

`DAT_012e27f0` is the current 3×4 matrix (12 floats, 0x30 bytes). Base of the stack is `DAT_00c6641c` (`InitMatrixStack` (`FUN_00569510`)). Identity lives at `DAT_005ce4f4`.

| Function | Role |
|----------|------|
| `MatrixPush` (`FUN_00569600`) | Push (copy 12 floats, advance the pointer) |
| `MatrixLoadIdentity` (`FUN_004b2938`) | Load identity |
| `MatrixTranslate` (`FUN_00474ecc`) / `MatrixTranslateEntity` (`FUN_0042f704`) / `MatrixTranslateAlt` (`FUN_004b4fd4`) | Translate |
| `MatrixRotateZ` (`FUN_004751f4`) / `MatrixRotateY` (`FUN_004750ec`) / `MatrixRotateX` (`FUN_00475380`) | Rotate Y / X / Z (sin/cos table `DAT_005697b0`, 16-bit angle) |
| `SubmitEntityTransform` (`FUN_004b9f5c`) | Translate + Y/X/Z + uniform scale (`entity+0x9c`), then submit |

Pop is `DAT_012e27f0 -= 0xC` (12 floats). `TransformPoint` (`FUN_00492170`) / `TransformPointAlt` (`FUN_00465d04`) transform a point by the current matrix.

`ProjectVertices` (`FUN_00579200`) / `ProjectVerticesWithClip` (`FUN_005792b0`) batch-transform `float3` verts through that 3×4, perspective-divide, and (in `ProjectVerticesWithClip` (`FUN_005792b0`)) write clip outcodes. Output stride is **7 floats (0x1c bytes)**:

```
+0x00  f32 x     view / then screen (× viewport scale × 1/z)
+0x04  f32 y
+0x08  f32 z     view z; forced to 1.0 if z < 1
+0x0c  f32 1/z
+0x18  u32 clip  bits: 4 left, 8 right, 0x10 top, 0x20 bottom (plus a near bit in the low byte)
```

A prim is rejected when the **AND** of the three/four clip words is non-zero (all verts off the same plane).

### Mesh submit

Stage load `LoadStageAssets` (`FUN_00418aa0`) fills one 7500-slot pointer table (`DAT_00d53080`, 30000 bytes):

1. Clear the table.
2. `ART\STAGE1\CREATURE\CREAT1.RBH` then `CREAT2.RBH` via `LoadCreatMeshBank` (`FUN_00419cac`) — `DAT_00d53080[id] = nodePtr` until `id == -1`.
3. `ART\STAGE%d\WORLD\WORLD_%d.RBH` via `LoadWorldMeshBank` (`FUN_00419cf4`) — `DAT_00d53080[id] = id-table row` until `id == 0`. The row is `{s16 id, s16 flag, u32 nodePtr…, 0}`.
4. `cam\allstage\camall.rbh`, `evt\allstage\evtall.rbh`.
5. Texture bank is `ART\STAGE1\CREATURE\texture.VMC` (`LoadPiffVvtp` (`FUN_00576610`)), not this function.

CREAT and world **share the table**. Draw helpers interpret a slot as a node pointer (creatures) or an id-table row (world). Creature type → model id: [creatures.md](creatures.md).

#### Instance batch

3D submit is a **deferred instance list**, not an immediate `DrawPrimitive`. `BeginInstanceFrame` (`FUN_0043d900`) begins a frame (clear queues). Each instance is 0x40 bytes: mesh id, flags, then the current 12-float matrix.

| Queue | Enqueue | Buffer | Counter |
|-------|---------|--------|---------|
| Opaque | `EnqueueOpaqueInstance` (`FUN_0043d948`) (`EnqueueOpaqueIfLive` (`FUN_0043d7f8`) when `DAT_00d53080[id]` is live) | `DAT_00d64cc0` | `DAT_00d6c9d8` |
| Translucent | `EnqueueTranslucentInstance` (`FUN_0043d990`) (`EnqueueTranslucentIfLive` (`FUN_0043d834`)) | `DAT_00d5cfc0` | `DAT_00d6c9cc` |

`SwapInstanceQueues` (`FUN_0043d928`) swaps front/back counters for the draw pass.

Typical callers:

- Creature / prop: build world matrix (`SubmitEntityTransform` (`FUN_004b9f5c`), `BuildCreatureWorldMatrix` (`FUN_00431330`), `WalkSkeleton` (`FUN_00478a74`) skeleton walk) then `EnqueueOpaqueIfLive` (`FUN_0043d7f8`) with `entity+0x5c` (CREAT id). Bone clip apply: [motion.md](motion.md).
- World: `EnqueueWorldMeshNodes` (`FUN_004920cc`) looks up the id-table row and enqueues **each** `nodePtr` until 0.
- Shadow pass (when `DAT_005cd36c != 0`): `ShadowPassSetup` (`FUN_0042ce70`) + `ShadowPassSubmit` (`FUN_00430318`) + a second `EnqueueOpaqueIfLive` (`FUN_0043d7f8`). Lighting / shadow matrix helpers are `RotateShadowLightMatrixZ` (`FUN_004c6954`)…`RebuildShadowLightMatrix` (`FUN_004c86d0`) (ground raycast at Y = `0x47000000` = 32768, same as the player plant).

`MirrorPassWalkChildren` (`FUN_004789c8`) is a mirror pass: push view, translate with **negated Z**, walk children.

#### Prim dispatch (`DispatchMeshPrims` (`FUN_00578bb0`))

Once an instance is bound, the node’s prim batches are walked. Layout matches [meshes.md](meshes.md). `kind = flags & 0x2007`. Transformed verts are the 0x1c records above (`param_2` is the projected pool; index `i` → `param_2 + i * 0x1c`).

| kind | Prim | Payload step | Vtable |
|------|------|--------------|--------|
| `0` / `1` | Plain tri | +4 shorts | `+0x78` |
| `2` | Textured tri | +0x12 shorts | `+0x80` |
| `0x2001` | Plain quad | +5 shorts | `+0x7c` |
| `0x2004` | Textured quad | +0x16 shorts | `+0x84` |

Facing test `PrimFacingTest` (`FUN_00578f60`) is a 2D cross product on projected XY. Skip it when `flags & 0x200`. Quads may pass if **either** split triangle faces the camera. **Order matters**: `DispatchMeshPrims` runs the clip-AND (all raw corner outcodes ANDed together) and `PrimFacingTest` on those same raw, pre-clip corners *before* geometric clipping. Clipping happens afterward, inside the vtable draw call. Testing facing on an already-clipped polygon is a different test whenever clipping reshapes the shape.

Textured records carry `texPageId` + pixel-space UVs on a 256×256 VVTP page. The rasterizer / D3D path binds that page from the VRAM table (below). This tool’s OBJ export only needs `0x2007` for record size; a viewer must honour `0x200` and the clip AND.

**Quad-to-triangle split is not one fixed convention across mesh kinds.** CREAT quads store their 4 indices in perimeter order, so the fan diagonal `(i0,i1,i2)+(i0,i2,i3)` matches `DispatchMeshPrims`. World quads (`world*.rbh`) are generated on a 2×2 vertex grid — `i0/i1` are one edge, `i2/i3` the opposite edge — so `i0–i2` is a rectangle side, and that same fan produces a bowtie. `-m` writes the four indices as one OBJ face and does not triangulate.

### Textures (VRAM)

Pixels are VVTP pages ([textures.md](textures.md)). Runtime:

1. `LoadPiffVvtp` (`FUN_00576610`) opens PIFF+VVTP (`0x46464950` / `0x50545656` — comments that say “PVT / FFPV” are the same fourcc read backwards). Each `BODY` registers `pageId` into `DAT_00c6713c` (stride **0x18**, 1000 slots, 24000 bytes). Slot `+0x04` holds the BODY pointer.
2. `GenerateTextures` (`FUN_0041a220`) (“Generating Textures”) builds a 64K RGB555 remap: identity, then `table[0] = table[0x8000] = 0x8421`, plus blood-colour overrides from `PTR_DAT_005ce830[DAT_00d5b1fc]`. Applies the table to every page BODY.
3. `PackRgb555` (`FUN_0045640c`) packs 5-bit R/G/B and ORs `0x8000` (engine “priority” bit). Channels other than `0x1f` are snapped to even (`& 0x1e`).
4. `AcquireVramSlot` (`FUN_00576350`) acquires a VRAM slot (vtable `+0x60` / `+0x64`). Overflow logs `VRAM_C_pos*`.
5. D3D: `CreateD3dTextureSurface` (`FUN_00584130`) creates a DirectDraw offscreen surface and binds it as a D3D texture. `D3dDrawIndexedPrimitive` (`FUN_00582ed0`) `SetRenderState(TEXTUREHANDLE, …)` then `DrawIndexedPrimitive` (`D3DPT_TRIANGLEFAN` = 6, vertex stride 32). Alpha blend uses render states `0x11` / `0x12` (`SRCBLEND` / `DESTBLEND`).

Clear colours `0x0000` and `0x8421` are transparent in this tool’s PNG path; the engine uses the same two as remap sentinels.

Page bands (header `pageId`, same numbers as `-p` / mesh `texPageId` / sprite `pageId`): **1–337** sprites, **338–511** unused, **512–546** world, **547–595** creature skins.

### Software rasterizers

When the software vtable is active, vtable `+0x78`…`+0x84` pack projected verts into a **0x224-byte prim record**, `ClipProjectedPolygonAgainstClip` (`FUN_005885d0`) clips it, then a scanline filler writes the locked back-buffer (`DAT_00c65380` + `y * pitch`). Affine UVs **on the span** (no perspective correction there). Clip-time UVs are perspective-correct (`InterpolatesClipPlaneVertexAttributes_005893f0` (`FUN_005893f0`): lerp `U·W` / lerp `W`). Before `ScanlineTexturedOpaque` (`FUN_0058ab88`), the camera draw multiplies `U,V` by `1/z`; the span then DDA in 16.16. Scratch setup: `InitMatrixStack` (`FUN_00569510`).

Do not mix in `ClipActivePolygonEdgeList` (`FUN_0058c2d0`) — that is the D3D sibling.

#### Prim record (`0x224`)

| Offset | Field |
|--------|--------|
| `+0x07` | Flat colour byte |
| `+0x08` | Type code (`0x52`/`0x62`/`0x92`/`0xa2`/`0xc92`/`0xca2`) |
| `+0x0c` / `+0x0e` | Clip-mode flags |
| `+0x10` | Winding (`1` / `-1`) |
| `+0x14` | Texture page id |
| `+0x18` | Vertex count (up to 8 after clip) |
| `+0x2c` | X[] |
| `+0x4c` | Y[] |
| `+0x6c` | `1/z`[] (W after the 0x80000 clip branch) |
| `+0x8c` | U[] (pixel; `U/z` going into the textured filler) |
| `+0xac` | V[] |
| `+0xcc` | Z[] / W |

#### Fillers

| Function | Fill |
|----------|------|
| `ScanlineFlat` (`FUN_0058830d`) | Flat (byte / replicated colour) |
| `ScanlineGouraudOpaque` (`FUN_005894ec`) | Gouraud, opaque (page-indexed, not RGB lerp) |
| `ScanlineGouraudTransparent` (`FUN_00589e40`) | Gouraud, transparent (skip zero source) |
| `ScanlineTexturedOpaque` (`FUN_0058ab88`) | Affine textured, opaque |
| `ScanlineTexturedTransparent` (`FUN_0058b5ac`) | Affine textured, transparent (skip zero texel) |
| `ClipSpriteToViewport` (`FUN_00567c70`) | Clip a 2D sprite/tile descriptor to the viewport, adjusting UVs |
| `BresenhamSpanX` (`FUN_00567f90`) | X-dominant Bresenham span |
| `BresenhamSpanY` (`FUN_00568000`) | Y-dominant Bresenham span |

Ghidra’s recovered inner loops write **bytes** (palette / texel index). `SetDirectDrawMode` (`FUN_005663d0`) sets 16-bit with `DAT_00c649f4` bit 2 (`4`).

No Z-buffer — nearer prims overwrite. The software setup allocates one polygon record (`AllocSoftwarePrimRecord` (`FUN_0057f3c0`)) with **head insertion** into a depth bucket and a depth key from **source** projected corners; `SoftwareDrawCamera` (`FUN_0057cce0`) walks those buckets. `WalkSortedDrawLists` (`FUN_0057a800`) walks a different pair of global object lists — do not treat it as the software primitive opaque/transparent partition.

D3D path (`D3dDrawIndexedPrimitive` (`FUN_00582ed0`)) does **not** use these fillers. It transforms the same polygon nodes, then `DrawIndexedPrimitive`. Hardware vs software is a backend swap, not a different mesh format.

### Sprites and HUD

`assets/sprite/spr.rbh` is UV/page metadata ([sprites.md](sprites.md)). BODY base after load is `DAT_005ce544`. `GetSpriteRecord` (`FUN_004430a4`) returns `DAT_005ce544[id]`.

`StampScrollSprite` (`FUN_004434b0`) is a **64×48 scroll-tile stamp**, not a GPU sprite draw. It looks up the sprite record, converts the header UV extent to tile counts (`>> 3`), clips to 0x40×0x30, and writes the sprite id into `PTR_DAT_005d24f4[layer][y * 0x40 + x]`. Out-of-range stamps log `Bogus scroll sprite`. `SetSpriteScreenUvRect` (`FUN_00442fa8`) sets the screen-space UV rectangle from `DAT_00c64a00` × `DAT_00c64a04`.

HUD / score (`StampScrollSprite` (`FUN_004434b0`) with ids such as `0x589` + digit, `0x4f0` lives, `0x504` / `0x505` labels) and UI text (`DrawUiGlyph` (`FUN_00428494`) glyphs through vtable `+0xbc`) reuse the same sprite table. Composite a HUD quad with `-s` JSON + `-p` PNGs: `pageId` + `(u0,v0)–(u1,v1)` on a 256×256 page.

### Event opcodes that poke the renderer

From [events-detailed.md](events-detailed.md); these do not add mesh data, they change globals the draw path reads:

| Op | Name | Effect |
|----|------|--------|
| `0x3c` | `CCTB` | Queue camera job (rail bind `0x40` → `camALL` group) |
| `0x42` / `0x4b` | `CAMDR2` / `CAMDR` | Camera director |
| `0x44` | `SHDWLT` | Shadow / light words |
| `0x46` / `0x47` | `SKYKD` / `SKYTB` | Sky kind / sky table |
| `0x4c` | `GGCOL` | Colour (two args) |
| `0x4f` | `TEXCHG` | Texture change |
| `0x28` | `WLTB` | Six floats (world / light) |

`SCNINIT` (`0x10`) resets camera slots and scores at scene start.

### Reconstructing a frame (this tool)

No `-r` / `--render` flag. To match what the exe would draw for one camera pose:

1. `-c` on `camALL.rbh` — `sample_camera_group` evaluates the six Hermite tracks at integer frame `t`; camera at tracks 0–2, look-at 3–5. `collect_rail_segments` resolves a `−1` start.
2. `-m` on `worldN.rbh` — stage OBJ in stage space (no `+0x20` bake). `usemtl page_N` → `-p` PNG. World quads are strip-ordered; do not fan-split them the way CREAT quads split.
3. `-m` on `CREAT1.RBH` / `CREAT2.rbh` plus [creatures.md](creatures.md) skeleton walk and a [motion.md](motion.md) clip frame. Instance each bone with the type-row scale.
4. `-p` on `B_RED.VMC` (or `bigger.vmc`) — RGB555 pages; treat `0x0000` / `0x8421` as clear.
5. `-s` on `spr.rbh` — HUD / FX quads on the same pages.
6. `-e` on `evtALL.rbh` — which `camGroup` / frame window, sky, and spawns are live.

Facing (`PrimFacingTest` (`FUN_00578f60`)), clip outcodes, and `flags & 0x200` are exe-only; the OBJ dump keeps every prim. Overlay zoom / shake / 2P blend only if matching the exe rather than the authored rail. Projection scale is live zoom ([cameras.md](cameras.md)), not a constant in the rail file.

---

## Enemy spawn, AI, scoring, and collision (`THOTD.exe`)

How the PC / Tantalus engine creates enemies, ticks their AI, awards score, and resolves gun hits. On-disk spawn records stay in [events-detailed.md](events-detailed.md); creature meshes / type rows in [creatures.md](creatures.md); the draw path in [game-rendering.md](game-rendering.md).

This note is **not** a CLI flag. Pair `-e` on `evtALL.rbh` with the exe tables below. Decomp: `hotd-decomp/THOTD-exe-commented.c`. Bytes checked against `hotd-exe/THOTD.exe` (PE32, image base `0x400000`, 8855552 bytes).

PE map (Watcom sections, `VirtualSize` is 0; use `SizeOfRawData`):

| Section | RVA | File | Role |
|---------|-----|------|------|
| `BEGTEXT` | `0x00010000` | `0x400` | Code. VA `0x41xxxx`…`0x56xxxx` |
| `DGROUP` | `0x001A0000` | `0x187400` | Data. VA `0x5A0000`…; file = `0x187400 + (VA − 0x5A0000)` |
| `.bss` | `0x00870000` | *(none)* | Runtime globals (`DAT_00d9fxxx`, `DAT_00daxxxx`) |

### Two type ids

Event `typeId` and creature type are **different namespaces**:

| Table | VA | Count | Indexed by |
|-------|----|------:|------------|
| Spawn functions | `DAT_005d8118` | **136** nonzero / 256 slots (max live index 225) | `ENTB` record `+0x00` |
| Creature stats | `DAT_005d46ac` | 94 × `0x4C` (92 rows with nonzero model/radius/scale) | `entity+0xd2 >> 16` after spawn init |

`ENTB` (`EvtOpEntb` (`FUN_0046e5c8`), handler for op `0x0a`) does `call DAT_005d8118[*(record+0)]`. Slot 100 (Stage 01 example) is `0x4a79cc`. Creature skins, scale, and hit radius come later from `ApplyCreatureTypeStats` (`FUN_00483ad0`) + `DAT_005d46ac`.

### Event VM (spawn source)

Retail `evtALL.rbh`: 9 stage slots, 66 scenes, 522 events, **1653** spawn records (from `-e`, not the exe).

Packed playhead (same as [events-detailed.md](events-detailed.md) / [cutscenes.md](cutscenes.md)):

| Address | Role |
|---------|------|
| `DAT_00da0cf4` | StageNo |
| `DAT_00da0cf3` | SceneNo |
| `DAT_00da0cf0` | EventNo |
| `DAT_00da0ab8` | PC into BODY |
| `DAT_00da0a98` | Yield flag (wait ops) |
| `DAT_00d5a5d0` | evtALL BODY base |

Bind `BindEventPlayhead` (`FUN_004c0d3c`): `PC = stages[StageNo][SceneNo][EventNo]`.

Tick `TickEventVm` (`FUN_004c0db0`): `opcode = *PC`; `call [DAT_005eeac0 + opcode*4]`. Idle / unnamed slots are `EventVmNop` (`LAB_00471658`) (44 of 96). Names are packed C strings at `0x5a3a00` (`0x00 : nop` … `0x5d : NEXTEV`). Exe spellings that differ from the short names in the decoder:

| Op | Exe string | Handler |
|----|------------|---------|
| `0x02` / `0x06` | `ET1P` / `ET2P` (not `ET1P1` / `ET2P1`) | same as `ET1PE` / `ET2PE` families |
| `0x50` | `WAIT_ENNUM/EVCOM/EVTB1` | `EvtOpWaitEnnum` (`FUN_004c0fc4`) — wait while spawn-gen `DAT_00da0ccc` high u16 `<` arg |
| `0x55` | `WAIT_ENALV/EVTB6` | `EvtOpWaitEnalv` (`FUN_004c121c`) — wait while enemies-alive `DAT_00da0cd0` `>` arg |
| `0x1e` / `0x34` / `0x59` | `PLTB` / `BRTB` / `EBLFNSH` | **nop** (`EventVmNop` (`LAB_00471658`)) — names only |

`ET1PE`…`ET1P3` / `ET2PE`…`ET2P3` share two handlers (`EvtOpEt1pSpawn` (`FUN_0046e548`) / `EvtOpEt2pSpawn` (`FUN_0046e588`)). `TEXCHG` (`0x4f`) shares `EvtOpGgsetTexchg` (`FUN_004c1514`) with `GGSET`.

### Spawn path

```
ENTB* list  →  DAT_005d8118[typeId]  →  `AllocEntity` (`FUN_0043e400`)  →  copy record
                                                    →  `ApplyCreatureTypeStats` (`FUN_00483ad0`) (if creature)
                                                    →  `InitSpawnedCreature` (`FUN_004a5180`) / species init
                                                    →  `ClaimEnemyLiveSlot` (`FUN_0046ee90`) live slot
```

1. **Allocate** `AllocEntity` (`FUN_0043e400`): writes `DAT_005cd2fc = 0x1a`, links a child node, unique id at `DAT_00d6ca20`. Gameplay fields run well past that header (past `+0x3cc`).
2. **ENTB copy** (`EvtOpEntb` (`FUN_0046e5c8`), bytes at `0x46e628`):
   - `record+0x04 | 1` → `entity+0x60`
   - `record+0x24` (u8) → `entity+0xd4` (`spawnEventId`)
   - `record+0x25` → `entity+0x6c`
   - `record+0x22` (u16) → **both** `entity+0x78` and `+0x7a` (combat HP)
   - `record+0x20 & 3` = posMode: `0` copies six floats from `+0x08` (XYZ + RX/RY/RZ); `1`/`2` transform
3. **Type stats** `ApplyCreatureTypeStats` (`FUN_00483ad0`): `entity+0x60 |= 0x401`; `DAT_005d46ac[type]+0x00` → `+0x5c` (model); `+0x14` fld → `fstp [entity+0x98]`; `+0x28` → scale at `+0x9c`.
4. **Live registry** `InitSpawnedCreature` (`FUN_004a5180`) increments u16 `DAT_00da0ccc+2` (spawn generation) and `DAT_00da0cd0` (enemies-alive), then `ClaimEnemyLiveSlot` (`FUN_0046ee90`) claims slot **2..12** (`eax < 0x0D`) in `DAT_00da0040` (stride `0x14`), stores index at `entity+0x2ef`.
5. Stage reset `ResetStageEnemyCounts` (`FUN_004c1524`) zeros `DAT_00da0cd0` / spawn-tracking. `SCNINIT` (`EvtOpScninit` (`FUN_004c15b4`)) resets camera slots (and related score/camera globals) at scene start.

Some FX spawners cap children with `DAT_005d7f6c < 9` (BSS; zero in the image). Secondary waves still go through `AllocEntity` (`FUN_0043e400`) (`SpawnSecondaryWave` (`FUN_00482bf8`), `SpawnSecondaryWaveB` (`FUN_004822b8`), `SpawnSecondaryWaveC` (`FUN_004815a4`), `SpawnSecondaryWaveD` (`FUN_0047e664`), bonus `SpawnBonusWave` (`FUN_004ea460`) / `SpawnBonusWaveB` (`FUN_004c4c60`)).

Record layout: [events-detailed.md](events-detailed.md) (`ENTB` 0x28 bytes, `ENTB2` 8 bytes, `ENTBE` ≥ 0x24).

### Behavior

`entity+0x00` is the tick callback. `InitSpawnedCreature` (`FUN_004a5180`) (20-way on `spawnEventId`) installs it, logs `ENGuard_BO_zonbiman` when type `== 0x10`, and claims the live slot. Shared per-frame body: `TickEnemyShared` (`FUN_00477b00`) (skeleton sample `SampleSkeleton` (`FUN_004776c8`), transform, cull, submit).

| Function | Role |
|----------|------|
| `EnemyQuadraticPathXyz` (`FUN_0046a91c`) / `EnemyQuadraticPathXyzAlt` (`FUN_0046a984`) | Quadratic path; waypoints at `+0x39c…+0x3b0`, duration `+0x2f8`; writes XYZ |
| `EnemyQuadraticPathVelocity` (`FUN_0046ab60`) / `EnemyQuadraticPathVelocityAlt` (`FUN_0046ac40`) | Same spline → velocity `+0x80/+0x84/+0x88` |
| `EnemyPickTargetPlayer` (`FUN_0046ae0c`) | Target player `+0x2f0` = P1 / P2 / random; skips a gun if `DAT_00da0cb4/cb5` (grab lock) |
| `EnemyFacePlayerQuadrant` (`FUN_0046ad04`) / `EnemyFacePlayerQuadrantAlt` (`FUN_0046ada0`) | Quadrant vs player XZ `DAT_00d9f038/040`; yaw `0 / 0x4000 / 0x8000 / 0xc000` |
| `FindNearestAlliedZombie` (`FUN_0046b4a8`) | Nearest allied zombie in the live-slot table (homing) |
| `ClampEnemyToScreenWalls` (`FUN_0046af9c`) | Clamp X/Z to screen walls `DAT_00da0bac/b9c/ba8/ba4`; damp velocity; `+0x32c` bit 7 |
| `ClampEnemyToDepthWall` (`FUN_0046b27c`) | 3D wall: if depth `>` `DAT_00da0ba4`, clamp and damp |
| `EnemyAfterEmergeWalkAttack` (`FUN_004a4e2c`) | After emerge: walk/attack layers; default tick `EnemyDefaultTick` (`LAB_004d9a90`) |
| `EnemyPatrolAi` (`FUN_004a3578`) | Patrol AI when `DAT_00da0bd8 == 2` (bonus / time-attack) |
| `EnemyAttackPhases` (`FUN_004fe320`) | Attack phases via `+0x340` |
| `EnemyGrabLunge` (`FUN_004fe53c`) | Grab: aim, 30-frame quadratic lunge, wall-clamp, sink, release |
| `EnemyBuriedEmerge` (`FUN_00505f50`) | Buried emerge: snap to floor `DAT_00da0b48`; 48 frames then chase |
| `EnemyApplyHitDamage` (`FUN_004fe118`) | Hit tick: if `+0x61` bit 0, subtract damage u16 from `+0x78` |
| `EnemyDeath` (`FUN_004a3064`) | Death: clear live bit, `DAT_00da0cd0 -= 1`, swap vtable |
| `EnemyDefeatScore` (`FUN_004aba08`) | Defeat: `DAT_00da0cd6` / `DAT_00da0cc6` += 1; **+400** score if player state `DAT_00d9f05c == 5` (`call `AddPlayerScore` (`FUN_00437344`)` with `edx = 0x190`) |
| `EnemyKnockdown` (`FUN_004d94b0`) | Knockdown: Y vel −0.5, sink, wait `0x28` frames, despawn |

Motion names: 674 pointers at `DAT_005f1258`, first `MO_b1_atk_a`, last `MO_z_ono_kick`. Prefix counts from this exe: `z` 192, `k` 80, `p` 53, `saru` 49, `ebitb` 39, `boss4` 32, `b3` 28, `b1` 23, `dr` 20, `s` 19, `b2` 16, `mol` 13, `gman` 12, `frog` 11. (`zonbi1` 4 sits beside `z`; `dog`/`inu`/`ddogg*` together match the older “dog/inu 23” grouping.)

Type-row floats checked in this image (matches [creatures.md](creatures.md)):

| Type | Model | Bones | Scale | `+0x14` (hit radius) |
|-----:|------:|------:|------:|---------------------:|
| 1 | `0x71d` | 16 | 0.5 | 8 |
| 2 | `0x71e` | 20 | 1.4 | 5 |
| 18 | `0x3b7` | 16 | 1.0 | 9 |
| 51 | `0x149c` | 18 | 1.0 | 12 |
| 64 | `0` | 28 | 1.0 | 2.6 |
| 76 | `0x1241` | 16 | 1.2 | 2.8 |

Type 0’s `0x4C` row is all zeros; bone count is still 21.

### Scoring

Player block stride **0xCC** (`0x33` dwords). Score `DAT_00d9f064[slot]`, lives `DAT_00d9f068[slot]`, state `DAT_00d9f05c[slot]`.

`AddPlayerScore` (`FUN_00437344`): `score += edx`, clamp at 0. Confirmed: `add eax, 0x00d9f058` then `[eax+0x0c]` is `DAT_00d9f064`.

| Event | Function | Effect (this exe) |
|-------|----------|-------------------|
| Hit-zone tree | `ScoreHitZoneTree` (`FUN_004c3d58`) → `ScoreHitZoneApply` (`FUN_004c4168`) | Per-type tables `DAT_00523a58` / `DAT_00527344` / `DAT_00538d44` (in `BEGTEXT`). Damage u16 lands in `DAT_00da0cc4` (`DAT_00da0cc2` high word). Route totals `DAT_00da6244`. |
| Kill | `EnemyDefeatScore` (`FUN_004aba08`) | Counters += 1; **+400** if `DAT_00d9f05c[player] == 5` |
| Life lost | `LoseLife` (`FUN_00436fe4`) | `dec` lives; `sub ebp, 0x64` (−100 score, floor 0); continue timer `DAT_00d9f050 = 0x5a` (90 frames) |
| Shot outside rect | `ShotMissOutsideRect` (`FUN_004371b8`) | Perspective-divide vs `DAT_005a1ba2…`; miss path calls `LoseLife` (`FUN_00436fe4`) then another −100 |
| 1UP | `ExtraLife` (`FUN_00437304`) | Lives += 1 if below cap `DAT_00da0cec` |
| HUD digits | `DrawHudScoreDigits` (`FUN_0051a598`) | `cmp esi, 99999` (`0x1869f`); sprite **`0x589` + digit** (six immediates in the function). Lives sprite `0x4f0`; labels `0x504` / `0x505` in the same HUD cluster |

`DAT_00d9f05c == 5` is the “this player is in the scoring/playing state” gate used by kill bonus and several route helpers — not a difficulty id.

High scores: string `scores.cfg` at VA `0x5a1118`, pointer `DAT_005ce8b0`. Load/reset and write live in the UI cluster around `SortHighScores` (`FUN_0042556c`) (sort **10** entries, stride **`0x1c`**: `cmp ebx, 0x0A` / `imul eax, ebx, 0x1C`). Insert `InsertHighScore` (`FUN_004b4bf8`) uses thresholds `DAT_005d29d8 = 14000` and `DAT_005d29cc = 16000`. Fatal: `Failed to write highscores file=%s` (spaces, not underscores). Grade `GradeFromTime` (`FUN_00420004`): float ≤ `DAT_005ce4c0` (**200**) → `'X'` (`0x58`); ≤ `DAT_005ce4c4` (**300**) → `'Y'`; else `'Z'`.

### Collision (gun hits)

Not a mesh ray. Per-frame sphere queue, then a separate stage-mesh ray for player plant / aim point.

| Step | Function | This exe |
|------|----------|----------|
| Clear | `ClearGunHitQueue` (`FUN_00489b94`) | Zeros `DAT_00da39f0` (0x24-byte results, `add eax, 0x24` loop), `DAT_00da25f0` depth keys, `DAT_00da2df0` candidates |
| Enqueue | `EnqueueGunHitCandidate` (`FUN_00489c18`) via `ProjectHitSphereCenter` (`FUN_00483c10`) | Live bit `+0x60` bit 0; projected center at `+0x40/+0x44/+0x48` |
| Per player | `ProcessPlayerGunShots` (`FUN_00489c84`) | `test ah, 2` on `DAT_00d9f060` (shot this frame); `call `TestGunHitSphere` (`FUN_00489d0c`)`; `and byte […+DAT_00d9f060], 0xFD` |
| Sphere | `TestGunHitSphere` (`FUN_00489d0c`) → `SphereHitTest` (`FUN_00414aac`) | `push [ebp+0x98]` as radius; `push [ebp+0x40/44/48]`. If `DAT_005ced98 == 5`, radius × CRT/lightgun table |
| Children | `WalkChildHitVolumes` (`FUN_00489e2c`) | Tree at `entity+0xd0`; count `[tree+0x34]`; only if `entity+0x74` bit 0 |
| Sort | `SortHitsByDepth` (`FUN_0048a44c`) | `sub esp, 0x400` (256-int histogram); 16-pass radix on packed depth |
| Apply | `ApplyGunHits` (`FUN_00489fbc`) | Sets `+0x60` player bit and `+0x61` bit 0; hit XYZ in `DAT_00d9ef60`; optional splatter `SpawnHitSplatter` (`FUN_0046bf8c`) |

**`DAT_005d46ac+0x14` is the hit-sphere radius, not combat HP.** `ApplyCreatureTypeStats` (`FUN_00483ad0`) `fstp`s it to `entity+0x98`; `TestGunHitSphere` (`FUN_00489d0c`) pushes that float into `SphereHitTest` (`FUN_00414aac`). Combat HP is the ENTB u16 at `+0x22` → `entity+0x78`, drained by `EnemyApplyHitDamage` (`FUN_004fe118`) (`mov si, [ebx+0x78]; sub si, cx` with `cx` from `DAT_00da0cc4`). Magician 12 vs Hermit 2.6 is aim-circle size.

Stage plant: `RaycastStageFloor` (`FUN_0048a15c`) walks collision-mesh slots (`DAT_00da0bb4`). Camera path uses ray `(eye.x, 32768, eye.z)` — same Y as the shadow pass ([game-rendering.md](game-rendering.md)). Screen-space helper `ScreenSpaceHitKind` (`FUN_0043db5c`) returns 1 / 2 / 4 (off / graze / solid).

Collision tree alloc: `AllocCollisionTree` (`FUN_00478b64`) from skeleton `DAT_005ef8e0[type]`, pointer at `entity+0xd0`. Same tree is walked for scoring (`ScoreHitZoneTree` (`FUN_004c3d58`)).

### Entity field map

Offsets from the callers above (BSS entity, not a file struct).

| Offset | Field | Set by | Read by |
|--------|-------|--------|---------|
| `+0x00` | Tick vtable | `InitSpawnedCreature` (`FUN_004a5180`) / death | Entity pump |
| `+0x28/+0x2c/+0x30` | XYZ | ENTB / path tick | Draw, AI, collision |
| `+0x34/+0x38/+0x3c` | Fixed-point RX/RY/RZ | ENTB / quadrant | Matrix |
| `+0x40/+0x44/+0x48` | Hit-sphere center | `ProjectHitSphereCenter` (`FUN_00483c10`) | `SphereHitTest` (`FUN_00414aac`) |
| `+0x5c` | CREAT model id | `ApplyCreatureTypeStats` (`FUN_00483ad0`) / spawnEventId maps | Draw `EnqueueOpaqueIfLive` (`FUN_0043d7f8`) |
| `+0x60` | Flags (bit 0 live; bits 1–2 P1/P2 hit) | ENTB, `ApplyGunHits` (`FUN_00489fbc`) | Enqueue / death |
| `+0x61` bit 0 | Hit this frame | `ApplyGunHits` (`FUN_00489fbc`) | `EnemyApplyHitDamage` (`FUN_004fe118`) |
| `+0x74` bit 0 | Walk child volumes | Spawn init | `TestGunHitSphere` (`FUN_00489d0c`) |
| `+0x78` | Combat HP (s16) | ENTB `+0x22` | `EnemyApplyHitDamage` (`FUN_004fe118`) |
| `+0x80/+0x84/+0x88` | Velocity | Spline / jitter | Wall clamp |
| `+0x98` | Hit radius (f32) | Type table `+0x14` | `SphereHitTest` (`FUN_00414aac`) |
| `+0x9c` | Scale | Type table `+0x28` | Submit |
| `+0xd0` | Collision tree | `AllocCollisionTree` (`FUN_00478b64`) | Hits + score tree |
| `+0xd4` | spawnEventId | ENTB `+0x24` | AI / waves |
| `+0x2ef` | Live-slot index | `ClaimEnemyLiveSlot` (`FUN_0046ee90`) | Homing scan |
| `+0x2f0` | Target player | `EnemyPickTargetPlayer` (`FUN_0046ae0c`) | Score / grab |
| `+0x3cc` | Path / death flags | `EnemyQuadraticPathXyz` (`FUN_0046a91c`) | Knockdown |

Globals: `DAT_00da0cd0` enemies-alive (`WAIT_ENALV`), `DAT_00da0ccc` high u16 spawn generation (`WAIT_ENNUM`), `DAT_00da0cd6` / `DAT_00da0cc6` kill counters, `DAT_00d9f038/03c/040` player XYZ, `DAT_00da0b48` floor (`FKRTB`).
