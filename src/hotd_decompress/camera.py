"""
Camera rail bank (assets/cam/allstage/camALL.rbh).

BODY0 root: groupPtrs[N] (N = firstPtr/4). Each group is a track-pointer
table whose length is implied by (firstTrackPtr - groupPtr) / 4.

Track (`TickCameraRail` (`FUN_004caa70`) Hermite-like keys):
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


@dataclass
class CameraVec3:
    x: float
    y: float
    z: float


@dataclass
class CameraPose:
    eye: CameraVec3
    lookAt: CameraVec3


def sample_track(track: CameraTrack, frame: float) -> float:
    """Cubic Hermite lookup (`HermiteTrackLookup` (`FUN_00461858`)).

    Span uses the previous key's slopeOut as m0 and the current key's slopeIn
    as m1. Clamps to the first / last key when `frame` is outside the track.
    """
    keys = track.keys
    if not keys:
        return 0.0
    first = keys[0]
    if len(keys) == 1 or frame <= first.t:
        return first.value
    last = keys[-1]
    if frame >= last.t:
        return last.value

    i = 1
    while i < len(keys) and keys[i].t < frame:
        i += 1
    k0 = keys[i - 1]
    k1 = keys[i]
    dt = k1.t - k0.t
    if dt == 0.0:
        return k1.value

    u = (frame - k0.t) / dt
    u2 = u * u
    u3 = u2 * u
    h00 = 2.0 * u3 - 3.0 * u2 + 1.0
    h10 = u3 - 2.0 * u2 + u
    h01 = -2.0 * u3 + 3.0 * u2
    h11 = u3 - u2
    return (
        h00 * k0.value
        + h10 * k0.slopeOut * dt
        + h01 * k1.value
        + h11 * k1.slopeIn * dt
    )


def sample_camera_group(group: CameraGroup, frame: float) -> CameraPose:
    """Pose channels are track order, not channelId: 0–2 eye XYZ, 3–5 look-at XYZ."""
    if len(group.tracks) < 6:
        raise ValueError(
            f"Camera group {group.index} has {len(group.tracks)} tracks, need 6"
        )
    sampled = [sample_track(group.tracks[i], frame) for i in range(6)]
    return CameraPose(
        eye=CameraVec3(x=sampled[0], y=sampled[1], z=sampled[2]),
        lookAt=CameraVec3(x=sampled[3], y=sampled[4], z=sampled[5]),
    )


def camera_group_by_index(bank: CameraBank, index: int) -> CameraGroup | None:
    for group in bank.groups:
        if group.index == index:
            return group
    return None


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
