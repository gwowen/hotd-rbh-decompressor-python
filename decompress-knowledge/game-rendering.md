# Game rendering (`THOTD.exe`)

How the PC / Tantalus engine turns decompressed assets into a frame. On-disk layouts stay in the per-type notes; this note is the **runtime** path: backends, view, mesh submit, textures, sprites, and the software / Direct3D rasterizers.

This note is **not** a CLI flag. Pair `-m` / `-p` / `-s` / `-c` / `-e` with the exe tables below. Decomp: `hotd-decomp/THOTD-exe-commented.c`. WinMain is `LAB_00563440` (recovered from `THOTD.exe` @ `0x563440`).

## Two backends

WinMain (`LAB_00563440`) picks a renderer from the command line, then seeds `PTR_DAT_00c649e0` (the graphics vtable every draw call goes through):

| Cmdline | Init | Vtable | Path |
|---------|------|--------|------|
| `ddraw` or `d3d` | `FUN_00573ca0` | `DAT_00c66ef8` | DirectDraw + Direct3D 6 (`IDirect3DDevice3`) |
| *(else)* | `FUN_00565e70` | `DAT_00c652a4` | Software: lock the back-buffer and scanline-fill |

`FUN_00573ca0` enumerates adapters (`DirectDrawEnumerateA`), `DirectDrawCreate` → `DAT_00c64cac` (`IDirectDraw*`), queries a second interface into `DAT_00c66ecc`, and later binds `DAT_00c66ee8` as the D3D device. `FUN_00565e70` only swaps the vtable pointer.

Game code never calls DirectDraw / D3D directly for meshes. It calls vtable slots; the two backends implement the same offsets.

| Vtable offset | Role |
|---------------|------|
| `+0x04` | Renderer init (`FUN_005627c0`) |
| `+0x08` | Teardown |
| `+0x10` | Pause/resume around MessageBox |
| `+0x24` | Per-camera draw (`FUN_005626d0` → this) |
| `+0x34` | Palette / mode hook (stage load) |
| `+0x60` / `+0x64` | Allocate / free a VRAM texture slot |
| `+0x68` | Present / flip (`FUN_00418434`) |
| `+0x78` | Draw triangle (plain) |
| `+0x7c` | Draw quad (plain) |
| `+0x80` | Draw textured triangle |
| `+0x84` | Draw textured quad |
| `+0xbc` | 2D blit (UI glyphs) |

D3D device vtable (on `DAT_00c66ee8`) is the real COM object: `+0x24` `BeginScene`, `+0x28` `EndScene`, `+0x5c` `SetRenderState`, `+0x78` `DrawIndexedPrimitive`.

## Frame loop

Idle pump `FUN_00562e30` (called while `DAT_00c64b14` bit 0 is set):

1. `PeekMessageA` — if a message is waiting, `GetMessageA` / `TranslateMessage` / `DispatchMessageA`.
2. Else, when the window is active (`DAT_00c64b2c`, `DAT_00c64b14` bit 1) and not paused (bit 10 clear):
   - `FUN_00568290` — scene-graph sync: run pending `+0x18` callbacks, copy last-frame matrices.
   - `FUN_00568350` — for each camera object with draw-enable, `FUN_005626d0` → vtable `+0x24`.
   - `FUN_00579fa0` flushes callback queues around those two.
   - Busy-wait `FUN_00578940` until `DAT_00da69b4` (next-frame deadline). Deadline is `now + 1000 / fps`.

`DAT_005cd35c != 0` skips 3D submit (load / fade). Present is vtable `+0x68`.

Gameplay tick `FUN_00458b7c` (from `FUN_00458720`) updates entities and camera **before** the pump draws. Camera rails: [cameras.md](cameras.md). Event scripts that queue those rails: [events-detailed.md](events-detailed.md). Scripted playback (title / attract / ending, no FMV): [cutscenes.md](cutscenes.md).

## Display surface

`FUN_005663d0` sets the DirectDraw mode. Logical size is `DAT_00c64a00` × `DAT_00c64a04`; bpp is `DAT_00c64a14` / `DAT_00c64a08`.

| bpp | Flag in `DAT_00c649f4` | Pixels |
|-----|------------------------|--------|
| 8 | bit 1 (`2`) | Paletted; software flat-fill writes a byte index |
| 16 | bit 2 (`4`) | RGB555 (same packing as VVTP pages) |

Software path:

