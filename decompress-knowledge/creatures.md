# Creatures (exe types → CREAT ids → VVTP pages)

On-disk creature data is **pooled**, not one file per enemy. Names live in `THOTD.exe` motion strings and a 94-row type table. Mesh parts are `CREAT1.RBH` / `CREAT2.rbh` ids; skins are VVTP pages in `texture.VMC` / `B_*`.

This note is **not** a CLI flag. `scripts/creature_map.py` joins the exe tables below to CREAT `texPageId`s and `evtALL` spawns. Decomp: `LoadStageAssets` (`FUN_00418aa0`) (load), `LoadCreatMeshBank` (`FUN_00419cac`) (CREAT id table → `DAT_00d53080`), `ApplyCreatureTypeStats` (`FUN_00483ad0`) (type → model id).

## Files are banks

| Asset | Role |
|--------|------|
| `CREAT1.RBH` | Creature/NPC mesh parts. 1397 ids, 917 nodes. Ids **0–6611**, no overlap with CREAT2. |
| `CREAT2.rbh` | Same layout. 2677 ids, 1517 nodes. Ids **55–7498**. |
| `texture.VMC` / `B_*` / `bigger.vmc` | One shared page bank. `B_RED`…`B_PURPL` are blood-colour remaps of the same 421 pages, not different species. |

`LoadStageAssets` (`FUN_00418aa0`) always loads `ART\STAGE1\CREATURE\CREAT1.RBH`, then `CREAT2.RBH`, then `texture.VMC`. There is no per-chapter creature file.

Each CREAT id is one **body-part node** (median ~20 verts), not a whole character. A creature is a skeleton of many ids.

`LoadCreatMeshBank` (`FUN_00419cac`) copies each CREAT id table into a global slot array:

```
for (id, nodePtr) in table until id == -1:
    DAT_00d53080[id] = nodePtr
```

CREAT2 is loaded second; ids do not collide, so both banks sit in one namespace. Draw looks up `DAT_00d53080[modelId]`. Spawn helpers also hardcode model ids (`0xb69`, `0x12c0`, `0xbb0`, …); those values are CREAT ids, not world ids.

## Exe tables (`THOTD.exe`)

PE: image base `0x400000`. DGROUP starts at VA `0x5A0000` (file offset `0x187400`). File offset = `0x187400 + (VA − 0x5A0000)`.

| VA | Layout | Role |
|----|--------|------|
| `DAT_005d46ac` | 94 × `0x4C` | Per-type stats (model, hit radius, scale, default motion) |
| `DAT_005efa58` | 94 × `s32` | Bone count |
| `DAT_005ef8e0` | 94 × pointer | Skeleton root (bone tree) |
| `DAT_005efbd0` | 674 × pointer | `MO_*` clip bases — [motion.md](motion.md) |
| `DAT_005f0658` | 674 × `s32` | Clip frame counts |
| `DAT_005f1258` | 674 × pointer | `MO_*` motion name strings |

**94 skeleton-backed types are not every actor.** `BindSpawnEventType` (`FUN_0047b2c4`) / `ApplyCreatureTypeStats` (`FUN_00483ad0`) index the `0x4C` stride with no visible 94-entry bounds check. Stage 1 has ten slot-128 occurrences with selector **107**; that row has model 0, radius 0, scale 1 and is a controller/special type, not permission to walk past the 94-entry skeleton arrays. Thirteen of the 94 trees also reference a CREAT id absent from both banks — some handlers reject selectors, some nodes are conditional. Keep the declared bone stride even when a walk finds fewer nodes (types 41/42/43/44/46/66 have 12 reachable nodes on an 18-bone stride; type 91 has 16/18).

Ghidra often reads the 16-bit type at `entity+0xd4` as `*(int*)(entity+0xd2) >> 16`. Motion id is the 16-bit at `+0xd8` (`>> 16` of `+0xd6`). Do not model `+0xd4` and that overlapping load as two independent simultaneous fields without tracing lifetimes.

### Type row (`0x4C`)

```
offset  size  field
0x00    4     u32 modelId     root / display id (may be absent from CREAT; bones have the real ids)
0x14    4     f32 hitRadius   copied to entity+0x98; gun sphere in `SphereHitTest` (`FUN_00414aac`) (not combat HP)
0x28    4     f32 scale
0x2C    4     f32 yOffset
0x30    4     f32 (extra)
0x44    4     u32 defaultMotion   index into DAT_005f1258
```

