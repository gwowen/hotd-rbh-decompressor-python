# Agent guide — hotd-decompress

uv + Python **decompression** CLI for House of the Dead (PC / Tantalus) PIFF assets.

Core job: expand Tantalus `PACK` → `BODY` (LZ) and write decoded payloads under `decompressed_assets/` (decompressed PIFF, PNG pages, WAV clips, OBJ meshes, JSON tables). Inspection (`uv run hotd-decompress <file.rbh>`) is a helper, not the product.

This tree is a port of the Bun/TypeScript CLI (`../typescript/hotd-decompress`). Prefer matching that implementation over inventing format variants.

## Stack

- Run with `uv` (Python 3.12+, src layout). No runtime third-party packages.
- Prefer small focused modules under `src/hotd_decompress/`; keep `cli.py` as CLI only.
- Match existing style: explicit types, little abstraction, comments only for format offsets / decomp anchors.

## Source of truth for formats

Behaviour and layouts come from the TypeScript port and `hotd-decomp/THOTD-exe-commented.c` in the sibling TypeScript tree (e.g. PACK/LZ, VVTP pages, blood-colour remapping, sound init / `sound\O_%s.rbh` requests). Prefer verifying against that decomp over inventing format variants.

CD music is MCI `cdaudio` in the exe and is **not** in `assets/sound/`.

## Hard constraints

- **`assets/` is often read-only.** Default outputs under `decompressed_assets/` (`*.decomp.*`, `*_png/`, `*_wav/`, `*_mesh/`, `*_spr/`, `*_evt/`, `*_cam/`), never write beside inputs under `assets/` unless the user asks.
- **HotD PIFF is not RIFF-padded.** Do not reintroduce odd-size chunk padding between chunks.
- **Do not commit** game assets (`assets/` is gitignored), `decompressed_assets/`, or large dumps (see `.gitignore`).
- **Do not redistribute** proprietary game files.
- Format notes for humans live in `decompress-knowledge/`; keep those in sync when PACK/BODY layouts change.

## Module map

| Module | Responsibility |
|--------|----------------|
| `src/hotd_decompress/piff.py` | Load/serialize PIFF; **decompress** `PACK` → `BODY` |
| `src/hotd_decompress/pack.py` | `u16 unc` / `u16 cmp` / LZ payload hunks |
| `src/hotd_decompress/lz.py` | Signed varint + LZ back-refs (`FUN_00410d3c` family) |
| `src/hotd_decompress/rbh.py` | RBHF summary: RBHH, BODY, RELC, pointer roots |
| `src/hotd_decompress/texture.py` | Detect/parse VVTP RGB555 pages; PNG decode |
| `src/hotd_decompress/png.py` | Minimal PNG writer used by texture decode |
| `src/hotd_decompress/audio.py` | Sound RBH parse (`O_*`, `gamesnds`); WAV decode |
| `src/hotd_decompress/wav.py` | Minimal PCM WAV writer used by audio decode |
| `src/hotd_decompress/mesh.py` | World/CREAT mesh parse (`FUN_00578bb0` prims); OBJ decode |
| `src/hotd_decompress/sprite.py` | `spr.rbh` UV/page frame table; JSON decode |
| `src/hotd_decompress/event.py` | `evtALL.rbh` stage/scene/section scripts; opcode + spawn + CCTB JSON decode |
| `src/hotd_decompress/camera.py` | `camALL.rbh` Hermite rail tracks; JSON decode |
| `src/hotd_decompress/binary.py` | Shared little-endian readers / 4-char tags |
| `src/hotd_decompress/cli.py` | CLI flags and default output paths |

## Asset facts (do not reverse incorrectly)

- `.vmc` = VVTP texture banks. `.rbh` = RBHF (meshes, events, sprites, audio, etc.).
- `spr.rbh` is **sprite metadata**, not texture pixels — PNG export needs a `.vmc`.
- Creature banks under `assets/art/stage1/creature/`:
  - `B_RED` / `B_GREEN` / `B_BLUE` / `B_YELLO` / `B_PURPL` = same 421-page bank, blood-colour remaps (PC `bloodcolor`).
  - `bigger.vmc` = uncompressed `BODY` bank (same page count; not byte-identical to a decompressed `B_*`).
  - `TEXTURE.VMC` = game load path; may be a stub in this tree.