- Lock: `FUN_005661f0` — `IDirectDrawSurface::Lock` on `DAT_00da8980`. Pixel base `DAT_00c65380`, pitch `DAT_00c64cdc`, flag bit 7 (`0x80`).
- Unlock: `FUN_005661a0`.
- Windowed vs fullscreen: `DAT_00c649f8 == 0` is windowed (`FUN_00574dc0` adjusts for menu chrome).

Primitive pool: `FUN_005627c0` `GlobalAlloc`s `N * 0x224` bytes into `DAT_00c64a38`. Sorted draw lists live at `DAT_00c65390` (opaque) and `DAT_00c65394` (transparent); `FUN_0057a800` walks both.

## Viewport

Clip rectangle in `DAT_00d53020` (x0), `DAT_00d53024` (y0), `DAT_00d53028` (x1), `DAT_00d5302c` (y1). Applied with `FUN_00568550` (viewport) and `FUN_00568770` (windowed scissor). `FUN_00568a00` recomputes origin/extent.

| Helper | Layout |
|--------|--------|
| `FUN_0048780c` | Full screen (`0,0`–`W,H`) |
| `FUN_0048769c` | Letterbox bands from screen height / `0x180` |
| `FUN_00487708` | 2P split: top band `(H * 0x28) / 0x180`, then two `FUN_00568770` surfaces |

Projection scale for a camera object sits at `+0x20` (X) and `+0x24` (Y). Near clip is view-space `z < 1.0` (`0x3f800001`).

## View and transform stack

Stage space is the same as world meshes and camera rails: **Y up**, X/Z along the corridor. Do not bake world-node `+0x20` XYZ as a translate ([meshes.md](meshes.md)).

### Camera → view

`FUN_004caa70` samples `camALL.rbh` (eye XYZ + look-at XYZ), then:

1. `FUN_00461a30` — direction = eye − look-at → fixed-point yaw/pitch (×16). Negate yaw, add `0x8000` to pitch, roll = 0.
2. `FUN_0048a15c` — raycast `(eye.x, 32768, eye.z)` onto the stage mesh; player XZ follows the camera, Y from the ground hit.

`FUN_0045f140` rebuilds **six** view slots (stride `0x154` at `DAT_00da01c0`). `DAT_00da0bd0` selects the live camera: `0` = gameplay (`FUN_00461adc`), `2` = title/alt (`FUN_00461b90`). Zoom, 2P aim blend, and shake sit on top of the rail and do not add tracks — [cameras.md](cameras.md).

### Matrix stack

`DAT_012e27f0` is the current 3×4 matrix (12 floats, 0x30 bytes). Base of the stack is `DAT_00c6641c` (`FUN_00569510`). Identity lives at `DAT_005ce4f4`.

| Function | Role |
|----------|------|
| `FUN_00569600` | Push (copy 12 floats, advance the pointer) |
| `FUN_004b2938` | Load identity |
| `FUN_00474ecc` / `FUN_0042f704` / `FUN_004b4fd4` | Translate |
| `FUN_004751f4` / `FUN_004750ec` / `FUN_00475380` | Rotate Y / X / Z (sin/cos table `DAT_005697b0`, 16-bit angle) |
| `FUN_004b9f5c` | Translate + Y/X/Z + uniform scale (`entity+0x9c`), then submit |

Pop is `DAT_012e27f0 -= 0xC` (12 floats). `FUN_00492170` / `FUN_00465d04` transform a point by the current matrix.

`FUN_00579200` / `FUN_005792b0` batch-transform `float3` verts through that 3×4, perspective-divide, and (in `FUN_005792b0`) write clip outcodes. Output stride is **7 floats (0x1c bytes)**:

```
+0x00  f32 x     view / then screen (× viewport scale × 1/z)
+0x04  f32 y
+0x08  f32 z     view z; forced to 1.0 if z < 1
+0x0c  f32 1/z
+0x18  u32 clip  bits: 4 left, 8 right, 0x10 top, 0x20 bottom (plus a near bit in the low byte)
```

A prim is rejected when the **AND** of the three/four clip words is non-zero (all verts off the same plane).

## Mesh submit

Stage load `FUN_00418aa0` fills one 7500-slot pointer table (`DAT_00d53080`, 30000 bytes):

1. Clear the table.
2. `ART\STAGE1\CREATURE\CREAT1.RBH` then `CREAT2.RBH` via `FUN_00419cac` — `DAT_00d53080[id] = nodePtr` until `id == -1`.
3. `ART\STAGE%d\WORLD\WORLD_%d.RBH` via `FUN_00419cf4` — `DAT_00d53080[id] = id-table row` until `id == 0`. The row is `{s16 id, s16 flag, u32 nodePtr…, 0}`.
4. `cam\allstage\camall.rbh`, `evt\allstage\evtall.rbh`.
5. Texture bank is `ART\STAGE1\CREATURE\texture.VMC` (`FUN_00576610`), not this function.

