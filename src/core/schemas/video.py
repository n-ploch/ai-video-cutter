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
    target_fps: float = 4.0
    target_width: int = 640   # height is derived from aspect ratio
    output_format: str = "mp4"
    hwaccel: str | None = None  # e.g. "videotoolbox" (macOS), "cuda", "vaapi"
