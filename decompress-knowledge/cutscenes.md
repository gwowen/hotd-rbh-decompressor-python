# Cutscenes (`THOTD.exe`)

How the PC / Tantalus engine **plays** a scripted sequence. There is no FMV, AVI, or other movie file in the asset tree. A “cutscene” is the same 3D world as gameplay: an event script (`evtALL.rbh`) binds a camera rail (`camALL.rbh`), spawns actors, plays digital SFX, and the frame pump draws meshes / sprites as usual.

This note is **not** a CLI flag. On-disk layouts stay in [events.md](events.md), [events-detailed.md](events-detailed.md), and [cameras.md](cameras.md). The draw path is [game-rendering.md](game-rendering.md). Decomp: `hotd-decomp/THOTD-exe-commented.c`.

Retail dump checked: 9 stage slots, 66 scenes, 522 events, 993 rail binds, 142 `camALL` groups.

## No separate cutscene format

Every sequence the player watches is an **event section** (opcode stream) under `assets/evt/allstage/evtALL.rbh`. Camera motion is **not** embedded in that stream. A `CCTB` job `0x40` names a group index + frame window into `assets/cam/allstage/camALL.rbh`. The same pair drives:

| Kind | Typical wait | What it looks like |
|------|----------------|--------------------|
| Gameplay corridor | `WAIT_ENALV` / `WAIT_ENNUM` after a rail bind | Enemies spawn; rail keeps rolling; guns live |
| Staged intro / talky beat | `WAIT_CAMJOB` / `WAIT_CAMFRM` / `WAIT_FRM` | Camera and actors play out; combat waits |
| Title / attract / ending | Same ops, on stages `tt` / `adv` / `end` | No separate player plant into a fight |

The engine does not switch to a movie player. `CHGSM` (change system mode) and `ATCMD` (attract-mode command) only poke globals; they do not load another container.

CD music is MCI `cdaudio` in the exe. It is **not** in `assets/sound/` and is not keyed from `evtALL`. Digital voice / SFX in a sequence are `SNDON` → `PlayDigitalSfx` (`FUN_00412000`) (`O_*.rbh` / `gamesnds.rbh`).

## Who owns the playhead

Packed bytes ([events-detailed.md](events-detailed.md)):

| Address | Role |
|---------|------|
| `DAT_00da0cf4` | StageNo (root slot in `evtALL`) |
| `DAT_00da0cf3` | SceneNo |
| `DAT_00da0cf0` | EventNo (section index inside the scene) |
| `DAT_00da0ab8` | PC (pointer into the event BODY) |

Bind (`BindEventPlayhead` (`0x4c0d3c`)):

```
PC = stages[StageNo][SceneNo][EventNo]
```

`LoadStageAssets` (`FUN_00418aa0`) (stage asset load) fills the 7500-slot mesh table, then requests `cam\allstage\camall.rbh` (`DAT_00d5a5c8`) and `evt\allstage\evtall.rbh` (`DAT_00d5a5d0`). World mesh path is `ART\STAGE%d\WORLD\WORLD_%d.RBH` with the same StageNo (clamped: slots 0–3 → stages 1–4; slots 4–5 → stage 5; slot 6 → 6; anything else → 1). Title / attract / ending scripts still run against whatever world that clamp loaded.

Debug UI names (`s_Stage_01_005ce918` / `PTR_s_Scene_000_005ceba4`):

| Slot | Name | Scenes | Role in playback |
|------|------|--------|------------------|
| 0–3 | Stage 01…04 | 20 / 16 / 8 / 5 | Arcade chapters. Scene `000`/`00` is the start beat; later scenes are rooms / forks. |
| 4 | Stage tt | 2 (`XX`, `00`) | Title-style loop: one rail, then `WAIT` forever. |
| 5 | Stage adv | 1 | Attract / demo reel (scripted rails + spawns, no `CHGSM`). |
| 6 | Stage end | 8 | Ending variants (rails 117–141), then a `WAIT_ITEM 254` hold. |
| 7 | *(null)* | 0 | Unused. |
| 8 | extra | 6 | Reachable if StageNo is set; copies late Stage 01 scenes. |

