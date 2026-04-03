from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from core.schemas.segment import FrameMetrics
from video.segmentation import SIGNAL_COLS


def compute_frame_metrics(
    frame_idx: int,
    timestamp: float,
    mag: float,
    coherence: float,
    decomp: dict | None,
) -> FrameMetrics:
    """
    Build a FrameMetrics from per-frame optical flow outputs.

    decomp is the dict returned by decompose_flow; pass None when RANSAC failed.
    """
    return FrameMetrics(
        frame_idx=frame_idx,
        timestamp=timestamp,
        flow_magnitude=mag,
        flow_coherence=coherence,
        pan=decomp["pan"] if decomp else None,
        tilt=decomp["tilt"] if decomp else None,
        roll=decomp["roll"] if decomp else None,
        zoom=decomp["zoom"] if decomp else None,
        scene_activity=decomp["scene_activity"] if decomp else None,
    )


def signal_row(timestamp: float, frame_idx: int, decomp: dict) -> dict:
    """
    Extract the SIGNAL_COLS dict from a successful RANSAC decomposition.

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
    project_id: str,
    metrics: list[FrameMetrics],
) -> Path:
    """Persist frame metrics to {project_id}/analysis/frame_metrics.json."""
    return storage.save_json(project_id, "frame_metrics", [asdict(m) for m in metrics])
