from __future__ import annotations

import json
import subprocess
from pathlib import Path

from core.schemas.video import VideoFile


class VideoIngestError(Exception):
    pass


def probe_video(path: Path | str) -> VideoFile:
    """
    Run ffprobe on *path* and parse the output into a VideoFile model.

    Raises VideoIngestError for:
      - file not found
      - no video stream present
      - corrupt / unreadable file
    """
    path = Path(path)
    if not path.exists():
        raise VideoIngestError(f"File not found: {path}")

    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise VideoIngestError("ffprobe not found; ensure ffmpeg is installed") from exc

    if result.returncode != 0:
        raise VideoIngestError(
            f"ffprobe failed on {path}: {result.stderr.strip()}"
        )

    try:
        probe = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise VideoIngestError(f"ffprobe returned invalid JSON for {path}") from exc

    video_stream = next(
        (s for s in probe.get("streams", []) if s.get("codec_type") == "video"),
        None,
    )
    if video_stream is None:
        raise VideoIngestError(f"No video stream found in {path}")

    fmt = probe.get("format", {})
    duration = _parse_float(
        video_stream.get("duration") or fmt.get("duration"), "duration"
    )
    fps = _parse_fps(video_stream.get("r_frame_rate", "0/1"))

    return VideoFile(
        path=path,
        duration=duration,
        fps=fps,
        width=int(video_stream["width"]),
        height=int(video_stream["height"]),
        codec=video_stream.get("codec_name", "unknown"),
    )


def _parse_float(value: str | float | None, field: str) -> float:
    if value is None:
        raise VideoIngestError(f"Missing {field} in ffprobe output")
    try:
        return float(value)
    except (ValueError, TypeError) as exc:
        raise VideoIngestError(f"Cannot parse {field}={value!r} as float") from exc


def _parse_fps(r_frame_rate: str) -> float:
    """Parse '60000/1001' or '30' into a float."""
    try:
        if "/" in r_frame_rate:
            num, den = r_frame_rate.split("/")
            den_f = float(den)
            return float(num) / den_f if den_f else 0.0
        return float(r_frame_rate)
    except (ValueError, ZeroDivisionError):
        return 0.0
