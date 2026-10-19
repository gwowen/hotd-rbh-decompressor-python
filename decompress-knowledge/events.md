# Events (`evtALL.rbh`)

`assets/evt/allstage/evtALL.rbh` is a nested pointer graph of stage → scene → event **script streams**. One BODY (`flags=2`), typically with a `RELC`.

Opcodes, spawn records, and `CCTB` → `camALL` binds: [events-detailed.md](events-detailed.md). How those scripts play as in-engine cutscenes (no FMV): [cutscenes.md](cutscenes.md).

Decomp: root table `DAT_00d5a5d0`. `CountStagesForSelectUi` (`FUN_00422808`) counts scenes per stage for the debug UI (stops at the first `-1` / `0xFFFFFFFF`). Gameplay bind is `BindEventPlayhead` (`0x4c0d3c`); the tick at `TickEventVm` (`0x4c0db0`) dispatches `handlers[opcode]` at `0x005eeac0`.

## Container

```
PIFF RBHF
  RBHH   one row, flags=2
  BODY   pointer graph + opcode streams + spawn records
  RELC   pointer fields in that BODY
```

Already uncompressed in the files this tool was checked against.

## Graph

```
BODY0
  stagePtrs[]          length = firstPtr / 4; 0xFFFFFFFF slots allowed
    → scenePtrs[]      terminated by 0xFFFFFFFF
      → sectionPtrs[]  terminated by 0xFFFFFFFF
        → opcode stream
```

Retail: 9 stage slots (slot 7 empty, slot 8 extra), 66 scenes, 522 events.

### Root (stages)

Unlike a simple null-terminated list, the **root may contain `0xFFFFFFFF` in the middle** (unused stage indices). Length is implied by the first child offset:

```
stageCount = firstChildOffset / 4
```

A null slot is an empty stage (no scenes). Non-null slots are BODY offsets of scene-pointer tables.

Exe debug names (`s_Stage_01_005ce918`): Stage 01, 02, 03, 04, tt, adv, end for slots 0–6.

### Scenes

At each stage pointer: a list of `u32` scene offsets, stopped by `0xFFFFFFFF`. Labels from `PTR_s_Scene_000_005ceba4` (e.g. `Scene 000`, `Scene 02A`, `Scene XX`).

### Sections (events)

At each scene pointer: a list of `u32` event offsets, stopped by `0xFFFFFFFF`. EventNo is this index.

Each event is a `u32` opcode stream. `0xFFFFFFFF` ends an `ENTB`-style pointer list **and**, at an instruction boundary, the event itself. Spawn records often sit in the bytes after the script until the next section. Do **not** treat the first `0xFFFFFFFF` as the event end — that was the old dump’s truncation.

Camera rails live in a separate bank (`camALL.rbh`). A `CCTB` job `0x40` names a group index + frame window — see [events-detailed.md](events-detailed.md) and [cameras.md](cameras.md).

## Null vs zero

Event tables use **`0xFFFFFFFF` as null / terminator**. Do not confuse with world mesh id tables, which use `0` to end a node-pointer list.

## How the tool works

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
