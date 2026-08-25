"""
Camera rail bank (assets/cam/allstage/camALL.rbh).

BODY0 root: groupPtrs[N] (N = firstPtr/4). Each group is a track-pointer
table whose length is implied by (firstTrackPtr - groupPtr) / 4.

Track (FUN_004caa70 Hermite-like keys):
  +0x00 u16 keyCount
  +0x02 u16 channelId   // observed 2..6
  +0x04 Key[keyCount]
  Key = { f32 t, value, slopeIn, slopeOut } (16 bytes)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hotd_decompress.binary import NULL, f32, u16, u32
from hotd_decompress.jsonutil import write_json
from hotd_decompress.piff import Source
from hotd_decompress.rbh import RbhFile, load_rbh


@dataclass
class CameraKey:
    t: float
    value: float
    slopeIn: float
    slopeOut: float


@dataclass
class CameraTrack:
    offset: int
    keyCount: int
    channelId: int
    keys: list[CameraKey]


@dataclass
class CameraGroup:
    index: int
    offset: int
    tracks: list[CameraTrack]


@dataclass
class CameraBank:
    groups: list[CameraGroup]
    path: str | None = None


def looks_like_root_table(body: bytes) -> bool:
    if len(body) < 8:
        return False
    first = u32(body, 0)
    if first == 0 or first == NULL or first % 4 != 0:
        return False
    if first > 0x1000 or first >= len(body):
        return False
    return True


def parse_track(body: bytes, offset: int) -> CameraTrack:
    if offset + 4 > len(body):
        raise ValueError(f"Track header @ 0x{offset:x} past end")
    key_count = u16(body, offset)
    channel_id = u16(body, offset + 2)
    end = offset + 4 + key_count * 16
    if end > len(body):
        raise ValueError(f"Track @ 0x{offset:x} extends past BODY ({key_count} keys)")

    keys: list[CameraKey] = []
    for i in range(key_count):
        at = offset + 4 + i * 16
        keys.append(
            CameraKey(
                t=f32(body, at),
                value=f32(body, at + 4),
                slopeIn=f32(body, at + 8),
                slopeOut=f32(body, at + 12),
            )
        )

    return CameraTrack(offset=offset, keyCount=key_count, channelId=channel_id, keys=keys)


def parse_group(body: bytes, index: int, offset: int) -> CameraGroup:
    if offset + 4 > len(body):
        raise ValueError(f"Camera group {index} @ 0x{offset:x} past end")
    first_track = u32(body, offset)
    if first_track < offset + 4 or first_track >= len(body):
        raise ValueError(
            f"Camera group {index}: bad first track ptr 0x{first_track:x}"
        )
    if (first_track - offset) % 4 != 0:
        raise ValueError(f"Camera group {index}: misaligned track table")

    track_count = (first_track - offset) // 4
    tracks: list[CameraTrack] = []
    for i in range(track_count):
        ptr = u32(body, offset + i * 4)
        tracks.append(parse_track(body, ptr))

    return CameraGroup(index=index, offset=offset, tracks=tracks)


def parse_camera_bank(file: RbhFile) -> CameraBank:
    if len(file.bodies) != 1:
        raise ValueError(f"Expected 1 BODY for camera bank, got {len(file.bodies)}")
    body = file.bodies[0].data
    if not looks_like_root_table(body):
        raise ValueError("BODY does not look like a camera group pointer table")

    group_count = u32(body, 0) // 4
    groups: list[CameraGroup] = []

    for i in range(group_count):
        ptr = u32(body, i * 4)
        if ptr == NULL:
            continue
        groups.append(parse_group(body, i, ptr))

    return CameraBank(path=file.path, groups=groups)


def extract_cameras(source: Source) -> CameraBank:
    return parse_camera_bank(load_rbh(source))


@dataclass
class WriteCamerasResult:
    bank: CameraBank
    written: list[str]


def convert_cameras_to_json(source: Source, out_dir: str) -> WriteCamerasResult:
    """Write cameras.json under outDir."""
    bank = extract_cameras(source)
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    payload = {
        "source": bank.path,
        "groupCount": len(bank.groups),
        "groups": bank.groups,
    }

    path = str(Path(out_dir) / "cameras.json")
    write_json(path, payload)
    return WriteCamerasResult(bank=bank, written=[path])