CREAT and world **share the table**. Draw helpers interpret a slot as a node pointer (creatures) or an id-table row (world). Creature type → model id: [creatures.md](creatures.md).

### Instance batch

3D submit is a **deferred instance list**, not an immediate `DrawPrimitive`. `FUN_0043d900` begins a frame (clear queues). Each instance is 0x40 bytes: mesh id, flags, then the current 12-float matrix.

| Queue | Enqueue | Buffer | Counter |
|-------|---------|--------|---------|
| Opaque | `FUN_0043d948` (`FUN_0043d7f8` when `DAT_00d53080[id]` is live) | `DAT_00d64cc0` | `DAT_00d6c9d8` |
| Translucent | `FUN_0043d990` (`FUN_0043d834`) | `DAT_00d5cfc0` | `DAT_00d6c9cc` |

`FUN_0043d928` swaps front/back counters for the draw pass.

Typical callers:

- Creature / prop: build world matrix (`FUN_004b9f5c`, `FUN_00431330`, `FUN_00478a74` skeleton walk) then `FUN_0043d7f8` with `entity+0x5c` (CREAT id).
- World: `FUN_004920cc` looks up the id-table row and enqueues **each** `nodePtr` until 0.
- Shadow pass (when `DAT_005cd36c != 0`): `FUN_0042ce70` + `FUN_00430318` + a second `FUN_0043d7f8`. Lighting / shadow matrix helpers are `FUN_004c6954`…`FUN_004c86d0` (ground raycast at Y = `0x47000000` = 32768, same as the player plant).

`FUN_004789c8` is a mirror pass: push view, translate with **negated Z**, walk children.

### Prim dispatch (`FUN_00578bb0`)

Once an instance is bound, the node’s prim batches are walked. Layout matches [meshes.md](meshes.md). `kind = flags & 0x2007`. Transformed verts are the 0x1c records above (`param_2` is the projected pool; index `i` → `param_2 + i * 0x1c`).

| kind | Prim | Payload step | Vtable |
|------|------|--------------|--------|
| `0` / `1` | Plain tri | +4 shorts | `+0x78` |
| `2` | Textured tri | +0x12 shorts | `+0x80` |
| `0x2001` | Plain quad | +5 shorts | `+0x7c` |
| `0x2004` | Textured quad | +0x16 shorts | `+0x84` |

Facing test `FUN_00578f60` is a 2D cross product on projected XY. Skip it when `flags & 0x200`. Quads may pass if **either** split triangle faces the camera.

Textured records carry `texPageId` + pixel-space UVs on a 256×256 VVTP page. The rasterizer / D3D path binds that page from the VRAM table (below). This tool’s OBJ export only needs `0x2007` for record size; a viewer must honour `0x200` and the clip AND.

## Textures (VRAM)

Pixels are VVTP pages ([textures.md](textures.md)). Runtime:

1. `FUN_00576610` opens PIFF+VVTP (`0x46464950` / `0x50545656` — comments that say “PVT / FFPV” are the same fourcc read backwards). Each `BODY` registers `pageId` into `DAT_00c6713c` (stride **0x18**, 1000 slots, 24000 bytes). Slot `+0x04` holds the BODY pointer.
2. `FUN_0041a220` (“Generating Textures”) builds a 64K RGB555 remap: identity, then `table[0] = table[0x8000] = 0x8421`, plus blood-colour overrides from `PTR_DAT_005ce830[DAT_00d5b1fc]`. Applies the table to every page BODY.
3. `FUN_0045640c` packs 5-bit R/G/B and ORs `0x8000` (engine “priority” bit). Channels other than `0x1f` are snapped to even (`& 0x1e`).
4. `FUN_00576350` acquires a VRAM slot (vtable `+0x60` / `+0x64`). Overflow logs `VRAM_C_pos*`.
5. D3D: `FUN_00584130` creates a DirectDraw offscreen surface and binds it as a D3D texture. `FUN_00582ed0` `SetRenderState(TEXTUREHANDLE, …)` then `DrawIndexedPrimitive` (`D3DPT_TRIANGLEFAN` = 6, vertex stride 32). Alpha blend uses render states `0x11` / `0x12` (`SRCBLEND` / `DESTBLEND`).

