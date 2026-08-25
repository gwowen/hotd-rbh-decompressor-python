# Events in detail (VM, opcodes, spawns, cameras)

Container and pointer graph: [events.md](events.md). Camera rails: [cameras.md](cameras.md). How a sequence plays (no FMV): [cutscenes.md](cutscenes.md).

This note is the **bytecode** inside each section: opcode names from `THOTD.exe`, spawn records, and how `CCTB` names a `camALL.rbh` group. Retail dump checked: 9 stage slots, 66 scenes, 522 events, 7660 ops, 1653 spawns, 993 rail binds.

## Runtime (`THOTD.exe`)

### Load

`FUN_00418aa0` requests `evt\allstage\evtall.rbh`. `DAT_00d5a5d0 = *(handle + 4)` is the BODY base.

Packed playhead bytes:

| Address | Role |
|---------|------|
| `DAT_00da0cf4` | StageNo |
| `DAT_00da0cf3` | SceneNo |
| `DAT_00da0cf0` | EventNo (section index) |
| `DAT_00da0ab8` | PC (pointer into BODY) |

Bind (`0x4c0d3c`):

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

`FUN_00422808` (stage-select) counts until the **first** `0xFFFFFFFF`, so it only sees slots 0–6. Gameplay indexes by StageNo directly; slot 8 is reachable if that byte is set.

### Tick

`0x4c0db0`: `opcode = *PC`; `call handlers[opcode]` at `DAT_005eeac0`. Names sit in DGROUP at `0x5a3a00` (`0x00 : nop` … `0x5d : NEXTEV`).

`DAT_00da0a98` is the yield flag. A wait op sets it and returns; the next frame retries the same opcode until the condition holds, then advances PC.

`NEXTEV` (`0x4c1948`) increments EventNo. If that slot is `-1`, a branch table at `0x5d3420` picks the next scene (fixed, indexed, or +1) and restarts at EventNo 1. If the scene pointer is `-1`, the stage is done.

EventNo is the **section index**. It is not the old JSON `eventId` field (that was a one-word opcode, usually `NEXTEV` / `CLTB` / `KGTB`).

A different id lives on spawned entities at `+0xd4` (from the spawn record’s `+0x24` byte). Enemy/prop helpers (`FUN_004812e4`, `FUN_00482bf8`) switch on that.

## Stream layout

Each section is a `u32` opcode stream. `0xFFFFFFFF` ends an `ENTB`-style list **and**, as a word at an instruction boundary, the event itself.

The previous dump stopped at the first `0xFFFFFFFF`, which truncated most events after the first spawn list. The decoder now bounds each section by the next section start in BODY order and walks opcodes, treating a non-opcode word as trailing spawn-record bytes (not script).

Most immediates are `opcode + one u32` (PC += 8). `WAIT_CAMJOB` / `SCNINIT` / `NEXTEV` / `WAIT` take no extra word. Lists consume pointers until `0xFFFFFFFF`.

## Opcode table

Handler `LAB_00471658` is idle (does not advance PC). Those slots are **nop** in the exe strings and do not appear as real script ops. The tool stops if it hits an unknown word (spawn payload / padding).

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
| `0x5a` | `SNDON` | +1 | Play digital SFX (`FUN_00412000`) |
| `0x5b` | `ATCMD` | +1 | Attract-mode command |
| `0x5c` | `WAIT` | 0 | Yield forever (does not advance PC) |
| `0x5d` | `NEXTEV` | 0 | Next event / scene |

Retail histogram (top): `CCTB` 1718, `WAIT_CAMJOB` 728, `NEXTEV` 521, `WAIT_CAMFRM` 460, `CAMDR` 374, `WAIT_ENALV` 346, `ENTB` 334, `GGSET` 322, `SNDON` 272.

## Spawn records (`ENTB*`)

List operands are **BODY offsets**, not inline coordinates. `ENTB` (`0x46e5c8`) reads each pointer, looks up `DAT_005d8118[typeId]` (spawn function), and copies the record into a new entity (`FUN_0043e400`).

