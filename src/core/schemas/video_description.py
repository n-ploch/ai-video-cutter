from __future__ import annotations

from pydantic import BaseModel


class VideoVlm(BaseModel):
    """VLM output for an entire video."""
    description: str = ""
    key_subjects: list[list[str]] = []  # [[name, description], ...]
    tone: list[str] = []
    genre_or_type: str = ""
    tags: list[str] = []


class VideoDescription(BaseModel):
    """Stored at videos/{video_hash}/descriptions/vlm.json."""
    video_id: str       # content-hash of the video file
    video_file: str     # original filename (e.g. "DJI_0135.MP4")
    vlm: VideoVlm = VideoVlm()
