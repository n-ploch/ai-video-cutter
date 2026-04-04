from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, field_validator


class VideoFile(BaseModel):
    path: Path
    duration: float       # seconds
    fps: float
    width: int
    height: int
    codec: str

    @field_validator("path", mode="before")
    @classmethod
    def coerce_path(cls, v: Any) -> Path:
        return Path(v)


class FrameMetrics(BaseModel):
    frame_index: int
    timestamp: float
    metrics: dict[str, Any] = {}


class ProcessingConfig(BaseModel):
    target_fps: float | None = None  # None → preserve native fps
    target_width: int = 640          # height is derived from aspect ratio
    output_format: str = "mp4"
    hwaccel: str | None = None  # e.g. "videotoolbox" (macOS), "cuda", "vaapi"


class SegmentationConfig(BaseModel):
    fd_penalty: float = 3.0       # Pelt l2 penalty for coarse scene boundaries
    subseg_penalty: float = 2.0   # Pelt l1 penalty for camera-movement boundaries
    savgol_window: int = 11       # Savitzky-Golay smoothing window
    savgol_poly: int = 2          # Savitzky-Golay polynomial order