`CountStagesForSelectUi` (`FUN_00422808`) (stage-select) only counts until the first `0xFFFFFFFF`, so the UI sees slots 0–6. Gameplay indexes StageNo directly.

## Per-frame playback

Idle pump `IdleFramePump` (`FUN_00562e30`) draws; gameplay tick `TickGameplay` (`FUN_00458b7c`) (from `TickGameplayParent` (`FUN_00458720`)) updates entities and camera **before** that draw. A scripted beat is four machines on the same frame:

```
event VM tick          camera job ring           rail sampler              draw pump
TickEventVm            DispatchCameraJob         TickCameraRail            DrawEnabledCameras
handlers[opcode]       DAT_005d8418[job]         six Hermite tracks        vtable +0x24
       │                      │                         │                        │
       ├─ CCTB 0x40 ──────────► bind group + [start,end]
       ├─ WAIT_CAMJOB ────────► yield until ring empty
       ├─ ENTB* ──────────────► spawn into DAT_00d53080 instances
       └─ SNDON ──────────────► PlayDigitalSfx
                                                        │
                                                        ├─ eye / look-at → yaw/pitch
                                                        ├─ plant player on floor
                                                        └─ view slots → rasterizer
```

### 1. Event VM

Tick at `TickEventVm` (`0x4c0db0`): `opcode = *PC`; `call handlers[opcode]` at `DAT_005eeac0`. Names at `0x5a3a00`.

`DAT_00da0a98` is the yield flag. A wait op sets it and returns; the next frame retries the same opcode until the condition holds, then advances PC. That is how a cutscene **holds**: the script does not sleep the process; it spins on `WAIT_CAMJOB` / `WAIT_CAMFRM` / `WAIT_FRM` / `WAIT_ITEM` while the camera and entities keep ticking.

`NEXTEV` (`0x4c1948`) increments EventNo. If that slot is `-1`, a branch table at `0x5d3420` picks the next scene (fixed, indexed, or +1) and restarts at EventNo 1. If the scene pointer is `-1`, the stage is done. `SCNINIT` (`0x10`) resets camera slots and scores at scene start.

Typical **scene open** (Stage 01 `Scene 000` event 1):

```
SCNINIT
SNDON    2
SKYKD    0
SKYTB    2
SHDWLT   0xf000 0xd000
FKRTB    ptr → floor Y
BGTB     1
CHGSM    5
ENTB2    spawn
WAIT_ITEM 248
CHGSM    5
NEXTEV
```

Then later events bind rails and spawn enemies. Scene-to-scene setup events are often a short `SNDON` + `CHGSM 6` + `NEXTEV` before the `SCNINIT` body.

Retail `CHGSM` args (change system mode; 169 uses): **6** (69, scene-to-scene), **5** (35, start / wait-item intros), **8** (21, often next to `TEXCHG`), **7** (21), **1** (21), **3** (12). `ATCMD` is 0 or 1 (14 uses). `PYPMD` is almost unused (one `0`, one `1`). `WAIT` (yield forever, no PC advance) appears **once**: Stage tt `Scene 00`.

### 2. Camera job ring

`CCTB` queues the current instruction onto a 16-slot ring (`DAT_00d9f1f0`). `DispatchCameraJob` (`FUN_0045f414`) reads `*(PC+4)` as the job type and dispatches `DAT_005d8418[job]`. Job `0x40` (`BindCameraRailJob` (`FUN_00460f88`) → `BindCameraRail` (`FUN_00460fd0`)) is the rail bind:

| Word | Copied to | Meaning |
|------|-----------|---------|
| start | `DAT_00d9ed04` | Start frame (`−1` keeps current `t`) |
| end | `DAT_00d9ed08` | End frame (tick while `t < end`) |
| camGroup | `DAT_00da0ca4` | `camALL.rbh` group index 0–141 |
| flags | `DAT_00d9ed10` | Bind flags. The update at `0x461171` tests mask **4**. Mask **2** is a different bit |