Clear colours `0x0000` and `0x8421` are transparent in this tool’s PNG path; the engine uses the same two as remap sentinels.

Page bands (header `pageId`, same numbers as `-p` / mesh `texPageId` / sprite `pageId`): **1–337** sprites, **338–511** unused, **512–546** world, **547–595** creature skins.

## Software rasterizers

When the software vtable is active, vtable `+0x78`…`+0x84` land in scanline fillers that write the locked back-buffer (`DAT_00c65380` + `y * pitch`). Affine UVs (no perspective correction on the span). Scratch setup: `FUN_00569510`.

| Function | Fill |
|----------|------|
| `FUN_0058830d` | Flat (byte / replicated colour) |
| `FUN_005894ec` | Gouraud, opaque |
| `FUN_00589e40` | Gouraud, transparent (skip zero source) |
| `FUN_0058ab88` | Affine textured, opaque |
| `FUN_0058b5ac` | Affine textured, transparent (skip zero texel) |
| `FUN_00567c70` | Clip a 2D sprite/tile descriptor to the viewport, adjusting UVs |
| `FUN_00567f90` | X-dominant Bresenham span |
| `FUN_00568000` | Y-dominant Bresenham span |

8-bit modes write palette indices; 16-bit modes write RGB555 words.

D3D path (`FUN_00582ed0`) does **not** use these fillers. It transforms the same polygon nodes, then `DrawIndexedPrimitive`. Hardware vs software is a backend swap, not a different mesh format.

## Sprites and HUD

`assets/sprite/spr.rbh` is UV/page metadata ([sprites.md](sprites.md)). BODY base after load is `DAT_005ce544`. `FUN_004430a4` returns `DAT_005ce544[id]`.

`FUN_004434b0` is a **64×48 scroll-tile stamp**, not a GPU sprite draw. It looks up the sprite record, converts the header UV extent to tile counts (`>> 3`), clips to 0x40×0x30, and writes the sprite id into `PTR_DAT_005d24f4[layer][y * 0x40 + x]`. Out-of-range stamps log `Bogus scroll sprite`. `FUN_00442fa8` sets the screen-space UV rectangle from `DAT_00c64a00` × `DAT_00c64a04`.

HUD / score (`FUN_004434b0` with ids such as `0x589` + digit, `0x4f0` lives, `0x504` / `0x505` labels) and UI text (`FUN_00428494` glyphs through vtable `+0xbc`) reuse the same sprite table. Composite a HUD quad with `-s` JSON + `-p` PNGs: `pageId` + `(u0,v0)–(u1,v1)` on a 256×256 page.

## Event opcodes that poke the renderer

From [events-detailed.md](events-detailed.md); these do not add mesh data, they change globals the draw path reads:

| Op | Name | Effect |
|----|------|--------|
| `0x3c` | `CCTB` | Queue camera job (rail bind `0x40` → `camALL` group) |
| `0x42` / `0x4b` | `CAMDR2` / `CAMDR` | Camera director |
| `0x44` | `SHDWLT` | Shadow / light words |
| `0x46` / `0x47` | `SKYKD` / `SKYTB` | Sky kind / sky table |
| `0x4c` | `GGCOL` | Colour (two args) |
| `0x4f` | `TEXCHG` | Texture change |
| `0x28` | `WLTB` | Six floats (world / light) |

`SCNINIT` (`0x10`) resets camera slots and scores at scene start.

## Reconstructing a frame (this tool)

No `-r` / `--render` flag. To match what the exe would draw for one camera pose:

1. `-c` on `camALL.rbh` — evaluate the six Hermite tracks at integer frame `t`; camera at tracks 0–2, look-at 3–5.
2. `-m` on `worldN.rbh` — stage OBJ in stage space (no `+0x20` bake). `usemtl page_N` → `-p` PNG.
3. `-m` on `CREAT1.RBH` / `CREAT2.rbh` plus [creatures.md](creatures.md) skeleton walk — instance each bone with the type-row scale.
4. `-p` on `B_RED.VMC` (or `bigger.vmc`) — RGB555 pages; treat `0x0000` / `0x8421` as clear.
5. `-s` on `spr.rbh` — HUD / FX quads on the same pages.
6. `-e` on `evtALL.rbh` — which `camGroup` / frame window, sky, and spawns are live.

Facing (`FUN_00578f60`), clip outcodes, and `flags & 0x200` are exe-only; the OBJ dump keeps every prim. Overlay zoom / shake / 2P blend only if matching the exe rather than the authored rail.
