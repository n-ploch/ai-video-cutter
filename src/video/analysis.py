from __future__ import annotations

import numpy as np

from core.schemas.segment import CameraMovement, SegmentBase, make_segment_id
from video.segmentation import (
    detect_movement_boundaries,
    detect_scene_boundaries,
    movement_stats,
)


def build_segments(
    signal: np.ndarray,
    timestamps: np.ndarray,
    fd_penalty: float = 3.0,
    subseg_penalty: float = 2.0,
    source_video: str = "",
    video_file: str = "",
) -> list[SegmentBase]:
    """Detect scene and camera-movement boundaries, return list of SegmentBase.

    Parameters
    ----------
    signal       : shape (T, C) — raw or preprocessed, caller's choice.
    timestamps   : shape (T,) aligned with signal rows.
    fd_penalty   : Pelt l2 penalty for coarse scene boundaries.
    subseg_penalty : Pelt l1 penalty for movement boundaries within each scene.
    source_video : content-hash of the source video file.
    video_file   : original filename (e.g. "DJI_0135.MP4").
    """
    if len(signal) < 2:
        return []

    scene_boundaries = detect_scene_boundaries(signal, penalty=fd_penalty)
    starts = [0] + scene_boundaries[:-1]
    ends = scene_boundaries

    segments: list[SegmentBase] = []
    for segment_idx, (s, e) in enumerate(zip(starts, ends)):
        scene_ts = timestamps[s:e]
        scene_signal = signal[s:e]

        if len(scene_ts) == 0:
            continue

        move_boundaries = detect_movement_boundaries(scene_signal, penalty=subseg_penalty)
        move_starts = [0] + move_boundaries[:-1]

        movements: list[CameraMovement] = []
        for sub_idx, (ms, me) in enumerate(zip(move_starts, move_boundaries)):
            sub_ts = scene_ts[ms:me]
            if len(sub_ts) < 2:
                continue
            movements.append(
                movement_stats(
                    scene_signal[ms:me], sub_ts,
                    segment_id=segment_idx, movement_id=sub_idx,
                )
            )

        segments.append(SegmentBase(
            segment_id=make_segment_id(source_video, segment_idx),
            video_file=video_file,
            source_video=source_video,
            start=float(scene_ts[0]),
            end=float(scene_ts[-1]),
            camera_movements=movements,
        ))

    return segments


def save_segments(
    storage,
    project_name: str,
    video_hash: str,
    segments: list[SegmentBase],
) -> None:
    """Persist segments to ``videos/{video_hash}/segments/segments.json``."""
    storage.save_json(
        project_name,
        f"videos/{video_hash}/segments/segments.json",
        segments,
    )
