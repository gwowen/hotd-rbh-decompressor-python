# Enemy spawn, AI, scoring, and collision (`THOTD.exe`)

How the PC / Tantalus engine creates enemies, ticks their AI, awards score, and resolves gun hits. On-disk spawn records stay in [events-detailed.md](events-detailed.md); creature meshes / type rows in [creatures.md](creatures.md); the draw path in [game-rendering.md](game-rendering.md).

This note is **not** a CLI flag. Pair `-e` on `evtALL.rbh` with the exe tables below. Decomp: `hotd-decomp/THOTD-exe-commented.c`. Bytes checked against `hotd-exe/THOTD.exe` (PE32, image base `0x400000`, 8855552 bytes).

PE map (Watcom sections, `VirtualSize` is 0; use `SizeOfRawData`):

| Section | RVA | File | Role |
|---------|-----|------|------|
| `BEGTEXT` | `0x00010000` | `0x400` | Code. VA `0x41xxxx`…`0x56xxxx` |
| `DGROUP` | `0x001A0000` | `0x187400` | Data. VA `0x5A0000`…; file = `0x187400 + (VA − 0x5A0000)` |
| `.bss` | `0x00870000` | *(none)* | Runtime globals (`DAT_00d9fxxx`, `DAT_00daxxxx`) |

## Two type ids

Event `typeId` and creature type are **different namespaces**:

| Table | VA | Count | Indexed by |
|-------|----|------:|------------|
| Spawn functions | `DAT_005d8118` | **136** nonzero / 256 slots (max live index 225) | `ENTB` record `+0x00` |
| Creature stats | `DAT_005d46ac` | 94 × `0x4C` (92 rows with nonzero model/radius/scale) | `entity+0xd2 >> 16` after spawn init |

`ENTB` (`FUN_0046e5c8`, handler for op `0x0a`) does `call DAT_005d8118[*(record+0)]`. Slot 100 (Stage 01 example) is `0x4a79cc`. Creature skins, scale, and hit radius come later from `FUN_00483ad0` + `DAT_005d46ac`.

## Event VM (spawn source)

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

Bind `FUN_004c0d3c` (`0x4c0d3c`): `PC = stages[StageNo][SceneNo][EventNo]`.

Tick `FUN_004c0db0`: `opcode = *PC`; `call [DAT_005eeac0 + opcode*4]`. Idle / unnamed slots are `LAB_00471658` (44 of 96). Names are packed C strings at `0x5a3a00` (`0x00 : nop` … `0x5d : NEXTEV`). Exe spellings that differ from the short names in the decoder:

| Op | Exe string | Handler |
|----|------------|---------|
| `0x02` / `0x06` | `ET1P` / `ET2P` (not `ET1P1` / `ET2P1`) | same as `ET1PE` / `ET2PE` families |
| `0x50` | `WAIT_ENNUM/EVCOM/EVTB1` | `FUN_004c0fc4` — wait while spawn-gen `DAT_00da0ccc` high u16 `<` arg |
| `0x55` | `WAIT_ENALV/EVTB6` | `FUN_004c121c` — wait while enemies-alive `DAT_00da0cd0` `>` arg |
| `0x1e` / `0x34` / `0x59` | `PLTB` / `BRTB` / `EBLFNSH` | **nop** (`LAB_00471658`) — names only |

`ET1PE`…`ET1P3` / `ET2PE`…`ET2P3` share two handlers (`FUN_0046e548` / `FUN_0046e588`). `TEXCHG` (`0x4f`) shares `FUN_004c1514` with `GGSET`.

## Spawn path

```
ENTB* list  →  DAT_005d8118[typeId]  →  FUN_0043e400  →  copy record
                                                    →  FUN_00483ad0 (if creature)
                                                    →  FUN_004a5180 / species init
                                                    →  FUN_0046ee90 live slot
```

