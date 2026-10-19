"""
Concatenate CCTB rail binds from evtALL scenes into a sampled camera path.

Walks sections/ops in file order. SKIP / branch ops are ignored — every job-0x40
bind plays back-to-back. startFrame 0xFFFFFFFF keeps the last end frame seen
for that camGroup (`BindCameraRail` (`FUN_00460fd0`)).

Not a CLI flag. `-c` still dumps keys.
"""

from __future__ import annotations

from dataclasses import dataclass

from hotd_decompress.camera import (
    CameraBank,
    CameraPose,
    camera_group_by_index,
    sample_camera_group,
)
from hotd_decompress.event import EventScene

# CCTB startFrame 0xFFFFFFFF: keep current t.
KEEP_CURRENT_T = 0xFFFFFFFF


@dataclass
class RailSegment:
    sceneIndex: int
    sceneName: str | None
    camGroup: int
    startFrame: int
    endFrame: int


def collect_rail_segments(scenes: list[EventScene]) -> list[RailSegment]:
    out: list[RailSegment] = []
    last_end_by_group: dict[int, int] = {}

    for scene in scenes:
        for section in scene.sections:
            for op in section.ops:
                cam = op.camera
                if cam is None or cam.jobName != "rail" or cam.camGroup is None:
                    continue
                cam_group = cam.camGroup
                start = 0 if cam.startFrame is None else cam.startFrame
                end = 0 if cam.endFrame is None else cam.endFrame
                if start == KEEP_CURRENT_T:
                    start = last_end_by_group.get(cam_group, 0)
                if start >= end:
                    continue
                out.append(
                    RailSegment(
                        sceneIndex=scene.index,
                        sceneName=scene.name,
                        camGroup=cam_group,
                        startFrame=start,
                        endFrame=end,
                    )
                )
                last_end_by_group[cam_group] = end

    return out


def sample_rail_segments(
    bank: CameraBank,
    segments: list[RailSegment],
) -> list[CameraPose]:
    """Sample each segment at integer frames [start, end)."""
    samples: list[CameraPose] = []
    for seg in segments:
        group = camera_group_by_index(bank, seg.camGroup)
        if group is None:
            raise ValueError(f"camALL has no group {seg.camGroup}")
        t = seg.startFrame
        while t < seg.endFrame:
            samples.append(sample_camera_group(group, float(t)))
            t += 1
    return samples
