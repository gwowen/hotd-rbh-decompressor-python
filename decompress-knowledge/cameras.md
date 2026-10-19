# Cameras (`camALL.rbh`)

`assets/cam/allstage/camALL.rbh` is one bank of scripted on-rails **camera paths**. Each group is six Hermite scalar tracks: eye XYZ + look-at XYZ. The exe samples them at the current integer frame, aims the view, then plants the player on the stage floor under the camera.

Retail file checked: 142 groups, 852 tracks (always 6 per group). Already uncompressed (`BODY` + `RELC`).

Decomp / exe: `LoadStageAssets` (`FUN_00418aa0`) loads `cam\allstage\camall.rbh` into `DAT_00d5a5c8` (BODY pointer). `BindCameraRail` (`FUN_00460fd0`) binds a group + frame window. `TickCameraRail` (`FUN_004caa70`) ticks; `SampleCameraGroupTracks` (`FUN_00461980`) samples six tracks; `HermiteTrackLookup` (`FUN_00461858`) is the cubic Hermite lookup; `EyeLookAtToYawPitch` (`FUN_00461a30`) turns eye−look-at into yaw/pitch. Event VM + rail playback (title / attract / ending): [cutscenes.md](cutscenes.md).

## Container

Same outer shape as events: RBHF, one BODY (`flags=2`), pointer graph, usually one `RELC`.

```
PIFF RBHF
  RBHH   one row, flags=2
  BODY   pointer graph
  RELC   pointer fields in that BODY
```

## Graph

```
BODY0
  groupPtrs[N]     N = firstPtr / 4
    → trackPtrs[6]  first track sits immediately after the table
      → Track
```

Root slots that are `0xFFFFFFFF` are skipped. Group tables are dense: the first track begins immediately after the group’s pointer list, so the track count is implied by that gap (same “child sits right after the table” rule as sprite/event roots).

The exe always reads **six** pointers at group `+0,+4,+8,+0xC,+0x10,+0x14`. Retail `camALL.rbh` matches that (142 × 6). Generic RBH inspect (`read_pointer_table` until `0xFFFFFFFF` / out-of-BODY) can over-count by walking into key data — a track header `keyCount|channelId<<16` can look like an in-range pointer. Trust `-c` / `src/hotd_decompress/camera.py`, not the inspect entry count, for camera groups.

## Track

```
offset  size  field
0x00    2     u16 keyCount     power of two: 4, 8, 16, 32, or 64
0x02    2     u16 channelId    log2(keyCount), so 2..6 — not an axis id
0x04    …     Key[keyCount]
```

`HermiteTrackLookup` (`FUN_00461858`) uses the low u16 as the key count (binary search starts at `keyCount/2`) and the high u16 minus one as the search iteration count. On all 852 retail tracks, `channelId == log2(keyCount)`.

**Pose channels are track order**, not `channelId`:

| Slot | Written to | Role |
|------|------------|------|
| 0 | `DAT_00d9ed18` | Eye X |
| 1 | `DAT_00d9ed1c` | Eye Y (often held near −10 or 15) |
| 2 | `DAT_00d9ed20` | Eye Z |
| 3 | `DAT_00d9ed30` | Look-at X |
| 4 | `DAT_00d9ed34` | Look-at Y |
| 5 | `DAT_00d9ed38` | Look-at Z |

Values are stage-space floats (same space as world meshes). Y is height; X/Z run along the corridor.

## Key (16 bytes)

```
offset  size  field
0x00    4     f32 t          time in **frames** (may be fractional on disk)
0x04    4     f32 value
0x08    4     f32 slopeIn    incoming tangent (used as m1 of the span)
0x0C    4     f32 slopeOut   outgoing tangent (used as m0 of the next span)
```

Cubic Hermite between `keys[i-1]` and `keys[i]`: previous `slopeOut` + current `slopeIn`. Engine doubles at `0x005a2a0c` are `2.0`, `3.0`, `−2.0` (Hermite basis). The sampler converts the integer frame to float (`fild` / `FloatChop` (`FUN_00562400`) chop) before the lookup.