1. **Allocate** `FUN_0043e400`: writes `DAT_005cd2fc = 0x1a`, links a child node, unique id at `DAT_00d6ca20`. Gameplay fields run well past that header (past `+0x3cc`).
2. **ENTB copy** (`FUN_0046e5c8`, bytes at `0x46e628`):
   - `record+0x04 | 1` → `entity+0x60`
   - `record+0x24` (u8) → `entity+0xd4` (`spawnEventId`)
   - `record+0x25` → `entity+0x6c`
   - `record+0x22` (u16) → **both** `entity+0x78` and `+0x7a` (combat HP)
   - `record+0x20 & 3` = posMode: `0` copies six floats from `+0x08` (XYZ + RX/RY/RZ); `1`/`2` transform
3. **Type stats** `FUN_00483ad0`: `entity+0x60 |= 0x401`; `DAT_005d46ac[type]+0x00` → `+0x5c` (model); `+0x14` fld → `fstp [entity+0x98]`; `+0x28` → scale at `+0x9c`.
4. **Live registry** `FUN_004a5180` increments u16 `DAT_00da0ccc+2` (spawn generation) and `DAT_00da0cd0` (enemies-alive), then `FUN_0046ee90` claims slot **2..12** (`eax < 0x0D`) in `DAT_00da0040` (stride `0x14`), stores index at `entity+0x2ef`.
5. Stage reset `FUN_004c1524` zeros `DAT_00da0cd0` / spawn-tracking. `SCNINIT` (`FUN_004c15b4`) resets camera slots (and related score/camera globals) at scene start.

Some FX spawners cap children with `DAT_005d7f6c < 9` (BSS; zero in the image). Secondary waves still go through `FUN_0043e400` (`FUN_00482bf8`, `FUN_004822b8`, `FUN_004815a4`, `FUN_0047e664`, bonus `FUN_004ea460` / `FUN_004c4c60`).

Record layout: [events-detailed.md](events-detailed.md) (`ENTB` 0x28 bytes, `ENTB2` 8 bytes, `ENTBE` ≥ 0x24).

## Behavior

`entity+0x00` is the tick callback. `FUN_004a5180` (20-way on `spawnEventId`) installs it, logs `ENGuard_BO_zonbiman` when type `== 0x10`, and claims the live slot. Shared per-frame body: `FUN_00477b00` (skeleton sample `FUN_004776c8`, transform, cull, submit).

| Function | Role |
|----------|------|
| `FUN_0046a91c` / `FUN_0046a984` | Quadratic path; waypoints at `+0x39c…+0x3b0`, duration `+0x2f8`; writes XYZ |
| `FUN_0046ab60` / `FUN_0046ac40` | Same spline → velocity `+0x80/+0x84/+0x88` |
| `FUN_0046ae0c` | Target player `+0x2f0` = P1 / P2 / random; skips a gun if `DAT_00da0cb4/cb5` (grab lock) |
| `FUN_0046ad04` / `FUN_0046ada0` | Quadrant vs player XZ `DAT_00d9f038/040`; yaw `0 / 0x4000 / 0x8000 / 0xc000` |
| `FUN_0046b4a8` | Nearest allied zombie in the live-slot table (homing) |
| `FUN_0046af9c` | Clamp X/Z to screen walls `DAT_00da0bac/b9c/ba8/ba4`; damp velocity; `+0x32c` bit 7 |
| `FUN_0046b27c` | 3D wall: if depth `>` `DAT_00da0ba4`, clamp and damp |
| `FUN_004a4e2c` | After emerge: walk/attack layers; default tick `LAB_004d9a90` |
| `FUN_004a3578` | Patrol AI when `DAT_00da0bd8 == 2` (bonus / time-attack) |
| `FUN_004fe320` | Attack phases via `+0x340` |
| `FUN_004fe53c` | Grab: aim, 30-frame quadratic lunge, wall-clamp, sink, release |
| `FUN_00505f50` | Buried emerge: snap to floor `DAT_00da0b48`; 48 frames then chase |
| `FUN_004fe118` | Hit tick: if `+0x61` bit 0, subtract damage u16 from `+0x78` |
| `FUN_004a3064` | Death: clear live bit, `DAT_00da0cd0 -= 1`, swap vtable |
| `FUN_004aba08` | Defeat: `DAT_00da0cd6` / `DAT_00da0cc6` += 1; **+400** score if player state `DAT_00d9f05c == 5` (`call FUN_00437344` with `edx = 0x190`) |
| `FUN_004d94b0` | Knockdown: Y vel −0.5, sink, wait `0x28` frames, despawn |

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

