# Audio (digital SFX)

Digital sound effects live in RBHF files under `assets/sound/`. They are already uncompressed (`BODY` only, no `PACK`).

Stage / menu **music** is CD audio via MCI (`cdaudio`) in the exe. It is not in these files.

Decomp: `FUN_00411f10` inits the mixer at **11025 Hz, 8-bit, 3 voices**. The “3 channels” are mixer voices, not stereo in the files. Sample rate constant `_DAT_00c721e4 = 0x2b11`. Runtime oneshoots are requested as `sound\O_%s.rbh`.

## Shared PCM format

| Property | Value |
|----------|-------|
| Rate | 11025 Hz (`0x2B11`) |
| Width | Unsigned 8-bit |
| Channels | Mono |
| Silence | ≈ `0x80` |

This tool writes standard PCM WAVs (`src/wav.ts`) with those parameters.

## Oneshoot — `O_*.rbh`

One clip per file. RBHH: a single row with `flags=0`. One `BODY`.

```
BODY:
  +0x00  u32  magic     0x00082C30
  +0x04  u16  0x0002
  +0x06  u16  soundId
  +0x08  u8[] unsigned PCM  (rest of BODY)
```

`0x00082C30` is also the **external-ref sentinel** in `gamesnds.rbh` (see below). `soundId` is how the bank points at a sibling `O_*` file.

Export: `bun run index.ts -w assets/sound/O_HELP.rbh` → `decompressed_assets/O_HELP_wav/O_HELP.wav`.

## Bank — `gamesnds.rbh`

RBHH two rows: `flags=2` then `flags=0`. Two BODYs:

| BODY | Role |
|------|------|
| 0 | Index: `N` records of **0x28** bytes |
| 1 | Concatenated embedded PCM |

Index size must be a multiple of `0x28`. This tool requires `sampleRate` at `+0x08` of the first row to be `0x2B11`.

### Index row (0x28 bytes)

Known fields used by `src/audio.ts`:

```
offset  size  field
0x00    4     (unused by this tool)
0x04    4     size         PCM byte length
0x08    4     sampleRate   0x2B11
0x0C    8     (unused by this tool)
0x14    4     soundId      O_* id when external
0x18    4     offset       into BODY1, or sentinel
0x1C    12    (unused by this tool)
```

### Embedded vs external

| `offset` (`+0x18`) | Meaning |
|--------------------|---------|
| Any other value | Byte offset into BODY1; take `size` bytes of PCM from there |
| `0x00082C30` | External: play the oneshoot whose `soundId` is at `+0x14` |

WAV export of the bank scans the same directory for `O_*.rbh`, keys them by `soundId`, and fills external rows. Missing siblings are skipped (`skippedExternal`).

Output names:

- Embedded: `clip_XXX.wav`
- External: `ext_XXX_O_NAME.wav`

## How the tool works

```text
bun run index.ts -w|--wav <file.rbh> [outdir]
```

`convertSoundsToWav` (`src/audio.ts` + `src/wav.ts`):

1. `loadPiff` + `decompressPiff` (sound files in this tree have no PACK; this is a no-op).
2. Collect `BODY` chunks.
3. **Oneshoot** if there is one BODY starting with `0x00082C30` / `u16 2`. Clip name = input stem (`O_HELP.rbh` → `O_HELP.wav`).
4. **gamesnds** if there are two BODYs, index length `% 0x28 == 0`, and `+0x08` of the first row is `0x2B11`. Then:
   - scan `dirname(input)` for `O_*.rbh`, parse each oneshoot, key by `soundId`;
   - embedded rows → slice BODY1, name `clip_XXX`;
   - external rows → copy the matching oneshoot, name `ext_XXX_O_NAME`; missing siblings increment `skippedExternal` and are omitted.
5. `encodeWavPcm8Mono` — RIFF WAV, unsigned 8-bit, 1 channel, 11025 Hz.
6. Default dir: `decompressed_assets/<stem>_wav/`.

Stdout: clip count, format line, skipped external refs (if any), files written.

Zero clips → exit 1 (wrong file, or CD music path). The tool does not touch MCI `cdaudio`.
