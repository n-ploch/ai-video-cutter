from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import numpy as np

from core.schemas.segment import Segment
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
) -> list[Segment]:
    """
    Detect scene and camera-movement boundaries, return list of Segment objects.

    Parameters
    ----------
    signal     : shape (T, C) — raw or preprocessed, caller's choice.
                 The same signal is used for both the l2 scene pass and the
                 l1 per-scene movement pass.
    timestamps : shape (T,) aligned with signal rows.
    fd_penalty : Pelt l2 penalty for coarse scene boundaries.
    subseg_penalty : Pelt l1 penalty for movement boundaries within each scene.
    """
    if len(signal) < 2:
        return []

    scene_boundaries = detect_scene_boundaries(signal, penalty=fd_penalty)
    starts = [0] + scene_boundaries[:-1]
    ends = scene_boundaries

    segments: list[Segment] = []
    for scene_idx, (s, e) in enumerate(zip(starts, ends)):
        scene_ts = timestamps[s:e]
        scene_signal = signal[s:e]

        if len(scene_ts) == 0:
            continue

        move_boundaries = detect_movement_boundaries(scene_signal, penalty=subseg_penalty)
        move_starts = [0] + move_boundaries[:-1]

        camera_movements = []
        for sub_idx, (ms, me) in enumerate(zip(move_starts, move_boundaries)):
            sub_ts = scene_ts[ms:me]
            if len(sub_ts) < 2:
                continue
            camera_movements.append(
                movement_stats(scene_signal[ms:me], sub_ts, scene_id=scene_idx, subsegment_id=sub_idx)
            )

        segments.append(Segment(
            scene_id=scene_idx,
            start_frame=s,
            end_frame=e - 1,
            start_time=float(scene_ts[0]),
            end_time=float(scene_ts[-1]),
            keyframe_indices=[s + len(scene_ts) // 2],
            camera_movements=camera_movements,
        ))

    return segments


def save_segments(
    storage,
    project_id: str,
    segments: list[Segment],
) -> Path:
    """Persist segments to {project_id}/analysis/segments.json."""
    return storage.save_json(project_id, "segments", [asdict(seg) for seg in segments])