## Scoring

Player block stride **0xCC** (`0x33` dwords). Score `DAT_00d9f064[slot]`, lives `DAT_00d9f068[slot]`, state `DAT_00d9f05c[slot]`.

`FUN_00437344`: `score += edx`, clamp at 0. Confirmed: `add eax, 0x00d9f058` then `[eax+0x0c]` is `DAT_00d9f064`.

| Event | Function | Effect (this exe) |
|-------|----------|-------------------|
| Hit-zone tree | `FUN_004c3d58` → `FUN_004c4168` | Per-type tables `DAT_00523a58` / `DAT_00527344` / `DAT_00538d44` (in `BEGTEXT`). Damage u16 lands in `DAT_00da0cc4` (`DAT_00da0cc2` high word). Route totals `DAT_00da6244`. |
| Kill | `FUN_004aba08` | Counters += 1; **+400** if `DAT_00d9f05c[player] == 5` |
| Life lost | `FUN_00436fe4` | `dec` lives; `sub ebp, 0x64` (−100 score, floor 0); continue timer `DAT_00d9f050 = 0x5a` (90 frames) |
| Shot outside rect | `FUN_004371b8` | Perspective-divide vs `DAT_005a1ba2…`; miss path calls `FUN_00436fe4` then another −100 |
| 1UP | `FUN_00437304` | Lives += 1 if below cap `DAT_00da0cec` |
| HUD digits | `FUN_0051a598` | `cmp esi, 99999` (`0x1869f`); sprite **`0x589` + digit** (six immediates in the function). Lives sprite `0x4f0`; labels `0x504` / `0x505` in the same HUD cluster |

`DAT_00d9f05c == 5` is the “this player is in the scoring/playing state” gate used by kill bonus and several route helpers — not a difficulty id.

High scores: string `scores.cfg` at VA `0x5a1118`, pointer `DAT_005ce8b0`. Load/reset and write live in the UI cluster around `FUN_0042556c` (sort **10** entries, stride **`0x1c`**: `cmp ebx, 0x0A` / `imul eax, ebx, 0x1C`). Insert `FUN_004b4bf8` uses thresholds `DAT_005d29d8 = 14000` and `DAT_005d29cc = 16000`. Fatal: `Failed to write highscores file=%s` (spaces, not underscores). Grade `FUN_00420004`: float ≤ `DAT_005ce4c0` (**200**) → `'X'` (`0x58`); ≤ `DAT_005ce4c4` (**300**) → `'Y'`; else `'Z'`.

## Collision (gun hits)

Not a mesh ray. Per-frame sphere queue, then a separate stage-mesh ray for player plant / aim point.

| Step | Function | This exe |
|------|----------|----------|
| Clear | `FUN_00489b94` | Zeros `DAT_00da39f0` (0x24-byte results, `add eax, 0x24` loop), `DAT_00da25f0` depth keys, `DAT_00da2df0` candidates |
| Enqueue | `FUN_00489c18` via `FUN_00483c10` | Live bit `+0x60` bit 0; projected center at `+0x40/+0x44/+0x48` |
| Per player | `FUN_00489c84` | `test ah, 2` on `DAT_00d9f060` (shot this frame); `call FUN_00489d0c`; `and byte […+DAT_00d9f060], 0xFD` |
| Sphere | `FUN_00489d0c` → `FUN_00414aac` | `push [ebp+0x98]` as radius; `push [ebp+0x40/44/48]`. If `DAT_005ced98 == 5`, radius × CRT/lightgun table |
| Children | `FUN_00489e2c` | Tree at `entity+0xd0`; count `[tree+0x34]`; only if `entity+0x74` bit 0 |
| Sort | `FUN_0048a44c` | `sub esp, 0x400` (256-int histogram); 16-pass radix on packed depth |
| Apply | `FUN_00489fbc` | Sets `+0x60` player bit and `+0x61` bit 0; hit XYZ in `DAT_00d9ef60`; optional splatter `FUN_0046bf8c` |

