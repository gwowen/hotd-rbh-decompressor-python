# hotd-decompress

Decompression CLI for the PC port of *The House of the Dead* (Tantalus / SEGA).

Expands Tantalus `PACK` chunks to `BODY` (LZ) and writes decoded assets under `decompressed_assets/` — decompressed PIFF, texture PNGs, SFX WAVs, mesh OBJ, and JSON for sprites / events / cameras.

Built with [uv](https://docs.astral.sh/uv/) and Python 3.12+. Formats are reverse-engineered against the TypeScript reference implementation and `hotd-decomp/THOTD-exe-commented.c` in the sibling TypeScript tree. Layout notes: `decompress-knowledge/`.

This is a Python port of the Bun CLI at `../typescript/hotd-decompress`. Game assets are not duplicated here.

## Setup

```bash
uv sync --group dev
```

Game assets belong under `assets/` (often read-only, gitignored). The tool never writes back into `assets/` by default; all decompressed output goes under `decompressed_assets/`.

If you already have the TypeScript tree, symlink assets instead of copying:

```bash
ln -s ../../typescript/hotd-decompress/assets assets
```

## Usage

```bash
# Flag help (--usage, --help, or -h)
uv run hotd-decompress --usage

# Expand PACK → BODY (Tantalus LZ) and write a decompressed PIFF
# → decompressed_assets/B_RED.decomp.VMC
uv run hotd-decompress -d assets/art/stage1/creature/B_RED.VMC
uv run hotd-decompress --decompress path/to/file.vmc out.decomp.vmc

# Summarize an .rbh (headers / BODY / PACK / RELC)
uv run hotd-decompress assets/sprite/spr.rbh

# Decompress VVTP RGB555 texture pages to PNG
# → decompressed_assets/B_RED_png/page_XXXX.png
uv run hotd-decompress -p assets/art/stage1/creature/B_RED.VMC
uv run hotd-decompress --png path/to/file.vmc my_outdir

# Decompress digital SFX to WAV (8-bit mono @ 11025 Hz)
# → decompressed_assets/O_HELP_wav/O_HELP.wav
uv run hotd-decompress -w assets/sound/O_HELP.rbh
# → decompressed_assets/gamesnds_wav/clip_XXX.wav (+ ext_* from sibling O_*.rbh)
uv run hotd-decompress --wav assets/sound/gamesnds.rbh

# Decompress world / creature meshes to OBJ + ids.json
# → decompressed_assets/world1_mesh/
uv run hotd-decompress -m assets/art/stage1/world/world1.rbh
uv run hotd-decompress --mesh assets/art/stage1/creature/CREAT1.RBH

# Decompress sprite metadata (UV/page frames; pixels are in .vmc)
# → decompressed_assets/spr_spr/sprites.json
uv run hotd-decompress -s assets/sprite/spr.rbh

# Decompress event scripts / camera rails to JSON
uv run hotd-decompress -e assets/evt/allstage/evtALL.rbh
uv run hotd-decompress -c assets/cam/allstage/camALL.rbh

# One-shot: every typed asset under assets/ → decompressed_assets/
uv run hotd-decompress --all
uv run hotd-decompress --all assets decompressed_assets

# One type for the whole tree (or a subdirectory)
uv run hotd-decompress -p --all
uv run hotd-decompress -w --all
uv run hotd-decompress -m --all assets/art
uv run hotd-decompress -s --all
uv run hotd-decompress -e --all
uv run hotd-decompress -c --all
uv run hotd-decompress -d --all          # packed PIFF only (skips BODY-only files)
uv run hotd-decompress -p assets/art     # directory → all .vmc under it
```

`uv run python -m hotd_decompress` is equivalent to `uv run hotd-decompress`.

| Flag | Purpose |
|------|---------|
| `--usage` / `--help` / `-h` | Print flag help and exit |
| `-d` / `--decompress` | Expand `PACK` → `BODY`, write decompressed PIFF |
| *(none)* `<file.rbh>` | Inspect RBHF (headers, BODY/PACK/RELC) |
| `-p` / `--png` | Decompress VVTP RGB555 pages to PNG (`PACK` expanded if needed) |
| `-w` / `--wav` | Decompress `assets/sound/` SFX to unsigned 8-bit mono WAV @ 11025 Hz |
| `-m` / `--mesh` | Decompress world/CREAT mesh RBHs to OBJ + `ids.json` |
| `-s` / `--sprites` | Decompress `spr.rbh` metadata to `sprites.json` |
| `-e` / `--evt` | Decompress event script bank to `events.json` (opcodes, spawns, camera binds) |
| `-c` / `--cam` | Decompress camera rail bank to `cameras.json` |
| `-a` / `--all` | Walk `assets/` (or a directory) and decode every matching file. Combine with a type flag (`-p --all`) to limit to one kind. A type flag given a directory does the same walk. |

`--all` uses the same per-file output names as the single-file flags (`<stem>_png/`, `<stem>_wav/`, …). It does **not** write `.decomp.*` PIFF unless you pass `-d --all` (typed flags already expand `PACK` in memory). `TEXTURE.VMC` stubs and already-unpacked files are skipped.

`--png` writes `page_XXXX.png` (one file per texture page id). `spr.rbh` is sprite metadata only — decompress a `.vmc` bank for pixels.

`--wav` accepts oneshoot `O_*.rbh` or `gamesnds.rbh`. For the bank, sibling `O_*.rbh` files resolve external refs. CD music is separate (not in these files).

`--mesh` writes one `node_XXXXXX.obj` per unique mesh node plus `ids.json` (model id → node map). Materials reference `page_<id>` (pair with `-p` on the matching `.vmc`).

## Tests

```bash
uv run pytest
```

Asset goldens (`pytest -m assets`) skip unless `assets/` exists (or `HOTD_ASSETS` is set). They compare against the TypeScript CLI when `bun` is available.

## Asset map

| Path | Kind | Notes |
|------|------|--------|
| `assets/art/stageN/world/worldN.rbh` | Stage geometry | Mesh RBH → `-m` |
| `assets/art/stage1/creature/CREAT*.rbh` | Creature meshes / data | Mesh RBH → `-m` |
| `assets/art/stage1/creature/*.vmc` | Creature texture banks (VVTP) | See below |
| `assets/sprite/spr.rbh` | Sprite metadata | `-s` for JSON; use `.vmc` for PNGs |
| `assets/evt/…` | Events | `-e` → `events.json` |
| `assets/cam/…` | Cameras | `-c` → `cameras.json` |
| `assets/sound/O_*.rbh` | Oneshoot SFX / voice | 8-byte header + unsigned 8-bit mono PCM @ 11025 Hz |
| `assets/sound/gamesnds.rbh` | SFX bank + index | Embedded clips + refs to `O_*` by id |

### Creature `.vmc` banks

All are PIFF form `VVTP` (256×256 RGB555 pages):

| File | Meaning |
|------|---------|
| `TEXTURE.VMC` | Path the game loads (`ART\STAGE1\CREATURE\texture.VMC`). May be a stub in this tree. |
| `bigger.vmc` | Full uncompressed bank (`BODY` chunks, ~53 MB, 421 pages). |
| `B_RED` / `B_GREEN` / `B_BLUE` / `B_YELLO` / `B_PURPL` | Same bank, LZ-`PACK`ed, pre-baked for each PC **blood colour** setting (registry `bloodcolor`, 5 options). Differ mainly on ~38 blood pages; other pages match. |

### Sound banks

- Engine digital audio is **11025 Hz, 8-bit** (`FUN_00411f10`). The “3 channels” in init are mixer voices, not stereo in the files.
- `O_*.rbh` — single clip; RBHH `flags=0`. Loaded at runtime as `sound\O_%s.rbh`.
- `gamesnds.rbh` — index `BODY` (0x28-byte rows, rate `0x2b11`) + sample `BODY`. Already uncompressed (no `PACK`).
- Stage / menu **music** is CD audio via MCI in the exe, not these RBHs.

## Formats (short)

- **PIFF** — RIFF-like container. HotD does **not** use RIFF odd-size padding between chunks. Forms include `RBHF` (`.rbh`) and `VVTP` (`.vmc`).
- **PACK** — compressed `BODY` via Tantalus LZ (signed varints + back-references). See `src/hotd_decompress/lz.py` / `pack.py`.
- **VVTP page** — 0x40-byte header + tightly packed RGB555 (`0x8000` bit present). Clear / transparent: `0x0000` and `0x8421`.
- **Sound oneshoot** — `BODY` starts with `u32 0x00082c30`, `u16 2`, `u16 soundId`, then unsigned 8-bit mono PCM (silence ≈ `0x80`).
- **Mesh** — world/CREAT share BODY0 graph + BODY1 float3 pool; prim batches from `FUN_00578bb0` (plain/textured tri/quad).
- **Sprites** — pointer table of UV/page frame records (`DAT_005ce544`).
- **Events / cameras** — nested pointer graphs; cameras store Hermite-like `{t,value,slopeIn,slopeOut}` keys per channel.

## Layout

```
src/hotd_decompress/cli.py     CLI (including --all batch)
src/hotd_decompress/discover.py Walk assets/ and classify by decode kind
src/hotd_decompress/piff.py    PIFF load / serialize / PACK→BODY decompress
src/hotd_decompress/pack.py    PACK hunk unpack
src/hotd_decompress/lz.py      Tantalus LZ
src/hotd_decompress/rbh.py     RBHF inspect (headers, BODY, RELC, pointers)
src/hotd_decompress/texture.py VVTP page parse + PNG decode
src/hotd_decompress/png.py     Minimal PNG encoder
src/hotd_decompress/audio.py   Sound RBH parse + WAV decode
src/hotd_decompress/wav.py     Minimal PCM WAV encoder
src/hotd_decompress/mesh.py    World/CREAT mesh parse + OBJ decode
src/hotd_decompress/sprite.py  Sprite bank parse + JSON decode
src/hotd_decompress/event.py   Event script parse + opcode / spawn / CCTB JSON decode
src/hotd_decompress/camera.py  Camera rail parse + JSON decode
decompress-knowledge/          Format notes (RBH + each asset type)
assets/                        Game data (gitignored; symlink or copy)
decompressed_assets/           Default output (gitignored)
```

## License / assets

This is a decompression tool for research and personal use. Game assets remain property of their respective owners; do not redistribute them. `assets/` and `decompressed_assets/` are gitignored.
