# RBH / RBHF

`.rbh` files are PIFF forms named **RBHF** (“RBH file”). The container is shared; the BODY payloads are not. This report covers the container. Payload layouts are in the per-type reports.

Decomp: `LoadPiffRbh` (`FUN_005769c0`) probes `PIFF` + `RBHF` (`0x46464950` / `0x46484252`). Mesh load goes through `LoadCreatMeshBank` (`FUN_00419cac`) / `LoadWorldMeshBank` (`FUN_00419cf4`) → `LoadPiffRbh` (`FUN_005769c0`).

## File shape

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

## RBHH — header table

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

## BODY

Opaque payload whose layout depends on the file. Pointers stored inside a BODY are **byte offsets from the start of that BODY**, not file offsets.

After load, the engine applies `RELC` so those offsets become real pointers. On disk they remain BODY-relative.

## RELC — relocations

Optional. Payload is a list of `u32` values. Non-zero entries are **BODY-relative offsets of fields that hold pointers** (or, for mesh BODY1, `vertBase` fields that index the vertex pool).

Zero slots are padding / unused. This tool counts non-zero entries only.

Mesh files typically have:

- `RELC0` — patch pointer fields in BODY0 (id table, node links, …)
- `RELC1` — mark `vertBase` fields (byte offsets into BODY1)

A file with a single pointer-graph BODY (events, cameras, sprites) usually has one `RELC` covering that BODY.

## Pointer tables

Many `flags=2` BODYs start with a table of `u32` offsets.

**Null terminator** is `0xFFFFFFFF` (not `0`). `0` is a real offset only when the format says so (world id-table node lists use `0` as end-of-list).

### Simple table

Walk `u32`s until `0xFFFFFFFF` or a value that falls outside the BODY. Used for event scene/section lists.

### Root table with holes

Event (and similar) **root** tables allow `0xFFFFFFFF` in the middle (unused stage slots). Length is implied by the first non-null child: the child table begins immediately after the root, so

```
slotCount = firstChildOffset / 4
```

Each slot is either a BODY offset or `0xFFFFFFFF`.

Sprite and camera roots use the same “first pointer / 4 = count” rule, but those tables are dense (no mid-list nulls in the retail files this tool was checked against). Camera groups skip a null root slot if one appears. Generic inspect can over-count a camera group’s child list by walking into key data; `-c` always finds six tracks per group (see [cameras.md](cameras.md)).

## How to tell types apart

The container does not store a type fourcc beyond `RBHF`. Heuristics used by this tool:

| Check | Type |
|-------|------|
| 1 BODY, starts with `u32 0x00082c30`, then `u16 2` | Oneshoot sound |
| 2 BODYs, index size `% 0x28 == 0`, rate `0x2b11` at `+0x08` | `gamesnds` |
| ≥2 BODYs, flags `2,0`, BODY1 size `% 12 == 0` | Mesh (then creat vs world by id table) |
| 1 BODY, first `u32 / 4` = count, record at that offset has a sane `frameCount` | Sprites |
| 1 BODY, small root (`firstPtr ≤ 0x400`), nested `0xFFFFFFFF`-terminated tables | Events |
| 1 BODY, groups of 6 Hermite tracks `{u16 keyCount, u16 log2(keyCount)}` | Cameras |

## How the tool works

### Inspect (no flag)

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

### Typed decompress

The container parser does not pick a payload type. Other flags run their own heuristics (table above) and fail if the BODY does not match:

| Flag | Entry | Failure |
|------|--------|---------|
| `-w` | `src/hotd_decompress/audio.py` | no oneshoot / gamesnds BODY |
| `-m` | `src/hotd_decompress/mesh.py` | not flags `2,0` + float3 BODY1 |
| `-s` | `src/hotd_decompress/sprite.py` | not 1 BODY / not a sprite pointer table |
| `-e` | `src/hotd_decompress/event.py` | not 1 BODY / not a small root table |
| `-c` | `src/hotd_decompress/camera.py` | not 1 BODY / not a camera group table |

`-d` only rewrites PIFF (`PACK`→`BODY`); it does not interpret RBHH. See [piff.md](piff.md).