Retail spans: 60–2510 frames (mean ~573). Group 80 is the longest (2510). Most rails sit in the 240–960 band.

## Runtime (`THOTD.exe`)

### Load

`LoadStageAssets` (`FUN_00418aa0`) (stage asset load) requests `cam\allstage\camall.rbh` via `LoadPiffRbh` (`FUN_005769c0`). `DAT_00d5a5c8 = *(handle + 4)` is the BODY base. `SampleCameraGroupTracks` (`FUN_00461980`) indexes `group = *(DAT_00d5a5c8 + groupIndex * 4)`.

### Bind (event → rail)

Camera slots are 0x154 bytes at `DAT_00da01c0` (six slots). Event dispatch (`DispatchCameraJob` (`FUN_0045f414`)) copies a script record into slot 0; `BindCameraRail` (`FUN_00460fd0`) / `PromoteCameraSlotGlobals` (`FUN_004610b0`) promote those fields to the globals the tick uses:

| Slot offset | Copied to | Meaning |
|-------------|-----------|---------|
| +0x120 | `DAT_00d9ed04` | Start frame, or `−1` to keep current `t` |
| +0x124 | `DAT_00d9ed08` | End frame (tick while `t < end`) |
| +0x128 | `DAT_00da0ca4` | `camALL` group index (0–141) |
| +0x12C | `DAT_00d9ed10` | Flags. The bind-update at `0x461171` tests mask **4**. Mask **2** appears often in rail data and is a different bit — do not treat them as one bind-behaviour flag |
| +0x14C | — | Current `t` as float. When start is `−1`, `PromoteCameraSlotGlobals` (`FUN_004610b0`) at `0x4610AC` loads this word, converts to integer, **increments it**, and stores the global frame (`0x4610E3–0x4610F5`) |
| +0x60 / +0x78 | slot-local | Per-slot eye / look-at sample buffers |

Slot 0 is special: binding it also pokes the event-script state machine (`DAT_00da0ab0`). Remaining frames (`end − t`) live in `DAT_00da0bf8`.

Events and cameras stay in **separate files**. A `CCTB` job `0x40` names a group and a frame window; `evtALL.rbh` does not embed spline keys. Opcode layout: [events-detailed.md](events-detailed.md).

### Tick

`TickCameraRail` (`FUN_004caa70`):

1. If `DAT_00d9ed04 < DAT_00d9ed08`, and the game is not paused (`DAT_00da0a80 == 0` and `DAT_00da0b5c ≠ 0`), increment the frame counter.
2. `EAX = DAT_00da0ca4` (group index); sample six tracks into `DAT_00d9ed18` (eye) and `DAT_00d9ed30` (look-at).
3. `EyeLookAtToYawPitch` (`FUN_00461a30`): direction = eye − look-at → fixed-point yaw/pitch (×16). Negate yaw, add `0x8000` to pitch, roll = 0.
4. `RaycastStageFloor` (`FUN_0048a15c`): raycast from `(eye.x, 32768, eye.z)` onto the stage mesh. Player XZ follows the camera; Y comes from the ground hit. Pitch copied to `DAT_00d9f048`.

Sibling `TickCameraRailPlantEye` (`FUN_004cab60`) does the same sample but copies eye XYZ into the player position (`DAT_00d9f038/03c/040`), with optional Y from `DAT_00da0b48` instead of the ground raycast.

### Layers on top of the rail

These do **not** add tracks to `camALL.rbh`:

