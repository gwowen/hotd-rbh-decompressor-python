# hotd-decompress

Decompression CLI for the PC port of *The House of the Dead* (Tantalus / SEGA).

* THIS IS A REVERSE ENGINEERING PROJECT FOR CURIOSITY ONLY - YOU NEED TO HAVE YOUR OWN COPY OF THE GAME! *

Expands Tantalus `PACK` chunks to `BODY` (LZ) and writes decoded assets under `decompressed_assets/` — decompressed PIFF, texture PNGs, SFX WAVs, mesh OBJ, and JSON for sprites / events / cameras.

Creature type rows, `MO_*` animation clips, and cutscene `SNDON` cues live in `THOTD.exe`, not in PIFF. Library modules and `scripts/` join those tables to the decoded files. They are not CLI flags.

Built with [uv](https://docs.astral.sh/uv/) and Python 3.12+. Formats are reverse-engineered against the game executable. Layout notes: [`decompress-knowledge/`](decompress-knowledge/README.md).

## Setup

```bash
uv sync --group dev
```

Game assets belong under `assets/` (often read-only, gitignored). The tool never writes back into `assets/` by default; all decompressed output goes under `decompressed_assets/`.

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

`--mesh` writes one `node_XXXXXX.obj` per unique mesh node plus `ids.json` (model id → node map). Materials reference `page_<id>` (pair with `-p` on the matching `.vmc`). JSON dumps (`ids.json`, `sprites.json`, `events.json`, `cameras.json`) use indent 2, omit unset optional fields, and write `NaN` / `Infinity` as `null`.

## Exe tables (not CLI flags)

Motion clips and the 94-row creature type table are in `THOTD.exe` DGROUP (image base `0x400000`, DGROUP file offset `0x187400`). Scripts look for the exe at `HOTD_EXE`, else `hotd-exe/THOTD.exe`. Assets come from `HOTD_ASSETS` or `assets/`. Output lands under `decompressed_assets/exe_tables/` (gitignored).

```bash
# 94 types → CREAT mesh ids, VVTP pages, evtALL spawns
# → decompressed_assets/exe_tables/creature-map.json
uv run python scripts/creature_map.py
uv run python scripts/creature_map.py clusters   # page-set clusters
uv run python scripts/creature_map.py more       # type rows 94–127
uv run python scripts/creature_map.py hp         # high-HP / slot-128 spawns

# Each evtALL SNDON joined to DAT_005cbda8 (270 sound-request rows)
# → decompressed_assets/exe_tables/cutscene-cues.json
uv run python scripts/cutscene_cues.py
```

| Module | Role |
|--------|------|
| `creature_map.py` | Type rows, bone counts, skeleton mesh ids, joined to CREAT `texPageId`s and evtALL spawns |
| `motion.py` | `sample_motion_frame` — one integer `MO_*` frame (`ax0, ax1, ax2` per bone). 674 clips; not a PIFF payload |
| `sound_table.py` | `DAT_005cbda8` rows and the `SNDON` cue sheet |
| `rail_timeline.py` | `CCTB` job-`0x40` windows; resolves `startFrame == -1` against `camALL` |

`sample_motion_frame(exe_bytes, motion_index, frame, bone_count)` reads one frame (no blend). The posed Hangedman reference is motion **22** (`MO_b2_base`), frame **0**, 10 bones. Species clip prefixes (`z`, `k`, `b2`, `boss4`, …) are in [creatures.md](decompress-knowledge/creatures.md).

## Tests

```bash
uv run pytest
```

Asset goldens (`pytest -m assets`) skip unless `assets/` exists (or `HOTD_ASSETS` is set).

## Asset map

| Path | Kind | Notes |
|------|------|--------|
| `assets/art/stageN/world/worldN.rbh` | Stage geometry | Mesh RBH → `-m`. Skins are VVTP pages 512–546 |
| `assets/art/stage1/creature/CREAT*.rbh` | Creature mesh **parts** | `CREAT1` then `CREAT2`, one id namespace (`LoadCreatMeshBank`). A character is a skeleton of many ids, not one file |
| `assets/art/stage1/creature/*.vmc` | Shared texture atlas (VVTP) | Creature skins are pages **547–595**. See below |
| `assets/sprite/spr.rbh` | Sprite metadata | `-s` for JSON; pixels are pages 1–337 in the `.vmc` |
| `assets/evt/allstage/evtALL.rbh` | Event scripts | `-e` → `events.json`. 9 stage slots, 66 scenes, 522 events. No FMV |
| `assets/cam/allstage/camALL.rbh` | Camera rails | `-c` → `cameras.json`. 142 groups × 6 Hermite tracks (eye XYZ + look-at XYZ) |
| `assets/sound/O_*.rbh` | Oneshoot SFX / voice | 8-byte header + unsigned 8-bit mono PCM @ 11025 Hz |
| `assets/sound/gamesnds.rbh` | SFX bank + index | Embedded clips + refs to `O_*` by id |
| `THOTD.exe` | Type table, `MO_*` clips, sound-request rows | `scripts/creature_map.py`, `scripts/cutscene_cues.py` |

### Creature `.vmc` banks

All are PIFF form `VVTP` (256×256 RGB555 pages):

| File | Meaning |
|------|---------|
| `TEXTURE.VMC` | Path the game loads (`ART\STAGE1\CREATURE\texture.VMC`). May be a stub in this tree. |
| `bigger.vmc` | Full uncompressed bank (`BODY` chunks, ~53 MB, 421 pages). |
| `B_RED` / `B_GREEN` / `B_BLUE` / `B_YELLO` / `B_PURPL` | Same bank, LZ-`PACK`ed, pre-baked for each PC **blood colour** setting (registry `bloodcolor`, 5 options). Differ mainly on ~38 blood pages; other pages match. |

The creature `.vmc` is a whole-game atlas, not one skin per species. Page ids match `-p` PNG names: **1–337** sprites, **338–511** unused, **512–546** world, **547–595** CREAT skins. `LoadStageAssets` always loads `CREAT1.RBH`, then `CREAT2.RBH`, then `texture.VMC` — there is no per-chapter creature file. Which pages a type uses is the skeleton walk in [creatures.md](decompress-knowledge/creatures.md).

### Sound banks

- Engine digital audio is **11025 Hz, 8-bit** (`InitSoundMixer` (`FUN_00411f10`)). The “3 channels” in init are mixer voices, not stereo in the files.
- `O_*.rbh` — single clip; RBHH `flags=0`. Loaded at runtime as `sound\O_%s.rbh`.
- `gamesnds.rbh` — index `BODY` (0x28-byte rows, rate `0x2b11`) + sample `BODY`. Already uncompressed (no `PACK`).
- Stage / menu **music** is CD audio via MCI in the exe, not these RBHs. Event `SNDON` kind 3 still requests a track (`PlayCdAudioTrack`).
- A cutscene `SNDON` operand is an index into exe table `DAT_005cbda8` (270 × 12-byte rows), not an `O_*` `soundId` and not a `gamesnds` row. Kind 4 loads `sound\O_%s.rbh`; kinds 1–2 play a `gamesnds` row; kind 3 is CD. See [cutscene-audio.md](decompress-knowledge/cutscene-audio.md).

### Events and cameras

`evtALL.rbh` is stage → scene → section opcode streams (slots 0–3 are chapters 1–4; 4 title `tt`; 5 attract `adv`; 6 ending `end`; slot 7 empty; slot 8 extra). There is no FMV file: a cutscene is an event section that binds a `camALL` rail (`CCTB` job `0x40`), spawns actors, and fires `SNDON`. Camera groups are six Hermite tracks (eye XYZ + look-at XYZ). `channelId` is `log2(keyCount)`, not an axis id. Playback notes: [cutscenes.md](decompress-knowledge/cutscenes.md).

## Formats (short)

- **PIFF** — RIFF-like container. HotD does **not** use RIFF odd-size padding between chunks. Forms include `RBHF` (`.rbh`) and `VVTP` (`.vmc`).
- **PACK** — compressed `BODY` via Tantalus LZ (signed varints + back-references). See `src/hotd_decompress/lz.py` / `pack.py`.
- **VVTP page** — 0x40-byte header + tightly packed RGB555 (`0x8000` bit present). Clear / transparent: `0x0000` and `0x8421`.
- **Sound oneshoot** — `BODY` starts with `u32 0x00082c30`, `u16 2`, `u16 soundId`, then unsigned 8-bit mono PCM (silence ≈ `0x80`).
- **Mesh** — world/CREAT share BODY0 graph + BODY1 float3 pool; prim batches from `DispatchMeshPrims` (`FUN_00578bb0`) (plain/textured tri/quad).
- **Sprites** — pointer table of UV/page frame records (`DAT_005ce544`).
- **Events / cameras** — nested pointer graphs (`0xFFFFFFFF` terminates lists). Cameras store Hermite `{t, value, slopeIn, slopeOut}` keys, six tracks per group.
- **Creatures** — 94 exe type rows (`DAT_005d46ac`, stride `0x4C`) plus skeleton trees. Mesh parts stay in `CREAT*.rbh`; skins are VVTP pages 547–595.
- **Motion** — 674 `MO_*` clips in the exe (`DAT_005efbd0` / `DAT_005f0658` / `DAT_005f1258`). Each frame is a root `float3` plus `s16` angle triplets (full circle = 65536). Bone count comes from the type, not the clip.

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
src/hotd_decompress/rail_timeline.py  CCTB job-0x40 windows (not a CLI flag)
src/hotd_decompress/creature_map.py   Exe types joined to CREAT pages and evtALL
src/hotd_decompress/motion.py         Exe MO_* frame sampler
src/hotd_decompress/sound_table.py    Exe sound-request rows and SNDON cues
src/hotd_decompress/jsonutil.py       JSON writer used by the dumps above
scripts/creature_map.py        Write creature-map.json (and clusters / more / hp)
scripts/cutscene_cues.py       Write cutscene-cues.json
decompress-knowledge/          Format notes (on-disk layouts and exe tables)
assets/                        Game data (gitignored; symlink or copy)
decompressed_assets/           Default output (gitignored)
```

Notes that are not a CLI flag: [creatures.md](decompress-knowledge/creatures.md), [motion.md](decompress-knowledge/motion.md), [cutscenes.md](decompress-knowledge/cutscenes.md), [cutscene-audio.md](decompress-knowledge/cutscene-audio.md), [game-rendering.md](decompress-knowledge/game-rendering.md), [enemy-systems.md](decompress-knowledge/enemy-systems.md). The index is [decompress-knowledge/README.md](decompress-knowledge/README.md).

## License

[MIT](LICENSE). Copyright (c) 2026 Gareth Owen.

Game assets remain property of their respective owners; do not redistribute them. `assets/` and `decompressed_assets/` are gitignored.