`ApplyCreatureTypeStats` (`FUN_00483ad0`) copies `+0x00` → `entity+0x5c` (model id), `+0x14` → `+0x98` (hit-sphere radius), `+0x28` → `+0x9c` (scale). Combat HP is the ENTB u16 at record `+0x22` → `entity+0x78` — [enemy-systems.md](enemy-systems.md).

`defaultMotion` is often a **shared idle** (`MO_b3_pose_2`, `MO_b1_atk_a`), not the species walk set. Species clips (`MO_ebitb_*`, `MO_k_*`, …) are selected at runtime by AI, so type index → Ebitan/Kageo is **not** a single column.

### Skeleton node (`DAT_005ef8e0[type]`)

```
offset  size  field
0x00    4     u32 meshId      CREAT id; 0 = dummy root
0x04    12    f32 xyz         local bone offset
0x14    4     bone index
0x18    4     u32 childCount  (0..8)
0x1C    4×N   child pointers
```

Walk only `+0x00` as the mesh id and `+0x1C` for `childCount` children. Treating every word as an id pulls in unrelated meshes (including id 0 → page 589). `+0x14` indexes the per-bone `s16` triplet in a `MO_*` frame ([motion.md](motion.md)).

Union of those mesh ids, then OBJ `usemtl page_N`, is the type’s skin set.

## Motion names (species roster)

674 strings at `DAT_005f1258`. Prefix is the developer name; Sega English names in the right column are inferred.

| Prefix | Clips | Index range (main run) | Likely character |
|--------|------:|------------------------|------------------|
| `z` | 196 | 467–650 | generic zombie |
| `k` | 80 | 211–288 | **Kageo** |
| `p` | 53 | 339–384 | player |
| `saru` | 49 | 403–451 | **Saruzou** |
| `ebitb` | 39 | 138–176 | **Ebitan** |
| `boss4` | 32 | 66–97 | **Magician** (stage 4) |
| `b3` | 28 | 38–65 | **Hermit** (`tojo_ana` = emerge from a hole) |
| `b1` | 23 | 0–21 | **Chariot** (`yoroi` = armor) |
| `dog` / `inu` | 23 | 100–210 | **Kenfis** |
| `dr` | 20 | 118–137 | **Drake** (knife/throw) |
| `s` | 18 | 385–402 | scientist / civilian (`help`) |
| `b2` | 16 | 22–37 | **Hangedman** (`fly` / `glider` / `bat`) |
| `mol` | 13 | 300–312 | **Murrer** (hole-emerge) |
| `gman` | 12 | 188–199 | **Goldman** |
| `kyu` / `kyuri` | 12 | 289–299 | **Cyril** |
| `frog` | 11 | 177–187 | **Bouere** |
| `tom` | 8 | 459–466 | **Thomas Rogan** |
| `hiru` | 6 | 200–205 | **Name** (leech / slug) |
| `mrg` | 4 | 332–335 | **G** |
| `onozonbia` | 3 | 336–338 | Cyril axe walk |
| `taraba` | 3 | 453–455 | **Taran** (crab) |
| `tekk` | 3 | 456–458 | **Robert** (iron arm) |

`O_*.rbh` names (`O_ST4BO1`, `O_ENEMY1`, `O_INU`, `O_FROG2`) are mixer labels (`sound\O_%s.rbh`), not CREAT or page keys.

## VVTP page bands

The creature `.vmc` is a **whole-game atlas**. Page ids (header `pageId`, same numbers as `-p` PNG names):

| Pages | Used by |
|------:|---------|
| 1–337 | `spr.rbh` frames |
| 338–511 | unused gap (174 missing ids in `B_RED`) |
| 512–546 | `world*.rbh` |
| **547–595** | **CREAT mesh skins** |

Page 18 is a sprite page, not a creature skin.

## Official roster → engine types

Sega names and A–G codes from the Saturn manual / Curien report. Engine types from `DAT_005d46ac` + CREAT skeleton pages + slot-128 `spawnEventId` (that field *is* the type for `BindSpawnEventType` (`FUN_0047b2c4`)). Default motions are often a shared idle (`MO_b3_pose_2`); species clips live in the 674-name `MO_*` list.

