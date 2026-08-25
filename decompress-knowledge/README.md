# Decompress knowledge

How *The House of the Dead* (PC / Tantalus) stores assets, and how this CLI decompresses them.

Formats come from `hotd-decomp/THOTD-exe-commented.c` and the parsers in `src/`. All multi-byte integers are **little-endian**.

## Reports

Each note covers **on-disk layout** and **what the tool does** (modules, flags, output names). Combined dump: [decompress-qwen.md](decompress-qwen.md).

| File | Subject | Flag |
|------|---------|------|
| [piff.md](piff.md) | PIFF container, `PACK` hunks, Tantalus LZ | `-d` |
| [rbh.md](rbh.md) | RBHF (`.rbh`) — headers, BODY, RELC, pointer graphs | *(inspect)* |
| [textures.md](textures.md) | VVTP texture banks (`.vmc`) | `-p` |
| [audio.md](audio.md) | Digital SFX (`O_*.rbh`, `gamesnds.rbh`) | `-w` |
| [meshes.md](meshes.md) | Stage / creature meshes (`world*.rbh`, `CREAT*.rbh`) | `-m` |
| [creatures.md](creatures.md) | Exe types → CREAT ids → VVTP pages (species map) | *(exe tables)* |
| [sprites.md](sprites.md) | Sprite UV/page metadata (`spr.rbh`) | `-s` |
| [events.md](events.md) | Event scripts (`evtALL.rbh`) | `-e` |
| [events-detailed.md](events-detailed.md) | Event VM, opcodes, spawns, `CCTB` → `camALL` | `-e` |
| [cameras.md](cameras.md) | Camera rails (`camALL.rbh`) | `-c` |
| [cutscenes.md](cutscenes.md) | In-engine cutscene playback (evt + cam + draw) | *(exe runtime)* |
| [game-rendering.md](game-rendering.md) | Exe draw path (backends, view, prims, VRAM) | *(exe runtime)* |
| [enemy-systems.md](enemy-systems.md) | Spawn, AI, scoring, gun collision (`THOTD.exe`) | *(exe runtime)* |

## How the tool works

`index.ts` is the only CLI. It never writes into `assets/` unless you pass an output path there. Defaults land under `decompressed_assets/` (gitignored).

```
assets/  (read-only game files)
    │
    ▼
index.ts  ── flag ──►  src/*.ts
    │
    ▼
decompressed_assets/
```

| Flag | Module | What it does |
|------|--------|----------------|
| `-d` / `--decompress` | `src/piff.ts` + `pack.ts` + `lz.ts` | Expand every `PACK` → `BODY`, rewrite PIFF |
| *(none)* `<file.rbh>` | `src/rbh.ts` | Print RBHH / BODY / PACK / RELC / pointer-root summary (no write) |
| `-p` / `--png` | `src/texture.ts` + `png.ts` | Decompress PIFF, decode VVTP pages → PNG |
| `-w` / `--wav` | `src/audio.ts` + `wav.ts` | Parse sound RBH → 8-bit mono WAV |
| `-m` / `--mesh` | `src/mesh.ts` | Parse world/CREAT RBH → OBJ + `ids.json` |
| `-s` / `--sprites` | `src/sprite.ts` | Parse `spr.rbh` → `sprites.json` |
| `-e` / `--evt` | `src/event.ts` | Parse event graph + opcodes → `events.json` |
| `-c` / `--cam` | `src/camera.ts` | Parse camera rails → `cameras.json` |

Two load paths:

1. **PIFF decompress** (`loadPiff` → `decompressPiff`) — used by `-d`, `-p`, `-w`. Packed pages/clips become `BODY` in memory first.
2. **RBHF parse** (`loadRbh`) — used by inspect, `-m`, `-s`, `-e`, `-c`. Expects `BODY` already (retail mesh/sprite/evt/cam files are uncompressed). Run `-d` first if you have a packed copy.

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

## Two containers, many payloads

Every asset this tool reads is a **PIFF** file (RIFF-like, but **not** odd-size padded). The 4-byte form after the PIFF header selects the payload family:

| Form | Extension | Typical contents |
|------|-----------|------------------|
| `RBHF` | `.rbh` | Meshes, sprites, events, cameras, digital SFX |
| `VVTP` | `.vmc` | Texture pages (256×256 RGB555) |

A compressed payload lives in a `PACK` chunk. After LZ expansion it is a `BODY` blob. Uncompressed files already store `BODY` and skip `PACK`.

CD music is MCI `cdaudio` in the exe. It is **not** in `assets/sound/` and is not documented here.

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
