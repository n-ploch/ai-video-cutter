from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FrameMetrics:
    frame_idx: int
    timestamp: float
    flow_magnitude: float | None
    flow_coherence: float | None
    pan: float | None
    tilt: float | None
    roll: float | None
    zoom: float | None
    scene_activity: float | None


@dataclass
class CameraMovement:
    scene_id: int
    subsegment_id: int
    start_time: float
    end_time: float
    pan_entry_vel: float
    tilt_entry_vel: float
    zoom_entry_vel: float
    pan_exit_vel: float
    tilt_exit_vel: float
    zoom_exit_vel: float
    pan_monotonicity: float
    tilt_monotonicity: float
    zoom_monotonicity: float
    pan_mean_abs_deriv: float
    tilt_mean_abs_deriv: float
    zoom_mean_abs_deriv: float
    pan_std_deriv: float
    tilt_std_deriv: float
    zoom_std_deriv: float


@dataclass
class Segment:
    scene_id: int
    start_frame: int
    end_frame: int
    start_time: float
    end_time: float
    keyframe_indices: list[int] = field(default_factory=list)
    camera_movements: list[CameraMovement] = field(default_factory=list)
