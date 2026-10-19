"""Spawn angles, motion clips, the sound-request table, and Hermite rails."""

from __future__ import annotations

import struct

import pytest

from hotd_decompress.camera import CameraKey, CameraTrack, sample_track
from hotd_decompress.creature_map import BONE_VA, DGROUP_FILE, DGROUP_VA, find_exe, load_exe
from hotd_decompress.event import (
    CameraBind,
    EventOp,
    EventScene,
    EventSection,
    extract_events,
    parse_entb_record,
    parse_entbe_record,
)
from hotd_decompress.motion import motion_frame_stride, sample_motion_frame
from hotd_decompress.rail_timeline import KEEP_CURRENT_T, collect_rail_segments
from hotd_decompress.sound_table import parse_sound_request_table
from tests.helpers import ASSETS, asset, requires_assets

EXE = find_exe()
requires_exe = pytest.mark.skipif(EXE is None, reason="THOTD.exe not found")


def _track() -> CameraTrack:
    return CameraTrack(
        offset=0,
        keyCount=2,
        channelId=2,
        keys=[
            CameraKey(t=0.0, value=0.0, slopeIn=0.0, slopeOut=0.0),
            CameraKey(t=2.0, value=10.0, slopeIn=0.0, slopeOut=0.0),
        ],
    )


def _rail_scene(binds: list[tuple[int, int, int]]) -> EventScene:
    ops = [
        EventOp(
            offset=0,
            op=0x3C,
            name="CCTB",
            args=[],
            camera=CameraBind(
                job=0x40,
                jobName="rail",
                args=[],
                startFrame=start,
                endFrame=end,
                camGroup=group,
                flags=0,
            ),
        )
        for start, end, group in binds
    ]
    return EventScene(
        index=2,
        offset=0,
        sections=[EventSection(offset=0, words=[], ops=ops)],
        name="Scene 002",
    )


def test_hermite_midpoint_and_clamp() -> None:
    track = _track()
    assert sample_track(track, -1.0) == 0.0
    assert sample_track(track, 2.0) == 10.0
    assert abs(sample_track(track, 1.0) - 5.0) < 1e-5


def test_keep_current_t_uses_previous_end_for_that_group() -> None:
    scene = _rail_scene(
        [
            (0, 80, 3),
            (KEEP_CURRENT_T, 150, 3),
            (KEEP_CURRENT_T, 40, 1),
            (10, 20, 3),
        ]
    )
    segments = collect_rail_segments([scene])
    assert [(s.camGroup, s.startFrame, s.endFrame) for s in segments] == [
        (3, 0, 80),
        (3, 80, 150),
        (1, 0, 40),
        (3, 10, 20),
    ]


def test_motion_stride() -> None:
    assert motion_frame_stride(10) == 72
    assert motion_frame_stride(0) == 12
    assert motion_frame_stride(1) == 20


def test_entb_angles_stay_integer_words() -> None:
    body = bytearray(0x28)
    struct.pack_into("<I", body, 0, 102)
    struct.pack_into("<f", body, 8, 1.0)
    struct.pack_into("<f", body, 12, -25.0)
    struct.pack_into("<f", body, 16, -1125.0)
    struct.pack_into("<I", body, 20, 0)
    struct.pack_into("<I", body, 24, 0xD000)
    struct.pack_into("<I", body, 28, 0)
    rec = parse_entb_record(bytes(body), 0)
    assert rec is not None
    assert rec.typeId == 102
    assert rec.x == 1.0
    assert rec.rx == 0
    assert rec.ry == 0xD000
    assert rec.rz == 0
    assert type(rec.ry) is int

    entbe = bytearray(0x24)
    struct.pack_into("<I", entbe, 24, 0x3000)
    extended = parse_entbe_record(bytes(entbe), 0)
    assert extended is not None
    assert extended.ry == 0x3000
    assert type(extended.ry) is int


@requires_assets
def test_scene002_slot102_yaw_words() -> None:
    bank = extract_events(asset("evt", "allstage", "evtALL.rbh"))
    stage = next(row for row in bank.stages if row.name == "Stage 01")
    scene = next(row for row in stage.scenes if row.name == "Scene 002")
    yaws = [
        spawn.ry
        for section in scene.sections
        for op in section.ops
        for spawn in (op.spawns or [])
        if spawn.typeId == 102 and spawn.ry is not None
    ]
    assert 0xD000 in yaws
    assert 0x3000 in yaws
    assert all(isinstance(yaw, int) for yaw in yaws)


@requires_exe
def test_sound_request_table() -> None:
    assert EXE is not None
    rows = parse_sound_request_table(load_exe(EXE).data)
    assert len(rows) == 270
    assert {row.kind for row in rows} <= set(range(6))
    by_id = {row.id: row for row in rows}
    assert by_id[123].kindName == "oneshot"
    assert by_id[123].oneshotName == "HELP"
    assert by_id[165].oneshotName == "VOC09"
    assert by_id[9].kindName == "mixer3"


@requires_exe
def test_hangedman_motion_22_frame_0() -> None:
    assert EXE is not None
    exe = load_exe(EXE)
    bone_at = DGROUP_FILE + (BONE_VA - DGROUP_VA) + 6 * 4
    bone_count = struct.unpack_from("<i", exe.data, bone_at)[0]
    assert bone_count == 10
    frame = sample_motion_frame(exe.data, 22, 0, bone_count)
    assert frame.name == "MO_b2_base"
    assert frame.frame == 0
    assert frame.frameCount == 60
    assert len(frame.bones) == 10
    assert frame.header[0] == 0.0 and frame.header[2] == 0.0
    assert abs(frame.header[1] - 16.149700164794922) < 1e-5
    assert (frame.bones[0].ax0, frame.bones[0].ax1, frame.bones[0].ax2) == (0, 0, 0)
    assert (frame.bones[1].ax0, frame.bones[1].ax1, frame.bones[1].ax2) == (16384, 3785, 16384)