| Sega | Name | Chapters | Type(s) | Conf. | Evidence |
|------|------|----------|---------|-------|----------|
| A-1 | **Sam** | 1–4 | **16**, 91 | high | Exe logs `ENGuard_BO_zonbiman` when type `== 0x10`; grey muscular page 556 |
| A-2 | Neil | 1–3 | 11? | medium | Stronger Sam; type 11 is scale 1.2 on the green-flesh + civilian mix |
| A-3 | **Cyril** | 1–3 | **18** | high | Grey suit + chest wound, radius 9, `MO_kyu_*` / `MO_onozonbia_*` |
| B-1 / B-2 | Kageo / Bourbon | 1, 3 | 3, 4 | medium | Green rotting page 550; `MO_k_*` is the largest non-generic clip set |
| B-3 / B-4 | Ebitan a / b | 1–3 | 87 | medium | Green cracked 575/583; `MO_ebitb_*` and `MO_d_sakaoli` (hang) |
| C-1 / C-2 | Samson / Bentley | 1–4 | 71, 73 | medium | Stony muscular + belt on page 578 |
| C-3 | Burner | 3 | 74? | low | Blowtorch Samson; red muscular page 580 |
| D-1 | Simon | 1–2 | 82 | medium | Grey muscular grinning; shoulder-tackle type |
| D-2 | Gilmore | 2, 4 | — | — | Sledgehammer; not pinned |
| D-3 | Harris | 3–4 | — | — | Ball and chain; not pinned |
| D-4 | Robert | 3–4 | — | — | Metal arm; `MO_tekk_*` |
| E-1 | Rubin | 2 | — | — | Rolls / claws; not pinned |
| E-2 | **Drake** | 2 | **83**, 84 | high | Default motion `MO_dr_l_nage`; grinning one-eyed page 574 |
| E-3 | Moody | 3–4 | — | — | Iron claw / wall; `MO_mood*` / `MO_monkabe*` |
| E-4 | Parlor | 3–4 | 84? | low | Drake-like; `MO_dr_knif_chaku` |
| F-1 | Kenfis | 1 | 75? | low | Hellhound; `MO_ddogg*` / `MO_inu*` |
| F-2 | **Saruzou** | 1 | **1** | high | Primate pages 582/585, scale 0.5; 68 Stage 01 slot-128 spawns |
| F-3 | Bouere | 1 | — | — | Water frog; `MO_frog_*` (not `MO_dr_*`) |
| F-4 | **Devilon** | 1, 2, 4 | **76** | high | Blue hexagonal demon, pages 557–558 |
| G-1 | Murrer | 1–2 | 60 / 75? | low | Hole-emerge; `MO_mol_hole_*` |
| G-2 | Name | 1 | 60 / 75? | low | Wall slug; `MO_hiru_*` |
| G-3 | Taran | 3 | — | — | Crawler; `MO_taraba_*` |
| other | kage / pdolob / neopetit / taalu | 1–3 | 86? | low | Unnamed in 1996 print; `MO_zonbi1/2/3` are background walkers |
| Type 27 | **Chariot** | 1, 4 | **35**, **36** | high | Armor pages 547–549; slot 37 writes type 35 (HP 480) |
| Type 041 | **Hangedman** | 1–2 | **6**, 7, 8, 38 | high | Bat-wing page 554; slots 35/36 hardcode type 6 |
| Type 6803 | **Hermit** | 3 | **64** | high | 28 bones; six-hole mask pages 561/562/591; `MO_b3_tojo_ana` |
| Type 0 | **Magician** | 4 | **51** | high | `MO_boss4_*`; grey bald page 569; radius 12 |
| NPC | **Goldman** | story | **2** | high | Brown coat, glasses, DBR badge; scale 1.4 |
| NPC | Scientists / civilians | 1–4 | 17, 19–28, 49, 65, 89 | high | Lab-coat page 551 cluster; civilian 552+568 |
| NPC | Rogan / G / Sophie / Curien | story | — | — | Single CREAT meshes from `DAT_005ce368` (Sophie = id **7482**, pages 559+560, scale 1.2). Clips `MO_p_*`, `MO_tom_*`, `MO_mrg_*`, `MO_synd_demo` exist but have no type-row skeleton. |

`DAT_005ce368` slot 5 ("Researcher", CREAT id **7483**, scale 0.8) is **not a character mesh**. Its 17 verts split into two mirrored clusters, and the UV patch on page 566 is a small ring (a lens), not skin. The name in the story-NPC table does not mean the CREAT id is a full body.

## Type → page (all 94)

Skeleton walk → unique pages, then checked against `B_RED` PNGs. Hit radius / scale from `DAT_005d46ac`. Bone count from `DAT_005efa58`. Radius is the gun hit-sphere, not combat HP.

High-confidence rows:

