from __future__ import annotations

from core.schemas.video import FrameMetrics
from video.segmentation import SIGNAL_COLS


def compute_frame_metrics(
    frame_idx: int,
    timestamp: float,
    mag: float,
    coherence: float,
    decomp: dict | None,
) -> FrameMetrics:
    """Build a FrameMetrics from per-frame optical flow outputs.

    All per-frame values are stored in the ``metrics`` dict so the schema
    stays flexible. ``decomp`` is the dict returned by decompose_flow; pass
    None when RANSAC failed.
    """
    metrics: dict = {
        "flow_magnitude": mag,
        "flow_coherence": coherence,
    }
    if decomp is not None:
        for key in ("pan", "tilt", "roll", "zoom", "scene_activity"):
            metrics[key] = decomp.get(key)

    return FrameMetrics(frame_index=frame_idx, timestamp=timestamp, metrics=metrics)


def signal_row(timestamp: float, frame_idx: int, decomp: dict) -> dict:
    """Extract the SIGNAL_COLS dict from a successful RANSAC decomposition.

    Returns a dict with keys: timestamp, frame_idx, pan, tilt, zoom, camera_magnitude.
    Only call this when decomp is not None.
    """
    return {
        "timestamp": timestamp,
        "frame_idx": frame_idx,
        **{col: decomp[col] for col in SIGNAL_COLS},
    }


def save_frame_metrics(
    storage,
    project_name: str,
    metrics: list[FrameMetrics],
) -> None:
    """Persist frame metrics to ``analysis/frame_metrics.json``."""
    storage.save_json(project_name, "analysis/frame_metrics.json", metrics)
