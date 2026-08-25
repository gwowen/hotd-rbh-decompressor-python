"""
HotD / Tantalus digital SFX in sound/*.rbh (not CD audio).

Engine init (FUN_00411f10): 11025 Hz, 8-bit; mixer has 3 voices.
Oneshoot O_*.rbh BODY:
  +0x00 u32 0x00082c30
  +0x04 u16 0x0002
  +0x06 u16 soundId
  +0x08 u8[] unsigned PCM (mono, silence ≈ 0x80)

gamesnds.rbh: RBHH flags 2 then 0 → index BODY + sample BODY.
Index entries are 0x28 bytes; sampleRate at +0x08 is 0x2b11 (11025).
Embedded clips use +0x18 as an offset into the sample BODY.
External clips use +0x18 == 0x00082c30 and +0x14 as the O_* soundId
(resolved from sibling O_*.rbh when exporting the bank).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from hotd_decompress.binary import u16, u32
from hotd_decompress.piff import PiffFile, Source, decompress_piff, load_piff
from hotd_decompress.wav import encode_wav_pcm8_mono

"""Matches FUN_00411f10 `_DAT_00c721e4 = 0x2b11`."""
SOUND_SAMPLE_RATE = 0x2B11

"""Oneshoot BODY magic / gamesnds external-offset sentinel."""
SOUND_ONESHOT_MAGIC = 0x00082C30

GAMESNDS_ENTRY_SIZE = 0x28


@dataclass
class SoundClip:
    """Stable name stem for output files (no extension)."""
    name: str
    soundId: int
    sampleRate: int
    """Unsigned 8-bit mono PCM."""
    pcm: bytes
    source: str  # "oneshot" | "gamesnds-embedded" | "gamesnds-external"


@dataclass
class ExtractSoundsResult:
    clips: list[SoundClip]
    skippedExternal: int


def is_oneshot_sound_body(data: bytes) -> bool:
    """True if a BODY payload looks like an O_* oneshoot sound."""
    if len(data) < 8:
        return False
    if u32(data, 0) != SOUND_ONESHOT_MAGIC:
        return False
    if u16(data, 4) != 2:
        return False
    return len(data) > 8


def parse_oneshot_sound_body(data: bytes, name: str = "sound") -> SoundClip:
    if not is_oneshot_sound_body(data):
        raise ValueError("Not an O_* oneshoot sound BODY")
    return SoundClip(
        name=name,
        soundId=u16(data, 6),
        sampleRate=SOUND_SAMPLE_RATE,
        pcm=data[8:],
        source="oneshot",
    )


@dataclass
class GamesndsEntry:
    index: int
    size: int
    sampleRate: int
    soundId: int
    offset: int
    external: bool


def parse_gamesnds_index(index_body: bytes) -> list[GamesndsEntry]:
    if len(index_body) % GAMESNDS_ENTRY_SIZE != 0:
        raise ValueError(
            f"gamesnds index size {len(index_body)} is not a multiple of {GAMESNDS_ENTRY_SIZE}"
        )

    entries: list[GamesndsEntry] = []
    count = len(index_body) // GAMESNDS_ENTRY_SIZE

    for i in range(count):
        at = i * GAMESNDS_ENTRY_SIZE
        size = u32(index_body, at + 0x04)
        sample_rate = u32(index_body, at + 0x08)
        sound_id = u32(index_body, at + 0x14)
        offset = u32(index_body, at + 0x18)
        if sample_rate != SOUND_SAMPLE_RATE:
            raise ValueError(f"gamesnds[{i}] sampleRate {sample_rate} != {SOUND_SAMPLE_RATE}")
        entries.append(
            GamesndsEntry(
                index=i,
                size=size,
                sampleRate=sample_rate,
                soundId=sound_id,
                offset=offset,
                external=offset == SOUND_ONESHOT_MAGIC,
            )
        )

    return entries


def is_gamesnds_bank(bodies: list[bytes]) -> bool:
    if len(bodies) != 2:
        return False
    index = bodies[0]
    if len(index) < GAMESNDS_ENTRY_SIZE:
        return False
    if len(index) % GAMESNDS_ENTRY_SIZE != 0:
        return False
    return u32(index, 0x08) == SOUND_SAMPLE_RATE


def extract_from_piff(
    file: PiffFile,
    *,
    oneshot_name: str | None = None,
    external_by_id: dict[int, SoundClip] | None = None,
) -> ExtractSoundsResult:
    decompressed = decompress_piff(file)
    bodies = [c.data for c in decompressed.chunks if c.tag == "BODY"]

    if len(bodies) == 1 and is_oneshot_sound_body(bodies[0]):
        stem = oneshot_name if oneshot_name is not None else "sound"
        return ExtractSoundsResult(
            clips=[parse_oneshot_sound_body(bodies[0], stem)],
            skippedExternal=0,
        )

    if not is_gamesnds_bank(bodies):
        return ExtractSoundsResult(clips=[], skippedExternal=0)

    entries = parse_gamesnds_index(bodies[0])
    sample_body = bodies[1]
    clips: list[SoundClip] = []
    skipped_external = 0

    for entry in entries:
        if entry.external:
            external = None if external_by_id is None else external_by_id.get(entry.soundId)
            if external is None:
                skipped_external += 1
                continue
            clips.append(
                SoundClip(
                    name=f"ext_{entry.index:03d}_{external.name}",
                    soundId=external.soundId,
                    sampleRate=external.sampleRate,
                    pcm=external.pcm,
                    source="gamesnds-external",
                )
            )
            continue

        if entry.offset + entry.size > len(sample_body):
            raise ValueError(
                f"gamesnds[{entry.index}] sample "
                f"0x{entry.offset:x}+{entry.size} exceeds BODY"
            )

        clips.append(
            SoundClip(
                name=f"clip_{entry.index:03d}",
                soundId=entry.soundId,
                sampleRate=entry.sampleRate,
                pcm=sample_body[entry.offset : entry.offset + entry.size],
                source="gamesnds-embedded",
            )
        )

    return ExtractSoundsResult(clips=clips, skippedExternal=skipped_external)


def load_oneshot_sounds_from_dir(dir: str) -> dict[int, SoundClip]:
    """Load sibling O_*.rbh oneshoots from the same directory, keyed by soundId."""
    by_id: dict[int, SoundClip] = {}
    path = Path(dir)
    try:
        names = [p.name for p in path.iterdir()]
    except OSError:
        return by_id

    for name in names:
        if not re.match(r"^O_.*\.rbh$", name, re.IGNORECASE):
            continue
        file_path = path / name
        file = load_piff(file_path)
        body = next((c for c in decompress_piff(file).chunks if c.tag == "BODY"), None)
        if body is None or not is_oneshot_sound_body(body.data):
            continue
        stem = re.sub(r"\.rbh$", "", name, flags=re.IGNORECASE)
        clip = parse_oneshot_sound_body(body.data, stem)
        by_id[clip.soundId] = clip

    return by_id


def extract_sound_clips(source: Source) -> ExtractSoundsResult:
    """Load a sound RBH and extract PCM clips."""
    file = load_piff(source)
    oneshot_name = None
    if isinstance(source, (str, Path)):
        oneshot_name = re.sub(r"\.rbh$", "", Path(source).name, flags=re.IGNORECASE)

    external_by_id: dict[int, SoundClip] | None = None
    if isinstance(source, (str, Path)):
        # Probe whether this is gamesnds before scanning the directory.
        bodies = [c.data for c in decompress_piff(file).chunks if c.tag == "BODY"]
        if is_gamesnds_bank(bodies):
            external_by_id = load_oneshot_sounds_from_dir(str(Path(source).parent))

    return extract_from_piff(file, oneshot_name=oneshot_name, external_by_id=external_by_id)


@dataclass
class WriteSoundsResult:
    clips: list[SoundClip]
    written: list[str]
    skippedExternal: int


def convert_sounds_to_wav(source: Source, out_dir: str) -> WriteSoundsResult:
    """Extract sound clips and write one WAV per clip."""
    extracted = extract_sound_clips(source)
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for clip in extracted.clips:
        path = str(Path(out_dir) / f"{clip.name}.wav")
        Path(path).write_bytes(encode_wav_pcm8_mono(clip.pcm, clip.sampleRate))
        written.append(path)

    return WriteSoundsResult(
        clips=extracted.clips,
        written=written,
        skippedExternal=extracted.skippedExternal,
    )
