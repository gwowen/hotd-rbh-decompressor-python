# Cutscene audio cue sheet

There is no FMV and no subtitle text. A “cutscene” is an `evtALL.rbh` event section: camera rail, actor spawns, and `SNDON`. This note is how those `SNDON` ops join to the clip `PlayDigitalSfx` (`FUN_00412000`) requests.

On-disk PCM: [audio.md](audio.md). Event VM / rails: [cutscenes.md](cutscenes.md), [events-detailed.md](events-detailed.md).

This is **not** a CLI flag. WAV export stays `-w`. The per-scene sheet is generated, not stored in this tree:

```text
uv run python scripts/cutscene_cues.py
```

That writes `decompressed_assets/exe_tables/cutscene-cues.json` (gitignored) from `evtALL.rbh` and `DAT_005cbda8`. Retail checks: 270 sound-request rows, 272 `SNDON` ops.

## `SNDON` → `PlayDigitalSfx` (`FUN_00412000`)

`SNDON` (`0x5a`) takes one `u32`. That value is an index into `DAT_005cbda8`, **not** an `O_*` `soundId` and **not** a `gamesnds` row.

```
DAT_005cbda8  270 × 0x0C
  +0x00  u32 kind     0 nop, 1 mixer, 2 mixerDrain, 3 mixer3 (CD via PlayCdAudioTrack), 4 oneshot, 5 stop
  +0x04  u32 namePtr  C string stem for kind 4 (sprintf "sound\\O_%s.rbh")
  +0x08  s32 extra    gamesnds index (kinds 1–2), CD gate (kind 3), mixer id (kind 4), or −1
```

PE: image base `0x400000`, DGROUP VA `0x5A0000` (file `0x187400`). File offset = `0x187400 + (VA − 0x5A0000)`.

| Kind | Name | What plays |
|------|------|------------|
| 0 | `nop` | Nothing (`extra` is usually `−1`) |
| 1 | `mixer` | `gamesnds.rbh` row `extra` (embedded PCM, or external `O_*` via `soundId`) |
| 2 | `mixerDrain` | Drain loop: `DispatchSoundCallback` (`FUN_005656d0`) until `−1` |
| 3 | `mixer3` | CD audio: `PlayDigitalSfx` (`FUN_00412000`) at `0x4120AA–0x4120EB` calls `PlayCdAudioTrack` (`FUN_00565d60`) when `DAT_00d5b214` is set and `extra != −1`. `extra` is not a `gamesnds` clip |
| 4 | `oneshot` | `sound\O_%s.rbh` from `namePtr`. `extra` is a mixer id, **not** the file `soundId` |
| 5 | `stop` | Stop / gate (`DispatchSoundCommand` (`FUN_00411f9c`)) |

Kind 4 `extra` is **not** the oneshoot header `soundId`. `O_HELP.rbh` is table id **123** (file `soundId` 28). `O_voc09.rbh` is table id **165**, the only `O_voc*` `SNDON` in `evtALL` (Stage 04 Scene 00). The other voc clips are fired from entity / player-voice code, not this opcode stream.

Stage **tt** (title) has no `SNDON`. Scene-open `SNDON 9` / `10` / `16` / `22` are per-chapter CD stingers (kind 3).

`scripts/cutscene_cues.py` records each `SNDON` as `{stage, scene, section, sndonId, kind, kindName, extra, sample}`. `sample` is `O_NAME.rbh`, `gamesnds[index]`, or `cdaudio[extra]`.