- Texture clear colours: `0x0000` and `0x8421`. Format is RGB555 (+ `0x8000` bit as in engine).
- Digital SFX under `assets/sound/` (exe init `FUN_00411f10`: 11025 Hz, 8-bit; 3 mixer voices — not channel count in the files):
  - `O_*.rbh` — oneshoot: RBHH `flags=0`, one `BODY`. Header `u32 0x00082c30`, `u16 2`, `u16 soundId`, then unsigned 8-bit mono PCM (silence ≈ `0x80`).
  - `gamesnds.rbh` — bank: RBHH `flags=2` then `0` → 0x28-byte index entries + sample `BODY`. Embedded rows use `+0x18` as sample offset; external rows use `+0x18 == 0x00082c30` and `+0x14` as `O_*` soundId (WAV export resolves siblings in the same directory).
  - These sound RBHs are already uncompressed (`BODY` only; no `PACK`).
- Mesh RBHs (`world*.rbh`, `CREAT*.rbh`): RBHH flags `2,0,0` → BODY0 graph + BODY1 float3 verts (+ empty BODY2). Creat id table is 8-byte entries until `id == -1`; world is `{id, flag, nodePtrs…, 0}` until `id == 0`. Prim batches: `flags & 0x2007` selects plain/textured tri/quad (`FUN_00578bb0`). World node `+0x20` XYZ is metadata — verts are already stage-space (do not bake as a translate).
- `evtALL.rbh` / `camALL.rbh`: single `flags=2` BODY pointer graphs. Camera tracks are `{u16 keyCount, u16 channelId}` + Hermite keys `{t, value, slopeIn, slopeOut}`.

## CLI contract

```text
uv run hotd-decompress --usage|--help|-h                  # flag help
uv run hotd-decompress -d|--decompress <file> [output]    # PACK→BODY (core)
uv run hotd-decompress <file.rbh>                         # inspect RBHF (helper)
uv run hotd-decompress -p|--png <file.vmc|rbh> [outdir]   # decompress pages → PNG
uv run hotd-decompress -w|--wav <file.rbh> [outdir]       # decompress SFX → WAV
uv run hotd-decompress -m|--mesh <file.rbh> [outdir]      # decompress mesh → OBJ
uv run hotd-decompress -s|--sprites <file.rbh> [outdir]   # decompress spr.rbh → JSON
uv run hotd-decompress -e|--evt <file.rbh> [outdir]       # decompress events → JSON
uv run hotd-decompress -c|--cam <file.rbh> [outdir]       # decompress cameras → JSON
```

Default outputs:

- decompress → `decompressed_assets/<name>.decomp.<ext>`
- png → `decompressed_assets/<stem>_png/page_XXXX.png`
- wav → `decompressed_assets/<stem>_wav/*.wav` (`O_NAME.wav`, or `clip_XXX.wav` / `ext_XXX_O_NAME.wav` for `gamesnds`)
- mesh → `decompressed_assets/<stem>_mesh/ids.json` + `node_XXXXXX.obj`
- sprites → `decompressed_assets/<stem>_spr/sprites.json`
- evt → `decompressed_assets/<stem>_evt/events.json`
- cam → `decompressed_assets/<stem>_cam/cameras.json`

Keep flags and default output naming stable unless the user requests a change.

## When changing format code

1. Test against a known packed VMC (`B_RED.VMC`), an already-unpacked RBH (`evtALL.rbh` / `spr.rbh` / `world1.rbh` / `CREAT1.RBH` / `camALL.rbh`), and sound (`O_HELP.rbh`, `gamesnds.rbh`).
2. Prefer round-trip or page/clip/node-count checks over large binary dumps in the repo.
3. If both a fix and an exploit/PoC are requested for unrelated systems, only do the project-relevant fix — this repo is a decompression tool, not offensive tooling.