Slot 0 of the 0x154-byte camera slots (`DAT_00da01c0`) also pokes the event-script state machine (`DAT_00da0ab0`). Remaining frames (`end − t`) live in `DAT_00da0bf8` (`WAIT_CAMFRM 0` / `RNWCJ` read that).

The bread-and-butter cutscene pair:

```
CCTB rail { start, end, camGroup, flags }
WAIT_CAMJOB
```

Gameplay often uses the same bind, then `WAIT_ENALV` so the rail and the fight overlap. `CAMDR` / `CAMDR2` (374 + 5 retail uses, arg usually `3`) are camera-director waits on top of that.

### 3. Rail sampler

`TickCameraRail` (`FUN_004caa70`) (paused when `DAT_00da0a80 != 0` or `DAT_00da0b5c == 0`):

1. If `start < end`, increment the integer frame counter.
2. Sample six Hermite tracks for group `DAT_00da0ca4` into eye XYZ (`DAT_00d9ed18`) and look-at XYZ (`DAT_00d9ed30`). Lookup is `HermiteTrackLookup` (`FUN_00461858`); pose channels are **track order**, not `channelId`.
3. `EyeLookAtToYawPitch` (`FUN_00461a30`): direction = eye − look-at → fixed-point yaw/pitch (×16). Roll = 0.
4. `RaycastStageFloor` (`FUN_0048a15c`): raycast `(eye.x, 32768, eye.z)` onto the stage mesh. Player XZ follows the camera; Y comes from the ground hit.

Zoom, 2P aim blend, and shake sit on top of the rail and do **not** add tracks ([cameras.md](cameras.md)). `DAT_00da0bd0` selects the live camera: `0` = gameplay (`GameplayCameraView` (`FUN_00461adc`)), `2` = title/alt (`TitleCameraView` (`FUN_00461b90`)).

### 4. Draw

Same path as any other frame ([game-rendering.md](game-rendering.md)): instance queues → `DispatchMeshPrims` (`FUN_00578bb0`) prims → software scanline or D3D `DrawIndexedPrimitive`. Sky (`SKYKD` / `SKYTB`), lights (`SHDWLT` / `WLTB`), and `TEXCHG` are event ops that only change globals the submit path reads. Letterbox bands (`SetLetterboxViewport` (`FUN_0048769c`), height / `0x180`) and 2P split (`SetSplitScreenViewport` (`FUN_00487708`)) are viewport helpers, not a movie overlay.

`DAT_005cd35c != 0` skips 3D submit (load / fade). HUD stamps (`StampScrollSprite` (`FUN_004434b0`)) still run: stage-intro countdown `TickStageIntroCountdown` (`FUN_0051a8d0`) is a **separate** entity state machine (voice / `SPR_Num` bonus / camera tilt) on top of the event script, not an opcode.

## Special stages (title, attract, ending)

These are ordinary `evtALL` slots. They are the closest thing the bank has to “dedicated cutscenes”: almost no `WAIT_ENALV`, lots of `WAIT_CAMJOB` / `WAIT_FRM`, and `ENTB2` props rather than corridor spawn tables.

### Stage tt (slot 4) — title loop

`Scene XX` event 1:

```
SCNINIT
SKYKD 0 / SKYTB 1 / CHGSM 6 / FKRTB / BGTB 2
CCTB rail group 106, frames 0–59
GGSET 29
ENTB  two spawns (typeId 129, 130)
WAIT_CAMJOB
WAIT_FRM 300
CCTB rail group 106, frames 60–175
WAIT_CAMJOB
CCTB camMode2
WAIT_FRM 9999
NEXTEV
```

`Scene 00` is a single `WAIT` — the VM yields forever. Title/attract UI mode 1 (`TitleAttractUiMode1` (`FUN_004210fc`)) and title camera matrices (`TitleCameraMatrices` (`FUN_00496f60`)) sit beside this script; they are not encoded in `evtALL`.

### Stage adv (slot 5) — attract / demo reel

