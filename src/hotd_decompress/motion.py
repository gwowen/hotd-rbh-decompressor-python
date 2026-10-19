"""
`MO_*` clips in `THOTD.exe` (`SampleSkeleton` (`FUN_004776c8`) / `ApplyFrameBoneRotates` (`FUN_00478448`)).

Not a PIFF payload and not a CLI flag. Frame stride = `(bone_count * 6 + 0x0F) & ~3`.
Playback: translate `(x, y, -z)`, then `Rz(-ax2) · Ry(ax1) · Rx(ax0)`.
"""

from __future__ import annotations

from dataclasses import dataclass

from hotd_decompress.binary import f32, s16, s32, u32

DGROUP_VA = 0x5A0000
DGROUP_FILE = 0x187400
MOTION_PTR_VA = 0x005EFBD0
FRAMECOUNT_VA = 0x005F0658
MOTION_NAME_VA = 0x005F1258
MOTION_COUNT = 674


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
        chars.append(chr(c))
        off += 1
        if len(chars) > 80:
            break
    return "".join(chars)


def motion_frame_stride(bone_count: int) -> int:
    return (bone_count * 6 + 0x0F) & ~3


@dataclass
class BoneAngles:
    ax0: int
    ax1: int
    ax2: int


@dataclass
class MotionFrame:
    index: int
    name: str
    frame: int
    frameCount: int
    header: tuple[float, float, float]
    bones: list[BoneAngles]


def sample_motion_frame(
    data: bytes,
    motion_index: int,
    frame: int,
    bone_count: int,
) -> MotionFrame:
    """One integer frame. No blend (`InterpolateBoneKeyframes` (`FUN_004775f4`) is unused)."""
    if motion_index < 0 or motion_index >= MOTION_COUNT:
        raise ValueError(f"motion {motion_index} out of range")
    if bone_count < 0:
        raise ValueError(f"bone count {bone_count} is negative")

    name_va = u32(data, va_to_file(MOTION_NAME_VA) + motion_index * 4)
    clip_va = u32(data, va_to_file(MOTION_PTR_VA) + motion_index * 4)
    frame_count = s32(data, va_to_file(FRAMECOUNT_VA) + motion_index * 4)
    stride = motion_frame_stride(bone_count)
    use_frame = frame
    if frame_count <= 0:
        use_frame = 0
    elif frame < 0:
        use_frame = 0
    elif frame > frame_count - 1:
        use_frame = frame_count - 1

    off = va_to_file(clip_va) + use_frame * stride
    if off + stride > len(data):
        raise ValueError(
            f"motion {motion_index} frame {use_frame} extends past the exe"
        )

    bones: list[BoneAngles] = []
    for i in range(bone_count):
        at = off + 0x0C + i * 6
        bones.append(
            BoneAngles(
                ax0=s16(data, at),
                ax1=s16(data, at + 2),
                ax2=s16(data, at + 4),
            )
        )

    return MotionFrame(
        index=motion_index,
        name=_cstr(data, name_va),
        frame=use_frame,
        frameCount=frame_count,
        header=(f32(data, off), f32(data, off + 4), f32(data, off + 8)),
        bones=bones,
    )