**`DAT_005d46ac+0x14` is the hit-sphere radius, not combat HP.** `FUN_00483ad0` `fstp`s it to `entity+0x98`; `FUN_00489d0c` pushes that float into `FUN_00414aac`. Combat HP is the ENTB u16 at `+0x22` → `entity+0x78`, drained by `FUN_004fe118` (`mov si, [ebx+0x78]; sub si, cx` with `cx` from `DAT_00da0cc4`). Magician 12 vs Hermit 2.6 is aim-circle size.

Stage plant: `FUN_0048a15c` walks collision-mesh slots (`DAT_00da0bb4`). Camera path uses ray `(eye.x, 32768, eye.z)` — same Y as the shadow pass ([game-rendering.md](game-rendering.md)). Screen-space helper `FUN_0043db5c` returns 1 / 2 / 4 (off / graze / solid).

Collision tree alloc: `FUN_00478b64` from skeleton `DAT_005ef8e0[type]`, pointer at `entity+0xd0`. Same tree is walked for scoring (`FUN_004c3d58`).

## Entity field map

Offsets from the callers above (BSS entity, not a file struct).

| Offset | Field | Set by | Read by |
|--------|-------|--------|---------|
| `+0x00` | Tick vtable | `FUN_004a5180` / death | Entity pump |
| `+0x28/+0x2c/+0x30` | XYZ | ENTB / path tick | Draw, AI, collision |
| `+0x34/+0x38/+0x3c` | Fixed-point RX/RY/RZ | ENTB / quadrant | Matrix |
| `+0x40/+0x44/+0x48` | Hit-sphere center | `FUN_00483c10` | `FUN_00414aac` |
| `+0x5c` | CREAT model id | `FUN_00483ad0` / spawnEventId maps | Draw `FUN_0043d7f8` |
| `+0x60` | Flags (bit 0 live; bits 1–2 P1/P2 hit) | ENTB, `FUN_00489fbc` | Enqueue / death |
| `+0x61` bit 0 | Hit this frame | `FUN_00489fbc` | `FUN_004fe118` |
| `+0x74` bit 0 | Walk child volumes | Spawn init | `FUN_00489d0c` |
| `+0x78` | Combat HP (s16) | ENTB `+0x22` | `FUN_004fe118` |
| `+0x80/+0x84/+0x88` | Velocity | Spline / jitter | Wall clamp |
| `+0x98` | Hit radius (f32) | Type table `+0x14` | `FUN_00414aac` |
| `+0x9c` | Scale | Type table `+0x28` | Submit |
| `+0xd0` | Collision tree | `FUN_00478b64` | Hits + score tree |
| `+0xd4` | spawnEventId | ENTB `+0x24` | AI / waves |
| `+0x2ef` | Live-slot index | `FUN_0046ee90` | Homing scan |
| `+0x2f0` | Target player | `FUN_0046ae0c` | Score / grab |
| `+0x3cc` | Path / death flags | `FUN_0046a91c` | Knockdown |

Globals: `DAT_00da0cd0` enemies-alive (`WAIT_ENALV`), `DAT_00da0ccc` high u16 spawn generation (`WAIT_ENNUM`), `DAT_00da0cd6` / `DAT_00da0cc6` kill counters, `DAT_00d9f038/03c/040` player XYZ, `DAT_00da0b48` floor (`FKRTB`).