One scene, 11 events. No `CHGSM`. Pattern: spawn a few `ENTB2`/`ENTB`/`ENTB3` actors, bind a rail, `WAIT_CAMJOB`, `WAIT_FRM`, `NEXTEV`. Rails used: groups **107–116** (plus 115 with a long 121–520 window). `SNDON 263` opens most beats. Attract/demo tick `TickAttractDemo` (`FUN_00473e04`) / `TickAttractScroll` (`FUN_00458bd8`) can restart or take coin/start; `ATCMD` from scripts is the event-side hook (14 uses, mostly in chapter scenes, not in `adv` itself).

### Stage end (slot 6) — ending variants

Eight scenes. Shared open: `SKYTB 1` / `SKYKD 5` / `SCNINIT` / `NEXTEV`, then a long event of `ENTB2` (typeIds 110, 161, 120, …) + rail slices + `WAIT_CAMJOB`.

| Scene | Rails (groups) | Notes |
|-------|----------------|-------|
| 00 | 117, 119 | Long first ending; `SNDON 69` then `70` / `14` |
| 01 | 117, 120, 121 | Same open, different later groups |
| 02 | 124, 123 | Same shape |
| 03 | 126–137, 140 | Many short 0–320 windows; sky/BGTB changes per beat |
| 04 | 140 (540–560) | Hold, then `WAIT_ITEM 254` |
| 05 / 06 | 140, 141 | Credits-like; `SNDON 44`; same `WAIT_ITEM 254` tail |
| 07 | — | `SCNINIT` / `NEXTEV` only |

`WAIT_ITEM 254` at the end of 04–06 is a hold until an item flag (continue / skip), not a movie stop.

## Attract, title, and intro overlays

These do **not** add tracks or opcodes. They run next to the VM:

| System | Function | Behaviour |
|--------|----------|-----------|
| Title / attract UI mode 1 | `TitleAttractUiMode1` (`FUN_004210fc`) | Main menu layout; optional stage-select `CountStagesForSelectUi` (`FUN_00422808`) |
| Attract/demo tick | `TickAttractDemo` (`FUN_00473e04`) | Demo input, stage restart, player-count transitions |
| Attract scroll / difficulty | `TickAttractScroll` (`FUN_00458bd8`) / `TickAttractDifficulty` (`FUN_00458c28`) | Called from the gameplay tick |
| Title camera matrices | `TitleCameraMatrices` (`FUN_00496f60`) | Fixed rotations for 1P vs 2P title layouts |
| Live camera = title/alt | `DAT_00da0bd0 == 2` | `TitleCameraView` (`FUN_00461b90`) instead of gameplay `GameplayCameraView` (`FUN_00461adc`) |
| Stage-intro countdown | `TickStageIntroCountdown` (`FUN_0051a8d0`) | HUD sprites + SFX; not an `evtALL` op |
| Route playback (intro/wait/active) | `DrawRoutePlaybackUi` (`FUN_004c608c`) | Sprite stamps for the route UI, not the 3D rail |

## Reconstructing a sequence (this tool)

No `-cutscene` flag. To replay one beat:

1. `-e` on `evtALL.rbh` — pick `stages[StageNo].scenes[SceneNo].sections[EventNo]`. Read `CCTB` `camera.camGroup` / `startFrame` / `endFrame`, plus `ENTB*` spawns and `SNDON` ids.
2. `-c` on `camALL.rbh` — evaluate that group’s six Hermite tracks at integer frame `t` in `[start, end)`. Camera at tracks 0–2, look-at 3–5 (Y-up).
3. `-m` on `worldN.rbh` and `CREAT1.RBH` / `CREAT2.rbh` — instance spawns by `typeId` → [creatures.md](creatures.md) (spawn `typeId` is the 137-slot function table, **not** the 94-row creature table).
4. `-p` on `B_RED.VMC` (or `bigger.vmc`) and `-s` on `spr.rbh` — pages + HUD / FX quads.
5. `-w` on `O_*.rbh` / `gamesnds.rbh` — `SNDON` args are sound ids, not filenames.

Hold the pose while the script would `WAIT_CAMJOB` (until `t` reaches `end`). Overlay zoom / shake / 2P blend / letterbox only if matching the exe rather than the authored rail. CD music has to come from the disc (MCI), not this CLI.
