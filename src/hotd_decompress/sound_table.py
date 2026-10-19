"""
Sound-request table in THOTD.exe (`PlayDigitalSfx` (`FUN_00412000`) / `DAT_005cbda8`).

SNDON's u32 arg is an index into 0x0C-byte rows:
  +0x00 u32 kind     0 nop, 1 mixer, 2 mixerDrain, 3 mixer3 (CD), 4 oneshot, 5 stop
  +0x04 u32 namePtr  C string stem for kind 4 (sprintf "sound\\O_%s.rbh")
  +0x08 s32 extra    gamesnds index (kinds 1–2), CD gate (kind 3), mixer id (kind 4), or -1

Not a CLI flag. PE: image base 0x400000, DGROUP VA 0x5A0000 (file 0x187400).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hotd_decompress.binary import s32, u32
from hotd_decompress.event import EventBank
from hotd_decompress.jsonutil import write_json

DGROUP_VA = 0x5A0000
DGROUP_FILE = 0x187400
SOUND_TABLE_VA = 0x005CBDA8
SOUND_STRIDE = 0x0C
SOUND_KIND_MAX = 5
SOUND_ROW_LIMIT = 512

SOUND_KIND_NAMES = (
    "nop",
    "mixer",
    "mixerDrain",
    "mixer3",
    "oneshot",
    "stop",
)


def va_to_file(va: int) -> int:
    if va < DGROUP_VA:
        raise ValueError(f"VA 0x{va:x} is not in DGROUP")
    return DGROUP_FILE + (va - DGROUP_VA)


def _cstr(data: bytes, va: int) -> str:
    if va == 0:
        return ""
    off = va_to_file(va)
    chars: list[str] = []
    while off < len(data):
        c = data[off]
        if c == 0:
            break
        if c < 32 or c > 126:
            return ""
        chars.append(chr(c))
        off += 1
        if len(chars) > 40:
            break
    return "".join(chars)


@dataclass
class SoundRequest:
    id: int
    kind: int
    kindName: str
    namePtr: int
    extra: int
    """Stem inside O_%s.rbh for kind 4 (e.g. HELP2, VOC09)."""
    oneshotName: str | None = None


def parse_sound_request_table(data: bytes) -> list[SoundRequest]:
    """Parse `DAT_005cbda8` until kind is outside 0..5. Retail: 270 rows."""
    rows: list[SoundRequest] = []
    base = va_to_file(SOUND_TABLE_VA)
    for i in range(SOUND_ROW_LIMIT):
        off = base + i * SOUND_STRIDE
        if off + SOUND_STRIDE > len(data):
            break
        kind = u32(data, off)
        if kind > SOUND_KIND_MAX:
            break
        name_ptr = u32(data, off + 4)
        extra = s32(data, off + 8)
        oneshot = _cstr(data, name_ptr) if kind == 4 else ""
        rows.append(
            SoundRequest(
                id=i,
                kind=kind,
                kindName=SOUND_KIND_NAMES[kind],
                namePtr=name_ptr,
                extra=extra,
                oneshotName=oneshot or None,
            )
        )
    return rows


def sample_label(row: SoundRequest) -> str | None:
    """What `PlayDigitalSfx` requests. Kind 3 is a CD track, not a gamesnds clip."""
    if row.kind == 4 and row.oneshotName:
        return f"O_{row.oneshotName}.rbh"
    if row.kind in (1, 2):
        return f"gamesnds[{row.extra}]"
    if row.kind == 3:
        return f"cdaudio[{row.extra}]"
    return None


@dataclass
class SndonCue:
    stage: str | None
    stageIndex: int
    scene: str | None
    sceneIndex: int
    section: int
    sndonId: int
    kind: int
    kindName: str
    extra: int
    sample: str | None


def collect_sndon_cues(bank: EventBank, rows: list[SoundRequest]) -> list[SndonCue]:
    cues: list[SndonCue] = []
    for stage in bank.stages:
        for scene in stage.scenes:
            for section_index, section in enumerate(scene.sections):
                for op in section.ops:
                    if op.name != "SNDON" or not op.args:
                        continue
                    sndon_id = op.args[0]
                    row = rows[sndon_id] if 0 <= sndon_id < len(rows) else None
                    cues.append(
                        SndonCue(
                            stage=stage.name,
                            stageIndex=stage.index,
                            scene=scene.name,
                            sceneIndex=scene.index,
                            section=section_index,
                            sndonId=sndon_id,
                            kind=row.kind if row else -1,
                            kindName=row.kindName if row else "missing",
                            extra=row.extra if row else 0,
                            sample=sample_label(row) if row else None,
                        )
                    )
    return cues


def write_cue_sheet(
    bank: EventBank,
    rows: list[SoundRequest],
    out_path: Path,
) -> Path:
    cues = collect_sndon_cues(bank, rows)
    payload = {
        "rowCount": len(rows),
        "sndonCount": len(cues),
        "rows": rows,
        "cues": cues,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(str(out_path), payload)
    return out_path