| Type | Pages | Bones | Radius | Scale | Identification |
|-----:|-------|------:|---:|------:|----------------|
| 1 | 582, 585 | 16 | 8 | 0.5 | **Saruzou** |
| 2 | 560, 565, 571 | 20 | 5 | 1.4 | **Goldman** |
| 6 | 554 | 10 | 7 | 1.0 | **Hangedman** (slots 35/36 write this; default motion is Hermit `MO_b3_atk_l`, posed ref is motion 22) |
| 16 | 556 | 18 | 2 | 1.5 | **Sam** (`zonbiman`) |
| 17, 19–21, 24, 49 | 551 | 18–20 | ~5–8 | 1.0 | DBR lab-coat scientists |
| 18 | 563 | 16 | 9 | 1.0 | **Cyril** |
| 35 / 36 | 35: 547–549, 576; 36: 548–549 | 18 | 1.8 / 8 | 0.5 / 1.0 | **Chariot** |
| 51 | 569 | 18 | 12 | 1.0 | **Magician** |
| 64 | 561, 562, 591 | **28** | 2.6 | 1.0 | **Hermit** |
| 76 | 557, 558 | 16 | 2.8 | 1.2 | **Devilon** |
| 83 | 574 | 18 | 2.5 | 1.0 | **Drake** (`MO_dr_l_nage`) |

Hangedman's skeleton is a chain, not a biped: root part `1078` branches into a 5-link run (`1080→1082→1084→1086→1088`, each offset `+1.30` in local Z) plus a shorter branch (`1076→1092→1090`). Do not map type-6 bone ids onto arms, legs, or a head without checking each mesh. Species clips are `MO_b2_*`; the type-row default `MO_b3_atk_l` is a shared Hermit idle.

Medium / notable variants: 3–4 Kageo family (page 550); 7 Hangedman body (554+576); 8 Hangedman-sized Stage 02 (radius 12.5); 11 Neil/swamp mix; 23/25–27 civilians (552+568); 38 flying/Hangedman (558+569); 71/73 C-type (578); 82 Simon (573); 84 Drake/Parlor (`MO_dr_knif_chaku`); 87 Ebitan (575+583); 91 Sam variant (556+576).

Type 0 is an all-zero template (bones still 21). Types 5, 10, 39, 44, 52, 66, 75 have **no** VVTP pages on the skeleton walk — 75 (9 bones, scale 0.5) and 60 (scale 0.25) are the best animal/insect candidates.

There are 94 types. Many are clothing/damage/LOD variants that share a page set. Gilmore, Harris, Robert, Rubin, Moody, Kenfis, Bouere, Murrer, Name, Taran, and Curien still have motion sets but no unique type-row default. Sophie / Rogan / G story meshes are the character table at `DAT_005ce368` (not the 94-row type table): slot 4 is Sophie, CREAT id 7482.

## How to reproduce

`scripts/creature_map.py` reads `THOTD.exe` and the retail files under `assets/` (`CREAT1.RBH`, `CREAT2.rbh`, `evtALL.rbh`, `B_RED.VMC`). Skin pages are the CREAT `texPageId`s on the skeleton walk, so a prior `-m` / `-p` / `-e` run is not required.

Exe: `HOTD_EXE`, else `hotd-exe/THOTD.exe`, else `../typescript/hotd-decompress/hotd-exe/THOTD.exe`. Assets: `HOTD_ASSETS` or `assets/`.

1. `uv run python scripts/creature_map.py` — 94 type rows, skeleton mesh ids, CREAT page sets, spawn-fn table (`DAT_005d8118`), and evtALL usage. Writes `decompressed_assets/exe_tables/creature-map.json`.
2. `uv run python scripts/creature_map.py clusters` — group types by page set; histogram `spawnEventId`; list callers of `ApplyCreatureTypeStats` (`FUN_00483ad0`). Writes `creature-clusters.json`.
3. `uv run python scripts/creature_map.py more` — type rows 94–127 and the slot-128 prolog.
4. `uv run python scripts/creature_map.py hp` — spawns with `unk22 >= 10`, Stage 03/04 slot usage, slot 128 by `spawnEventId`.
5. `sample_motion_frame` in `src/hotd_decompress/motion.py` — one `MO_*` frame (Hangedman reference: motion 22, frame 0, 10 bones). See [motion.md](motion.md).

To join a type to a skin by hand: walk `DAT_005ef8e0[type]`, collect `meshId`s, look up that CREAT node's `usemtl page_N`.

JSON from the runner lands under `decompressed_assets/exe_tables/` (`creature-map.json`, `creature-clusters.json`). Gitignored, not a CLI output.
