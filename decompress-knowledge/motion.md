# Motion clips (`THOTD.exe`)

Creature animation is **not** a PIFF payload. The 674 `MO_*` clips live in `THOTD.exe` DGROUP: a name, a frame count, and a packed angle stream per bone. Mesh parts stay in `CREAT*.rbh`; bind-pose trees stay in the type table ([creatures.md](creatures.md)). This note is the clip bytes.

This note is **not** a CLI flag. `src/hotd_decompress/motion.py` samples one integer frame. It does not walk the skeleton or submit meshes. Decomp: `SampleSkeleton` (`FUN_004776c8`), `PlayClipSkeleton` (`FUN_00476b70`) / `ApplyFrameBoneRotates` (`FUN_00478448`), `CopyBoneAngleTriplets` (`FUN_00478324`).

PE map is the same as [creatures.md](creatures.md): image base `0x400000`, DGROUP VA `0x5A0000` (file `0x187400`).

## Tables

| VA | Layout | Role |
|----|--------|------|
| `DAT_005efbd0` | 674 × pointer | Clip base (first frame) |
| `DAT_005f0658` | 674 × `s32` | Frame count |
| `DAT_005f1258` | 674 × pointer | `MO_*` name strings |

Indexed by the 16-bit motion id at `entity+0xd8` (`>> 16` of `+0xd6`). Type-row `defaultMotion` (`DAT_005d46ac+0x44`) is often a **shared idle**, not the species walk set — [creatures.md](creatures.md). Type 6 (Hangedman) stores `MO_b3_atk_l` (Hermit); Hangedman clips are `MO_b2_*`. The posed reference frame is motion **22** (`MO_b2_base`), frame **0**.

Bone count for the stride comes from `DAT_005efa58[type]`, not from the clip.

## Frame layout

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

## Playback (`PlayClipSkeleton` / `FUN_00476b70`)

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

## What the tool does

| Module | Role |
|--------|------|
| `src/hotd_decompress/creature_map.py` | Type rows + bind-pose mesh ids (`meshId`, children) |
| `src/hotd_decompress/motion.py` | Name / frame count / clip bytes → `ax0, ax1, ax2` on each bone |

`sample_motion_frame(exe_bytes, motion_index, frame, bone_count)` clamps `frame` into `0 .. frameCount-1`.

## How to reproduce

1. `-m` on `CREAT1.RBH` / `CREAT2.rbh` and `-p` on `B_RED.VMC` — same as [creatures.md](creatures.md).
2. Call `sample_motion_frame` with motion **22**, frame **0**, and type 6’s bone count (`DAT_005efa58[6]` = 10).

Prefix roster (`z`, `k`, `b2`, …) stays in [creatures.md](creatures.md). Spawn / AI that picks a motion id: [enemy-systems.md](enemy-systems.md). Draw submit after the bone matrix: [game-rendering.md](game-rendering.md).