| System | Function | Behaviour |
|--------|----------|-----------|
| Six view slots | `BuildViewSlotMatrices` (`FUN_0045f140`) | Builds a view matrix per slot from `DAT_00da0220` (stride 0x154). `DAT_00da0bd0` is the live camera: 0 = gameplay (`GameplayCameraView` (`FUN_00461adc`)), 2 = title/alt (`TitleCameraView` (`FUN_00461b90`)). |
| 2P aim blend | `BlendTwoPlayerAim` (`FUN_004609e4`) | Averages P1/P2 entity points (`DAT_00da0044` / `0058` at +0x2DC) into `DAT_00da0c74`. Falls back to the rail look-at if neither gun entity is live. |
| Zoom / FOV | `UpdateCameraZoom` (`FUN_00461690`) | Compares camera-forward to that aim point. 16-bit zoom word in `DAT_00da0c04`, clamped to `0x10`–`0x40`. High half `0xFFFF` disables auto-zoom. |
| Shake | `ApplyCameraShake` (`FUN_004ca884`) | Decaying offset for 30 frames (`DAT_00d9ed5c`) into `DAT_00d9f038/03c/040` when `DAT_00d9ed54` is set. |
| Chase / panic | `StartChasePanicCamera` (`FUN_004bd4a8`) → `TickChasePanicCamera` (`FUN_004bd678`) | Separate entity state machine: ease aim toward the crosshair while path progress &lt; 1.0, then a timed wait and optional homing spawn. Hijacks the live camera entity. |
| Gun-aim jitter | `GunAimJitter` (`FUN_0049cad0`) | Same 6-track Hermite sampler on a **different** table, scaled into screen-space wobble by view quadrant. |

Projection scale at the camera object `+0x20` (X) and `+0x24` (Y) is what `ProjectVerticesWithClip` (`FUN_005792b0`) multiplies into screen X/Y. Those floats track live zoom from `UpdateCameraZoom` (`FUN_00461690`): the 16-bit word `DAT_00da0c04` is clamped to `0x10`–`0x40`, and `DAT_00da0c06` is an override. They are recomputed from the aim point (`BlendTwoPlayerAim` (`FUN_004609e4`)), which falls back to the rail look-at when no gun is live. They are not a stage FOV constant in `camALL.rbh`.

## How the tool works

```text
uv run hotd-decompress -c|--cam <file.rbh> [outdir]
```

`convert_cameras_to_json` (`src/hotd_decompress/camera.py`) uses `load_rbh` (no PACK expand). Retail `camALL.rbh` is already BODY.

1. Require one BODY that looks like a root pointer table (`firstPtr ≤ 0x1000`).
2. `groupCount = firstPtr / 4`. Skip `0xFFFFFFFF` slots.
3. Each group: `trackCount = (firstTrackPtr - groupPtr) / 4`, then parse tracks at those pointers.
4. Each track: `keyCount` / `channelId`, then `keyCount` × `{t, value, slopeIn, slopeOut}`.
5. Write `cameras.json`. Default dir: `decompressed_assets/<stem>_cam/`.

Stdout: group count, total tracks, output path.

The `-c` dump does not evaluate the Hermite spline; it writes keys. `sample_track` / `sample_camera_group` in `src/hotd_decompress/camera.py` implement `HermiteTrackLookup` (`FUN_00461858`) (cubic Hermite; previous `slopeOut` + current `slopeIn`). Pose channels are track order 0–2 eye, 3–5 look-at, not `channelId`. `channelId` is left numeric (`log2(keyCount)` in retail data). `cameras.json` is `jsonutil.write_json`, so whole-valued key floats print as `n.0`.

`src/hotd_decompress/rail_timeline.py` walks `evtALL` CCTB job-`0x40` binds in file order, resolves `startFrame == 0xFFFFFFFF` to the last end frame seen for that `camGroup`, and can sample `[start, end)`. Branch ops are ignored, so binds in one scene play back-to-back.

JSON shape:

```json
{
  "source": "…",
  "groupCount": N,
  "groups": [
    {
      "index": 0,
      "offset": 1234,
      "tracks": [
        {
          "offset": 5678,
          "keyCount": 4,
          "channelId": 2,
          "keys": [
            { "t": 0, "value": 1.0, "slopeIn": 0, "slopeOut": 0 }
          ]
        }
      ]
    }
  ]
}
```

To play a rail in a viewer: call `sample_camera_group` at integer frame `t`, place the camera at tracks 0–2, look at tracks 3–5 (Y-up as in the mesh exporter). `collect_rail_segments` resolves a `−1` start to the previous end for that group. Overlay zoom / shake / 2P blend only if matching the exe rather than the authored path.
