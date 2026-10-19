# Meshes (`world*.rbh`, `CREAT*.rbh`)

Stage geometry and creature models share one RBHF layout: a pointer graph plus a float3 vertex pool. Prim batches match `DispatchMeshPrims` (`FUN_00578bb0`). Load path: `LoadCreatMeshBank` (`FUN_00419cac`) / `LoadWorldMeshBank` (`FUN_00419cf4`) → `LoadPiffRbh` (`FUN_005769c0`).

## Container

RBHH flags **`2, 0, 0`**. Three BODYs (BODY2 is empty). Usually two `RELC` chunks.

| Chunk | flags | Contents |
|-------|-------|----------|
| BODY0 | 2 | Id table + mesh nodes + prim batches |
| BODY1 | 0 | Vertex pool: tightly packed `f32 x, y, z` (12 bytes each) |
| BODY2 | 0 | Empty |
| RELC0 | | Pointer fields in BODY0 |
| RELC1 | | `vertBase` fields (byte offsets into BODY1) |

BODY1 size is a multiple of 12. Vertices are already in **stage space**. World node `+0x20` XYZ is metadata — do **not** bake it as a translate when exporting.

## Id tables (start of BODY0)

Two layouts. This tool tries creat first, then world.

### Creature (`CREAT*.rbh`)

Fixed 8-byte rows until `id == -1`:

```
offset  size  field
0x00    2     s16 id
0x02    2     s16 flag
0x04    4     u32 nodePtr    BODY0 offset of the mesh node
```

Each id maps to **one** node.

### World (`world*.rbh`)

Variable-length rows until `id == 0`:

```
s16 id
s16 flag
u32 nodePtr, nodePtr, … , 0     (0 terminates the pointer list)
```

One world id can reference several nodes. `0` here is end-of-list, not `0xFFFFFFFF`.

## Mesh node

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

## Prim batches (`DispatchMeshPrims` (`FUN_00578bb0`))

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

### Textured tri (36 bytes)

```
+0x00  u16 i0, i1, i2
+0x06  u16 texPageId
+0x08  (4 bytes unused by this tool)
+0x0C  f32 u0, v0
+0x14  f32 u1, v1
+0x1C  f32 u2, v2
```

### Textured quad (44 bytes)

```
+0x00  u16 i0, i1, i2, i3
+0x08  u16 texPageId
+0x0A  (2 bytes unused by this tool)
+0x0C  f32 u0, v0 … u3, v3     (8 floats)
```

UVs are **pixel coordinates** on a 256×256 VVTP page (`MESH_PAGE_SIZE`). `texPageId` matches `page_XXXX` from `-p` on the matching `.vmc`. OBJ export converts to `0..1` and flips V (`(256 - v) / 256`) so OBJ’s V-up matches the page’s V-down.

## How the tool works

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