### `ENTB` / `ET*` / `ENTB3` (0x28 bytes)

```
offset  size  field
0x00    4     u32 typeId     index into DAT_005d8118
0x04    4     u32 flags      OR 1 → entity+0x60
0x08    4     f32 x
0x0C    4     f32 y
0x10    4     f32 z
0x14    4     f32 rx
0x18    4     f32 ry
0x1C    4     f32 rz
0x20    1     posMode        low 2 bits: 0 = raw XYZ, 1/2 = transform
0x22    2     u16 combat HP  copied to entity+0x7a **and** +0x78 (drained on hit)
0x24    1     spawnEventId   → entity+0xd4
0x25    1     u8             → entity+0x6c
0x26    1     u8             ENTB3 → entity+0x328
0x27    1     u8             ENTB3 → entity+0x32c
```

`typeId` is a spawn-function index (**136** live slots in this `THOTD.exe`, max 256), **not** the 94-row creature table in [creatures.md](creatures.md). `spawnEventId` is the byte those creature helpers switch on.

### `ENTB2` (8 bytes)

```
0x00  u32 typeId
0x04  u16 copied to entity+0x7a / +0x78
```

### `ENTBE` (≥ 0x24 bytes)

Same 6 floats as `ENTB`, then `u16` at `+0x20`. The handler stores `record+0x24` at `entity+0x364` (extra payload pointer).

XYZ is stage space (same as world meshes / camera rails). Example from Stage 01 event 4: type 100 at `(17, -25, -1125)` and `(-30, -25, -1165)`, `spawnEventId` 19 and 17.

## `CCTB` → `camALL` groups

`CCTB` does not embed splines. It queues the current instruction onto a 16-slot ring (`DAT_00d9f1f0`). `FUN_0045f414` reads `*(PC+4)` as a **camera job type** and dispatches `DAT_005d8418[job]`.

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

Job `0x40` (`FUN_00460f88` → `FUN_00460fd0`) is the rail bind:

| Word | Copied to | Meaning |
|------|-----------|---------|
| start | `DAT_00d9ed04` / slot `+0x120` | Start frame (`−1` keeps current `t`) |
| end | `DAT_00d9ed08` / slot `+0x124` | End frame (tick while `t < end`) |
| camGroup | `DAT_00da0ca4` / slot `+0x128` | `camALL.rbh` group index 0–141 |
| flags | `DAT_00d9ed10` / slot `+0x12C` | Bit 1 (`2`) changes bind behaviour |

Retail: 993 `rail` binds, 117 distinct groups, indices 0–141 (the full `camALL` range). Typical pattern:

```
CCTB rail { start, end, camGroup, flags }
WAIT_CAMJOB
```

or `WAIT_CAMFRM` / `RNWCJ` when the script needs the remaining frame window (`DAT_00da0bf8`).

## Example (Stage 01, `Scene 000`, event 1)

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

## How the tool works

```text
bun run index.ts -e|--evt <file.rbh> [outdir]
```

`convertEventsToJson` (`src/event.ts`):

1. Same root/scene/section pointer walk as [events.md](events.md).
2. Collect every section offset; bound each by the next offset in BODY order (sections are not always sequential inside a scene).
3. Walk `u32` opcodes with the table above. List ops consume pointers until `0xFFFFFFFF`. `CCTB` size uses the job-type formula.
4. Deref `ENTB*` pointers into spawn records; deref `WLTB` / `FKRTB` pointers into floats.
5. Job `0x40` becomes `camera: { jobName: "rail", startFrame, endFrame, camGroup, flags }`.
6. Write `events.json`. Stdout also prints op / spawn / rail-bind counts.

JSON extras vs the raw tree: `name` on stages/scenes (from the exe strings), `ops[]` on each section, `spawns` / `camera` / `floats` on ops. `words` is the script slice only (internal list terminators kept; trailing spawn bytes omitted). The old one-word `eventId` field is gone — that word is `ops[0].name`.
